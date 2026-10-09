"""One door per state change (spec section 6.6). A domain verified, a domain rejected, a
homepage verified, an institution verified, an institution rejected, an entity sent to review,
two entities merged: each sets the status in one place, records who did it in `entered_by`, and
returns what the assignments module should spawn (spec section 7.3). The rules, the reviewer, the
list loader and the country seed all call these functions and nothing else changes a status.

Every function here flushes and leaves the commit to the caller, so a decision and what it sets
in motion land together or not at all.
"""

import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.evidence.models import Evidence
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EnteredBy,
    Entity,
    EntityStatus,
    Homepage,
    Identifier,
    Institution,
    InstitutionServedPlace,
    Metric,
    Place,
    Source,
    Webpage,
)
from public_atlas.shared.exceptions import ConflictError, UnprocessableError

__all__ = [
    "StatusChange",
    "merge_entities",
    "previewing",
    "reject_domain",
    "reject_homepage",
    "reject_institution",
    "reject_place",
    "reject_source",
    "send_to_review",
    "verify_domain",
    "verify_homepage",
    "verify_institution",
    "verify_place",
    "verify_source",
]

logger = logging.getLogger(__name__)

# The statuses a claim can still be decided from.
OPEN = (EntityStatus.CANDIDATE, EntityStatus.NEEDS_REVIEW)
SUPERSEDED = "another homepage of the institution was verified"
INSTITUTION_REJECTED = "the institution was rejected"
MERGED = "the institution was merged into another"


@dataclass(frozen=True, slots=True)
class StatusChange:
    entity: Entity
    before: EntityStatus
    after: EntityStatus


# The changes of a decision being previewed; None when the changes are real.
_previewed: ContextVar[list[StatusChange] | None] = ContextVar("previewed", default=None)


@contextmanager
def previewing() -> Iterator[list[StatusChange]]:
    """Collect the status changes made inside, in order, for a preview of a decision the caller
    rolls back. They are not logged, since they do not happen."""
    changes: list[StatusChange] = []
    token = _previewed.set(changes)
    try:
        yield changes
    finally:
        _previewed.reset(token)


def _set_status(entity: Entity, status: EntityStatus, entered_by: EnteredBy) -> bool:
    """The one assignment to an entity's status. Whether it changed; a repeat is no change, so
    a decision made twice sets nothing in motion twice."""
    if entity.status is status:
        return False
    previewed = _previewed.get()
    if previewed is None:
        logger.info(
            "%s %s: %s -> %s by %s", entity.kind, entity.id, entity.status, status, entered_by
        )
    else:
        previewed.append(StatusChange(entity, entity.status, status))
    entity.status = status
    entity.entered_by = entered_by
    return True


# --- Domains ---


async def verify_domain(
    session: AsyncSession, domain: Domain, *, entered_by: EnteredBy
) -> list[Spawn]:
    """Verifying an official domain trusts it (spec section 6.1): its pages now verify what they
    name. Verifying a platform only records that a person confirmed it is one; a platform is
    never trusted (`graph.is_trusted`). Nothing is spawned: the homepage verified on the new
    domain is what spawns work."""
    _set_status(domain, EntityStatus.VERIFIED, entered_by)
    await session.flush()
    return []


async def reject_domain(
    session: AsyncSession, domain: Domain, *, entered_by: EnteredBy, reason: str
) -> list[Spawn]:
    """A dead site, or one that is nobody's. Every open homepage claim on it is rejected with
    the reason, and each institution that claimed one looks again (spec section 7.3)."""
    _set_status(domain, EntityStatus.REJECTED, entered_by)
    spawns: list[Spawn] = []
    for homepage in await _open_homepages_on(session, domain):
        institution = await session.get_one(Institution, homepage.institution_id)
        spawns.extend(
            await reject_homepage(session, homepage, entered_by=entered_by, reason=reason)
        )
        if institution.status is EntityStatus.REJECTED:
            spawns = [spawn for spawn in spawns if spawn.subject_id != institution.id]
    await session.flush()
    return _distinct(spawns)


async def _open_homepages_on(session: AsyncSession, domain: Domain) -> list[Homepage]:
    """The homepage claims on the domain's pages still waiting for a decision. A page captured
    before the domain had a row is found by its host."""
    rows = await session.scalars(
        select(Homepage)
        .join(Webpage, Webpage.id == Homepage.webpage_id)
        .where(
            Homepage.status.in_(OPEN),
            or_(
                Webpage.domain_id == domain.id,
                Webpage.url.like(f"http%://{domain.name}/%"),
                Webpage.url.like(f"http%://%.{domain.name}/%"),
            ),
        )
        .order_by(Homepage.id)
    )
    return list(rows)


