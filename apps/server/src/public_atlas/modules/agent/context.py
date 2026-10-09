"""What one session knows: the assignment and its run, the type's descriptor, the country's
rules, the subject, the browser allowlist, and, in a `find_homepage` session, the candidate it
is deciding on. Built from the database at the start of every session and never carried over
(spec principle 1). The finishing tools set `ended`; the runner stops the session when it sees
it."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from procrastinate import App
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.config import Settings
from public_atlas.integrations.browser import BrowserPolicy
from public_atlas.integrations.search import Searcher
from public_atlas.integrations.storage import ObjectStore
from public_atlas.modules.assignments.descriptors import Checklist, Descriptor, descriptor_for
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentType,
    Run,
)
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

# The stall rule of a discovery assignment (`runner.py`): model requests since the assignment
# last saved a finding, counted across its sessions. At the first number the next tool result
# tells the agent to finish unless it has a concrete page left; at the second the runner ends
# the assignment `complete` with a summary the handoff model writes. Tuned on each eval run.
STALL_WARNING_REQUESTS = 30
STALL_END_REQUESTS = 60


class SubjectMissingError(Exception):
    """The assignment's subject is gone or of the wrong kind; the assignment cannot run."""


@dataclass(frozen=True, slots=True)
class Ended:
    """How the session ended the assignment: set by a finishing tool."""

    result: AssignmentResult
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class Candidate:
    """The homepage claim a `find_homepage` session is deciding on, with its domain: the one
    domain outside the trusted set the session may open (spec section 6.1, step 4)."""

    domain_id: uuid.UUID
    domain_name: str
    homepage_id: uuid.UUID


@dataclass
class SessionContext:
    res: Resources
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
    # The browser's policy, once the browser exists; `read_file` fetches under it.
    policy: BrowserPolicy | None = None
    candidate: Candidate | None = None
    # The sites this session's searches returned, by their domain name: a homepage on one may
    # be saved with no page linking to it.
    search_hosts: set[str] = field(default_factory=set)
    ended: Ended | None = None
    # Searches made this session; capped per assignment.
    searches: int = 0
    # `confirm_domain` calls that failed on something the agent can put right.
    confirm_attempts: int = 0
    # Finishes refused for leaving a type unaccounted for; the second ends `complete_with_gaps`.
    short_closes: int = 0
    tool_calls: int = 0
    # Model requests since the assignment last saved a finding, over every session (the stall
    # rule): started from the row, counted up by the runner, reset by a save.
    requests_since_finding: int = 0
    stall_warned: bool = False

    def session(self) -> AsyncSession:
        return self.session_factory()

    @property
    def assignment_id(self) -> uuid.UUID:
        return self.assignment.id

    @property
    def finding_homepage(self) -> bool:
        return self.descriptor.type is AssignmentType.FIND_HOMEPAGE

    @property
    def has_stall_rule(self) -> bool:
        """Only a discovery assignment can stall: `find_homepage` ends by its own decision tools
        and its budget is small."""
        return self.descriptor.checklist is not Checklist.NONE

    @property
    def stalled(self) -> bool:
        return self.has_stall_rule and self.requests_since_finding >= STALL_END_REQUESTS

    def note_finding(self) -> None:
        """A finding was saved: the stall count starts over."""
        self.requests_since_finding = 0
        self.stall_warned = False

    def stall_notice(self) -> str | None:
        """The line the next tool result carries once the assignment has gone a long way without
        a finding; said once per stall in each session, since a new session starts with no
        memory of the last one's notice."""
        if (
            not self.has_stall_rule
            or self.stall_warned
            or self.requests_since_finding < STALL_WARNING_REQUESTS
        ):
            return None
        self.stall_warned = True
        return (
            f"{self.requests_since_finding} moves without a finding; finish with a summary "
            "unless you have a concrete page left to open."
        )

    def end(self, result: AssignmentResult, summary: str | None = None) -> None:
        self.ended = Ended(result, summary)

    def allow_domain(self, name: str) -> None:
        """Let the browser reach `name`: `allowed_domains` is the list the policy reads."""
        if name not in self.allowed_domains:
            self.allowed_domains.append(name)

    def take_candidate(self, domain: Domain, homepage: Homepage) -> None:
        """The claim this session decides on; its domain opens for the session."""
        self.candidate = Candidate(domain.id, domain.name, homepage.id)
        self.allow_domain(domain.name)

    def drop_candidate(self) -> None:
        """The candidate is decided: its domain closes again unless it is trusted now."""
        if self.candidate is None:
            return
        name = self.candidate.domain_name
        self.candidate = None
        self.confirm_attempts = 0
        if name in self.allowed_domains and name not in self.search_hosts:
            self.allowed_domains.remove(name)

    def file_policy(self) -> BrowserPolicy:
        """The policy `read_file` fetches under: the browser's own, or one over the same
        allowlist when no browser was started (a test calling the findings directly)."""
        if self.policy is None:
            self.policy = BrowserPolicy(
                self.allowed_domains,
                block_private_addresses=not self.settings.browser_allow_private_addresses,
                respect_robots=self.settings.browser_respect_robots,
                min_interval=self.settings.browser_min_interval.total_seconds(),
            )
        return self.policy


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
    candidate = None
    if isinstance(subject, Institution) and descriptor.type is AssignmentType.FIND_HOMEPAGE:
        for domain in await candidate_domains(session, subject):
            if domain.name not in allowed:
                allowed.append(domain.name)
        candidate = await open_candidate(session, subject)
    return SessionContext(
        res=res,
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
        candidate=candidate,
        requests_since_finding=assignment.requests_since_finding,
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


async def _open_claims(
    session: AsyncSession, institution: Institution, statuses: tuple[EntityStatus, ...]
) -> list[tuple[Homepage, Domain | None]]:
    rows = await session.execute(
        select(Homepage, Webpage)
        .join(Webpage, Webpage.id == Homepage.webpage_id)
        .where(Homepage.institution_id == institution.id, Homepage.status.in_(statuses))
        .order_by(Homepage.id)
    )
    found = []
    for homepage, webpage in rows.all():
        found.append((homepage, await graph.domain_of_webpage(session, webpage)))
    return found


async def candidate_domains(session: AsyncSession, institution: Institution) -> list[Domain]:
    """The domains of the institution's homepage claims still waiting for a decision: what a
    `find_homepage` session may open to decide them."""
    found: dict[uuid.UUID, Domain] = {}
    for _, domain in await _open_claims(
        session, institution, (EntityStatus.CANDIDATE, EntityStatus.NEEDS_REVIEW)
    ):
        if domain is not None and domain.status is not EntityStatus.REJECTED:
            found[domain.id] = domain
    return list(found.values())


async def open_candidate(session: AsyncSession, institution: Institution) -> Candidate | None:
    """The claim a `find_homepage` session starts out deciding: the institution's oldest
    candidate homepage on an official domain that is a candidate itself. A claim a reviewer
    holds, or one on a trusted domain or a platform, is not the session's to decide."""
    for homepage, domain in await _open_claims(session, institution, (EntityStatus.CANDIDATE,)):
        if (
            domain is not None
            and domain.domain_kind is DomainKind.OFFICIAL
            and domain.status is EntityStatus.CANDIDATE
        ):
            return Candidate(domain.id, domain.name, homepage.id)
    return None
