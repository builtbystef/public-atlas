"""The eval harness (spec section 10): the eval database, a database of its own on the configured
server, reset and migrated; the country seeded through the real seed and loader with every
assignment held; each subject's place, government, trusted domains and homepage seeded as the
loader would have made them, and its discovery queued; the queues served in this process with a
parse worker in a process of its own; and the cost of what ran. The seed is only what the loader
would have made had the subject been an anchor; the agent finds the rest."""

import asyncio
import importlib.util
import logging
import os
import sys
import uuid
from collections.abc import Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from decimal import Decimal
from types import ModuleType
from typing import Any

from alembic import command
from pydantic import PostgresDsn
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from public_atlas.config import Settings
from public_atlas.db import migrations
from public_atlas.integrations.parse import Parser
from public_atlas.integrations.storage import ObjectStore
from public_atlas.jobs import QUEUES, Queue
from public_atlas.jobs.worker import concurrency_for
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    Run,
    Usage,
)
from public_atlas.modules.assignments.service import Spawn
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evals.dataset import Municipality, Name, PlaceList, SubjectFile
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph import status_changes
from public_atlas.modules.graph.models import (
    DomainKind,
    EnteredBy,
    EntityStatus,
    Homepage,
    Identifier,
    IdentifierScheme,
    Institution,
    Place,
)
from public_atlas.modules.imports import service as imports
from public_atlas.resources import Resources, worker_context

logger = logging.getLogger(__name__)

# apps/server, where pyproject.toml holds Alembic's settings.
# Everything the harness seeds was verified by hand: the dataset is the labeller's word.
BY = EnteredBy.MANUAL

POLL_SECONDS = 5.0
# Two empty looks in a row, not one: a job that just finished may have deferred another that
# the first look does not see yet.
EMPTY_POLLS_TO_STOP = 2
# A progress line about once a minute.
PROGRESS_EVERY_POLLS = 12
# A parse worker that exits sooner than this after starting did not start; this many such exits
# in a row stop the run.
PARSE_START_SECONDS = 60.0
PARSE_FAILED_STARTS = 3
# How long a parse worker gets to finish its file when the run stops, before it is killed.
PARSE_STOP_SECONDS = 30.0

type Report = Callable[[str], None]


# --- The eval database ---


def eval_settings(settings: Settings) -> Settings:
    """The same settings on the eval database (spec section 10)."""
    url = make_url(str(settings.database_url)).set(database=settings.eval_database_name)
    return settings.model_copy(
        update={"database_url": PostgresDsn(url.render_as_string(hide_password=False))}
    )


def refuse_shared_database(settings: Settings, eval_name: str) -> None:
    """An eval run resets its database; it must never be the main one."""
    main = make_url(str(settings.database_url)).database
    if main == eval_name:
        raise ValueError(f"the eval database {eval_name!r} is the main database; name another")


def _create_database(settings: Settings, name: str) -> bool:
    """Create the eval database on the configured server if it is not there. Whether it was
    created. Synchronous: CREATE DATABASE cannot run inside a transaction, hence autocommit."""
    engine = create_engine(
        make_url(str(settings.database_url)).set(drivername="postgresql+psycopg"),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
            ).scalar()
            if exists:
                return False
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            return True
    finally:
        engine.dispose()


async def ensure_database(settings: Settings) -> bool:
    """The eval database exists on the configured server. Whether it was created now."""
    refuse_shared_database(settings, settings.eval_database_name)
    return await asyncio.to_thread(_create_database, settings, settings.eval_database_name)


def _upgrade(connection: Connection) -> None:
    config = migrations.alembic_config()
    # Alembic's env.py migrates on a connection passed this way instead of opening its own.
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def require_main_migrated(resources: Resources) -> None:
    """The main database is at the latest migration. An eval run and its scores are rows there;
    checked before a run starts, not at the insert hours later. On the resources' own session,
    so a test's transaction counts."""
    async with resources.session() as session:
        connection = await session.connection()
        await connection.run_sync(migrations.check_head)


async def migrate(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)


