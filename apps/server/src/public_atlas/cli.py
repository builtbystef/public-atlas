"""`public-atlas`: the operator's command line. Each command builds the resources the way the
API's lifespan does and calls a module's service; the logic lives there, not here. The one
place, with asgi.py and the worker, that reads the environment."""

import argparse
import asyncio
from collections.abc import Sequence
from dataclasses import fields

from public_atlas.config import Settings
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import SEEDS
from public_atlas.resources import build_resources
from public_atlas.shared import logs


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
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = Settings()
    logs.configure(settings.log_level, settings.log_format)
    args.run(args)


if __name__ == "__main__":
    main()
