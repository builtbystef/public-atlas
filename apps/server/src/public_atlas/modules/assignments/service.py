"""The assignments module's door: runs (spec section 7.1), the assignments inside them and how
they are spawned (section 7.3), their budgets, and what each call cost.

A run is how a person controls work. Creating one seeds it with the work due for the subjects
its filter names: `find_homepage` for an institution without a verified homepage, `find_sources`
for one with, `find_institutions` for a place whose government has one. From then on every
status change that asks for work (`Spawn`) is turned into an assignment here, in the run of the
assignment that caused it, held or queued by the run's mode and bounded by its filter. Only the
backend creates work; the agent has no tool for it.
"""

import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from procrastinate import App
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.jobs.tasks import defer
from public_atlas.modules.agent.models import AgentRunEvent
from public_atlas.modules.assignments import lifecycle
from public_atlas.modules.assignments.descriptors import descriptor_for
from public_atlas.modules.assignments.models import (
    OPEN_STATUSES,
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
    Run,
    RunMode,
    RunStatus,
    Usage,
    UsageKind,
)
from public_atlas.modules.assignments.pricing import load_prices
from public_atlas.modules.assignments.schemas import Progress, RunFilter
from public_atlas.modules.evidence.models import Evidence
from public_atlas.modules.graph.models import (
    EntityStatus,
    Homepage,
    Institution,
    Place,
)
from public_atlas.shared.exceptions import ConflictError, NotFoundError

__all__ = [
    "RUN_ASSIGNMENT_TASK",
    "Spawn",
    "assignment_cost",
    "cancel",
    "count_assignments",
    "create_run",
    "due_work",
    "events_of",
    "get_assignment",
    "get_run",
    "list_assignments",
    "list_runs",
    "move_subject",
    "open_assignments",
    "pause_run",
    "progress",
    "progress_many",
    "queue_job",
    "queue_spawns",
    "record_usage",
    "release",
    "requeue",
    "resume_run",
    "run_filter",
    "run_for_decision",
    "seed_run",
    "spawn",
    "spawn_on_finish",
    "stop_run",
    "subjects_of",
]

logger = logging.getLogger(__name__)

# The job that runs an assignment (`jobs.py`). Looked up by name on the app, so this module
# never imports the job module, which imports the agent, which imports this module.
RUN_ASSIGNMENT_TASK = "assignments.run_assignment"
# A subject with a finished assignment of a type that ended one of these ways has had that
# work done: a run seeding itself does not do it again, and nor does a finish that saved the
# subject again. Any other ending leaves it to be redone. `no_homepage` is settled because the
# searches were made and a review item asks a person for the address; another search would
# find the same nothing.
SETTLED_RESULTS = (
    AssignmentResult.COMPLETE,
    AssignmentResult.COMPLETE_WITH_GAPS,
    AssignmentResult.NO_HOMEPAGE,
)

_unpriced: set[str] = set()


@dataclass(frozen=True, slots=True)
class Spawn:
    """Work a status change asks for (spec section 7.3): one assignment type on one subject. The
    backend inserts it and queues or holds it by the run's mode; the status change only says."""

    type: AssignmentType
    subject_id: uuid.UUID


# --- Runs ---


def run_filter(run: Run) -> RunFilter:
    return RunFilter.model_validate(run.filter)


async def create_run(  # noqa: PLR0913
    session: AsyncSession,
    jobs: App,
    *,
    name: str,
    country_code: str,
    mode: RunMode,
    filter: RunFilter | None = None,  # noqa: A002 - the column's name
    record_video: bool = False,
    is_eval: bool = False,
    run_id: uuid.UUID | None = None,
    seed: bool = True,
    hold: bool = False,
) -> Run:
    """A run, seeded with the work due for the subjects in its filter unless `seed` is off, held
    whatever the mode when `hold` (the eval harness seeds the country held and queues its
    subjects' work itself). `run_id` is given when the same run is recorded in two databases.
    Flushed, not committed."""
    run = Run(
        name=name,
        country_code=country_code,
        mode=mode,
        filter=(filter or RunFilter()).model_dump(mode="json"),
        record_video=record_video,
        is_eval=is_eval,
    )
    if run_id is not None:
        run.id = run_id
    session.add(run)
    await session.flush()
    if seed:
        await seed_run(session, jobs, run, hold=hold)
    return run


