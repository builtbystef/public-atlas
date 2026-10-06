"""`public-atlas`: the operator's command line. Each command builds the resources the way the
API's lifespan does and calls a module's service; the logic lives there, not here. The one
place, with asgi.py and the worker, that reads the environment."""

import argparse
import asyncio
import sys
import uuid
from collections.abc import Sequence
from dataclasses import fields

from public_atlas.config import Settings
from public_atlas.jobs import QUEUES, Queue
from public_atlas.jobs import worker as jobs_worker
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import AssignmentType, Run, RunMode
from public_atlas.modules.assignments.schemas import Progress, RunFilter
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import SEEDS
from public_atlas.modules.imports import service as imports
from public_atlas.modules.imports.files import ListFileError
from public_atlas.modules.imports.lists import LISTS
from public_atlas.resources import build_resources
from public_atlas.shared import logs
from public_atlas.shared.exceptions import AppError

# --- seed ---


async def seed(settings: Settings, name: str) -> countries.SeedReport:
    async with build_resources(settings) as resources, resources.session() as session:
        report = await countries.seed(session, SEEDS[name])
        await session.commit()
    return report


def run_seed(args: argparse.Namespace) -> None:
    report = asyncio.run(seed(Settings(), args.country))
    for item in fields(report):
        print(f"{item.name}: {getattr(report, item.name)} added")  # noqa: T201 - a command line
    print(f"{report.added} rows added")  # noqa: T201


# --- load-list ---


async def load_list(settings: Settings, name: str, *, apply: bool) -> imports.LoadReport:
    """A dry run rolls back, so the diff it prints is exactly what `--apply` writes."""
    async with build_resources(settings) as resources, resources.session() as session:
        report = await imports.load_list(
            session,
            resources.object_store,
            LISTS[name],
            cache_dir=settings.lists_cache_dir,
            apply=apply,
            parser=resources.parser,
        )
        if apply:
            await session.commit()
        else:
            await session.rollback()
    return report


def run_load_list(args: argparse.Namespace) -> None:
    try:
        report = asyncio.run(load_list(Settings(), args.name, apply=args.apply))
    except (ListFileError, AppError) as exc:
        sys.exit(f"load-list {args.name}: {exc}")
    print(report.render())  # noqa: T201


# --- run ---


def describe_run(run: Run, progress: Progress) -> str:
    """One run as the terminal shows it."""
    by_status = ", ".join(
        f"{count} {status.value}" for status, count in sorted(progress.by_status.items())
    )
    by_result = ", ".join(
        f"{count} {result.value}" for result, count in sorted(progress.by_result.items())
    )
    lines = [
        (
            f"Run {run.id}: {run.name!r} ({run.country_code}, {run.mode.value} mode, "
            f"{run.status.value})"
        ),
        f"  assignments: {by_status or 'none'}",
    ]
    if by_result:
        lines.append(f"  results: {by_result}")
    lines.append(f"  cost: ${progress.cost:.4f}")
    return "\n".join(lines)


async def create_run(settings: Settings, args: argparse.Namespace) -> str:
    wanted = RunFilter(
        administrative_levels=args.level or [],
        institution_types=args.type or [],
        assignment_types=[AssignmentType(name) for name in args.assignment_type or []],
        subject_ids=[uuid.UUID(value) for value in args.subject or []],
    )
    async with build_resources(settings) as resources, resources.session() as session:
        run = await assignments.create_run(
            session,
            resources.jobs,
            name=args.name,
            country_code=args.country,
            mode=RunMode(args.mode),
            filter=wanted,
            record_video=args.video,
        )
        progress = await assignments.progress(session, run)
        await session.commit()
    return describe_run(run, progress)


async def change_run(settings: Settings, run_id: uuid.UUID, action: str) -> str:
    async with build_resources(settings) as resources, resources.session() as session:
        run = await assignments.get_run(session, run_id)
        match action:
            case "pause":
                await assignments.pause_run(session, run)
            case "resume":
                await assignments.resume_run(session, run)
            case "stop":
                await assignments.stop_run(session, run)
        progress = await assignments.progress(session, run)
        await session.commit()
    return describe_run(run, progress)


async def release_run(settings: Settings, args: argparse.Namespace) -> str:
    async with build_resources(settings) as resources, resources.session() as session:
        run = await assignments.get_run(session, args.run_id)
        released = await assignments.release(
            session,
            resources.jobs,
            run,
            limit=args.limit,
            assignment_type=AssignmentType(args.type) if args.type else None,
            assignment_ids=[uuid.UUID(value) for value in args.assignment or []],
        )
        progress = await assignments.progress(session, run)
        await session.commit()
    lines = [f"Released {len(released)} assignment(s):"]
    lines.extend(f"  {row.type.value} {row.id} on {row.subject_id}" for row in released)
    lines.append(describe_run(run, progress))
    return "\n".join(lines)