async def reset_schema(engine: AsyncEngine) -> None:
    """Drop everything and migrate from nothing: the eval graph is built fresh each run."""
    async with engine.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await migrate(engine)


async def prepare_database(settings: Settings, *, keep: bool) -> None:
    """The eval database, created if missing, reset unless `keep`, and migrated to head."""
    await ensure_database(settings)
    engine = create_async_engine(str(eval_settings(settings).database_url), poolclass=NullPool)
    try:
        if keep:
            await migrate(engine)
        else:
            await reset_schema(engine)
    finally:
        await engine.dispose()


# --- Seeding ---


async def seed_country(  # noqa: PLR0913 - what a load needs
    session: AsyncSession,
    store: ObjectStore,
    settings: Settings,
    *,
    seed: dict[str, Any],
    lists: Iterable[ModuleType],
    parser: Parser | None,
    report: Report = logger.info,
) -> CountryRules:
    """The country as the real seed and loader make it: its tables, platforms and anchor, then
    each official list's places with their governments and candidate homepages. Flushed, not
    committed."""
    seeded = await countries.seed(session, seed)
    report(f"seeded the country: {seeded.added} rows added")
    for module in lists:
        loaded = await imports.load_list(
            session,
            store,
            module,
            cache_dir=settings.lists_cache_dir,
            apply=True,
            parser=parser,
        )
        report(
            f"loaded {loaded.list_name}: {loaded.entries} entries, "
            f"{loaded.count('add', 'place')} places added"
        )
    return await countries.load_rules(session, str(seed["settings"]["country_code"]))


@dataclass(slots=True)
class Seeded:
    slug: str
    place_id: uuid.UUID
    # The government or the ministry; a places file has none.
    institution_id: uuid.UUID | None
    # The assignments the subject's work starts from, queued.
    queued: list[Assignment] = field(default_factory=list)


async def seed_subject(  # noqa: PLR0913
    session: AsyncSession,
    resources: Resources,
    run: Run,
    rules: CountryRules,
    expected: SubjectFile,
    *,
    slug: str,
) -> Seeded:
    """Seed one subject file into `run`'s database and queue its discovery: `find_sources` for
    the government or ministry and `find_institutions` for its place, as a verified homepage
    would have spawned them (spec section 7.3), within the run's filter. Flushed, not
    committed. Seeding again changes nothing."""
    subject = expected.subject
    government = expected.institution(subject.institution)
    if government is None:
        raise ValueError(f"{slug}: {subject.institution} is not among the institutions")
    if subject.kind == "place":
        place = await _find_or_create_place(
            session,
            rules,
            level=subject.level,
            name=subject.name,
            parent_name=subject.parent,
            code=subject.official_code,
        )
        institution = await _government_of(session, rules, place, government.names)
    else:
        # A ministry's place is the province itself, which the seed loaded.
        places = await graph.find_places(
            session, rules.country_code, subject.place, rules=rules, levels=[subject.level]
        )
        if not places:
            raise ValueError(f"{slug}: {subject.place} ({subject.level}) is not loaded")
        place = places[0]
        if subject.government_homepage is not None and place.government_institution_id:
            head = await session.get_one(Institution, place.government_institution_id)
            await _verified_homepage(session, head, subject.government_homepage)
        institution = await _find_or_create_institution(
            session, rules, place, government.type, government.names
        )
    for domain_name in expected.trusted_at_start:
        await _trusted_domain(session, domain_name)
    if government.homepage:
        await _verified_homepage(session, institution, government.homepage)
    await _cancel_stale_searches(session, institution)
    queued = await assignments.queue_spawns(
        session,
        resources.jobs,
        run,
        [
            Spawn(AssignmentType.FIND_SOURCES, institution.id),
            Spawn(AssignmentType.FIND_INSTITUTIONS, place.id),
        ],
    )
    await session.flush()
    return Seeded(slug=slug, place_id=place.id, institution_id=institution.id, queued=queued)


