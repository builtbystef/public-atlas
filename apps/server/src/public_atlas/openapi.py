import argparse
import json
import sys
from pathlib import Path

from public_atlas.config import Settings
from public_atlas.main import create_app


def schema_json() -> str:
    # The app is built, never started: no database or store is touched.
    return json.dumps(create_app(Settings()).openapi(), indent=2) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Export the OpenAPI schema without starting a server."
    )
    parser.add_argument("-o", "--output", type=Path, help="write here instead of stdout")
    args = parser.parse_args(argv)

    if args.output is None:
        sys.stdout.write(schema_json())
    else:
        args.output.write_text(schema_json())


if __name__ == "__main__":
    main()
