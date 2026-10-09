"""The evals module's door: an eval run end to end (spec section 10), scoring a database against
the dataset, recording the result, and reading eval runs back.

An eval run is a run with `is_eval`, recorded in the main database and mirrored, with the same
id, in the eval database where its assignments live. The runner prepares the eval database,
seeds the country through the real seed and loader with every assignment held, seeds each
chosen subject and queues its discovery, serves the queues in this process, then scores and
prices the graph and writes `eval_runs` and `eval_scores` to the main database, so history
survives a reset of the eval database.
"""

import logging
import uuid
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.config import Settings
from public_atlas.db.base import utcnow
from public_atlas.jobs import Queue
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.descriptors import DESCRIPTORS
from public_atlas.modules.assignments.models import AssignmentType, Run, RunMode, RunStatus
from public_atlas.modules.assignments.schemas import RunFilter
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.evals import dataset, harness, scorer
from public_atlas.modules.evals.dataset import PlaceList, SubjectFile
from public_atlas.modules.evals.harness import CostLine, Report, Seeded
from public_atlas.modules.evals.models import EvalRun, EvalScore
from public_atlas.modules.evals.schemas import (
    EvalRunDetail,
    EvalRunOutput,
    EvalScoreOutput,
    TypeSummary,
)
from public_atlas.modules.imports.lists.canada.ontario import places as ontario_places
from public_atlas.resources import Resources, build_resources
from public_atlas.shared.exceptions import NotFoundError

__all__ = [
    "DEFAULT_LISTS",
    "EvalReport",
    "ScoreReport",
    "default_queues",
    "list_eval_runs",
    "load_dataset",
    "read_eval_run",
    "record_results",
    "run_eval",
    "score_database",
]

logger = logging.getLogger(__name__)

# The official lists the eval database is loaded with: what the live database holds before any
# agent runs. Product data, so the dataset's places exist as the loader made them.
DEFAULT_LISTS: tuple[ModuleType, ...] = (ontario_places,)
COUNTRY_SEED: dict[str, Any] = canada.SEED
default_queues = harness.default_queues


# --- The dataset ---


def load_dataset(
    files: Sequence[Path], *, rules: countries.CountryRules | None = None
) -> tuple[dict[str, SubjectFile], dict[str, PlaceList]]:
    """The chosen files, by slug, after the whole dataset validated: a subject may refer to
    another file. Against the seed's rules unless `rules` is given."""
    rules = rules if rules is not None else countries.rules_from_seed(COUNTRY_SEED)
    errors = dataset.validate_files(dataset.all_files(), rules)
    if errors:
        raise ValueError("the eval dataset does not validate:\n" + "\n".join(errors))
    subjects, lists, errors = dataset.load_all(list(files))
    if errors:
        raise ValueError("\n".join(errors))
    return {p.stem: g for p, g in subjects.items()}, {p.stem: d for p, d in lists.items()}


# --- Scoring a database ---


@dataclass(slots=True)
class ScoreReport:
    database: str
    institutions: int
    cards: list[scorer.Scorecard]
    # Set when the scores were recorded against an eval run.
    eval_run_id: uuid.UUID | None = None

    def render(self, *, details: bool = False) -> str:
        head = f"scored: {self.database} ({self.institutions} institutions)"
        if self.eval_run_id is not None:
            head += f"; recorded on eval run {self.eval_run_id}"
        return head + "\n\n" + scorer.render(self.cards, details=details)

    def as_json(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "eval_run_id": str(self.eval_run_id) if self.eval_run_id else None,
            **scorer.as_json(self.cards),
        }