async def seed_places(  # noqa: PLR0913
    session: AsyncSession,
    resources: Resources,
    run: Run,
    rules: CountryRules,
    data: PlaceList,
    *,
    slug: str,
) -> Seeded:
    """The loader made every listed municipality from the register already, so only each
    listed government's `find_homepage` is queued: the held one released, or a new one."""
    roots = await graph.find_places(session, rules.country_code, data.place, rules=rules)
    if not roots:
        raise ValueError(f"{slug}: {data.place} is not loaded; is it an anchor?")
    seeded = Seeded(slug=slug, place_id=roots[0].id, institution_id=None)
    for municipality in data.municipalities:
        place = await _listed_place(session, rules, municipality, roots[0])
        if place is None or place.government_institution_id is None:
            raise ValueError(f"{slug}: {municipality.name} is not loaded with a government")
        government = await session.get_one(Institution, place.government_institution_id)
        if government.homepage_id is None:
            seeded.queued.extend(
                await assignments.queue_spawns(
                    session,
                    resources.jobs,
                    run,
                    [Spawn(AssignmentType.FIND_HOMEPAGE, government.id)],
                )
            )
    await session.flush()
    return seeded


async def _listed_place(
    session: AsyncSession, rules: CountryRules, municipality: Municipality, root: Place
) -> Place | None:
    """The place a list names: by its code when it has one, else by name at its level under
    its parent."""
    if municipality.official_code is not None:
        held = await session.scalar(
            select(Identifier).where(
                Identifier.scheme == IdentifierScheme.STATCAN_SGC,
                Identifier.value == municipality.official_code,
                Identifier.place_id.is_not(None),
            )
        )
        if held is not None and held.place_id is not None:
            return await session.get(Place, held.place_id)
    parent = root
    if municipality.parent != root.name:
        parents = await graph.find_places(
            session,
            rules.country_code,
            municipality.parent,
            rules=rules,
            levels=rules.levels_above(municipality.level),
        )
        if parents:
            parent = parents[0]
    found = await graph.find_places(
        session,
        rules.country_code,
        municipality.name,
        rules=rules,
        levels=[municipality.level],
        parent=parent,
    )
    return found[0] if found else None


async def _find_or_create_place(  # noqa: PLR0913
    session: AsyncSession,
    rules: CountryRules,
    *,
    level: str,
    name: str,
    parent_name: str | None,
    code: str | None,
) -> Place:
    """The place at `level` going by `name`, verified; created under the parent named (itself
    created at the level just above when it is not loaded) when the loader did not make it."""
    found = await graph.find_places(session, rules.country_code, name, rules=rules, levels=[level])
    parent = None
    if parent_name is not None:
        above = rules.levels_above(level)
        parents = await graph.find_places(
            session, rules.country_code, parent_name, rules=rules, levels=above
        )
        if parents:
            parent = parents[0]
    place = await _pick_place(session, rules, found, name, parent)
    if place is not None:
        if place.status is not EntityStatus.VERIFIED:
            await status_changes.verify_place(session, place, entered_by=BY)
        return place
    if parent_name is not None and parent is None:
        above = rules.levels_above(level)
        if above:
            parent = await _find_or_create_place(
                session,
                rules,
                level=above[-1],
                name=parent_name,
                parent_name=await _any_place_name_at(session, rules, above[-1]),
                code=None,
            )
            await _government_of(session, rules, parent, [Name(text=parent_name, lang="en")])
    place = await graph.create_place(
        session,
        name=name,
        country_code=rules.country_code,
        administrative_level=level,
        parent=parent,
        entered_by=BY,
    )
    await status_changes.verify_place(session, place, entered_by=BY)
    if code is not None:
        session.add(Identifier(place_id=place.id, scheme=IdentifierScheme.STATCAN_SGC, value=code))
        await session.flush()
    return place


async def _pick_place(
    session: AsyncSession,
    rules: CountryRules,
    found: Sequence[Place],
    name: str,
    parent: Place | None,
) -> Place | None:
    """Of the places going by `name`, one whose names carry no designator of another kind (the
    City of Hamilton is not the Township of Hamilton), the one under `parent` first."""
    aliases = await graph.aliases_of(session, found)
    kept = [
        place
        for place in found
        if not rules.naming.designators_differ([name], [place.name, *aliases[place.id]])
    ]
    if parent is not None:
        under = [place for place in kept if place.parent_place_id == parent.id]
        if under:
            return under[0]
    return kept[0] if kept else None


