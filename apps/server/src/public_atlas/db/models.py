"""Every model, imported once so the mapper registry is complete before any module configures
a relationship. Each module's `models.py` is listed here as it is added."""

from public_atlas.db.base import Base

__all__ = ["Base"]
