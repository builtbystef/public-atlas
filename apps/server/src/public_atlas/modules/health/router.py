import logging
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from public_atlas.dependencies import ObjectStoreDep, SessionDep
from public_atlas.shared import telemetry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class Health(BaseModel):
    status: str


async def probe(name: str, check: Callable[[], Awaitable[object]]) -> Health:
    with telemetry.quiet():
        try:
            await check()
        except Exception as exc:  # noqa: BLE001 - any failure means not ready
            logger.warning("Health check %s failed: %s", name, exc)
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"{name} is unavailable"
            ) from None
    return Health(status="ok")


@router.get("")
async def read_health() -> Health:
    """Liveness: the process is up."""
    return Health(status="ok")


@router.get("/db")
async def read_health_db(session: SessionDep) -> Health:
    """Readiness: the database answers."""
    return await probe("database", lambda: session.execute(text("SELECT 1")))


@router.get("/storage")
async def read_health_storage(store: ObjectStoreDep) -> Health:
    """Readiness: the object store answers and the bucket exists."""
    return await probe("storage", store.ping)
