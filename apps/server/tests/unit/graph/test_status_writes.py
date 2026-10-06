"""Every path that changes an entity's status goes through `graph/status_changes.py`: a grep of
the source for direct status writes finds nothing else (phase 3's done-when)."""

import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "src" / "public_atlas"
THE_ONE_DOOR = SOURCE / "modules" / "graph" / "status_changes.py"
# `status=EntityStatus.X` in a constructor or an update, and `.status = EntityStatus.X` on a row.
STATUS_WRITE = re.compile(r"\bstatus\s*=\s*EntityStatus\.")


def test_only_status_changes_writes_an_entity_status():
    offenders = []
    for path in sorted(SOURCE.rglob("*.py")):
        if path == THE_ONE_DOOR:
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if STATUS_WRITE.search(line):
                offenders.append(f"{path.relative_to(SOURCE)}:{number}: {line.strip()}")
    assert offenders == []


def test_the_one_door_does_write_statuses():
    text = THE_ONE_DOOR.read_text()
    assert "entity.status = status" in text
    assert "entity.status = EntityStatus.NEEDS_REVIEW" in text
