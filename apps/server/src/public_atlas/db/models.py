"""Every model, imported once so the mapper registry is complete before any module configures
a relationship. Each module's `models.py` is listed here as it is added."""

from public_atlas.db.base import Base
from public_atlas.modules.agent import models as agent
from public_atlas.modules.assignments import models as assignments
from public_atlas.modules.countries import models as countries
from public_atlas.modules.evals import models as evals
from public_atlas.modules.evidence import models as evidence
from public_atlas.modules.graph import models as graph
from public_atlas.modules.imports import models as imports
from public_atlas.modules.review import models as review

__all__ = [
    "Base",
    "agent",
    "assignments",
    "countries",
    "evals",
    "evidence",
    "graph",
    "imports",
    "review",
]
