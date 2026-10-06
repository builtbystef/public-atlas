"""What every finding shares: the session each tool runs in, the page that must have been
opened, the quote that must be on it and name what it is saved for, the likely duplicate the
agent must decide, and the work a finding sets in motion."""

import uuid
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass

from pydantic_ai import ModelRetry, RunContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.modules.agent.context import SessionContext
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import Assignment, Run
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.countries.naming import Naming
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind, Snapshot
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import (
    Domain,
    DomainKind,
    EnteredBy,
    EntityStatus,
    Institution,
    Place,
    Webpage,
)
from public_atlas.shared.text import repair_mojibake

# Every tool spells out `RunContext[SessionContext]`: Pydantic AI recognises the run context only
# when the annotation is `RunContext[...]` itself, not an alias of it.

DECISION_NEW = "new"
DECISION_UNSURE = "unsure"
# Pages on the same host named when the agent cites a URL it never opened.
OPENED_NEARBY = 8


class FindingError(Exception):
    """Refused, with what the model should do instead. The adapter turns it into a retry prompt;
    nothing was saved."""


async def in_session[T](
    ctx: RunContext[SessionContext], work: Callable[[AsyncSession], Awaitable[T]]
) -> T:
    """Run `work` in a database session of its own and commit, so what a tool saved survives
    whatever the agent does next. A refusal rolls back and is returned to the model."""
    async with ctx.deps.session() as session:
        try:
            result = await work(session)
        except FindingError as exc:
            await session.rollback()
            raise ModelRetry(str(exc)) from None
        await session.commit()
    return result


# --- Pages ---


@dataclass(frozen=True, slots=True)
class Page:
    """A page the agent opened, with the domain row that covers it."""

    webpage: Webpage
    domain: Domain | None

    @property
    def trusted(self) -> bool:
        return self.domain is not None and graph.is_trusted(self.domain)

    @property
    def platform(self) -> bool:
        return self.domain is not None and self.domain.domain_kind is DomainKind.PLATFORM


def absolute_url(url: str) -> str:
    try:
        normalized = graph.normalize_url(url)
    except ValueError:
        raise FindingError(f"Not a URL: {url!r}") from None
    host = graph.host_of(normalized)
    if not host or any(char.isspace() for char in host):
        raise FindingError(f"Not an absolute URL: {url!r}")
    return normalized


async def page_of(session: AsyncSession, webpage: Webpage) -> Page:
    return Page(webpage=webpage, domain=await graph.domain_of_webpage(session, webpage))


async def _captured(session: AsyncSession, url: str) -> Webpage | None:
    webpage = await graph.webpage_by_url(session, url)
    if webpage is None or await evidence.latest_snapshot(session, webpage.id) is None:
        return None
    return webpage


async def visited_page(session: AsyncSession, url: str) -> Page:
    """The stored page at `url`; the agent must have opened it, in any session of any
    assignment, for its text to vouch for anything. A URL the browser was redirected from is
    read on the page that answered: the agent cites what it typed, the store holds what it got."""
    normalized = absolute_url(url)
    webpage = await _captured(session, normalized)
    if webpage is None:
        for hop in await graph.redirect_chain(session, normalized):
            webpage = await _captured(session, hop)
            if webpage is not None:
                break
    if webpage is None:
        raise FindingError(
            f"{normalized} has not been opened, so its text cannot vouch for a finding. Open it "
            "with navigate (or read_file for a document) first, then quote from it."
            + await _opened_nearby(session, normalized)
        )
    return await page_of(session, webpage)


async def _opened_nearby(session: AsyncSession, url: str) -> str:
    """The pages opened on the same host, for an agent that cited a URL from memory: the exact
    URL is in this list, or it was never opened."""
    host = graph.host_of(url)
    if not host:
        return ""
    rows = await session.scalars(
        select(Webpage.url)
        .join(Snapshot, Snapshot.webpage_id == Webpage.id)
        .where(Webpage.url.like(f"%://{host}/%"))
        .group_by(Webpage.url)
        .order_by(func.max(Snapshot.fetched_at).desc())
        .limit(OPENED_NEARBY)
    )
    opened = list(rows)
    if not opened:
        return ""
    return f" Pages opened on {host}: {', '.join(opened)}."


# --- Quotes ---


async def matched_quote(
    ctx: SessionContext, session: AsyncSession, page: Page, quote: str
) -> evidence.QuoteMatch:
    """Where `quote` is in the stored copy of `page`, or a refusal with the page's closest
    wording (spec section 6.2)."""
    quote = quote.strip()
    if len(quote) < evidence.MIN_QUOTE_CHARS:
        raise FindingError(
            f"The quote is too short to check (under {evidence.MIN_QUOTE_CHARS} characters). "
            "Quote a phrase from the page."
        )
    match = await evidence.check_quote(session, ctx.store, page.webpage, quote)
    if match is None:
        nearest = await evidence.nearest_text(session, ctx.store, page.webpage, quote)
        hint = f" The closest text on the page is: {nearest!r}." if nearest else ""
        raise FindingError(
            f"The quote was not found word for word on {page.webpage.url}. Copy the text exactly "
            f"as the page shows it (get_text returns it verbatim); do not paraphrase or add "
            f"words.{hint}"
        )
    return match