async def seed_run(
    session: AsyncSession, jobs: App, run: Run, *, hold: bool = False
) -> list[Assignment]:
    """The work due for every place and institution the run's filter covers, skipping what a
    finished assignment settled already; created held whatever the mode when `hold`. Safe to
    call again: open work is never doubled."""
    wanted = run_filter(run)
    created: list[Assignment] = []
    start_as = AssignmentStatus.HELD if hold else None
    for subject in await _subjects_in_scope(session, run.country_code, wanted):
        spawns = await due_work(session, subject)
        created.extend(
            await spawn(session, jobs, run, spawns, skip_settled=True, start_as=start_as)
        )
    logger.info("Run %s (%s) seeded with %d assignments", run.name, run.id, len(created))
    return created


async def _subjects_in_scope(
    session: AsyncSession, country_code: str, wanted: RunFilter
) -> list[Place | Institution]:
    """The places and institutions a run starts from: the ones its filter names, or every one
    of the country at the filter's levels, with the institutions of the filter's types."""
    if wanted.subject_ids:
        places = list(
            await session.scalars(
                select(Place).where(
                    Place.id.in_(wanted.subject_ids), Place.country_code == country_code
                )
            )
        )
        institutions = list(
            await session.scalars(select(Institution).where(Institution.id.in_(wanted.subject_ids)))
        )
        return [*places, *institutions]
    place_query = select(Place).where(
        Place.country_code == country_code, Place.status != EntityStatus.REJECTED
    )
    if wanted.administrative_levels:
        place_query = place_query.where(
            Place.administrative_level.in_(wanted.administrative_levels)
        )
    places = list(await session.scalars(place_query.order_by(Place.id)))
    institution_query = select(Institution).where(
        Institution.place_id.in_([place.id for place in places]),
        Institution.status != EntityStatus.REJECTED,
    )
    if wanted.institution_types:
        institution_query = institution_query.where(
            Institution.institution_type.in_(wanted.institution_types)
        )
    institutions = list(await session.scalars(institution_query.order_by(Institution.id)))
    return [*places, *institutions]


async def due_work(session: AsyncSession, subject: Place | Institution) -> list[Spawn]:
    """What the subject is owed now (spec section 7.3): `find_institutions` for a place whose
    government has a verified homepage; `find_sources` for an institution with one;
    `find_homepage` for an institution without, unless a reviewer is deciding a claim of its."""
    if subject.status is EntityStatus.REJECTED:
        return []
    if isinstance(subject, Place):
        return await _due_for_place(session, subject)
    return await _due_for_institution(session, subject)


async def _due_for_place(session: AsyncSession, place: Place) -> list[Spawn]:
    if place.government_institution_id is None:
        return []
    government = await session.get_one(Institution, place.government_institution_id)
    if government.homepage_id is None or government.status is EntityStatus.REJECTED:
        return []
    return [Spawn(AssignmentType.FIND_INSTITUTIONS, place.id)]


async def _due_for_institution(session: AsyncSession, institution: Institution) -> list[Spawn]:
    if institution.homepage_id is not None:
        return [Spawn(AssignmentType.FIND_SOURCES, institution.id)]
    pending = await session.scalar(
        select(Homepage.id)
        .where(
            Homepage.institution_id == institution.id,
            Homepage.status == EntityStatus.NEEDS_REVIEW,
        )
        .limit(1)
    )
    if pending is not None:
        return []
    return [Spawn(AssignmentType.FIND_HOMEPAGE, institution.id)]


async def list_runs(
    session: AsyncSession, *, limit: int = 100, offset: int = 0
) -> tuple[list[Run], int]:
    """A page of runs, newest first, and how many there are."""
    rows = await session.scalars(
        select(Run).order_by(Run.created_at.desc(), Run.id.desc()).limit(limit).offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(Run))
    return list(rows), int(total or 0)


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise NotFoundError("no such run")
    return run


async def pause_run(session: AsyncSession, run: Run) -> None:
    """The worker starts none of the run's assignments until it is resumed; running ones finish
    their session. Queued jobs stay queued."""
    if run.status is not RunStatus.ACTIVE:
        raise ConflictError(f"a {run.status.value} run cannot be paused")
    run.status = RunStatus.PAUSED
    await session.flush()


async def resume_run(session: AsyncSession, run: Run) -> None:
    if run.status is not RunStatus.PAUSED:
        raise ConflictError(f"a {run.status.value} run cannot be resumed")
    run.status = RunStatus.ACTIVE
    await session.flush()


