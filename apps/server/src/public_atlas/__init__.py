# Loaded first by every process (API, worker, scheduler, Alembic, tests), so the
# mapper registry is complete before any module configures a relationship.
from public_atlas.db import models as _models  # noqa: F401