async def show_run(settings: Settings, run_id: uuid.UUID) -> str:
    async with build_resources(settings) as resources, resources.session() as session:
        run = await assignments.get_run(session, run_id)
        return describe_run(run, await assignments.progress(session, run))


def run_run(args: argparse.Namespace) -> None:
    settings = Settings()
    try:
        match args.action:
            case "create":
                print(asyncio.run(create_run(settings, args)))  # noqa: T201
            case "pause" | "resume" | "stop":
                print(asyncio.run(change_run(settings, args.run_id, args.action)))  # noqa: T201
            case "release":
                print(asyncio.run(release_run(settings, args)))  # noqa: T201
            case "show":
                print(asyncio.run(show_run(settings, args.run_id)))  # noqa: T201
    except (AppError, ValueError) as exc:
        sys.exit(f"run {args.action}: {exc}")


# --- worker ---


def run_worker(args: argparse.Namespace) -> None:
    queues: list[Queue] = args.queues or list(QUEUES)
    asyncio.run(jobs_worker.run(Settings(), queues))


def _queues(value: str) -> list[Queue]:
    names = [name.strip() for name in value.split(",")]
    unknown = [name for name in names if name not in QUEUES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown queue: {', '.join(unknown)} (expected {', '.join(QUEUES)})"
        )
    return [name for name in QUEUES if name in names]


# --- The parser ---


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="public-atlas", description="Operate Public Atlas.")
    commands = parser.add_subparsers(dest="command", required=True)

    seed_command = commands.add_parser(
        "seed",
        help="fill the country tables and the anchors from a seed module; "
        "adds what is missing and never deletes",
    )
    seed_command.add_argument("country", choices=sorted(SEEDS), help="the seed to load")
    seed_command.set_defaults(run=run_seed)

    load_command = commands.add_parser(
        "load-list",
        help="load an official list: print what would be added, changed or removed, "
        "and write it with --apply",
    )
    load_command.add_argument("name", choices=sorted(LISTS), help="the list module to load")
    load_command.add_argument(
        "--apply", action="store_true", help="write the rows; without it nothing is written"
    )
    load_command.set_defaults(run=run_load_list)

    run_command = commands.add_parser(
        "run", help="start, pause, resume, stop or advance a run (spec section 7.1)"
    )
    actions = run_command.add_subparsers(dest="action", required=True)
    create = actions.add_parser(
        "create",
        help="a run with a filter and a mode, seeded with the work due for its subjects",
    )
    create.add_argument("name", help="what to call the run")
    create.add_argument("--country", default="CA", help="the country code (default: CA)")
    create.add_argument(
        "--mode",
        choices=[mode.value for mode in RunMode],
        default=RunMode.STEP.value,
        help="step: spawned assignments are held until released; auto: queued at once",
    )
    create.add_argument(
        "--level",
        action="append",
        metavar="LEVEL",
        help="an administrative level to work (repeatable)",
    )
    create.add_argument(
        "--type", action="append", metavar="TYPE", help="an institution type to work (repeatable)"
    )
    create.add_argument(
        "--assignment-type",
        action="append",
        metavar="NAME",
        choices=[kind.value for kind in AssignmentType],
        help="an assignment type to run (repeatable)",
    )
    create.add_argument(
        "--subject",
        action="append",
        metavar="ID",
        help="a place or institution id to start from (repeatable)",
    )
    create.add_argument(
        "--video", action="store_true", help="record a video of every page the browser opens"
    )
    for action, text in (
        ("pause", "stop starting the run's assignments; running ones finish their session"),
        ("resume", "start the run's assignments again"),
        ("stop", "cancel everything held or queued"),
        ("show", "the run's progress and cost"),
    ):
        changed = actions.add_parser(action, help=text)
        changed.add_argument("run_id", type=uuid.UUID, help="the run's id")
    release = actions.add_parser("release", help="queue held assignments of a step-mode run")
    release.add_argument("run_id", type=uuid.UUID, help="the run's id")
    release.add_argument("--limit", type=int, default=1, help="how many, oldest first (default: 1)")
    release.add_argument(
        "--type", choices=[kind.value for kind in AssignmentType], help="only this assignment type"
    )
    release.add_argument(
        "--assignment", action="append", metavar="ID", help="a held assignment's id (repeatable)"
    )
    run_command.set_defaults(run=run_run)

    worker = commands.add_parser("worker", help="run queued jobs, as public-atlas-worker does")
    worker.add_argument(
        "--queues",
        type=_queues,
        metavar="NAME[,NAME...]",
        help=f"serve only these queues, out of {', '.join(QUEUES)} (default: every queue)",
    )
    worker.set_defaults(run=run_worker)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = Settings()
    logs.configure(settings.log_level, settings.log_format)
    args.run(args)


if __name__ == "__main__":
    main()