async def _any_place_name_at(session: AsyncSession, rules: CountryRules, level: str) -> str | None:
    """The name of a place at the level above `level`, which in an eval database is the anchor:
    where a created parent hangs."""
    above = rules.levels_above(level)
    if not above:
        return None
    row = await session.scalar(
        select(Place)
        .where(Place.country_code == rules.country_code, Place.administrative_level == above[-1])
        .order_by(Place.id)
        .limit(1)
    )
    return row.name if row is not None else None


async def _government_of(
    session: AsyncSession, rules: CountryRules, place: Place, names: Sequence[Name]
) -> Institution:
    """The place's government, created verified when it has none, with every name the dataset
    gives it."""
    if place.government_institution_id is not None:
        government = await session.get_one(Institution, place.government_institution_id)
        await _add_names(session, government, names)
        return government
    government = await _find_or_create_institution(
        session, rules, place, rules.government_type(place.administrative_level), names
    )
    place.government_institution_id = government.id
    await session.flush()
    return government


async def _find_or_create_institution(
    session: AsyncSession,
    rules: CountryRules,
    place: Place,
    institution_type: str,
    names: Sequence[Name],
) -> Institution:
    for name in names:
        found = await graph.find_institutions(session, place, name.text, rules=rules)
        if found:
            institution = found[0]
            if institution.status is not EntityStatus.VERIFIED:
                await status_changes.verify_institution(session, institution, entered_by=BY)
            await _add_names(session, institution, names)
            return institution
    first = names[0]
    institution = await graph.create_institution(
        session,
        name=first.text,
        institution_type=institution_type,
        place=place,
        entered_by=BY,
        language=first.lang,
    )
    await status_changes.verify_institution(session, institution, entered_by=BY)
    await _add_names(session, institution, names)
    return institution


async def _add_names(session: AsyncSession, owner: Institution, names: Sequence[Name]) -> None:
    for name in names:
        await graph.add_alias(
            session,
            owner,
            name.text,
            language=name.lang,
            entered_by=BY,
            is_acronym=name.is_acronym,
        )


async def _trusted_domain(session: AsyncSession, name: str) -> None:
    """The domain trusted, as an anchor's is. A platform stays a platform."""
    domain, _ = await graph.ensure_domain(session, name, entered_by=BY)
    if domain.domain_kind is DomainKind.OFFICIAL and not graph.is_trusted(domain):
        await status_changes.verify_domain(session, domain, entered_by=BY)


async def _verified_homepage(session: AsyncSession, institution: Institution, url: str) -> None:
    """The institution's homepage, verified by hand: its domain is trusted (the dataset says the
    page is the body's own), the claim is made and verified through the same door the rules
    use, which supersedes the loader's candidate. What the verification would spawn is the
    subject's own discovery, which the caller queues."""
    normalized = graph.normalize_url(url)
    await _trusted_domain(session, graph.host_of(normalized))
    domain, _ = await graph.ensure_domain(session, graph.host_of(normalized), entered_by=BY)
    webpage = await graph.ensure_webpage(session, normalized, domain=domain)
    homepage = await session.scalar(
        select(Homepage).where(
            Homepage.institution_id == institution.id, Homepage.webpage_id == webpage.id
        )
    )
    if homepage is None:
        homepage = await graph.create_homepage(session, institution, webpage, entered_by=BY)
    if institution.homepage_id != homepage.id:
        await status_changes.verify_homepage(session, homepage, entered_by=BY)


async def _cancel_stale_searches(session: AsyncSession, institution: Institution) -> None:
    """A `find_homepage` the run seeded held for a government whose homepage the dataset gives
    has nothing left to find."""
    for assignment in await assignments.open_assignments(session, institution.id):
        if (
            assignment.type is AssignmentType.FIND_HOMEPAGE
            and assignment.status is AssignmentStatus.HELD
        ):
            assignments.cancel(assignment)
    await session.flush()