def require_name(name: str, what: str) -> str:
    """The name with its spacing collapsed and mojibake put right (a list that writes the bytes
    of "Café" as Windows-1252 means "Café"); a blank one is refused."""
    name = " ".join(repair_mojibake(name).split())
    if not name:
        raise FindingError(f"The {what}'s name is empty. Pass the name as the page writes it.")
    return name


def quote_names(quote: str, names: Iterable[str | None], what: str, *, naming: Naming) -> None:
    """A phrase proves an entity only if the entity is named in it (spec section 6.2)."""
    wanted = [name for name in names if name]
    if not evidence.mentions_any(quote, wanted, key=naming.key):
        raise FindingError(
            f"The quote does not name the {what} ({' / '.join(wanted)}). Quote the phrase "
            "where the page names it, exactly as the page writes it."
        )


async def add_quote(  # noqa: PLR0913
    ctx: SessionContext,
    session: AsyncSession,
    entity_id: uuid.UUID,
    match: evidence.QuoteMatch,
    quote: str,
    *,
    kind: EvidenceKind = EvidenceKind.APPEARS_ON,
    link_url: str | None = None,
) -> bool:
    """The quote as this assignment's evidence for the entity."""
    return await evidence.add_evidence(
        session,
        entity_id=entity_id,
        snapshot=match.snapshot,
        kind=kind,
        quote=quote,
        entered_by=EnteredBy.AGENT,
        locator=match.locator,
        link_url=link_url,
        assignment_id=ctx.assignment_id,
    )


# --- Entities ---


def parse_uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise FindingError(f"{what} is not an id: {value!r}") from None


async def institution_by_id(session: AsyncSession, value: str) -> Institution:
    """The institution a finding is about. A rejected one (a human's decision, or a duplicate
    merged away) takes no more findings."""
    institution = await session.get(Institution, parse_uuid(value, "institution_id"))
    if institution is None:
        raise FindingError(f"No institution with id {value}. Save it first, or check status().")
    if institution.status is EntityStatus.REJECTED:
        raise FindingError(
            f"Institution {value} was rejected (or merged into another); nothing more is "
            "recorded on it. Check status() for the one to use."
        )
    return institution


async def subject_institution(
    ctx: SessionContext, session: AsyncSession, institution_id: str | None
) -> Institution:
    """The institution named, else the assignment's own subject when that is an institution."""
    if institution_id is not None:
        return await institution_by_id(session, institution_id)
    if isinstance(ctx.subject, Institution):
        return await institution_by_id(session, str(ctx.subject.id))
    raise FindingError("Pass institution_id: the institution this belongs to.")


async def name_texts(session: AsyncSession, owner: Place | Institution) -> list[str]:
    return [alias.text for alias in await graph.names_of(session, owner)]


def place_label(place: Place) -> str:
    return f"{place.name} ({place.administrative_level})"


# --- Duplicates ---


@dataclass(frozen=True, slots=True)
class Likely:
    """One likely duplicate, as the agent is shown it."""

    entity_id: uuid.UUID
    alias: str
    score: float
    detail: str

    def __str__(self) -> str:
        return f"- {self.alias!r} ({self.detail}) id={self.entity_id} similarity={self.score:.2f}"


@dataclass(frozen=True, slots=True)
class LikelyDuplicates:
    """Not saved: the agent decides whether the body is one of these."""

    what: str
    matches: list[Likely]

    def __str__(self) -> str:
        return (
            f"Not saved: {self.what} may already exist. Likely matches in this place:\n"
            + "\n".join(str(match) for match in self.matches)
            + f"\nCall again with decision='{DECISION_NEW}' if it is a different {self.what}, "
            "decision=<id> if it is one of these (the name is added to it), or "
            f"decision='{DECISION_UNSURE}' to save it for a human to settle."
        )


def resolve_decision(
    matches: Sequence[Likely], decision: str | None, what: str
) -> tuple[uuid.UUID | None, bool, LikelyDuplicates | None]:
    """(existing id, unsure, the offer). An offer means nothing was saved and the agent must
    decide. An id that is not among the matches is refused, whether or not there were any: the
    agent may only match what it was offered."""
    if not matches:
        if decision not in (None, DECISION_NEW, DECISION_UNSURE):
            parse_uuid(decision, "decision")
            raise FindingError(
                f"decision={decision} was not offered: no existing {what} has a name like this "
                f"one. Call again without a decision, or with decision='{DECISION_NEW}'."
            )
        return None, False, None
    if decision is None:
        return None, False, LikelyDuplicates(what, list(matches))
    if decision == DECISION_NEW:
        return None, False, None
    if decision == DECISION_UNSURE:
        return None, True, None
    chosen = parse_uuid(decision, "decision")
    if chosen not in {match.entity_id for match in matches}:
        raise FindingError(f"decision={decision} is not one of the likely matches listed.")
    return chosen, False, None


# --- Spawning ---


async def spawn(
    ctx: SessionContext, session: AsyncSession, spawns: Sequence[Spawn]
) -> list[Assignment]:
    """Turn what a status change asked for into assignments of this run, as the backend does
    (spec section 7.3). The agent never asks for work itself."""
    if not spawns:
        return []
    run = await session.get_one(Run, ctx.run.id)
    parent = await session.get_one(Assignment, ctx.assignment_id)
    return await assignments.spawn(session, ctx.jobs, run, spawns, parent=parent)


def describe_assignments(rows: Sequence[Assignment]) -> str:
    return ", ".join(f"{row.type.value} ({row.status.value})" for row in rows) or "nothing new"
