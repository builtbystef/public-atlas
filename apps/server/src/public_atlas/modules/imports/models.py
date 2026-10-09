"""The loader's record of the files it read (spec section 5.2)."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base, UUIDPrimaryKey
from public_atlas.db.checked_strings import checked_string


class Retrieval(StrEnum):
    """How a list's file is obtained: downloaded from its URL with the hash pinned, or
    collected by a person following the module's instructions and dropped in the cache."""

    FETCHED = "fetched"
    MANUAL = "manual"


class OfficialList(UUIDPrimaryKey, Base):
    """One row per source file a list module loaded, so an identifier or a metric can say which
    list it came from. A file whose contents changed is a new row."""

    __tablename__ = "official_lists"

    # `<list>/<file>`: the list's name (its path under `lists/`, `canada/ontario/places`) and
    # the file's name in the module.
    name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(Text)
    # Copied from the file: which rows rest on a hand-collected file.
    retrieval: Mapped[Retrieval] = checked_string(Retrieval, "retrieval")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The stored file and its text, so a quote can be checked against it.
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("snapshots.id"))

    __table_args__ = (UniqueConstraint("name", "sha256"),)
