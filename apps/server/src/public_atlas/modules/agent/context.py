"""What one session knows: the assignment and its run, the type's descriptor, the country's
rules, the subject, and the browser allowlist. Built from the database at the start of every
session and never carried over (spec principle 1). The finishing tools set `ended`; the runner
stops the session when it sees it."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from procrastinate import App
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.config import Settings
from public_atlas.integrations.search import Searcher
from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.assignments.descriptors import Descriptor, descriptor_for
from public_atlas.modules.assignments.models import Assignment, AssignmentResult, Run
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import (
    Domain,
    DomainKind,
    EntityStatus,
    Homepage,
    Institution,
    Place,
    Webpage,
)
from public_atlas.resources import Resources

# Nothing here hides behind TYPE_CHECKING: the tools' schemas are built at run time from
# `RunContext[SessionContext]`.


class SubjectMissingError(Exception):
    """The assignment's subject is gone or of the wrong kind; the assignment cannot run."""


@dataclass(frozen=True, slots=True)
class Ended:
    """How the session ended the assignment: set by a finishing tool."""

    result: AssignmentResult
    summary: str | None = None


@dataclass
class SessionContext:
    settings: Settings
    session_factory: Callable[[], AsyncSession]
    store: ObjectStore
    jobs: App
    assignment: Assignment
    run: Run
    descriptor: Descriptor
    rules: CountryRules
    subject: Place | Institution
    # The subject's place: the place itself, or the institution's.
    place: Place
    # The browser allowlist, read live by the policy (spec section 8.2): every trusted domain and
    # every platform, plus a `find_homepage` session's candidate domain and the sites its
    # searches return.
    allowed_domains: list[str]
    searcher: Searcher | None = None
    capture: evidence.PageCapture | None = None
    ended: Ended | None = None
    # Searches made this session; capped per assignment.
    searches: int = 0
    # Finishes refused for leaving a type unaccounted for; the second ends `complete_with_gaps`.
    short_closes: int = 0
    tool_calls: int = 0

    def session(self) -> AsyncSession:
        return self.session_factory()

    @property
    def assignment_id(self) -> uuid.UUID:
        return self.assignment.id

    def end(self, result: AssignmentResult, summary: str | None = None) -> None:
        self.ended = Ended(result, summary)

    def allow_domain(self, name: str) -> None:
        """Let the browser reach `name`: `allowed_domains` is the list the policy reads."""
        if name not in self.allowed_domains:
            self.allowed_domains.append(name)


async def build_context(
    session: AsyncSession, res: Resources, assignment: Assignment
) -> SessionContext:
    run = await session.get_one(Run, assignment.run_id)
    descriptor = descriptor_for(assignment.type)
    rules = await countries.load_rules(session, run.country_code)
    subject = await _subject(session, assignment, descriptor)
    place = (
        subject if isinstance(subject, Place) else await session.get_one(Place, subject.place_id)
    )
    allowed = await allowed_domains(session)
    if isinstance(subject, Institution):
        for domain in await candidate_domains(session, subject):
            if domain.name not in allowed:
                allowed.append(domain.name)
    return SessionContext(
        settings=res.settings,
        session_factory=res.session_factory,
        store=res.object_store,
        jobs=res.jobs,
        assignment=assignment,
        run=run,
        descriptor=descriptor,
        rules=rules,
        subject=subject,
        place=place,
        allowed_domains=allowed,
        searcher=res.searcher,
    )


async def _subject(
    session: AsyncSession, assignment: Assignment, descriptor: Descriptor
) -> Place | Institution:
    entity = await graph.entity_by_id(session, assignment.subject_id)
    if entity is None:
        raise SubjectMissingError(f"subject {assignment.subject_id} does not exist")
    if entity.kind is not descriptor.subject_kind or not isinstance(entity, Place | Institution):
        raise SubjectMissingError(
            f"{assignment.type.value} works on a {descriptor.subject_kind.value}, not a "
            f"{entity.kind.value}"
        )
    return entity


async def allowed_domains(session: AsyncSession) -> list[str]:
    """Every trusted domain and every platform (spec section 8.2)."""
    rows = await session.scalars(
        select(Domain.name)
        .where(
            or_(
                Domain.domain_kind == DomainKind.PLATFORM,
                and_(
                    Domain.domain_kind == DomainKind.OFFICIAL,
                    Domain.status == EntityStatus.VERIFIED,
                ),
            )
        )
        .order_by(Domain.name)
    )
    return list(rows)


async def candidate_domains(session: AsyncSession, institution: Institution) -> list[Domain]:
    """The domains of the institution's homepage claims still waiting for a decision: what a
    `find_homepage` session may open to decide them."""
    webpages = await session.scalars(
        select(Webpage)
        .join(Homepage, Homepage.webpage_id == Webpage.id)
        .where(
            Homepage.institution_id == institution.id,
            Homepage.status.in_([EntityStatus.CANDIDATE, EntityStatus.NEEDS_REVIEW]),
        )
    )
    found: dict[uuid.UUID, Domain] = {}
    for webpage in webpages:
        domain = await graph.domain_of_webpage(session, webpage)
        if domain is not None and domain.status is not EntityStatus.REJECTED:
            found[domain.id] = domain
    return list(found.values())
