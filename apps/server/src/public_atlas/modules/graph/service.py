"""The graph's door for other modules: URLs and domain names in one spelling, the domain and
webpage rows a URL needs, creating and finding places and institutions, the aliases they go by,
and the duplicate search behind `save_institution`. Every entity is created a candidate; the
status moves only in `status_changes.py`, the graph's other door (spec section 6.6).

The duplicate search takes the country's rules for its naming forms. It imports them from
`countries.rules`, below `countries.service`, which seeds anchors through this module: the two
services never import each other.
"""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import ColumnElement, func, select, true
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.graph.models import (
    Alias,
    Domain,
    DomainKind,
    EnteredBy,
    Entity,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    ProcurementHandledBy,
    Source,
    SourceAccess,
    Webpage,
)

__all__ = [
    "MAX_MATCHES",
    "SIMILARITY_FLOOR",
    "Match",
    "add_alias",
    "aliases_of",
    "candidate_domain_name",
    "create_domain",
    "create_homepage",
    "create_institution",
    "create_place",
    "create_source",
    "domain_by_name",
    "domain_of_host",
    "domain_of_webpage",
    "ensure_domain",
    "ensure_webpage",
    "entity_by_id",
    "find_institutions",
    "find_places",
    "homepages_of",
    "host_of",
    "institutions_at",
    "is_domain_name",
    "is_trusted",
    "names_of",
    "normalize_url",
    "place_chain",
    "redirect_chain",
    "redirected_from",
    "redirects_to",
    "similar_institutions",
    "similar_places",
    "trusted_path_of",
    "under_trusted_path",
    "verified_homepage_owner",
    "webpage_by_url",
]

_DOMAIN_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DOMAIN = re.compile(rf"^(?:{_DOMAIN_LABEL}\.)+{_DOMAIN_LABEL}$")
MAX_DOMAIN_LENGTH = 253
# Set as `pg_trgm.similarity_threshold` for the duplicate search, so `%` applies it: two names
# less alike than this are not offered as a possible match.
SIMILARITY_FLOOR = 0.35
# At most this many likely duplicates are offered, one per entity.
MAX_MATCHES = 5
# The last path segment of a platform homepage that names a page, not a section: dropped from
# the trusted path, so "/view/elmwood-library/home" vouches for "/view/elmwood-library/".
_PAGE_SEGMENT = re.compile(
    r"^(?:home|index|default|main|welcome|.*\.[a-z0-9]{1,5})$", re.IGNORECASE
)


# --- URLs and domain names ---


def is_domain_name(value: str) -> bool:
    return bool(_DOMAIN.match(value.lower())) and len(value) <= MAX_DOMAIN_LENGTH


def normalize_url(url: str) -> str:
    """One spelling per page: lower-cased scheme and host, no fragment, no default port, and a
    trailing slash on a bare host. A bare "www.elmwood.ca" gets the scheme it leaves out."""
    url = url.strip()
    if "://" not in url:
        url = f"http://{url}"
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), host, path, parts.query, ""))


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def candidate_domain_name(host: str) -> str:
    """The domain a first link to `host` creates: the host without a leading `www.`. The
    allowlist admits `www.x` under `x` but not the reverse, so a site that redirects `www.x` to
    `x` (or to `en.x`) would otherwise be refused inside its own assignment."""
    host = host.lower()
    bare = host.removeprefix("www.")
    return bare if is_domain_name(bare) else host


def trusted_path_of(url: str) -> str:
    """The URL prefix a verified homepage on a platform vouches for (spec section 6.4): the
    homepage's own path as a section, with a page-like last segment dropped and no query. A
    platform's root is refused: it is nobody's homepage."""
    parts = urlsplit(normalize_url(url))
    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        raise ValueError(f"{url} is the root of its site, which no one institution owns")
    if len(segments) > 1 and _PAGE_SEGMENT.match(segments[-1]):
        segments.pop()
    return urlunsplit((parts.scheme, parts.netloc, "/" + "/".join(segments) + "/", "", ""))


def under_trusted_path(url: str, trusted_path: str) -> bool:
    """Whether `url` is the trusted path's own page or one under it."""
    normalized = normalize_url(url)
    return normalized.rstrip("/") == trusted_path.rstrip("/") or normalized.startswith(trusted_path)