async def stop_run(session: AsyncSession, run: Run) -> list[Assignment]:
    """Cancel everything held or queued. A running assignment finishes its session and is
    cancelled by the runner when it sees the run stopped. Nothing is spawned into a stopped
    run."""
    if run.status is RunStatus.STOPPED:
        raise ConflictError("the run is stopped already")
    run.status = RunStatus.STOPPED
    cancelled = list(
        await session.scalars(
            select(Assignment).where(
                Assignment.run_id == run.id,
                Assignment.status.in_([AssignmentStatus.HELD, AssignmentStatus.QUEUED]),
            )
        )
    )
    for assignment in cancelled:
        lifecycle.cancel(assignment)
    await session.flush()
    return cancelled


async def release(  # noqa: PLR0913 - one argument per way of choosing
    session: AsyncSession,
    jobs: App,
    run: Run,
    *,
    limit: int = 1,
    assignment_type: AssignmentType | None = None,
    assignment_ids: Iterable[uuid.UUID] = (),
) -> list[Assignment]:
    """Queue held assignments of the run, oldest first: `limit` of them, of one type, or the
    ones named. A step-mode run advances this way."""
    if run.status is RunStatus.STOPPED:
        raise ConflictError("the run is stopped")
    query = select(Assignment).where(
        Assignment.run_id == run.id, Assignment.status == AssignmentStatus.HELD
    )
    ids = list(assignment_ids)
    if ids:
        query = query.where(Assignment.id.in_(ids))
    if assignment_type is not None:
        query = query.where(Assignment.type == assignment_type)
    released = list(
        await session.scalars(query.order_by(Assignment.created_at, Assignment.id).limit(limit))
    )
    for assignment in released:
        lifecycle.queue(assignment)
        await queue_job(session, jobs, assignment)
    await session.flush()
    return released


async def progress(session: AsyncSession, run: Run) -> Progress:
    return (await progress_many(session, [run.id]))[run.id]


async def progress_many(
    session: AsyncSession, run_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Progress]:
    """How far each run has got and what it has spent, in three queries for the batch."""
    found = {run_id: Progress(by_status={}, by_result={}, cost=Decimal(0)) for run_id in run_ids}
    if not run_ids:
        return found
    ids = list(found)
    by_status = await session.execute(
        select(Assignment.run_id, Assignment.status, func.count())
        .where(Assignment.run_id.in_(ids))
        .group_by(Assignment.run_id, Assignment.status)
    )
    for run_id, status, count in by_status.tuples():
        found[run_id].by_status[AssignmentStatus(status)] = count
    by_result = await session.execute(
        select(Assignment.run_id, Assignment.result, func.count())
        .where(Assignment.run_id.in_(ids), Assignment.result.is_not(None))
        .group_by(Assignment.run_id, Assignment.result)
    )
    for run_id, result, count in by_result.tuples():
        found[run_id].by_result[AssignmentResult(result)] = count
    costs = await session.execute(
        select(Assignment.run_id, func.coalesce(func.sum(Usage.cost), 0))
        .join(Assignment, Assignment.id == Usage.assignment_id)
        .where(Assignment.run_id.in_(ids))
        .group_by(Assignment.run_id)
    )
    for run_id, cost in costs.tuples():
        found[run_id].cost = Decimal(cost or 0)
    return found


# --- Spawning ---


async def spawn(  # noqa: C901, PLR0913 - one rule per line
    session: AsyncSession,
    jobs: App,
    run: Run,
    spawns: Sequence[Spawn],
    *,
    parent: Assignment | None = None,
    skip_settled: bool = False,
    start_as: AssignmentStatus | None = None,
) -> list[Assignment]:
    """Turn what a status change asked for into assignments of `run`: held in step mode, queued
    with a job in auto mode, or `start_as` (held or queued) whatever the mode. Work outside the
    run's filter, on a subject with that type open already, or (with `skip_settled`) done by a
    finished assignment is not created; nor is anything in a stopped run. Flushed, not
    committed."""
    if run.status is RunStatus.STOPPED:
        if spawns:
            logger.info("Run %s is stopped: %d spawns dropped", run.id, len(spawns))
        return []
    if start_as is None:
        start_as = AssignmentStatus.HELD if run.mode is RunMode.STEP else AssignmentStatus.QUEUED
    elif start_as not in (AssignmentStatus.HELD, AssignmentStatus.QUEUED):
        raise ConflictError(f"an assignment cannot start {start_as.value}")
    wanted = run_filter(run)
    created: list[Assignment] = []
    for asked in dict.fromkeys(spawns):
        subject = await _subject(session, asked)
        if subject is None or not await _in_scope(session, wanted, asked.type, subject):
            continue
        if await _open(session, asked) is not None:
            continue
        if skip_settled and await _settled(session, asked) is not None:
            continue
        assignment = await _insert(session, run, asked, parent, start_as)
        if assignment is None:
            continue
        if assignment.status is AssignmentStatus.QUEUED:
            await queue_job(session, jobs, assignment)
        logger.info(
            "%s %s on %s: %s", asked.type.value, assignment.id, asked.subject_id, assignment.status
        )
        created.append(assignment)
    await session.flush()
    return created