# --- Homepages ---


async def verify_homepage(
    session: AsyncSession, homepage: Homepage, *, entered_by: EnteredBy
) -> list[Spawn]:
    """The claim holds: the page is on a trusted domain, or on a platform a rule or a reviewer
    vouched for, and no other institution owns it. The institution's `homepage_id` is set, its
    other open claims are rejected as superseded, and the institution's sources are looked for;
    a government's place gets its institutions looked for too (spec section 7.3). On a platform
    the homepage's `trusted_path` is set (spec section 6.4)."""
    institution = await session.get_one(Institution, homepage.institution_id)
    if homepage.status is EntityStatus.VERIFIED and institution.homepage_id == homepage.id:
        return []
    webpage = await session.get_one(Webpage, homepage.webpage_id)
    trusted_path = await _homepage_checks(session, institution, homepage, webpage)
    _set_status(homepage, EntityStatus.VERIFIED, entered_by)
    homepage.trusted_path = trusted_path
    homepage.rejected_reason = None
    institution.homepage_id = homepage.id
    await session.flush()
    for claim in await graph.homepages_of(session, institution):
        if claim.id != homepage.id and claim.status in OPEN:
            await reject_homepage(session, claim, entered_by=entered_by, reason=SUPERSEDED)
            await _reject_superseded_domain(session, claim, webpage, entered_by)
    spawns = [Spawn(AssignmentType.FIND_SOURCES, institution.id)]
    place = await session.get_one(Place, institution.place_id)
    if place.government_institution_id == institution.id:
        spawns.append(Spawn(AssignmentType.FIND_INSTITUTIONS, place.id))
    return spawns


async def _reject_superseded_domain(
    session: AsyncSession, claim: Homepage, verified_page: Webpage, entered_by: EnteredBy
) -> None:
    """A superseded claim on a candidate official domain, such as the directory's old address of
    a government whose homepage was verified on another domain, would leave that domain
    undecided for good: no assignment opens it again. It is rejected with the claim, unless
    another institution still has an open claim on it, which that institution's own
    `find_homepage` decides."""
    old_page = await session.get_one(Webpage, claim.webpage_id)
    domain = await graph.domain_of_webpage(session, old_page)
    if (
        domain is None
        or domain.domain_kind is not DomainKind.OFFICIAL
        or domain.status is not EntityStatus.CANDIDATE
        or await _open_homepages_on(session, domain)
    ):
        return
    await reject_domain(
        session,
        domain,
        entered_by=entered_by,
        reason=f"{SUPERSEDED}: {verified_page.url} is verified instead",
    )


async def _homepage_checks(
    session: AsyncSession, institution: Institution, homepage: Homepage, webpage: Webpage
) -> str | None:
    """The checks before a claim is verified; the trusted path when the page is on a platform.
    A page captured before its domain had a row is attached to the domain here."""
    domain = await graph.domain_of_webpage(session, webpage)
    if domain is None:
        raise UnprocessableError(f"no domain row covers {webpage.url}")
    trusted_path = None
    if domain.domain_kind is DomainKind.PLATFORM:
        try:
            trusted_path = graph.trusted_path_of(webpage.url)
        except ValueError as exc:
            raise UnprocessableError(str(exc)) from None
    elif not graph.is_trusted(domain):
        raise UnprocessableError(f"{domain.name} is not trusted; verify the domain first")
    other = await graph.verified_homepage_owner(session, webpage, excluding=institution)
    if other is not None:
        raise ConflictError(f"{webpage.url} is the verified homepage of {other.name!r} already")
    if institution.homepage_id not in (None, homepage.id):
        raise ConflictError(f"{institution.name!r} has a verified homepage already")
    if webpage.domain_id is None:
        webpage.domain_id = domain.id
    return trusted_path


async def reject_homepage(
    session: AsyncSession, homepage: Homepage, *, entered_by: EnteredBy, reason: str
) -> list[Spawn]:
    """The claim does not hold, with the reason for the briefing and the reviewer. An
    institution left without a verified homepage looks again."""
    institution = await session.get_one(Institution, homepage.institution_id)
    if institution.homepage_id == homepage.id:
        institution.homepage_id = None
    _set_status(homepage, EntityStatus.REJECTED, entered_by)
    homepage.rejected_reason = reason
    await session.flush()
    if institution.homepage_id is None and institution.status is not EntityStatus.REJECTED:
        return [Spawn(AssignmentType.FIND_HOMEPAGE, institution.id)]
    return []