# --- Domains ---


def is_trusted(domain: Domain) -> bool:
    """Trusted: verified and official. A platform is never trusted, whatever its status."""
    return domain.status is EntityStatus.VERIFIED and domain.domain_kind is DomainKind.OFFICIAL


async def domain_by_name(session: AsyncSession, name: str) -> Domain | None:
    return await session.scalar(select(Domain).where(Domain.name == name.lower()))


async def domain_of_host(session: AsyncSession, host: str) -> Domain | None:
    """The domain row that covers `host`, subdomains included: the longest match when several
    do (`toronto.bidsandtenders.ca` is under `bidsandtenders.ca`)."""
    labels = host.lower().split(".")
    candidates = [".".join(labels[i:]) for i in range(len(labels) - 1)]
    if not candidates:
        return None
    rows = list(await session.scalars(select(Domain).where(Domain.name.in_(candidates))))
    if not rows:
        return None
    return max(rows, key=lambda domain: len(domain.name))


async def domain_of_webpage(session: AsyncSession, webpage: Webpage) -> Domain | None:
    """The webpage's domain row: the one attached, else the one covering its host."""
    if webpage.domain_id is not None:
        return await session.get(Domain, webpage.domain_id)
    return await domain_of_host(session, host_of(webpage.url))


async def create_domain(
    session: AsyncSession, name: str, *, kind: DomainKind, entered_by: EnteredBy
) -> Domain:
    """A candidate domain. The seed and the rules verify it through `status_changes`."""
    domain = Domain(name=name.lower(), domain_kind=kind, entered_by=entered_by)
    session.add(domain)
    await session.flush()
    return domain


async def ensure_domain(
    session: AsyncSession, host: str, *, entered_by: EnteredBy
) -> tuple[Domain, bool]:
    """The domain that covers `host`, or a new candidate official one named for it. Whether it
    was created."""
    found = await domain_of_host(session, host)
    if found is not None:
        return found, False
    domain = await create_domain(
        session, candidate_domain_name(host), kind=DomainKind.OFFICIAL, entered_by=entered_by
    )
    return domain, True


# --- Webpages ---


async def webpage_by_url(session: AsyncSession, url: str) -> Webpage | None:
    return await session.scalar(select(Webpage).where(Webpage.url == normalize_url(url)))


async def ensure_webpage(
    session: AsyncSession,
    url: str,
    *,
    domain: Domain | None = None,
    assignment_id: uuid.UUID | None = None,
) -> Webpage:
    """The row for `url`, created if new. Its domain is `domain`, or the row that covers the
    host; a row made before its domain had a row (a page on a site a search returned) is
    attached to the domain here, so its evidence counts once the domain is trusted. Two writers
    may race for one URL (the agent's tool calls from one response run at once); the savepoint
    lets the loser take the winner's row."""
    normalized = normalize_url(url)
    if domain is None:
        domain = await domain_of_host(session, host_of(normalized))
    webpage = await webpage_by_url(session, normalized)
    if webpage is None:
        webpage = Webpage(
            url=normalized,
            domain_id=domain.id if domain is not None else None,
            first_seen_assignment_id=assignment_id,
        )
        try:
            async with session.begin_nested():
                session.add(webpage)
                await session.flush()
        except IntegrityError:
            webpage = await webpage_by_url(session, normalized)
            if webpage is None:  # pragma: no cover - the other writer's row is committed
                raise
    if webpage.domain_id is None and domain is not None:
        webpage.domain_id = domain.id
        await session.flush()
    return webpage


# How many recorded redirects are followed from one URL: the browser's own cap.
MAX_REDIRECT_HOPS = 5


async def redirect_chain(session: AsyncSession, url: str) -> list[str]:
    """The URLs the browser is on record as having been sent to from `url`, in order: a page a
    site forwards to another address, then wherever that one forwards. Empty when `url` has
    no redirect on record."""
    chain: list[str] = []
    current = normalize_url(url)
    for _ in range(MAX_REDIRECT_HOPS):
        webpage = await webpage_by_url(session, current)
        if webpage is None or webpage.redirects_to_url is None:
            break
        current = webpage.redirects_to_url
        if current in chain:
            break
        chain.append(current)
    return chain


