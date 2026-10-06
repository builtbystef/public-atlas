"""`save_institution`: the duplicate rules, the type and level checks, the body no listed type
fits, and the parent and buyer the page names (spec sections 6.5 and 9)."""

import uuid
from dataclasses import dataclass
from typing import Any

from pydantic_ai import RunContext
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.agent.findings.homepages import record_homepage
from public_atlas.modules.agent.findings.shared import (
    FindingError,
    Likely,
    LikelyDuplicates,
    add_quote,
    in_session,
    matched_quote,
    parse_uuid,
    place_label,
    quote_names,
    require_name,
    resolve_decision,
    visited_page,
)
from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    EnteredBy,
    EntityStatus,
    Institution,
    Place,
    ProcurementHandledBy,
)
from public_atlas.modules.review import service as review

OTHER_TYPE = "other"
SUGGESTED_TYPE_LENGTH = 100


@dataclass(frozen=True, slots=True)
class Review:
    """A review item a save raises: its rule, its reason and the facts the reviewer decides."""

    rule: str
    reason: str
    question: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SavedInstitution:
    institution_id: uuid.UUID
    name: str
    institution_type: str
    status: EntityStatus
    # Whether the name and quote were added to an institution saved before.
    matched: bool
    reviews: list[str]
    homepage: str | None

    def __str__(self) -> str:
        if self.matched:
            text = f"Matched existing institution {self.institution_id}; name and evidence added."
            if self.status is EntityStatus.VERIFIED:
                text += " Now verified: the page is trusted."
        else:
            text = (
                f"Saved institution {self.name!r} ({self.institution_type}) "
                f"id={self.institution_id}, status {self.status.value}."
            )
        text += "".join(f" Sent for review: {reason}" for reason in self.reviews)
        if self.homepage:
            text += f" {self.homepage}"
        return text


async def save_institution(  # noqa: PLR0913
    ctx: RunContext[SessionContext],
    *,
    name: str,
    language: str,
    institution_type: str,
    quote: str,
    page_url: str,
    place_id: str | None = None,
    acronym: str | None = None,
    parent_institution_id: str | None = None,
    procurement_handled_by: str = "self",
    homepage_url: str | None = None,
    decision: str | None = None,
    suggested_type: str | None = None,
) -> SavedInstitution | LikelyDuplicates:
    """Save a public body found on a page: a ministry, agency, board, hospital, school
    board, utility, and so on. Returns likely duplicates first when there are any;
    call again with `decision` to settle them.

    Args:
        name: The body's full name as its own page writes it ("Ministry of
            Transportation"), never a directory's short label ("Transportation").
        language: BCP 47 tag of the language the name is in: "en", "fr".
        institution_type: One of the country's institution types. Use it even when the
            type is expected at another level; the body is kept and sent for review.
            When no listed type fits a public body that buys things, pass "other" with
            suggested_type; a human adds the type.
        quote: A verbatim phrase from the page that names the body.
        page_url: The URL of the page the quote is on (one you opened).
        place_id: The place it belongs to. Defaults to this assignment's place. Pass a
            place above it, from the briefing's "Places to save under" line, when the
            body serves that whole place. Only those places are accepted.
        acronym: An acronym the page uses for it, if any.
        parent_institution_id: The body it sits under, when a page says so (a city and
            its transit agency, a ministry and its agency). Defaults to the place's
            government.
        procurement_handled_by: "self" when it buys on its own account, "parent" when
            the body it sits under buys for it.
        homepage_url: Its homepage, when the page links to it (the exact href).
        decision: After a duplicate warning: "new", "unsure", or the id of the match.
        suggested_type: With institution_type "other" only: the kind of body this is,
            in a few words ("housing corporation", "port authority").
    """
    return await in_session(
        ctx,
        lambda session: record_institution(
            ctx.deps,
            session,
            name=name,
            language=language,
            institution_type=institution_type,
            quote=quote,
            page_url=page_url,
            place_id=place_id,
            acronym=acronym,
            parent_institution_id=parent_institution_id,
            procurement_handled_by=procurement_handled_by,
            homepage_url=homepage_url,
            decision=decision,
            suggested_type=suggested_type,
        ),
    )