# --- Serving the queues ---


def default_queues() -> tuple[Queue, ...]:
    """The agent's queue and the platform's, plus `parse` when Docling is installed; without it
    the files the agent opens stay unread."""
    queues: tuple[Queue, ...] = ("assignment", "default")
    return (*queues, "parse") if importlib.util.find_spec("docling") else queues


async def serve_until_drained(
    resources: Resources,
    *,
    queues: Sequence[Queue],
    report: Report = logger.info,
    poll_seconds: float = POLL_SECONDS,
) -> None:
    """Serve `queues` until nothing is queued or running on them. `parse` goes to a process of
    its own (`parse_worker`); the rest run here, on `resources`."""
    served = [queue for queue in QUEUES if queue in queues]
    here: list[Queue] = [queue for queue in served if queue != "parse"]
    workers: list[asyncio.Task[None]] = []
    if "parse" in served:
        workers.append(asyncio.create_task(parse_worker(resources.settings, report)))
    if here:
        workers.append(
            asyncio.create_task(
                resources.jobs.run_worker_async(
                    queues=here,
                    concurrency=concurrency_for(here, resources.settings.jobs_concurrency),
                    additional_context=worker_context(resources),
                    install_signal_handlers=False,
                )
            )
        )
    try:
        await _wait_for_drain(resources, served, workers, report, poll_seconds)
    finally:
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker


async def parse_worker(settings: Settings, report: Report) -> None:
    """The parse worker in a process of its own on the eval database, started again whenever it
    stops, until cancelled."""
    # Not in this process: a parse worker runs one job at a time, which would make every agent
    # session here wait its turn, and it retires its own process once its memory has grown
    # (`parse_retire_rss_mb`), which here would end the run.
    url = make_url(str(settings.database_url)).render_as_string(hide_password=False)
    # Warnings only: Docling logs every page, which would bury the run's report.
    env = {**os.environ, "PUBLIC_ATLAS_DATABASE_URL": url, "PUBLIC_ATLAS_LOG_LEVEL": "WARNING"}
    command_line = [sys.executable, "-m", "public_atlas.jobs.worker", "--queues", "parse"]
    loop = asyncio.get_running_loop()
    failed_starts = 0
    while True:
        started = loop.time()
        process = await asyncio.create_subprocess_exec(*command_line, env=env)
        try:
            code = await process.wait()
        except asyncio.CancelledError:
            await _stop(process)
            raise
        failed_starts = failed_starts + 1 if loop.time() - started < PARSE_START_SECONDS else 0
        if failed_starts >= PARSE_FAILED_STARTS:
            raise RuntimeError(
                f"the parse worker failed to start {failed_starts} times (exit {code})"
            )
        report(f"The parse worker stopped (exit {code}); starting another.")


async def _stop(process: asyncio.subprocess.Process) -> None:
    """Let the worker finish its file, then make sure it is gone."""
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), PARSE_STOP_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()


async def _wait_for_drain(
    resources: Resources,
    queues: list[Queue],
    workers: list[asyncio.Task[None]],
    report: Report,
    poll_seconds: float,
) -> None:
    empty = 0
    polls = 0
    while True:
        if done := [worker for worker in workers if worker.done()]:
            for worker in done:
                worker.result()
            return
        pending = await pending_jobs(resources, queues)
        empty = empty + 1 if pending == 0 else 0
        if empty >= EMPTY_POLLS_TO_STOP:
            return
        polls += 1
        if polls % PROGRESS_EVERY_POLLS == 1:
            report(await progress(resources))
        await asyncio.sleep(poll_seconds)


async def pending_jobs(resources: Resources, queues: Sequence[Queue]) -> int:
    async with resources.session() as session:
        count = await session.scalar(
            text(
                "SELECT count(*) FROM procrastinate_jobs "
                "WHERE status IN ('todo', 'doing') AND queue_name = ANY(:queues)"
            ),
            {"queues": list(queues)},
        )
    return int(count or 0)


