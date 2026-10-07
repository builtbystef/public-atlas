"""Scoring a places file: each government's domain decisions and homepage. The loader made the
places themselves from the register, and a unit test checks them against it."""

from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evals.dataset import Municipality, PlaceList
from public_atlas.modules.evals.scorer.graph import REJECTED, Graph, PlaceRow
from public_atlas.modules.evals.scorer.rules import homepage_matches, place_forms
from public_atlas.modules.evals.scorer.subjects import FIND_HOMEPAGE, find_place, score_domains
from public_atlas.modules.evals.scorer.tally import HOMEPAGE, LIST_MEASURES, Scorecard, Tally

NAMED = 3


def match_municipality(
    graph: Graph, rules: CountryRules, municipality: Municipality, parent: PlaceRow | None
) -> PlaceRow | None:
    """The code when both sides have one, else the name in any of its forms at the same level
    and of the same kind (the City of Hamilton is not the Township of Hamilton, though both are
    "Hamilton" bare). The one under the right parent wins when several match."""
    names = [municipality.name, *([municipality.names_fr] if municipality.names_fr else [])]
    wanted: set[str] = set()
    for name in names:
        wanted |= place_forms(rules, name)
    found = [
        row
        for row in graph.places.values()
        if row.level == municipality.level
        and row.status != REJECTED
        and (
            (municipality.official_code is not None and row.code == municipality.official_code)
            or (
                any(wanted & place_forms(rules, text) for text in row.names)
                and not rules.naming.designators_differ(names, list(row.names))
            )
        )
    ]
    if not found:
        return None
    if parent is not None:
        under = [row for row in found if row.parent_id == parent.id]
        if under:
            return under[0]
    return found[0]


def score_places(graph: Graph, rules: CountryRules, slug: str, data: PlaceList) -> Scorecard:
    """Each listed government's domain decisions and the homepage they leave it with."""
    card = Scorecard(slug=slug, kind="list", status="draft")
    for measure in LIST_MEASURES:
        card.tally(measure)
    tally = card.tally(FIND_HOMEPAGE)
    root = find_place(graph, rules, data.place)
    if root is None:
        card.notes.append(f"{data.place} is not in the database; everything below is a miss")
    for municipality in data.municipalities:
        if municipality.parent == data.place:
            parent = root
        else:
            parent = find_place(graph, rules, municipality.parent, level="region")
            if parent is None:
                parent = find_place(graph, rules, municipality.parent)
        row = match_municipality(graph, rules, municipality, parent)
        if municipality.homepage:
            _score_government_homepage(tally, graph, municipality, row)
        score_domains(tally, graph, municipality.candidates())
    return card


def _score_government_homepage(
    tally: Tally, graph: Graph, municipality: Municipality, row: PlaceRow | None
) -> None:
    label = municipality.name
    wanted = [municipality.homepage, municipality.listed_homepage]
    wanted_urls = [url for url in wanted if url]
    if row is None:
        tally.miss(f"{label}: place not found", "place not found", group=HOMEPAGE)
        return
    government = graph.institutions.get(row.government_id) if row.government_id else None
    if government is None:
        tally.miss(f"{label}: no government saved", "no government", group=HOMEPAGE)
        return
    claimed = list(graph.claimed_urls(government.id))
    if government.homepage_url and any(
        homepage_matches(government.homepage_url, url) for url in wanted_urls
    ):
        tally.hit(f"{label}: {government.homepage_url}", "verified", group=HOMEPAGE)
    elif any(homepage_matches(saved, url) for saved in claimed for url in wanted_urls):
        tally.hit(f"{label}: candidate claimed", "candidate", group=HOMEPAGE)
    elif claimed:
        tally.wrong(
            f"{label}: saved {', '.join(claimed[:NAMED])}, expected {municipality.homepage}",
            "wrong homepage",
            group=HOMEPAGE,
        )
    else:
        tally.miss(
            f"{label}: no homepage saved (expected {municipality.homepage})",
            "no homepage",
            group=HOMEPAGE,
        )
