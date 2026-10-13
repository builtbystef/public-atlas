"""The Public Atlas server.

Every process (API, worker, scheduler, Alembic, tests) imports this package first, so loading the
models here completes the mapper registry before any module configures a relationship."""

from public_atlas.db import models as _models  # noqa: F401
