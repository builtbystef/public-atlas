import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_the_app_has_only_the_health_routes(client: TestClient):
    schema = client.get("/openapi.json").json()
    assert sorted(schema["paths"]) == ["/health", "/health/db", "/health/storage"]
    assert schema["info"]["title"] == "Public Atlas API"


def test_openapi_operation_ids(client: TestClient):
    schema = client.get("/openapi.json").json()
    assert schema["paths"]["/health"]["get"]["operationId"] == "health-read_health"
    assert schema["paths"]["/health/db"]["get"]["operationId"] == "health-read_health_db"


def test_real_app_answers_with_a_request_id(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert len(response.headers["x-request-id"]) == 16


def test_a_trailing_slash_is_not_redirected(client: TestClient):
    """A redirect would carry the API's own address to the browser; a 404 is honest."""
    response = client.get("/health/", follow_redirects=False)
    assert response.status_code == 404


def test_health_checks_are_not_in_the_access_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
):
    with caplog.at_level(logging.INFO, logger="public_atlas.access"):
        client.get("/health")
        client.get("/openapi.json")
    assert [r.getMessage()[:17] for r in caplog.records if r.name == "public_atlas.access"] == [
        "GET /openapi.json"
    ]