async def progress(resources: Resources) -> str:
    """One line: assignments by status, then the types still queued or running."""
    async with resources.session() as session:
        rows = await session.execute(
            select(Assignment.type, Assignment.status, func.count())
            .group_by(Assignment.type, Assignment.status)
            .order_by(Assignment.type, Assignment.status)
        )
    by_status: dict[str, int] = {}
    open_types: dict[str, int] = {}
    for type_, status, count in rows.tuples():
        by_status[status] = by_status.get(status, 0) + count
        if status in (AssignmentStatus.QUEUED, AssignmentStatus.RUNNING):
            open_types[type_] = open_types.get(type_, 0) + count
    statuses = ", ".join(f"{status} {count}" for status, count in sorted(by_status.items()))
    open_ = ", ".join(f"{type_} {count}" for type_, count in sorted(open_types.items()))
    return f"assignments: {statuses or 'none'}; open: {open_ or 'none'}"


# --- Cost ---


@dataclass(frozen=True, slots=True)
class CostLine:
    """What one purpose (an assignment type, a handoff) spent on one provider."""

    purpose: str
    provider: str
    calls: int
    units: int
    cached_units: int
    cost: Decimal


async def cost_lines(session: AsyncSession, run_id: uuid.UUID) -> list[CostLine]:
    """The run's usage by purpose and provider, priced as it was recorded."""
    rows = await session.execute(
        select(
            Usage.purpose,
            Usage.provider,
            func.count(),
            func.sum(Usage.units),
            func.sum(Usage.cached_units),
            func.sum(Usage.cost),
        )
        .join(Assignment, Assignment.id == Usage.assignment_id)
        .where(Assignment.run_id == run_id)
        .group_by(Usage.purpose, Usage.provider)
        .order_by(Usage.purpose, Usage.provider)
    )
    return [
        CostLine(
            purpose=purpose,
            provider=provider,
            calls=int(calls),
            units=int(units or 0),
            cached_units=int(cached or 0),
            cost=Decimal(cost or 0),
        )
        for purpose, provider, calls, units, cached, cost in rows.tuples()
    ]


async def cost_by_subject(
    session: AsyncSession, run_id: uuid.UUID, roots: dict[str, Sequence[uuid.UUID]]
) -> dict[str, Decimal]:
    """What each subject's work cost: the assignments it started with and everything spawned
    from them, by `parent_assignment_id`."""
    parents = dict(
        (
            await session.execute(
                select(Assignment.id, Assignment.parent_assignment_id).where(
                    Assignment.run_id == run_id
                )
            )
        )
        .tuples()
        .all()
    )
    children: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for child, parent in parents.items():
        children.setdefault(parent, []).append(child)
    spent = dict(
        (
            await session.execute(
                select(Usage.assignment_id, func.sum(Usage.cost))
                .join(Assignment, Assignment.id == Usage.assignment_id)
                .where(Assignment.run_id == run_id)
                .group_by(Usage.assignment_id)
            )
        )
        .tuples()
        .all()
    )
    costs: dict[str, Decimal] = {}
    for slug, started in roots.items():
        total = Decimal(0)
        queue = list(started)
        seen: set[uuid.UUID] = set()
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            total += Decimal(spent.get(current) or 0)
            queue.extend(children.get(current, ()))
        costs[slug] = total
    return costs


def render_costs(lines: Iterable[CostLine], by_subject: dict[str, Decimal]) -> str:
    header = (
        f"   {'purpose':20} {'provider':16} {'calls':>6} {'units':>12} {'cached':>12} {'cost':>9}"
    )
    out = [header]
    total = Decimal(0)
    for line in lines:
        total += line.cost
        out.append(
            f"   {line.purpose:20} {line.provider:16} {line.calls:6} {line.units:12} "
            f"{line.cached_units:12} ${line.cost:8.4f}"
        )
    out.append(f"   total ${total:.4f}")
    out.extend(f"   {slug:38} ${cost:8.4f}" for slug, cost in sorted(by_subject.items()))
    return "\n".join(out)
