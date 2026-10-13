import json
from collections.abc import Iterator, Sequence

from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from public_atlas.config import Settings
from public_atlas.main import create_app
from public_atlas.openapi import main, schema_json


def api_paths(routes: Sequence[BaseRoute]) -> Iterator[str]:
    """The paths of the API routes, down through the routers the app includes."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route.path
        included = getattr(route, "original_router", None)
        if included is not None:
            yield from api_paths(included.routes)


def test_the_schema_describes_every_route_of_the_app_and_no_other():
    schema = json.loads(schema_json())
    assert schema["openapi"].startswith("3.1")
    routes = set(api_paths(create_app(Settings()).routes))
    assert set(schema["paths"]) == routes
    assert {"/health", "/health/db", "/health/storage", "/runs"} <= routes


def test_main_writes_file(tmp_path):
    out = tmp_path / "openapi.json"
    main(["-o", str(out)])
    assert out.read_text() == schema_json()


def test_main_writes_stdout(capsys):
    main([])
    assert capsys.readouterr().out == schema_json()