async def record_institution(  # noqa: PLR0913
    ctx: SessionContext,
    session: AsyncSession,
    *,
    name: str,
    language: str,
    institution_type: str,
    quote: str,
    page_url: str,
    place_id: str | None = None,
    acronym: str | None = None,
    parent_institution_id: str | None = None,
    procurement_handled_by: str = "self",
    homepage_url: str | None = None,
    decision: str | None = None,
    suggested_type: str | None = None,
) -> SavedInstitution | LikelyDuplicates:
    rules = ctx.rules
    suggested = _check_type(rules, institution_type, suggested_type)
    name = require_name(name, "institution")
    acronym = " ".join(acronym.split()) or None if acronym else None
    buys = _buyer(procurement_handled_by)
    place, chain = await _place_for(ctx, session, place_id)
    parent = await _parent_for(session, parent_institution_id)
    reviews = _reviews_for(rules, institution_type, suggested, name, place)
    page = await visited_page(session, page_url)
    match = await matched_quote(ctx, session, page, quote)
    quote_names(quote, [name, acronym], "institution", naming=rules.naming)

    # The search runs over the whole chain, not the one place: a regional body another
    # assignment saved under its town is still offered when this one saves it under the region.
    matches = [
        Likely(found.entity.id, found.alias, found.score, _detail(found.entity))
        for found in await graph.similar_institutions(session, chain, name, rules=rules)
    ]
    if homepage_url:
        # The same verified homepage means the same institution, whatever the names say.
        owner = await _verified_owner(session, homepage_url)
        if owner is not None:
            decision = str(owner.id)
            if owner.id not in {likely.entity_id for likely in matches}:
                matches.append(Likely(owner.id, owner.name, 1.0, "same homepage"))
    existing_id, unsure, offer = resolve_decision(matches, decision, "institution")
    if offer is not None:
        return offer

    told: list[str] = []
    if existing_id is not None:
        institution = await session.get_one(Institution, existing_id)
        await _name_and_cite(ctx, session, institution, name, acronym, language, match, quote)
        if institution.status is EntityStatus.CANDIDATE and page.trusted:
            # A candidate named on a trusted page is verified, as a new finding would be.
            await status_changes.verify_institution(
                session, institution, entered_by=EnteredBy.AGENT
            )
    else:
        institution = await graph.create_institution(
            session,
            name=name,
            institution_type=institution_type,
            place=place,
            entered_by=EnteredBy.AGENT,
            parent=parent,
            procurement_handled_by=buys,
            suggested_type=suggested,
            language=language,
        )
        await _name_and_cite(ctx, session, institution, name, acronym, language, match, quote)
        if unsure:
            reviews.append(
                Review(
                    review.Rule.DUPLICATE,
                    "Possible duplicate of:\n" + "\n".join(str(likely) for likely in matches),
                    {"duplicate_of": [str(likely.entity_id) for likely in matches]},
                )
            )
        told = await _send_for_review(ctx, session, institution, reviews)
        if not reviews and page.trusted:
            # The spawn (its homepage search) comes when this assignment finishes.
            await status_changes.verify_institution(
                session, institution, entered_by=EnteredBy.AGENT
            )
    homepage = None
    if homepage_url:
        homepage = str(
            await record_homepage(
                ctx,
                session,
                url=homepage_url,
                institution_id=str(institution.id),
                found_on_url=page_url,
                link_quote=quote,
            )
        )
    return SavedInstitution(
        institution_id=institution.id,
        name=institution.name,
        institution_type=institution.institution_type,
        status=institution.status,
        matched=existing_id is not None,
        reviews=told,
        homepage=homepage,
    )


def _check_type(
    rules: CountryRules, institution_type: str, suggested_type: str | None
) -> str | None:
    """The cleaned suggested type for `other`, None for a listed type."""
    listed = sorted(name for name in rules.uses if name != OTHER_TYPE)
    if institution_type == OTHER_TYPE:
        cleaned = " ".join(suggested_type.split()) if suggested_type else ""
        if not cleaned:
            raise FindingError(
                f"institution_type={OTHER_TYPE!r} needs suggested_type: the kind of body this "
                "is, in a few words ('housing corporation'). Use a listed type when one fits."
            )
        return cleaned[:SUGGESTED_TYPE_LENGTH]
    if institution_type not in rules.institution_types:
        raise FindingError(
            f"Unknown institution type {institution_type!r}. Types: {', '.join(listed)}; or "
            f"{OTHER_TYPE!r} with suggested_type when none fits."
        )
    if suggested_type:
        raise FindingError(f"suggested_type goes with institution_type={OTHER_TYPE!r} only.")
    return None