async def _subject(session: AsyncSession, asked: Spawn) -> Place | Institution | None:
    kind = descriptor_for(asked.type).subject_kind
    table: type[Place | Institution] = Place if kind == "place" else Institution
    subject = await session.get(table, asked.subject_id)
    if subject is None:
        logger.warning("No %s %s for %s", kind, asked.subject_id, asked.type.value)
    return subject


async def _in_scope(
    session: AsyncSession, wanted: RunFilter, assignment_type: AssignmentType, subject: object
) -> bool:
    """Whether the run's filter admits this work: its type, the level of the subject's place and,
    for an institution, its type. The subject ids bound only what a run starts from."""
    if wanted.assignment_types and assignment_type not in wanted.assignment_types:
        return False
    if isinstance(subject, Place):
        place = subject
    elif isinstance(subject, Institution):
        place = await session.get_one(Place, subject.place_id)
        if wanted.institution_types and subject.institution_type not in wanted.institution_types:
            return False
    else:  # pragma: no cover - `_subject` returns one of the two
        return False
    return (
        not wanted.administrative_levels
        or place.administrative_level in wanted.administrative_levels
    )


async def _open(session: AsyncSession, asked: Spawn) -> Assignment | None:
    return await session.scalar(
        select(Assignment)
        .where(
            Assignment.subject_id == asked.subject_id,
            Assignment.type == asked.type,
            Assignment.status.in_(OPEN_STATUSES),
        )
        .limit(1)
    )


async def _settled(session: AsyncSession, asked: Spawn) -> Assignment | None:
    """The newest finished assignment that settled this work, if any."""
    return await session.scalar(
        select(Assignment)
        .where(
            Assignment.subject_id == asked.subject_id,
            Assignment.type == asked.type,
            Assignment.status == AssignmentStatus.FINISHED,
            Assignment.result.in_(SETTLED_RESULTS),
        )
        .order_by(Assignment.created_at.desc(), Assignment.id.desc())
        .limit(1)
    )


async def _insert(
    session: AsyncSession,
    run: Run,
    asked: Spawn,
    parent: Assignment | None,
    status: AssignmentStatus,
) -> Assignment | None:
    """The row, in `status`. Two workers may ask for the same work at once; the partial unique
    index lets one in, and the loser takes nothing."""
    budget = descriptor_for(asked.type).budget
    assignment = Assignment(
        run_id=run.id,
        type=asked.type,
        subject_id=asked.subject_id,
        status=status,
        budget_requests=budget.requests,
        budget_tokens=budget.tokens,
        parent_assignment_id=parent.id if parent is not None else None,
    )
    try:
        async with session.begin_nested():
            session.add(assignment)
            await session.flush()
    except IntegrityError:
        logger.info("%s on %s was queued by another worker", asked.type.value, asked.subject_id)
        return None
    return assignment


async def queue_spawns(
    session: AsyncSession,
    jobs: App,
    run: Run,
    spawns: Sequence[Spawn],
    *,
    parent: Assignment | None = None,
) -> list[Assignment]:
    """The assignments for `spawns`, queued now whatever the run's mode: one held on the subject
    is released, one queued, running or finished with its work settled is returned as it is,
    and a missing one is created queued. How the eval harness starts a subject's work in a run
    seeded held, and starts it once. The run's filter still applies. Flushed, not committed."""
    queued: list[Assignment] = []
    for asked in dict.fromkeys(spawns):
        found = await _open(session, asked) or await _settled(session, asked)
        if found is None:
            queued.extend(
                await spawn(
                    session, jobs, run, [asked], parent=parent, start_as=AssignmentStatus.QUEUED
                )
            )
            continue
        if found.status is AssignmentStatus.HELD:
            lifecycle.queue(found)
            await queue_job(session, jobs, found)
        queued.append(found)
    await session.flush()
    return queued


