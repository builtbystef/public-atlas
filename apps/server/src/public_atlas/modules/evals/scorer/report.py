"""Scoring every file, and rendering the result as text or JSON, with the pilot's gates."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evals.dataset import PlaceList, SubjectFile
from public_atlas.modules.evals.scorer.graph import Graph
from public_atlas.modules.evals.scorer.places import score_places
from public_atlas.modules.evals.scorer.subjects import match_subject, score_subject
from public_atlas.modules.evals.scorer.tally import (
    DOMAIN,
    HOMEPAGE,
    MEASURES,
    PARENT,
    CardKind,
    Scorecard,
    Tally,
)


def score_files(
    graph: Graph,
    rules: CountryRules,
    subjects: dict[str, SubjectFile],
    lists: dict[str, PlaceList],
) -> list[Scorecard]:
    """One scorecard per file, subjects first. Every subject is matched before any is scored, so
    a cross-file reference finds its row."""
    matches = {slug: match_subject(graph, rules, expected) for slug, expected in subjects.items()}
    cards = [score_subject(graph, rules, slug, matches, subjects) for slug in sorted(subjects)]
    cards.extend(score_places(graph, rules, slug, data) for slug, data in sorted(lists.items()))
    return cards


def totals(cards: Iterable[Scorecard]) -> dict[AssignmentType, Tally]:
    """Each measure summed over every card, in reporting order."""
    summed: dict[AssignmentType, Tally] = {}
    for card in cards:
        for measure, tally in card.tallies.items():
            summed.setdefault(measure, Tally()).add(tally)
    return {measure: summed[measure] for measure in MEASURES if measure in summed}


# --- The gates ---


@dataclass(frozen=True, slots=True)
class Gate:
    """A target of the pilot (spec section 1.2) the dataset can judge: a recall floor on one
    measure, over some of its groups or all of them, on the subject files, the place lists or
    both."""

    name: str
    measure: AssignmentType
    floor: float
    groups: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    cards: CardKind | None = None

    def tally(self, cards: Sequence[Scorecard]) -> Tally:
        summed = Tally()
        for card in cards:
            if self.cards is not None and card.kind != self.cards:
                continue
            found = card.tallies.get(self.measure)
            if found is not None:
                summed.add(found.only(self.groups, self.exclude))
        return summed

    def what(self) -> str:
        over = f" over {', '.join(self.groups)}" if self.groups else ""
        where = f" on the {self.cards} files" if self.cards is not None else ""
        return f"{self.measure.value} recall{over}{where}"


GATES: tuple[Gate, ...] = (
    Gate(
        "homepages",
        AssignmentType.FIND_HOMEPAGE,
        0.99,
        groups=(HOMEPAGE,),
        cards="list",
    ),
    Gate(
        "institutions",
        AssignmentType.FIND_INSTITUTIONS,
        0.95,
        exclude=(PARENT,),
        cards="subject",
    ),
    Gate(
        "sources",
        AssignmentType.FIND_SOURCES,
        0.90,
        groups=("procurement", "council_meeting", "board_meeting", "budget"),
        cards="subject",
    ),
)


@dataclass(frozen=True, slots=True)
class GateResult:
    gate: Gate
    hits: int
    misses: int

    @property
    def recall(self) -> float | None:
        total = self.hits + self.misses
        return self.hits / total if total else None

    @property
    def verdict(self) -> str:
        recall = self.recall
        if recall is None:
            return "-"
        return "pass" if recall >= self.gate.floor else "fail"

    def as_json(self) -> dict[str, Any]:
        return {
            "name": self.gate.name,
            "assignment_type": self.gate.measure.value,
            "what": self.gate.what(),
            "floor": self.gate.floor,
            "hits": self.hits,
            "misses": self.misses,
            "recall": self.recall,
            "verdict": self.verdict,
        }

    def render(self) -> str:
        return (
            f"   {self.gate.name}: {self.gate.what()} >= {self.gate.floor:.0%}: "
            f"{_percent(self.recall)} ({_ratio(self.hits, self.hits + self.misses)}) {self.verdict}"
        )


def gates(cards: Sequence[Scorecard]) -> list[GateResult]:
    results = []
    for gate in GATES:
        tally = gate.tally(cards)
        results.append(GateResult(gate, tally.hits, tally.misses))
    return results


# --- Reporting ---

# The groups a measure line names besides its buckets.
SUBGROUPS: dict[AssignmentType, tuple[str, ...]] = {
    AssignmentType.FIND_INSTITUTIONS: (PARENT,),
    AssignmentType.FIND_HOMEPAGE: (HOMEPAGE, DOMAIN),
}


def _percent(value: float | None) -> str:
    return "   -" if value is None else f"{value:4.0%}"


def _ratio(hits: int, total: int) -> str:
    return f"{hits}/{total}"


def render(cards: Sequence[Scorecard], *, details: bool = False) -> str:
    """One block per file with a line per measure, then the totals and the gates. `details` adds
    the per-entity lines under each measure and the hits and misses of every group under the
    totals."""
    out: list[str] = []
    for card in cards:
        out.append(f"== {card.slug} ({card.status})")
        out.extend(f"   note: {note}" for note in card.notes)
        for measure, tally in card.tallies.items():
            out.append(_measure_line(measure, tally))
            if details:
                out.extend(f"      {line}" for line in tally.lines)
        out.append("")
    summed = totals(cards)
    out.append("== totals")
    for measure, tally in summed.items():
        out.append(_measure_line(measure, tally))
        if details:
            out.extend(
                f"      {group}: {hits}/{hits + misses}"
                for group, (hits, misses) in tally.groups.items()
            )
    out.append("")
    out.append("== gates")
    out.extend(result.render() for result in gates(cards))
    return "\n".join(out)


def _measure_line(measure: AssignmentType, tally: Tally) -> str:
    buckets = ", ".join(f"{name} {count}" for name, count in sorted(tally.buckets.items()))
    found = _ratio(tally.hits, tally.hits + tally.misses)
    right = _ratio(tally.hits, tally.hits + tally.false_positives)
    groups = tally.groups
    subgroups = " ".join(
        f"{group} {hits}/{hits + misses}"
        for group in SUBGROUPS.get(measure, ())
        for hits, misses in [groups.get(group, (0, 0))]
        if hits + misses
    )
    return (
        f"   {measure.value:20} recall {_percent(tally.recall)} ({found:>7})"
        f"  precision {_percent(tally.precision)} ({right:>7})"
        + (f"  [{subgroups}]" if subgroups else "")
        + f"  | {buckets}"
    )


def tally_json(tally: Tally) -> dict[str, Any]:
    return {
        "hits": tally.hits,
        "misses": tally.misses,
        "false_positives": tally.false_positives,
        "recall": tally.recall,
        "precision": tally.precision,
        "buckets": dict(sorted(tally.buckets.items())),
        "groups": {g: {"hits": h, "misses": m} for g, (h, m) in tally.groups.items()},
        "lines": tally.lines,
    }


def as_json(cards: Sequence[Scorecard]) -> dict[str, Any]:
    """The same numbers as a document, so two runs can be diffed."""
    return {
        "files": {
            card.slug: {
                "kind": card.kind,
                "status": card.status,
                "notes": card.notes,
                "measures": {m.value: tally_json(t) for m, t in card.tallies.items()},
            }
            for card in cards
        },
        "totals": {m.value: tally_json(t) for m, t in totals(cards).items()},
        "gates": [result.as_json() for result in gates(cards)],
    }
