from typing import TYPE_CHECKING

from public_atlas.dependencies import get_object_store
from public_atlas.integrations.storage.memory import MemoryObjectStore

if TYPE_CHECKING:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient


def test_liveness_db_and_storage_answer(client: TestClient):
    for path in ("/health", "/health/db", "/health/storage"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.json() == {"status": "ok"}


class DownStore(MemoryObjectStore):
    async def ping(self) -> None:
        msg = "no bucket"
        raise RuntimeError(msg)


def test_a_dead_store_is_a_503(app: FastAPI, client: TestClient):
    app.dependency_overrides[get_object_store] = DownStore
    response = client.get("/health/storage")
    assert response.status_code == 503
    assert response.json()["detail"] == "storage is unavailable"
