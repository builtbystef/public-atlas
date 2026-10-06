import logging
from typing import TYPE_CHECKING

import pytest

from public_atlas.jobs.tasks import defer, task
from public_atlas.resources import Resources
from public_atlas.shared.logs import RequestIdFilter, request_id

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from tests.integration.conftest import Database, InlineConnector

log = logging.getLogger("public_atlas.tests")

seen: list[str] = []


@task("tests.log_request_id")
async def log_request_id(_res: Resources) -> None:
    log.info("inside the job")
    seen.append(request_id.get())


async def run_job(db: Database, queue: InlineConnector) -> str:
    assert queue.resources is not None
    async with db.session() as session:
        await defer(queue.resources.jobs, session, log_request_id)
    return seen.pop()


def test_a_job_runs_under_the_request_id_that_queued_it(
    client: TestClient, db: Database, queue: InlineConnector, caplog: pytest.LogCaptureFixture
):
    """Jobs run as soon as they are deferred (see conftest), so the queueing context is a plain
    `request_id.set`, as the API's middleware does it."""

    async def queue_inside_request() -> str:
        token = request_id.set("report-9")
        try:
            return await run_job(db, queue)
        finally:
            request_id.reset(token)

    caplog.handler.addFilter(RequestIdFilter())
    assert client.portal is not None
    with caplog.at_level(logging.INFO, logger="public_atlas.tests"):
        assert client.portal.call(queue_inside_request) == "report-9"
    (inside,) = [r for r in caplog.records if r.getMessage() == "inside the job"]
    assert getattr(inside, "request_id", None) == "report-9"


def test_a_job_queued_outside_a_request_gets_its_own_id(
    client: TestClient, db: Database, queue: InlineConnector
):
    assert client.portal is not None
    rid = client.portal.call(run_job, db, queue)
    assert rid != "-"
    assert len(rid) == 16
    assert client.portal.call(run_job, db, queue) != rid
    assert request_id.get() == "-"