async def spawn_on_finish(
    session: AsyncSession, jobs: App, assignment: Assignment
) -> list[Assignment]:
    """What a finished assignment sets in motion (spec section 7.3): `find_homepage` for every
    institution it saved that has no verified homepage and no decision pending. Spec section
    7.3 names `find_institutions`; the other two types may save a body they meet, and that body
    is owed the same. The subject of a `find_homepage` is never its own follow-up: one that
    ended `no_homepage` is settled by its review item. Nothing after a `failed` one."""
    if assignment.result is AssignmentResult.FAILED:
        return []
    run = await session.get_one(Run, assignment.run_id)
    saved = select(Evidence.entity_id).where(Evidence.assignment_id == assignment.id)
    institutions = await session.scalars(
        select(Institution)
        .where(Institution.id.in_(saved), Institution.id != assignment.subject_id)
        .order_by(Institution.id)
    )
    spawns = [
        spawn_
        for institution in institutions
        for spawn_ in await due_work(session, institution)
        if spawn_.type is AssignmentType.FIND_HOMEPAGE
    ]
    return await spawn(session, jobs, run, spawns, parent=assignment, skip_settled=True)


async def run_for_decision(
    session: AsyncSession, *, assignment_id: uuid.UUID | None, country_code: str | None
) -> Run | None:
    """The run a reviewer's decision spawns into: the run of the assignment that raised the
    question, while it is not stopped, else the newest run of the country still going. None
    when there is none: the work waits for the next run to seed itself."""
    if assignment_id is not None:
        raised_by = await session.get(Assignment, assignment_id)
        if raised_by is not None:
            run = await session.get_one(Run, raised_by.run_id)
            if run.status is not RunStatus.STOPPED:
                return run
    if country_code is None:
        return None
    return await session.scalar(
        select(Run)
        .where(
            Run.country_code == country_code,
            Run.status != RunStatus.STOPPED,
            Run.is_eval.is_(False),
        )
        .order_by(Run.created_at.desc(), Run.id.desc())
        .limit(1)
    )


# --- Queueing ---


async def queue_job(
    session: AsyncSession, jobs: App, assignment: Assignment, *, delay: timedelta | None = None
) -> int:
    """One job for the assignment, in the session's transaction. Jobs of one assignment never
    run at once."""
    return await defer(
        jobs,
        session,
        jobs.tasks[RUN_ASSIGNMENT_TASK],
        lock=f"assignment:{assignment.id}",
        schedule_in=delay,
        assignment_id=str(assignment.id),
    )


async def requeue(session: AsyncSession, jobs: App, assignment: Assignment) -> None:
    """Another job for a running assignment whose job has had its twenty sessions, or whose run
    was paused meanwhile. The next job's first session resumes from the handoff note."""
    lifecycle.queue(assignment)
    await queue_job(session, jobs, assignment)
    await session.flush()


# --- Assignments ---


async def open_assignments(session: AsyncSession, subject_id: uuid.UUID) -> list[Assignment]:
    """The held, queued and running assignments on a subject."""
    rows = await session.scalars(
        select(Assignment)
        .where(Assignment.subject_id == subject_id, Assignment.status.in_(OPEN_STATUSES))
        .order_by(Assignment.id)
    )
    return list(rows)