# --- Institutions ---


async def verify_institution(
    session: AsyncSession, institution: Institution, *, entered_by: EnteredBy
) -> list[Spawn]:
    """The body exists and is public. One without a verified homepage has it looked for."""
    _set_status(institution, EntityStatus.VERIFIED, entered_by)
    await session.flush()
    if institution.homepage_id is None:
        return [Spawn(AssignmentType.FIND_HOMEPAGE, institution.id)]
    return []


async def reject_institution(
    session: AsyncSession, institution: Institution, *, entered_by: EnteredBy
) -> list[Spawn]:
    """Not a public body, or not one of its own. Its open homepage claims go with it. A place's
    government cannot be rejected while it is the government."""
    governs = await session.scalar(
        select(Place.id).where(Place.government_institution_id == institution.id).limit(1)
    )
    if governs is not None:
        raise ConflictError(f"{institution.name!r} is a place's government")
    _set_status(institution, EntityStatus.REJECTED, entered_by)
    for claim in await graph.homepages_of(session, institution):
        if claim.status in OPEN:
            await reject_homepage(
                session, claim, entered_by=entered_by, reason=INSTITUTION_REJECTED
            )
    await session.flush()
    return []


# --- Places ---


async def verify_place(
    session: AsyncSession, place: Place, *, entered_by: EnteredBy
) -> list[Spawn]:
    """A place a register lists, or a reviewer confirmed."""
    _set_status(place, EntityStatus.VERIFIED, entered_by)
    await session.flush()
    return []


async def reject_place(
    session: AsyncSession, place: Place, *, entered_by: EnteredBy
) -> list[Spawn]:
    """Refused while places or institutions sit under it: merge or move them first."""
    child = await session.scalar(select(Place.id).where(Place.parent_place_id == place.id).limit(1))
    if child is not None:
        raise ConflictError(f"places sit under {place.name!r}")
    body = await session.scalar(
        select(Institution.id).where(Institution.place_id == place.id).limit(1)
    )
    if body is not None:
        raise ConflictError(f"institutions sit under {place.name!r}")
    _set_status(place, EntityStatus.REJECTED, entered_by)
    await session.flush()
    return []


# --- Sources ---


async def verify_source(
    session: AsyncSession, source: Source, *, entered_by: EnteredBy
) -> list[Spawn]:
    _set_status(source, EntityStatus.VERIFIED, entered_by)
    await session.flush()
    return []


async def reject_source(
    session: AsyncSession, source: Source, *, entered_by: EnteredBy
) -> list[Spawn]:
    _set_status(source, EntityStatus.REJECTED, entered_by)
    await session.flush()
    return []


# --- Review ---


async def send_to_review(session: AsyncSession, entity: Entity) -> bool:
    """Raising a review item sets a candidate to `needs_review` (spec section 6.5). A verified
    or rejected entity keeps its status while the question is open: the item is the record.
    Whether the status changed; `entered_by` stays, since nothing was decided."""
    if entity.status is not EntityStatus.CANDIDATE:
        return False
    entity.status = EntityStatus.NEEDS_REVIEW
    await session.flush()
    return True


# --- Merging ---


async def merge_entities(
    session: AsyncSession,
    duplicate: Place | Institution,
    into: Place | Institution,
    *,
    entered_by: EnteredBy,
) -> list[Spawn]:
    """Fold `duplicate` into `into`: its aliases, evidence, identifiers, metrics, served places,
    sources, homepages, children and open assignments move over, the government and homepage
    links are set, and the duplicate is rejected. Conflicts are checked before anything moves.
    What the survivor already holds (an alias, a code in a scheme, a figure for a year, a source
    on a page) stays as it is; the duplicate's copy is dropped or rejected."""
    if type(duplicate) is not type(into):
        raise ConflictError("a place and an institution cannot be merged")
    if duplicate.id == into.id:
        raise ConflictError("an entity cannot be merged into itself")
    if into.status is EntityStatus.REJECTED:
        raise ConflictError(f"{into.name!r} is rejected; merge into a live entity")
    if isinstance(duplicate, Institution) and isinstance(into, Institution):
        await _merge_institutions(session, duplicate, into, entered_by)
    elif isinstance(duplicate, Place) and isinstance(into, Place):
        await _merge_places(session, duplicate, into, entered_by)
    _set_status(duplicate, EntityStatus.REJECTED, entered_by)
    await session.flush()
    return []