def _home_pages(url: str) -> list[str]:
    """The home page of `url`'s site, with and without `www.`, in both schemes: where an old
    address usually forwards from when the listed page itself is dead."""
    host = host_of(url)
    bare = host.removeprefix("www.")
    hosts = dict.fromkeys([host, bare, f"www.{bare}"])
    return [f"{scheme}://{name}/" for name in hosts for scheme in ("https", "http")]


async def redirected_from(session: AsyncSession, target: str) -> list[str]:
    """The URLs the browser is on record as having been sent on from to `target`: the address
    a page linked, when the site answered from another one."""
    rows = await session.scalars(
        select(Webpage.url)
        .where(Webpage.redirects_to_url == normalize_url(target))
        .order_by(Webpage.url)
    )
    return list(rows)


async def redirects_to(session: AsyncSession, start: str, target: str) -> bool:
    """Whether the browser recorded `start`, or the home page of its site with or without
    `www.`, as redirecting to `target` (directly or through further hops)."""
    wanted = normalize_url(target)
    for origin in [normalize_url(start), *_home_pages(start)]:
        if wanted in await redirect_chain(session, origin):
            return True
    return False


# --- Entities ---


async def entity_by_id(session: AsyncSession, entity_id: uuid.UUID) -> Entity | None:
    """The entity as its own class with every column loaded. A plain load of `Entity` gives the
    subclass with its own columns left to a lazy load, which async code cannot make."""
    entity = await session.get(Entity, entity_id)
    if entity is not None:
        await session.refresh(entity)
    return entity


# --- Places and institutions ---


async def create_place(  # noqa: PLR0913
    session: AsyncSession,
    *,
    name: str,
    country_code: str,
    administrative_level: str,
    parent: Place | None,
    entered_by: EnteredBy,
    language: str = "en",
) -> Place:
    """A candidate place with its name as its first alias."""
    place = Place(
        name=" ".join(name.split()),
        country_code=country_code,
        administrative_level=administrative_level,
        parent_place_id=parent.id if parent is not None else None,
        entered_by=entered_by,
    )
    session.add(place)
    await session.flush()
    await add_alias(session, place, place.name, language=language, entered_by=entered_by)
    return place


async def create_institution(  # noqa: PLR0913
    session: AsyncSession,
    *,
    name: str,
    institution_type: str,
    place: Place,
    entered_by: EnteredBy,
    parent: Institution | None = None,
    procurement_handled_by: ProcurementHandledBy = ProcurementHandledBy.SELF,
    suggested_type: str | None = None,
    language: str = "en",
) -> Institution:
    """A candidate institution with its name as its first alias. `parent` is the body it sits
    under; None leaves the place's government as the default, when the place has one."""
    if parent is None and place.government_institution_id is not None:
        parent_id = place.government_institution_id
    else:
        parent_id = parent.id if parent is not None else None
    institution = Institution(
        name=" ".join(name.split()),
        institution_type=institution_type,
        suggested_type=suggested_type,
        place_id=place.id,
        parent_institution_id=parent_id,
        procurement_handled_by=procurement_handled_by,
        entered_by=entered_by,
    )
    session.add(institution)
    await session.flush()
    await add_alias(
        session, institution, institution.name, language=language, entered_by=entered_by
    )
    return institution


async def create_homepage(
    session: AsyncSession,
    institution: Institution,
    webpage: Webpage,
    *,
    entered_by: EnteredBy,
    found_on: Webpage | None = None,
) -> Homepage:
    """A candidate homepage claim. `found_on` is the trusted page that linked to it; None for a
    search result or a directory link."""
    homepage = Homepage(
        institution_id=institution.id,
        webpage_id=webpage.id,
        found_on_webpage_id=found_on.id if found_on is not None else None,
        entered_by=entered_by,
    )
    session.add(homepage)
    await session.flush()
    return homepage


async def create_source(  # noqa: PLR0913
    session: AsyncSession,
    institution: Institution,
    webpage: Webpage,
    *,
    source_type: str,
    entered_by: EnteredBy,
    access: SourceAccess = SourceAccess.PUBLIC,
) -> Source:
    source = Source(
        institution_id=institution.id,
        webpage_id=webpage.id,
        source_type=source_type,
        access=access,
        entered_by=entered_by,
    )
    session.add(source)
    await session.flush()
    return source