async def list_assignments(  # noqa: PLR0913
    session: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
    status: AssignmentStatus | None = None,
    result: AssignmentResult | None = None,
    assignment_type: AssignmentType | None = None,
    subject_id: uuid.UUID | None = None,
    newest_first: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[Assignment]:
    """A page of assignments, oldest first unless `newest_first`."""
    query = _assignments_matching(
        run_id=run_id,
        status=status,
        result=result,
        assignment_type=assignment_type,
        subject_id=subject_id,
    )
    order = (
        (Assignment.created_at.desc(), Assignment.id.desc())
        if newest_first
        else (Assignment.created_at, Assignment.id)
    )
    rows = await session.scalars(query.order_by(*order).limit(limit).offset(offset))
    return list(rows)


async def count_assignments(  # noqa: PLR0913 - one argument per filter
    session: AsyncSession,
    *,
    run_id: uuid.UUID | None = None,
    status: AssignmentStatus | None = None,
    result: AssignmentResult | None = None,
    assignment_type: AssignmentType | None = None,
    subject_id: uuid.UUID | None = None,
) -> int:
    """How many assignments `list_assignments` would page through with the same filters."""
    query = _assignments_matching(
        run_id=run_id,
        status=status,
        result=result,
        assignment_type=assignment_type,
        subject_id=subject_id,
    )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    return int(total or 0)


def _assignments_matching(
    *,
    run_id: uuid.UUID | None,
    status: AssignmentStatus | None,
    result: AssignmentResult | None,
    assignment_type: AssignmentType | None,
    subject_id: uuid.UUID | None,
) -> Select[tuple[Assignment]]:
    query = select(Assignment)
    if run_id is not None:
        query = query.where(Assignment.run_id == run_id)
    if status is not None:
        query = query.where(Assignment.status == status)
    if result is not None:
        query = query.where(Assignment.result == result)
    if assignment_type is not None:
        query = query.where(Assignment.type == assignment_type)
    if subject_id is not None:
        query = query.where(Assignment.subject_id == subject_id)
    return query


async def subjects_of(
    session: AsyncSession, assignments: Iterable[Assignment]
) -> dict[uuid.UUID, Place | Institution]:
    """The place or institution each assignment works on, by subject id, in two queries. A
    subject merged away or deleted since is left out."""
    ids = list({assignment.subject_id for assignment in assignments})
    if not ids:
        return {}
    found: dict[uuid.UUID, Place | Institution] = {}
    for place in await session.scalars(select(Place).where(Place.id.in_(ids))):
        found[place.id] = place
    for institution in await session.scalars(select(Institution).where(Institution.id.in_(ids))):
        found[institution.id] = institution
    return found


async def get_assignment(session: AsyncSession, assignment_id: uuid.UUID) -> Assignment:
    assignment = await session.get(Assignment, assignment_id)
    if assignment is None:
        raise NotFoundError("no such assignment")
    return assignment


async def assignment_cost(session: AsyncSession, assignment_id: uuid.UUID) -> Decimal:
    cost = await session.scalar(
        select(func.coalesce(func.sum(Usage.cost), 0)).where(Usage.assignment_id == assignment_id)
    )
    return Decimal(cost or 0)


async def events_of(session: AsyncSession, assignment_id: uuid.UUID) -> list[AgentRunEvent]:
    """Everything the agent saw, said and did on the assignment, in order."""
    rows = await session.scalars(
        select(AgentRunEvent)
        .where(AgentRunEvent.assignment_id == assignment_id)
        .order_by(AgentRunEvent.session, AgentRunEvent.position)
    )
    return list(rows)


def cancel(assignment: Assignment) -> None:
    lifecycle.cancel(assignment)


async def move_subject(session: AsyncSession, from_id: uuid.UUID, into_id: uuid.UUID) -> None:
    """When two entities merge, the duplicate's open assignments move to the survivor, except
    where the survivor has one of that type open already: those are cancelled, since one open
    assignment per subject and type is all the index allows."""
    taken = {assignment.type for assignment in await open_assignments(session, into_id)}
    for assignment in await open_assignments(session, from_id):
        if assignment.type in taken:
            lifecycle.cancel(assignment)
        else:
            assignment.subject_id = into_id
            taken.add(assignment.type)
    await session.flush()


# --- Usage ---


async def record_usage(  # noqa: PLR0913
    session: AsyncSession,
    *,
    assignment_id: uuid.UUID,
    kind: UsageKind,
    provider: str,
    purpose: str,
    units: int,
    cached_units: int = 0,
    output_units: int = 0,
    at: datetime | None = None,
) -> Usage:
    """One priced model or search call for the assignment. `provider` is the price list's key:
    the model's name for a model call, the engine's name for a search. `purpose` names what the
    call was for (the assignment type, "handoff", "summary"). For a model, `units` is every
    token the call used, `cached_units` the input served from the cache and `output_units` the
    output; for a search, `units` is the requests. Flushed, not committed."""
    cost = load_prices().cost(
        kind, provider, units=units, cached_units=cached_units, output_units=output_units
    )
    if cost is None:
        if provider not in _unpriced:
            _unpriced.add(provider)
            logger.warning("No price for %s %s: its usage is recorded at zero cost", kind, provider)
        cost = Decimal(0)
    usage = Usage(
        assignment_id=assignment_id,
        kind=kind,
        provider=provider,
        purpose=purpose,
        units=units,
        cached_units=cached_units,
        cost=cost,
    )
    if at is not None:
        usage.at = at
    session.add(usage)
    await session.flush()
    return usage