async def _merge_institutions(
    session: AsyncSession, duplicate: Institution, into: Institution, entered_by: EnteredBy
) -> None:
    governed = await session.scalar(
        select(Place).where(Place.government_institution_id == duplicate.id)
    )
    if governed is not None:
        if into.place_id != governed.id:
            raise ConflictError(
                f"{duplicate.name!r} is the government of {governed.name!r}; only an "
                "institution at that place can take its place"
            )
        into_governs = await session.scalar(
            select(Place.id).where(Place.government_institution_id == into.id).limit(1)
        )
        if into_governs is not None:
            raise ConflictError(f"{into.name!r} is another place's government")
    if (
        duplicate.homepage_id is not None
        and into.homepage_id is not None
        and duplicate.homepage_id != into.homepage_id
    ):
        raise ConflictError("both institutions have a verified homepage; reject one first")

    await _move_attachments(session, duplicate, into)
    await _move_served_places(session, duplicate, into)
    # Children and the parent link: nothing may end up under itself.
    if into.parent_institution_id == duplicate.id:
        into.parent_institution_id = duplicate.parent_institution_id
    await session.execute(
        update(Institution)
        .where(Institution.parent_institution_id == duplicate.id)
        .values(parent_institution_id=into.id)
    )
    if governed is not None:
        governed.government_institution_id = None
        await session.flush()
        governed.government_institution_id = into.id
    await _move_sources(session, duplicate, into, entered_by)
    await _move_homepages(session, duplicate, into, entered_by)
    await assignments.move_subject(session, duplicate.id, into.id)
    await session.flush()


async def _merge_places(
    session: AsyncSession, duplicate: Place, into: Place, entered_by: EnteredBy
) -> None:
    if duplicate.country_code != into.country_code:
        raise ConflictError("the places are in different countries")
    if duplicate.administrative_level != into.administrative_level:
        raise ConflictError(
            f"{duplicate.name!r} is a {duplicate.administrative_level} and {into.name!r} a "
            f"{into.administrative_level}"
        )
    government_id = duplicate.government_institution_id
    await _move_attachments(session, duplicate, into)
    for served in await session.scalars(
        select(InstitutionServedPlace).where(InstitutionServedPlace.place_id == duplicate.id)
    ):
        exists = await session.get(InstitutionServedPlace, (served.institution_id, into.id))
        if exists is None:
            session.add(
                InstitutionServedPlace(institution_id=served.institution_id, place_id=into.id)
            )
        await session.delete(served)
    await session.flush()
    if into.parent_place_id == duplicate.id:
        into.parent_place_id = duplicate.parent_place_id
    await session.execute(
        update(Place).where(Place.parent_place_id == duplicate.id).values(parent_place_id=into.id)
    )
    # The government link points at an institution of the place itself, so it is let go before
    # the institutions move and set again once they are there.
    duplicate.government_institution_id = None
    await session.flush()
    await session.execute(
        update(Institution).where(Institution.place_id == duplicate.id).values(place_id=into.id)
    )
    await session.flush()
    if government_id is not None:
        government = await session.get_one(Institution, government_id)
        if into.government_institution_id is None:
            into.government_institution_id = government.id
        else:
            survivor = await session.get_one(Institution, into.government_institution_id)
            await _merge_institutions(session, government, survivor, entered_by)
            _set_status(government, EntityStatus.REJECTED, entered_by)
    await assignments.move_subject(session, duplicate.id, into.id)
    await session.flush()


async def _move_attachments(
    session: AsyncSession, duplicate: Place | Institution, into: Place | Institution
) -> None:
    """Aliases, evidence, identifiers and metrics: moved where the survivor lacks them."""
    await _move_aliases(session, duplicate, into)
    await _move_evidence(session, duplicate, into)
    await _move_identifiers(session, duplicate, into)
    await _move_metrics(session, duplicate, into)


def _owner(row: Alias | Identifier | Metric, into: Place | Institution) -> None:
    if isinstance(into, Place):
        row.place_id = into.id
    else:
        row.institution_id = into.id


async def _move_aliases(
    session: AsyncSession, duplicate: Place | Institution, into: Place | Institution
) -> None:
    column = Alias.place_id if isinstance(duplicate, Place) else Alias.institution_id
    held = set(await session.scalars(select(Alias.text).where(column == into.id)))
    for alias in await session.scalars(select(Alias).where(column == duplicate.id)):
        if alias.text in held:
            await session.delete(alias)
        else:
            _owner(alias, into)
            held.add(alias.text)
    await session.flush()