def _forms(rules: CountryRules, names: Iterable[str]) -> set[str]:
    forms: set[str] = set()
    for name in names:
        forms |= rules.naming.forms(name)
    return forms


async def _named[T: (Place, Institution)](
    session: AsyncSession, rows: Sequence[T], name: str, rules: CountryRules
) -> list[T]:
    """The rows that go by `name` in any of its forms, by their name or an alias."""
    wanted = rules.naming.forms(name)
    aliases = await aliases_of(session, rows)
    return [row for row in rows if _forms(rules, [row.name, *aliases[row.id]]) & wanted]


async def find_places(  # noqa: PLR0913
    session: AsyncSession,
    country_code: str,
    name: str,
    *,
    rules: CountryRules,
    levels: Iterable[str] | None = None,
    parent: Place | None = None,
) -> list[Place]:
    """The country's places going by `name`, at any of `levels` (every level when None) and
    under `parent` when one is given. Rejected places never match."""
    query = select(Place).where(
        Place.country_code == country_code, Place.status != EntityStatus.REJECTED
    )
    if levels is not None:
        query = query.where(Place.administrative_level.in_(list(levels)))
    if parent is not None:
        query = query.where(Place.parent_place_id == parent.id)
    rows = list(await session.scalars(query))
    return await _named(session, rows, name, rules)


async def find_institutions(
    session: AsyncSession,
    place: Place,
    name: str,
    *,
    rules: CountryRules,
    institution_type: str | None = None,
) -> list[Institution]:
    """The institutions at `place` going by `name`, of `institution_type` when one is given."""
    rows = await institutions_at(session, place, institution_type=institution_type)
    return await _named(session, rows, name, rules)


async def institutions_at(
    session: AsyncSession, place: Place, *, institution_type: str | None = None
) -> list[Institution]:
    """Every institution at the place that is not rejected."""
    query = select(Institution).where(
        Institution.place_id == place.id, Institution.status != EntityStatus.REJECTED
    )
    if institution_type is not None:
        query = query.where(Institution.institution_type == institution_type)
    return list(await session.scalars(query.order_by(Institution.name)))


async def place_chain(session: AsyncSession, place: Place) -> list[Place]:
    """The place and each place above it, up to the country: the places a body found under the
    first may belong to."""
    chain = [place]
    seen = {place.id}
    current = place
    while current.parent_place_id is not None and current.parent_place_id not in seen:
        current = await session.get_one(Place, current.parent_place_id)
        seen.add(current.id)
        chain.append(current)
    return chain


async def homepages_of(session: AsyncSession, institution: Institution) -> list[Homepage]:
    rows = await session.scalars(
        select(Homepage).where(Homepage.institution_id == institution.id).order_by(Homepage.id)
    )
    return list(rows)


async def verified_homepage_owner(
    session: AsyncSession, webpage: Webpage, *, excluding: Institution | None = None
) -> Institution | None:
    """The institution whose verified homepage is on `webpage`, if any: two institutions cannot
    both have a verified homepage on one webpage."""
    # Both extend `entities`, so the homepage is a subquery, not a join.
    on_webpage = select(Homepage.id).where(Homepage.webpage_id == webpage.id)
    query = select(Institution).where(Institution.homepage_id.in_(on_webpage))
    if excluding is not None:
        query = query.where(Institution.id != excluding.id)
    return await session.scalar(query.limit(1))


# --- Aliases ---


def _owner_column(owner: Place | Institution) -> InstrumentedAttribute[uuid.UUID | None]:
    return Alias.place_id if isinstance(owner, Place) else Alias.institution_id


async def aliases_of(
    session: AsyncSession, owners: Iterable[Place | Institution]
) -> dict[uuid.UUID, list[str]]:
    """Every alias text of each owner, by owner id. One query for a batch."""
    owners = list(owners)
    if not owners:
        return {}
    column = _owner_column(owners[0])
    rows = await session.execute(
        select(column, Alias.text).where(column.in_([owner.id for owner in owners]))
    )
    found: dict[uuid.UUID, list[str]] = {owner.id: [] for owner in owners}
    for owner_id, text in rows:
        found[owner_id].append(text)
    return found