async def score_database(
    resources: Resources, files: Sequence[Path], *, eval_database: bool = False
) -> ScoreReport:
    """Score the main database, or the eval database an eval run left, against `files`. With
    the eval database, an eval run recorded for it and not yet finished gets the scores and
    the cost: how a run served by workers of its own (`--no-worker`) is completed."""
    subjects, lists = load_dataset(files)
    if not eval_database:
        async with resources.session() as session:
            graph, rules = await _graph_and_rules(session)
        return ScoreReport(
            database=str(resources.engine.url.database),
            institutions=len(graph.institutions),
            cards=scorer.score_files(graph, rules, subjects, lists),
        )
    settings = harness.eval_settings(resources.settings)
    await harness.require_main_migrated(resources)
    async with _eval_resources(resources, settings) as eval_res:
        async with eval_res.session() as session:
            graph, rules = await _graph_and_rules(session)
            run = await session.scalar(
                select(Run).where(Run.is_eval.is_(True)).order_by(Run.created_at.desc()).limit(1)
            )
        cards = scorer.score_files(graph, rules, subjects, lists)
        report = ScoreReport(
            database=settings.eval_database_name,
            institutions=len(graph.institutions),
            cards=cards,
        )
        if run is None:
            return report
        async with resources.session() as session:
            eval_run = await session.scalar(
                select(EvalRun).where(EvalRun.run_id == run.id, EvalRun.finished_at.is_(None))
            )
            if eval_run is None:
                return report
            async with eval_res.session() as eval_session:
                costs = await harness.cost_lines(eval_session, run.id)
            await record_results(session, eval_run, cards, costs)
            await session.commit()
            report.eval_run_id = eval_run.id
    return report


async def _graph_and_rules(session: AsyncSession) -> tuple[scorer.Graph, countries.CountryRules]:
    graph = await scorer.load_graph(session)
    rules = await countries.load_rules(session, str(COUNTRY_SEED["settings"]["country_code"]))
    return graph, rules


def _eval_resources(
    resources: Resources, settings: Settings
) -> AbstractAsyncContextManager[Resources]:
    """The eval database with the main resources' store, search engine, model and parser."""
    return build_resources(
        settings,
        object_store=resources.object_store,
        searcher=resources.searcher,
        models=resources.models,
        parser=resources.parser,
    )


# --- An eval run ---


@dataclass(slots=True)
class EvalReport:
    """What an eval run did: what it seeded, what it cost and how it scored."""

    eval_run_id: uuid.UUID
    run_id: uuid.UUID
    database: str
    seeded: list[Seeded] = field(default_factory=list)
    served: bool = False
    cards: list[scorer.Scorecard] = field(default_factory=list)
    costs: list[CostLine] = field(default_factory=list)
    cost_by_subject: dict[str, Decimal] = field(default_factory=dict)

    @property
    def cost(self) -> Decimal:
        return sum((line.cost for line in self.costs), Decimal(0))

    def render(self, *, details: bool = False) -> str:
        out = [f"eval run {self.eval_run_id} (run {self.run_id}) on {self.database}"]
        for item in self.seeded:
            queued = ", ".join(f"{a.type.value} {a.id}" for a in item.queued) or "nothing"
            out.append(f"seeded {item.slug}: queued {queued}")
        if not self.served:
            out.append(
                "Not serving the queues: start workers on the eval database, then score with "
                "`public-atlas eval score --evals`."
            )
            return "\n".join(out)
        out.extend(["", "== cost", harness.render_costs(self.costs, self.cost_by_subject), ""])
        out.append(scorer.render(self.cards, details=details))
        return "\n".join(out)

    def as_json(self) -> dict[str, Any]:
        return {
            "eval_run_id": str(self.eval_run_id),
            "run_id": str(self.run_id),
            "database": self.database,
            "served": self.served,
            "cost": str(self.cost),
            "cost_by_subject": {slug: str(cost) for slug, cost in self.cost_by_subject.items()},
            **scorer.as_json(self.cards),
        }