async def _move_evidence(
    session: AsyncSession, duplicate: Place | Institution, into: Place | Institution
) -> None:
    """A quote the survivor holds from the same snapshot is one quote: the duplicate's copy
    goes."""
    quoted = set(
        (
            await session.execute(
                select(Evidence.snapshot_id, Evidence.kind, Evidence.quote).where(
                    Evidence.entity_id == into.id
                )
            )
        )
        .tuples()
        .all()
    )
    for row in await session.scalars(select(Evidence).where(Evidence.entity_id == duplicate.id)):
        key = (row.snapshot_id, row.kind, row.quote)
        if key in quoted:
            await session.delete(row)
        else:
            row.entity_id = into.id
            quoted.add(key)
    await session.flush()


async def _move_identifiers(
    session: AsyncSession, duplicate: Place | Institution, into: Place | Institution
) -> None:
    """A code in a scheme the survivor has one in stays on the duplicate: the survivor's is the
    one a person has seen, and a value has one owner."""
    column = Identifier.place_id if isinstance(duplicate, Place) else Identifier.institution_id
    schemes = set(await session.scalars(select(Identifier.scheme).where(column == into.id)))
    for identifier in await session.scalars(select(Identifier).where(column == duplicate.id)):
        if identifier.scheme not in schemes:
            _owner(identifier, into)
            schemes.add(identifier.scheme)
    await session.flush()


async def _move_metrics(
    session: AsyncSession, duplicate: Place | Institution, into: Place | Institution
) -> None:
    column = Metric.place_id if isinstance(duplicate, Place) else Metric.institution_id
    years = set(
        (await session.execute(select(Metric.name, Metric.year).where(column == into.id)))
        .tuples()
        .all()
    )
    for metric in await session.scalars(select(Metric).where(column == duplicate.id)):
        if (metric.name, metric.year) not in years:
            _owner(metric, into)
            years.add((metric.name, metric.year))
    await session.flush()


async def _move_served_places(
    session: AsyncSession, duplicate: Institution, into: Institution
) -> None:
    for served in await session.scalars(
        select(InstitutionServedPlace).where(InstitutionServedPlace.institution_id == duplicate.id)
    ):
        exists = await session.get(InstitutionServedPlace, (into.id, served.place_id))
        if exists is None:
            session.add(InstitutionServedPlace(institution_id=into.id, place_id=served.place_id))
        await session.delete(served)
    await session.flush()


async def _move_sources(
    session: AsyncSession, duplicate: Institution, into: Institution, entered_by: EnteredBy
) -> None:
    """A source the survivor has on the same page with the same type keeps the survivor's row;
    the duplicate's evidence moves to it and its row is rejected."""
    held = {
        (source.webpage_id, source.source_type): source
        for source in await session.scalars(select(Source).where(Source.institution_id == into.id))
    }
    for source in await session.scalars(
        select(Source).where(Source.institution_id == duplicate.id)
    ):
        kept = held.get((source.webpage_id, source.source_type))
        if kept is None:
            source.institution_id = into.id
            held[source.webpage_id, source.source_type] = source
            continue
        await session.execute(
            update(Evidence).where(Evidence.entity_id == source.id).values(entity_id=kept.id)
        )
        _set_status(source, EntityStatus.REJECTED, entered_by)
    await session.flush()


async def _move_homepages(
    session: AsyncSession, duplicate: Institution, into: Institution, entered_by: EnteredBy
) -> None:
    """Every claim moves; the verified one becomes the survivor's when it has none, and any
    other open claim of the survivor is then superseded."""
    verified_id = duplicate.homepage_id
    duplicate.homepage_id = None
    await session.flush()
    await session.execute(
        update(Homepage)
        .where(Homepage.institution_id == duplicate.id)
        .values(institution_id=into.id)
    )
    await session.flush()
    if verified_id is not None and into.homepage_id is None:
        into.homepage_id = verified_id
        await session.flush()
    if into.homepage_id is not None:
        for claim in await graph.homepages_of(session, into):
            if claim.id != into.homepage_id and claim.status in OPEN:
                await reject_homepage(session, claim, entered_by=entered_by, reason=SUPERSEDED)


def _distinct(spawns: Sequence[Spawn]) -> list[Spawn]:
    return list(dict.fromkeys(spawns))