async def names_of(session: AsyncSession, owner: Place | Institution) -> list[Alias]:
    """The owner's aliases, names before acronyms."""
    rows = await session.scalars(
        select(Alias).where(_owner_column(owner) == owner.id).order_by(Alias.is_acronym, Alias.text)
    )
    return list(rows)


async def add_alias(  # noqa: PLR0913
    session: AsyncSession,
    owner: Place | Institution,
    text: str,
    *,
    language: str,
    entered_by: EnteredBy,
    is_acronym: bool = False,
) -> bool:
    """Whether the alias was added; one the owner has already is left as it is."""
    text = " ".join(text.split())
    found = await session.scalar(
        select(Alias.id).where(_owner_column(owner) == owner.id, Alias.text == text)
    )
    if found is not None:
        return False
    alias = Alias(text=text, language=language, is_acronym=is_acronym, entered_by=entered_by)
    if isinstance(owner, Place):
        alias.place_id = owner.id
    else:
        alias.institution_id = owner.id
    session.add(alias)
    await session.flush()
    return True


# --- Duplicate search ---


@dataclass(frozen=True, slots=True)
class Match[T: (Place, Institution)]:
    """A likely duplicate: the entity, the alias of it most like the name, and how alike."""

    entity: T
    alias: str
    score: float


async def similar_institutions(
    session: AsyncSession, places: Iterable[Place], name: str, *, rules: CountryRules
) -> list[Match[Institution]]:
    """Institutions at any of `places` with a name or acronym like `name`, most alike first,
    each once with its most alike alias, at most `MAX_MATCHES`. The caller passes a place and
    the places above it, so a regional body one assignment saved under its town is offered when
    another saves it under the region. Two bodies whose names carry designators of different
    kinds ("Township of Elmwood", "City of Elmwood") are never offered for each other."""
    return await _similar(
        session,
        table=Institution,
        owner_column=Alias.institution_id,
        filters=[Institution.place_id.in_([place.id for place in places])],
        name=name,
        rules=rules,
    )


async def similar_places(
    session: AsyncSession,
    country_code: str,
    name: str,
    *,
    rules: CountryRules,
    levels: Iterable[str] | None = None,
) -> list[Match[Place]]:
    """As `similar_institutions`, for the country's places at `levels` (every level when None)."""
    filters: list[ColumnElement[bool]] = [Place.country_code == country_code]
    if levels is not None:
        filters.append(Place.administrative_level.in_(list(levels)))
    return await _similar(
        session, table=Place, owner_column=Alias.place_id, filters=filters, name=name, rules=rules
    )


async def _similar[T: (Place, Institution)](  # noqa: PLR0913 - one argument per clause
    session: AsyncSession,
    *,
    table: type[T],
    owner_column: InstrumentedAttribute[uuid.UUID | None],
    filters: list[ColumnElement[bool]],
    name: str,
    rules: CountryRules,
) -> list[Match[T]]:
    name = " ".join(name.split())
    if not name:
        return []
    similarity = func.similarity(Alias.text, name)
    # `%` is what the trigram index answers; `similarity(...) > x` is not. It compares against
    # `pg_trgm.similarity_threshold`, pinned below for this transaction. An exact match has
    # similarity 1, so it needs no clause of its own.
    best = (
        select(
            owner_column.label("owner_id"),
            Alias.text,
            similarity.label("score"),
            func.row_number()
            .over(partition_by=owner_column, order_by=(similarity.desc(), Alias.text))
            .label("rank"),
        )
        .join(table, owner_column == table.id)
        .where(*filters, table.status != EntityStatus.REJECTED, Alias.text.op("%")(name))
        .subquery()
    )
    await session.execute(
        select(func.set_config("pg_trgm.similarity_threshold", str(SIMILARITY_FLOOR), true()))
    )
    rows = await session.execute(
        select(table, best.c.text, best.c.score)
        .join(best, best.c.owner_id == table.id)
        .where(best.c.rank == 1)
        .order_by(best.c.score.desc(), best.c.text)
    )
    found = [
        Match(entity=entity, alias=text, score=float(score)) for entity, text, score in rows.all()
    ]
    aliases = await aliases_of(session, [match.entity for match in found])
    kept = [
        match
        for match in found
        if not rules.naming.designators_differ(
            [name], [match.entity.name, *aliases[match.entity.id]]
        )
    ]
    return kept[:MAX_MATCHES]