async def run_eval(  # noqa: PLR0913 - the steps of a run, in order
    resources: Resources,
    files: Sequence[Path],
    *,
    types: Sequence[AssignmentType] = tuple(AssignmentType),
    keep: bool = False,
    serve: bool = True,
    queues: Sequence[Queue] | None = None,
    lists: Iterable[ModuleType] = DEFAULT_LISTS,
    name: str | None = None,
    report: Report = logger.info,
    poll_seconds: float = harness.POLL_SECONDS,
) -> EvalReport:
    """One eval run over the dataset files `files` (spec section 10). `resources` is the main
    database's: the eval run and its scores are recorded there. `types` bounds the run: the
    assignment types it works, as its filter. `keep` leaves the eval database as it is instead
    of resetting it. With `serve` off the work is queued and left to workers of the eval
    database. `lists` are the official lists the country is loaded with."""
    subjects, place_lists = load_dataset(files)
    queues = tuple(queues) if queues is not None else harness.default_queues()
    settings = harness.eval_settings(resources.settings)
    harness.refuse_shared_database(resources.settings, settings.eval_database_name)
    # The run and its scores are rows in the main database; a column it lacks would fail the
    # insert at the end of the run, hours in.
    await harness.require_main_migrated(resources)
    if serve and resources.models is None:
        raise ValueError("no model is configured (PUBLIC_ATLAS_OPENAI_API_KEY); nothing can run")
    report(f"preparing the eval database {settings.eval_database_name}")
    await harness.prepare_database(resources.settings, keep=keep)

    run_filter = RunFilter(assignment_types=list(types))
    run_name = name or f"eval {', '.join(sorted([*subjects, *place_lists]))}"
    async with resources.session() as session:
        run = await assignments.create_run(
            session,
            resources.jobs,
            name=run_name,
            country_code=str(COUNTRY_SEED["settings"]["country_code"]),
            mode=RunMode.AUTO,
            filter=run_filter,
            is_eval=True,
            seed=False,
        )
        eval_run = EvalRun(
            run_id=run.id,
            dataset_version=dataset.version(),
            model=", ".join(dict.fromkeys(d.model.name for d in DESCRIPTORS.values())),
            settings={
                "subjects": sorted(subjects),
                "lists": sorted(place_lists),
                "assignment_types": [t.value for t in types],
                "queues": list(queues),
                "serve": serve,
                "keep": keep,
                "models": {
                    t.value: {
                        "name": d.model.name,
                        "reasoning_effort": d.model.reasoning_effort,
                    }
                    for t, d in DESCRIPTORS.items()
                },
                "official_lists": [module.__name__.rsplit(".", 1)[-1] for module in lists],
            },
            cost=Decimal(0),
            started_at=utcnow(),
        )
        session.add(eval_run)
        await session.commit()
    result = EvalReport(
        eval_run_id=eval_run.id, run_id=run.id, database=settings.eval_database_name
    )

    async with _eval_resources(resources, settings) as eval_res:
        async with eval_res.session() as session:
            rules = await harness.seed_country(
                session,
                eval_res.object_store,
                eval_res.settings,
                seed=COUNTRY_SEED,
                lists=lists,
                parser=eval_res.parser,
                report=report,
            )
            await session.commit()
        async with eval_res.session() as session:
            # The same run, where its assignments are: seeded held, so the province's own
            # discovery waits and only what the subjects queue runs.
            mirrored = await assignments.create_run(
                session,
                eval_res.jobs,
                name=run_name,
                country_code=rules.country_code,
                mode=RunMode.AUTO,
                filter=run_filter,
                is_eval=True,
                run_id=run.id,
                hold=True,
            )
            for slug, expected in sorted(subjects.items()):
                result.seeded.append(
                    await harness.seed_subject(
                        session, eval_res, mirrored, rules, expected, slug=slug
                    )
                )
            for slug, data in sorted(place_lists.items()):
                result.seeded.append(
                    await harness.seed_places(session, eval_res, mirrored, rules, data, slug=slug)
                )
            await session.commit()
        for item in result.seeded:
            queued = ", ".join(f"{a.type.value} {a.id}" for a in item.queued) or "nothing"
            report(f"seeded {item.slug}: queued {queued}")
        if not serve:
            return result
        if "parse" not in queues:
            report(
                "Not serving `parse`: files the agent opens stay unread unless a parse worker "
                f"runs: PUBLIC_ATLAS_DATABASE_URL={settings.database_url} "
                "public-atlas-worker --queues parse"
            )
        await harness.serve_until_drained(
            eval_res, queues=queues, report=report, poll_seconds=poll_seconds
        )
        result.served = True
        async with eval_res.session() as session:
            graph, rules = await _graph_and_rules(session)
            result.costs = await harness.cost_lines(session, run.id)
            result.cost_by_subject = await harness.cost_by_subject(
                session,
                run.id,
                {item.slug: [a.id for a in item.queued] for item in result.seeded},
            )
            mirrored = await assignments.get_run(session, run.id)
            if mirrored.status is not RunStatus.STOPPED:
                await assignments.stop_run(session, mirrored)
            await session.commit()
    result.cards = scorer.score_files(graph, rules, subjects, place_lists)
    async with resources.session() as session:
        eval_run = await session.get_one(EvalRun, eval_run.id)
        await record_results(session, eval_run, result.cards, result.costs)
        run = await assignments.get_run(session, run.id)
        if run.status is not RunStatus.STOPPED:
            await assignments.stop_run(session, run)
        await session.commit()
    return result


