"""`public-atlas-worker`: the process that runs queued jobs for one or more queues. The one
place, with asgi.py and the CLI, that reads the environment."""

import argparse
import asyncio
import logging
from collections.abc import Sequence

from public_atlas.config import Settings
from public_atlas.jobs import QUEUES, Queue
from public_atlas.resources import build_resources, worker_context
from public_atlas.shared import logs, telemetry

logger = logging.getLogger(__name__)


def parse_args(argv: Sequence[str] | None = None) -> list[Queue]:
    """The queues to serve, in `QUEUES` order; every one by default."""
    parser = argparse.ArgumentParser(prog="public-atlas-worker", description="Run queued jobs.")
    parser.add_argument(
        "--queues",
        metavar="NAME[,NAME...]",
        help=f"serve only these queues, out of {', '.join(QUEUES)} (default: every queue)",
    )
    args = parser.parse_args(argv)
    if args.queues is None:
        return list(QUEUES)
    names = [name.strip() for name in args.queues.split(",")]
    if unknown := [name for name in names if name not in QUEUES]:
        parser.error(f"unknown queue: {', '.join(unknown)} (expected {', '.join(QUEUES)})")
    return [name for name in QUEUES if name in names]


def concurrency_for(queues: list[Queue], configured: int) -> int:
    """One job at a time for a worker that parses: the parser is synchronous and one per
    process, and two conversions at once doubled what Docling holds, past the memory the
    worker has."""
    if "parse" in queues and configured != 1:
        logger.info("Serving parse: one job at a time, not %d", configured)
        return 1
    return configured


async def run(settings: Settings, queues: list[Queue]) -> None:
    logs.configure(settings.log_level, settings.log_format)
    if (handler := telemetry.configure(settings, service_name="public-atlas-worker")) is not None:
        logging.getLogger().addHandler(handler)
    async with build_resources(settings) as resources:
        if "parse" in queues:
            logger.info("Loading the parser's models")
            await asyncio.to_thread(resources.parser.warm_up)
        jobs = resources.jobs
        logger.info(
            "Worker ready: %d tasks registered, serving %s", len(jobs.tasks), ", ".join(queues)
        )
        await jobs.run_worker_async(
            queues=queues,
            concurrency=concurrency_for(queues, settings.jobs_concurrency),
            additional_context=worker_context(resources),
        )


def main(argv: Sequence[str] | None = None) -> None:
    queues = parse_args(argv)
    asyncio.run(run(Settings(), queues))


if __name__ == "__main__":
    main()