def _buyer(value: str) -> ProcurementHandledBy:
    try:
        return ProcurementHandledBy(value)
    except ValueError:
        raise FindingError("procurement_handled_by must be 'self' or 'parent'.") from None


async def _place_for(
    ctx: SessionContext, session: AsyncSession, place_id: str | None
) -> tuple[Place, list[Place]]:
    """The place the body is saved under, and the places it may be saved under: the assignment's
    place and each place above it, up to the country. By default the assignment's own. Any other
    id is refused with the allowed places named, so the agent cannot file a body under a place it
    was never briefed on."""
    place = await session.get_one(Place, ctx.place.id)
    chain = await graph.place_chain(session, place)
    if place_id is None:
        return chain[0], chain
    wanted = parse_uuid(place_id, "place_id")
    for found in chain:
        if found.id == wanted:
            return found, chain
    allowed = "; ".join(f"{place_label(found)} id={found.id}" for found in chain)
    raise FindingError(
        f"place_id {place_id} is not a place this assignment may save under. Allowed: the "
        f"subject's place and the places above it: {allowed}."
    )


async def _parent_for(
    session: AsyncSession, parent_institution_id: str | None
) -> Institution | None:
    if parent_institution_id is None:
        return None
    parent = await session.get(
        Institution, parse_uuid(parent_institution_id, "parent_institution_id")
    )
    if parent is None or parent.status is EntityStatus.REJECTED:
        raise FindingError(
            f"No institution with id {parent_institution_id} to sit under. Save the parent first, "
            "or leave parent_institution_id out for the place's government."
        )
    return parent


def _reviews_for(
    rules: CountryRules, institution_type: str, suggested: str | None, name: str, place: Place
) -> list[Review]:
    """What a human must decide about the body before it is verified: a type the country does
    not expect at this level (the level's list is a floor, not a ceiling), a body no type fits,
    a name that misses its type's pattern."""
    reviews: list[Review] = []
    level = place.administrative_level
    if suggested is not None:
        reviews.append(
            Review(
                review.Rule.NEW_TYPE,
                f"No listed institution type fits; the agent suggests {suggested!r} (under a "
                f"{level}). Add the type on the countries page, give the body a listed type, "
                "or reject it.",
                {"suggested_type": suggested, "level": level},
            )
        )
    elif institution_type not in rules.expected_institution_types(level):
        reviews.append(
            Review(
                review.Rule.TYPE_LEVEL,
                f"A {institution_type} found under a {level}; the country does not expect "
                f"{institution_type} at that level. Confirm it, or add the type to the level "
                "on the countries page.",
                {"institution_type": institution_type, "level": level},
            )
        )
    odd_name = rules.name_mismatch(institution_type, name)
    if odd_name is not None:
        reviews.append(
            Review(review.Rule.NAME_PATTERN, odd_name, {"institution_type": institution_type})
        )
    return reviews


async def _send_for_review(
    ctx: SessionContext, session: AsyncSession, institution: Institution, reviews: list[Review]
) -> list[str]:
    for item in reviews:
        await review.raise_review(
            session,
            institution,
            rule=item.rule,
            reason=item.reason,
            question=item.question,
            assignment_id=ctx.assignment_id,
        )
    return [item.reason for item in reviews]


async def _name_and_cite(  # noqa: PLR0913, PLR0917
    ctx: SessionContext,
    session: AsyncSession,
    institution: Institution,
    name: str,
    acronym: str | None,
    language: str,
    match: evidence.QuoteMatch,
    quote: str,
) -> None:
    await graph.add_alias(session, institution, name, language=language, entered_by=EnteredBy.AGENT)
    if acronym:
        await graph.add_alias(
            session,
            institution,
            acronym,
            language=language,
            entered_by=EnteredBy.AGENT,
            is_acronym=True,
        )
    await add_quote(ctx, session, institution.id, match, quote)


def _detail(institution: Institution) -> str:
    return f"{institution.institution_type}, {institution.status.value}"


async def _verified_owner(session: AsyncSession, url: str) -> Institution | None:
    try:
        webpage = await graph.webpage_by_url(session, url)
    except ValueError:
        return None
    if webpage is None:
        return None
    return await graph.verified_homepage_owner(session, webpage)
