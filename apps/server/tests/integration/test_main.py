import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_the_app_has_the_health_countries_graph_review_runs_and_evals_routes(client: TestClient):
    schema = client.get("/openapi.json").json()
    assert sorted(schema["paths"]) == [
        "/assignments",
        "/assignments/{assignment_id}",
        "/assignments/{assignment_id}/events",
        "/assignments/{assignment_id}/findings",
        "/countries",
        "/countries/{country_code}",
        "/countries/{country_code}/administrative-levels/{name}",
        "/countries/{country_code}/institution-types/{institution_type}",
        "/countries/{country_code}/institution-types/{institution_type}/name-pattern-check",
        "/default-expected-source-types",
        "/eval-runs",
        "/eval-runs/{eval_run_id}",
        "/evidence/{evidence_id}/context",
        "/health",
        "/health/db",
        "/health/storage",
        "/institution-types",
        "/institution-types/{name}",
        "/institutions",
        "/institutions/{institution_id}",
        "/naming-rules/preview",
        "/places",
        "/places/{place_id}",
        "/review-items",
        "/review-items/kinds/approve",
        "/review-items/kinds/approve/preview",
        "/review-items/kinds/reject",
        "/review-items/kinds/reject/preview",
        "/review-items/{review_item_id}",
        "/review-items/{review_item_id}/approve",
        "/review-items/{review_item_id}/approve/preview",
        "/review-items/{review_item_id}/merge",
        "/review-items/{review_item_id}/merge/preview",
        "/review-items/{review_item_id}/reject",
        "/review-items/{review_item_id}/reject/preview",
        "/runs",
        "/runs/{run_id}",
        "/runs/{run_id}/pause",
        "/runs/{run_id}/release",
        "/runs/{run_id}/resume",
        "/runs/{run_id}/stop",
        "/source-types",
        "/source-types/{name}",
    ]
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
