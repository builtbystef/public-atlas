"""Tallies and scorecards: the hits, misses and false positives per measure, with the bucket of
each, and the gates."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from public_atlas.modules.assignments.models import AssignmentType

type Kind = Literal["hit", "miss", "false_positive", "wrong", "unlabelled", "off_list"]
type CardKind = Literal["subject", "list"]

# One character per kind, for the per-entity lines.
MARKS: dict[Kind, str] = {
    "hit": "+",
    "miss": "-",
    "false_positive": "x",
    "wrong": "x",
    "unlabelled": "?",
    "off_list": "~",
}
# The groups inside a measure that are not the assignment's main population: the parent links
# `find_institutions` saves, and the domain decisions `find_homepage` makes.
PARENT = "parent"
HOMEPAGE = "homepage"
DOMAIN = "domain"


@dataclass(frozen=True, slots=True)
class Entry:
    """One judged thing: what it is, why it counts as it does, and the label it is grouped by (a
    source type, an institution type, `parent`, `homepage`, `domain`)."""

    kind: Kind
    line: str
    bucket: str
    group: str | None = None

    @property
    def counts_as_miss(self) -> bool:
        return self.kind in ("miss", "wrong")

    @property
    def counts_as_false_positive(self) -> bool:
        return self.kind in ("false_positive", "wrong")

    def render(self) -> str:
        return f"{MARKS[self.kind]} {self.line}"

    def as_json(self) -> dict[str, Any]:
        return {"line": self.line, "bucket": self.bucket, "group": self.group}


@dataclass(slots=True)
class Tally:
    """One measure of one dataset file. A saved row the dataset says nothing about is
    `unlabelled`: counted in neither recall nor precision, but shown so the labeller sees it."""

    entries: list[Entry] = field(default_factory=list)

    def hit(self, line: str, bucket: str = "found", *, group: str | None = None) -> None:
        self.entries.append(Entry("hit", line, bucket, group))

    def miss(self, line: str, bucket: str, *, group: str | None = None) -> None:
        self.entries.append(Entry("miss", line, bucket, group))

    def false_positive(self, line: str, bucket: str = "saved, wrong") -> None:
        self.entries.append(Entry("false_positive", line, bucket))

    def wrong(self, line: str, bucket: str, *, group: str | None = None) -> None:
        """A wrong decision: a miss for the right one and a false positive for the saved one."""
        self.entries.append(Entry("wrong", line, bucket, group))

    def unlabelled(self, line: str, bucket: str = "unlabelled") -> None:
        self.entries.append(Entry("unlabelled", line, bucket))

    def off_list(self, line: str, bucket: str) -> None:
        """Reported but counted in neither recall nor precision: the agent was never asked for
        it (a source type its institution's type does not list, a trap it never met)."""
        self.entries.append(Entry("off_list", line, bucket))

    def add(self, other: Tally) -> None:
        self.entries.extend(other.entries)

    def only(self, groups: tuple[str, ...] = (), exclude: tuple[str, ...] = ()) -> Tally:
        """The entries of `groups` (every group when empty), minus those of `exclude`."""
        return Tally(
            [
                entry
                for entry in self.entries
                if (not groups or entry.group in groups) and entry.group not in exclude
            ]
        )

    @property
    def hits(self) -> int:
        return sum(entry.kind == "hit" for entry in self.entries)

    @property
    def misses(self) -> int:
        return sum(entry.counts_as_miss for entry in self.entries)

    @property
    def false_positives(self) -> int:
        return sum(entry.counts_as_false_positive for entry in self.entries)

    @property
    def judged(self) -> int:
        """How many entries count in recall or precision."""
        return sum(
            entry.kind in ("hit", "miss", "false_positive", "wrong") for entry in self.entries
        )

    @property
    def buckets(self) -> Counter[str]:
        return Counter(entry.bucket for entry in self.entries)

    @property
    def groups(self) -> dict[str, tuple[int, int]]:
        """Hits and misses by group, for the groups entries carry."""
        found: dict[str, list[int]] = {}
        for entry in self.entries:
            if entry.group is None:
                continue
            slots = found.setdefault(entry.group, [0, 0])
            if entry.kind == "hit":
                slots[0] += 1
            elif entry.counts_as_miss:
                slots[1] += 1
        return {group: (hits, misses) for group, (hits, misses) in sorted(found.items())}

    @property
    def lines(self) -> list[str]:
        return [entry.render() for entry in self.entries]

    @property
    def recall(self) -> float | None:
        total = self.hits + self.misses
        return self.hits / total if total else None

    @property
    def precision(self) -> float | None:
        total = self.hits + self.false_positives
        return self.hits / total if total else None

    def misses_json(self) -> list[dict[str, Any]]:
        return [entry.as_json() for entry in self.entries if entry.counts_as_miss]

    def false_positives_json(self) -> list[dict[str, Any]]:
        return [entry.as_json() for entry in self.entries if entry.counts_as_false_positive]


# The measures, in reporting order: one per assignment type. `find_institutions` holds the
# institutions (grouped by type) and the parent links (`parent`); `find_homepage` the homepages
# (`homepage`) and the domain decisions (`domain`); `find_sources` the sources by source type.
MEASURES: tuple[AssignmentType, ...] = (
    AssignmentType.FIND_INSTITUTIONS,
    AssignmentType.FIND_HOMEPAGE,
    AssignmentType.FIND_SOURCES,
)
# A places file: the loader made the places from the register (a test checks them against it),
# so only each government's homepage and domain decisions are the agent's to score.
LIST_MEASURES: tuple[AssignmentType, ...] = (AssignmentType.FIND_HOMEPAGE,)


@dataclass(slots=True)
class Scorecard:
    slug: str
    kind: CardKind
    # The dataset file's own status: `draft` or `reviewed`.
    status: str
    tallies: dict[AssignmentType, Tally] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def tally(self, measure: AssignmentType) -> Tally:
        return self.tallies.setdefault(measure, Tally())