async def record_results(
    session: AsyncSession,
    eval_run: EvalRun,
    cards: Sequence[scorer.Scorecard],
    costs: Iterable[CostLine],
) -> list[EvalScore]:
    """The scores of `cards` as `eval_scores` rows, one per subject and assignment type that
    had anything to judge, and the gates, the cost and the finish on the eval run. Flushed,
    not committed."""
    rows: list[EvalScore] = []
    for card in cards:
        for measure, tally in card.tallies.items():
            if not tally.judged:
                continue
            rows.append(
                EvalScore(
                    eval_run_id=eval_run.id,
                    subject=card.slug,
                    assignment_type=measure,
                    recall=tally.recall,
                    precision=tally.precision,
                    hits=tally.hits_json(),
                    misses=tally.misses_json(),
                    false_positives=tally.false_positives_json(),
                )
            )
    session.add_all(rows)
    eval_run.gates = [result.as_json() for result in scorer.gates(cards)]
    eval_run.cost = sum((line.cost for line in costs), Decimal(0))
    eval_run.finished_at = utcnow()
    await session.flush()
    return rows


# --- Reading eval runs ---


async def list_eval_runs(
    session: AsyncSession, *, limit: int = 100, offset: int = 0
) -> tuple[list[EvalRunOutput], int]:
    """A page of eval runs, newest first, and how many there are."""
    rows = await session.scalars(
        select(EvalRun)
        .order_by(EvalRun.started_at.desc(), EvalRun.id.desc())
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(select(func.count()).select_from(EvalRun))
    outputs = [EvalRunOutput.model_validate(row) for row in rows]
    summaries = await _summaries(session, [output.id for output in outputs])
    for output in outputs:
        output.summary = summaries.get(output.id, {})
    return outputs, int(total or 0)


async def _summaries(
    session: AsyncSession, eval_run_ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, dict[AssignmentType, TypeSummary]]:
    """Each run's scores folded per assignment type, in one query for the batch."""
    if not eval_run_ids:
        return {}
    rows = await session.execute(
        select(
            EvalScore.eval_run_id,
            EvalScore.assignment_type,
            func.count(),
            func.avg(EvalScore.recall),
            func.avg(EvalScore.precision),
            func.sum(func.jsonb_array_length(EvalScore.hits)),
            func.sum(func.jsonb_array_length(EvalScore.misses)),
            func.sum(func.jsonb_array_length(EvalScore.false_positives)),
        )
        .where(EvalScore.eval_run_id.in_(list(eval_run_ids)))
        .group_by(EvalScore.eval_run_id, EvalScore.assignment_type)
    )
    found: dict[uuid.UUID, dict[AssignmentType, TypeSummary]] = {}
    for row in rows.tuples():
        eval_run_id, assignment_type, subjects, recall, precision, hits, misses, wrong = row
        found.setdefault(eval_run_id, {})[AssignmentType(assignment_type)] = TypeSummary(
            subjects=int(subjects),
            mean_recall=float(recall) if recall is not None else None,
            mean_precision=float(precision) if precision is not None else None,
            hits=int(hits) if hits is not None else None,
            misses=int(misses or 0),
            false_positives=int(wrong or 0),
        )
    return found


async def read_eval_run(session: AsyncSession, eval_run_id: uuid.UUID) -> EvalRunDetail:
    eval_run = await session.get(EvalRun, eval_run_id)
    if eval_run is None:
        raise NotFoundError("no such eval run")
    scores = await session.scalars(
        select(EvalScore)
        .where(EvalScore.eval_run_id == eval_run_id)
        .order_by(EvalScore.subject, EvalScore.assignment_type)
    )
    summaries = await _summaries(session, [eval_run_id])
    output = EvalRunOutput.model_validate(eval_run)
    output.summary = summaries.get(eval_run_id, {})
    previous_id = await session.scalar(
        select(EvalRun.id)
        .where(EvalRun.finished_at.is_not(None), EvalRun.started_at < eval_run.started_at)
        .order_by(EvalRun.started_at.desc(), EvalRun.id.desc())
        .limit(1)
    )
    return EvalRunDetail(
        **output.model_dump(),
        scores=[EvalScoreOutput.model_validate(row) for row in scores],
        previous_id=previous_id,
    )


def report_to(lines: list[str]) -> Callable[[str], None]:
    """A `report` that collects its lines, for tests."""
    return lines.append
