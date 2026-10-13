"""Every path that changes an entity's status goes through `graph/status_changes.py`: a grep of
the source for status writes finds nothing else (phase 3's done-when). The statuses of an
assignment, a run and a review item are other lifecycles with doors of their own, listed by the
line that writes them so a new write anywhere else is an offender."""

import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / "src" / "public_atlas"
THE_ONE_DOOR = "modules/graph/status_changes.py"
OTHER_DOORS = {
    ("modules/assignments/lifecycle.py", "assignment.status = status"),
    ("modules/assignments/service.py", "run.status = RunStatus.PAUSED"),
    ("modules/assignments/service.py", "run.status = RunStatus.ACTIVE"),
    ("modules/assignments/service.py", "run.status = RunStatus.STOPPED"),
    ("modules/review/service.py", "item.status = status"),
}
# `row.status = anything` (not `==`), `status=EntityStatus.X` in a constructor or an update's
# keywords, any `status=` inside `.values(...)`, and `setattr(row, "status", ...)`.
STATUS_WRITES = [
    re.compile(r"\.status\s*=(?!=)"),
    re.compile(r"\bstatus\s*=(?!=)\s*EntityStatus\."),
    re.compile(r"\.values\([^)]*\bstatus\s*=(?!=)"),
    re.compile(r"""setattr\([^,]+,\s*["']status["']"""),
]


def test_only_status_changes_writes_an_entity_status():
    offenders = []
    for path in sorted(SOURCE.rglob("*.py")):
        name = path.relative_to(SOURCE).as_posix()
        if name == THE_ONE_DOOR:
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if any(pattern.search(line) for pattern in STATUS_WRITES):
                if (name, line.strip()) in OTHER_DOORS:
                    continue
                offenders.append(f"{name}:{number}: {line.strip()}")
    assert offenders == []


def test_the_other_doors_are_where_they_are_said_to_be():
    """A door that moved or went away would otherwise be allowed forever."""
    for name, line in OTHER_DOORS:
        lines = [row.strip() for row in (SOURCE / name).read_text().splitlines()]
        assert line in lines, (name, line)
