"""The videos a session's browser recorded (spec section 8.2): stored through the storage port
under the assignment and session, then the recording directory is removed."""

import asyncio
import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from public_atlas.integrations.storage import ObjectStore

logger = logging.getLogger(__name__)

PREFIX = "videos"
MEDIA_TYPE = "video/webm"


def recording_dir() -> Path:
    """Where one session's browser writes its videos, one file per page."""
    return Path(tempfile.mkdtemp(prefix="public-atlas-video-"))


def video_key(assignment_id: uuid.UUID, session_no: int, index: int) -> str:
    return f"{PREFIX}/{assignment_id}/{session_no}/{index}.webm"


def assignment_prefix(assignment_id: uuid.UUID) -> str:
    """Every video of the assignment sits under this key prefix."""
    return f"{PREFIX}/{assignment_id}/"


def _recorded(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.webm")) if directory.is_dir() else []


async def store_videos(
    store: ObjectStore, directory: Path, *, assignment_id: uuid.UUID, session_no: int
) -> list[tuple[str, int]]:
    """Store every video in `directory` and remove it. The keys and sizes stored, in order."""
    stored: list[tuple[str, int]] = []
    try:
        files = await asyncio.to_thread(_recorded, directory)
        for path in files:
            data = await asyncio.to_thread(path.read_bytes)
            if not data:
                continue
            key = video_key(assignment_id, session_no, len(stored))
            await store.put(key, data, MEDIA_TYPE)
            stored.append((key, len(data)))
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    if stored:
        logger.info(
            "Stored %d video(s) of assignment %s session %d", len(stored), assignment_id, session_no
        )
    return stored
