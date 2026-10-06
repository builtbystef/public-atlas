import logging
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from public_atlas.shared.logs import RequestIdFilter, request_id
from public_atlas.shared.middleware import INTERNAL_ERROR_DETAIL, RequestIdMiddleware

if TYPE_CHECKING:
    from collections.abc import Iterator

log = logging.getLogger("public_atlas.tests")

INTERNAL_DETAIL = "the database ate my homework"


@pytest.fixture
def failing_client() -> Iterator[TestClient]:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, str]:
        log.info("inside the request")
        return {"request_id": request_id.get()}

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError(INTERNAL_DETAIL)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_generates_a_request_id_and_sets_it_for_the_handler(failing_client: TestClient):
    response = failing_client.get("/ok")
    assert response.status_code == 200
    rid = response.headers["x-request-id"]
    assert len(rid) == 16
    assert response.json() == {"request_id": rid}


def test_echoes_a_usable_incoming_request_id(failing_client: TestClient):
    response = failing_client.get("/ok", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers["x-request-id"] == "trace-abc-123"


@pytest.mark.parametrize("bad", ["", "x" * 129, "line\nbreak", "ünïcode"])
def test_replaces_an_unusable_incoming_request_id(failing_client: TestClient, bad: str):
    response = failing_client.get("/ok", headers={b"X-Request-ID": bad.encode("latin-1")})
    assert response.headers["x-request-id"] != bad
    assert len(response.headers["x-request-id"]) == 16


def test_unhandled_error_becomes_a_500_with_the_request_id(
    failing_client: TestClient, caplog: pytest.LogCaptureFixture
):
    caplog.handler.addFilter(RequestIdFilter())
    with caplog.at_level(logging.ERROR, logger="public_atlas.shared.middleware"):
        response = failing_client.get("/boom", headers={"X-Request-ID": "report-42"})
    assert response.status_code == 500
    assert response.headers["x-request-id"] == "report-42"
    assert response.json() == {"detail": INTERNAL_ERROR_DETAIL, "request_id": "report-42"}
    assert INTERNAL_DETAIL not in response.text

    [record] = [r for r in caplog.records if r.name == "public_atlas.shared.middleware"]
    assert getattr(record, "request_id", None) == "report-42"
    assert record.exc_info is not None
    assert "Unhandled error on GET /boom" in record.getMessage()


def test_each_request_gets_an_access_log_line(
    failing_client: TestClient, caplog: pytest.LogCaptureFixture
):
    caplog.handler.addFilter(RequestIdFilter())
    with caplog.at_level(logging.INFO, logger="public_atlas.access"):
        failing_client.get("/ok", headers={"X-Request-ID": "report-7"})
        failing_client.get("/boom")
    lines = [r for r in caplog.records if r.name == "public_atlas.access"]
    assert [getattr(r, "request_id", None) for r in lines] == [
        "report-7",
        getattr(lines[1], "request_id", None),
    ]
    assert [r.getMessage().rsplit(" ", 1)[0] for r in lines] == ["GET /ok 200", "GET /boom 500"]
    assert all(r.getMessage().endswith("ms") for r in lines)


def test_log_lines_outside_a_request_read_dash(caplog: pytest.LogCaptureFixture):
    caplog.handler.addFilter(RequestIdFilter())
    log.warning("no request here")
    assert getattr(caplog.records[-1], "request_id", None) == "-"
