"""The scorer's rules, on graphs built by hand."""

import uuid

import pytest

from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.evals import scorer
from public_atlas.modules.evals.dataset import PlaceList, SubjectFile
from public_atlas.modules.evals.scorer import (
    DOMAIN,
    HOMEPAGE,
    PARENT,
    AssignmentRow,
    DomainRow,
    Graph,
    HomepageRow,
    InstitutionRow,
    PlaceRow,
    SourceRow,
)

FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_SOURCES = AssignmentType.FIND_SOURCES


@pytest.fixture(scope="module")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(canada.SEED)


# --- The small rules ---


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Kitchener, City of", "City of Kitchener"),
        ("Kitchener, City of", "Kitchener"),
        ("Regional Municipality of Waterloo", "Waterloo"),
        ("Waterloo, Regional Municipality of", "Regional Municipality of Waterloo"),
        ("Haldimand County", "County of Haldimand"),
        ("Ville de Hawkesbury", "Town of Hawkesbury"),
        ("The Corporation of the Township of McGarry", "McGarry"),
        ("United Counties of Prescott and Russell", "Prescott and Russell"),
    ],
)
def test_place_names_meet_in_a_shared_form(rules: countries.CountryRules, a: str, b: str):
    assert scorer.place_forms(rules, a) & scorer.place_forms(rules, b)


def test_place_names_that_differ_do_not_meet(rules: countries.CountryRules):
    assert not scorer.place_forms(rules, "Town of Hawkesbury") & scorer.place_forms(
        rules, "Township of East Hawkesbury"
    )


@pytest.mark.parametrize(
    ("saved", "wanted", "expected"),
    [
        ("https://metrolinx.com/en/", "https://www.metrolinx.com/en", True),
        ("https://www.toronto.ca/home", "https://www.toronto.ca/", True),
        ("https://en.ottawa.ca/", "https://ottawa.ca/", True),
        (
            "https://www.ontario.ca/page/ministry-transportation",
            "https://www.ontario.ca/page/ministry-transportation",
            True,
        ),
        (
            "https://www.ontario.ca/page/ministry-transportation-x",
            "https://www.ontario.ca/page/ministry-transportation",
            False,
        ),
        ("https://www.caledon.ca/en/", "https://www.caledon.ca/en/index.aspx", False),
        ("https://ttc.ca/", "https://www.toronto.ca/", False),
    ],
)
def test_homepage_rule(saved: str, wanted: str, *, expected: bool):
    assert scorer.homepage_matches(saved, wanted) is expected


def test_source_rule_ignores_scheme_www_slash_and_query():
    key = scorer.source_key("http://www.mcgarry.ca/town-hallbudget-and-finances/?lang=en")
    assert key == scorer.source_key("https://mcgarry.ca/town-hallbudget-and-finances")
    assert key != scorer.source_key("https://mcgarry.ca/town-hall")


def test_summary_names_a_source_type_in_either_spelling():
    assert scorer.mentions_source_type("No capital_plan page was found", "capital_plan")
    assert scorer.mentions_source_type("Searched for capital plans; none", "capital_plan")
    assert not scorer.mentions_source_type("Found the budget and the tenders", "capital_plan")
    assert not scorer.mentions_source_type(None, "budget")


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        (DomainRow("a.ca", "verified", official=True), "confirm"),
        (DomainRow("a.ca", "verified", official=False), "review"),
        (DomainRow("a.ca", "needs_review", official=True), "review"),
        (DomainRow("a.ca", "rejected", official=True), "reject"),
        (DomainRow("a.ca", "candidate", official=True), scorer.OUTCOME_UNDECIDED),
        (None, scorer.OUTCOME_NOT_SURFACED),
    ],
)
def test_domain_outcome(row: DomainRow | None, expected: str):
    assert scorer.domain_outcome(row) == expected


def test_find_domain_takes_the_row_that_covers_the_name():
    graph = Graph(
        domains={"beckwith.on.ca": DomainRow("beckwith.on.ca", "rejected", official=True)}
    )
    found = scorer.find_domain(graph, "twp.beckwith.on.ca")
    assert found is not None
    assert found.name == "beckwith.on.ca"
    assert scorer.find_domain(graph, "other.ca") is None


# --- A subject file against a graph ---


def ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


ONTARIO, TOWN, REGION = ids(3)
GOVERNMENT, TRANSIT, LIBRARY, BIA, STRAY, TWIN = ids(6)


def subject_file() -> SubjectFile:
    return SubjectFile.model_validate(
        {
            "subject": {
                "kind": "place",
                "name": "Town of Fixture",
                "level": "municipality",
                "place": "Town of Fixture",
                "parent": "Ontario",
                "tier": "single",
                "institution": "town-of-fixture",
            },
            "status": "draft",
            "labelled_at": "2026-09-29",
            "trusted_at_start": ["ontario.ca", "fixture.ca"],
            "institutions": [
                {
                    "key": "town-of-fixture",
                    "type": "municipal_government",
                    "names": [{"text": "Town of Fixture", "lang": "en"}],
                    "homepage": "https://fixture.ca/",
                    "homepage_host": "trusted_domain",
                    "evidence": {"url": "https://fixture.ca/", "quote": "Town of Fixture"},
                },
                {
                    "key": "fixture-transit",
                    "type": "transit_agency",
                    "names": [{"text": "Fixture Transit Commission", "lang": "en"}],
                    "homepage": "https://www.fixturetransit.ca/",
                    "homepage_host": "own_domain",
                    "evidence": {"url": "https://fixture.ca/", "quote": "Fixture Transit"},
                    "parent": {
                        "institution": "town-of-fixture",
                        "label": "agency of",
                        "evidence": {"url": "https://fixture.ca/", "quote": "Fixture Transit"},
                    },
                },
                {
                    "key": "fixture-library",
                    "type": "library",
                    "names": [{"text": "Fixture Public Library", "lang": "en"}],
                    "homepage": "https://fixture.ca/library",
                    "homepage_host": "trusted_domain",
                    "evidence": {"url": "https://fixture.ca/", "quote": "Fixture Library"},
                    "parent": {
                        "institution": "town-of-fixture",
                        "label": "board of",
                        "evidence": {"url": "https://fixture.ca/", "quote": "Fixture Library"},
                    },
                },
                {
                    "key": "fixture-fire",
                    "type": "fire_service",
                    "names": [{"text": "Fixture Fire Services", "lang": "en"}],
                    "homepage": "https://fixture.ca/fire",
                    "homepage_host": "trusted_domain",
                    "evidence": {"url": "https://fixture.ca/", "quote": "Fixture Fire"},
                },
            ],
            "sources": [
                {
                    "institution": "town-of-fixture",
                    "source_type": "budget",
                    "url": "https://fixture.ca/budget",
                    "evidence": {"url": "https://fixture.ca/budget", "quote": "The budget"},
                },
                {
                    "institution": "fixture-transit",
                    "source_type": "procurement",
                    "url": "https://www.fixturetransit.ca/buy/",
                    "alternates": ["https://www.fixturetransit.ca/procurement"],
                    "evidence": {"url": "https://www.fixturetransit.ca/buy/", "quote": "Buying"},
                },
                {
                    "institution": "fixture-transit",
                    "source_type": "board_meeting",
                    "url": "https://www.fixturetransit.ca/board",
                    "evidence": {"url": "https://www.fixturetransit.ca/board", "quote": "Board"},
                },
            ],
            "absent_sources": [
                {"institution": "fixture-transit", "source_type": "tender", "note": "none"},
                {
                    "institution": "fixture-library",
                    "source_type": "budget",
                    "note": "through the town",
                    "covered_by": "town-of-fixture",
                },
                {"institution": "fixture-library", "source_type": "tender", "note": "none"},
            ],
            "candidate_domains": [
                {
                    "domain": "fixturetransit.ca",
                    "institution": "fixture-transit",
                    "expected": "confirm",
                    "reason": "its own domain",
                },
                {
                    "domain": "fixturebia.ca",
                    "institution": "town-of-fixture",
                    "expected": "reject",
                    "reason": "a BIA",
                },
                {
                    "domain": "never.ca",
                    "institution": "town-of-fixture",
                    "expected": "reject",
                    "reason": "never linked",
                },
            ],
            "out_of_scope": [
                {"name": "Fixture BIA", "url": "https://fixturebia.ca/", "reason": "a BIA"},
            ],
        }
    )


def subject_graph() -> Graph:
    graph = Graph()
    graph.places = {
        ONTARIO: PlaceRow(
            ONTARIO, "province_territory", None, None, None, "verified", ("Ontario",)
        ),
        TOWN: PlaceRow(
            TOWN,
            "municipality",
            ONTARIO,
            GOVERNMENT,
            None,
            "verified",
            ("Town of Fixture", "Fixture"),
        ),
    }
    graph.institutions = {
        GOVERNMENT: InstitutionRow(
            GOVERNMENT,
            TOWN,
            "municipal_government",
            "verified",
            "https://fixture.ca/",
            None,
            ("Town of Fixture",),
        ),
        # Named differently from the dataset, so only its homepage can match it. Its parent is
        # the town, as the page says.
        TRANSIT: InstitutionRow(
            TRANSIT,
            TOWN,
            "transit_agency",
            "verified",
            "https://fixturetransit.ca/en",
            GOVERNMENT,
            ("FTC",),
        ),
        # Saved for a human, as the dataset expects for a type at an unlisted level; no parent.
        LIBRARY: InstitutionRow(
            LIBRARY, TOWN, "library", "needs_review", None, None, ("Fixture Public Library",)
        ),
        BIA: InstitutionRow(
            BIA, TOWN, "agency", "verified", "https://fixturebia.ca/", GOVERNMENT, ("Fixture BIA",)
        ),
        STRAY: InstitutionRow(
            STRAY, TOWN, "agency", "candidate", None, GOVERNMENT, ("Fixture Arena Corporation",)
        ),
        TWIN: InstitutionRow(
            TWIN, TOWN, "library", "candidate", None, GOVERNMENT, ("Fixture Public Library",)
        ),
    }
    graph.homepages = {
        GOVERNMENT: (HomepageRow(GOVERNMENT, "https://fixture.ca/", "verified"),),
        TRANSIT: (HomepageRow(TRANSIT, "https://fixturetransit.ca/en", "verified"),),
        LIBRARY: (HomepageRow(LIBRARY, "https://fixture.ca/library/", "candidate"),),
    }
    graph.sources = [
        SourceRow(GOVERNMENT, "budget", "https://fixture.ca/budget/", "verified"),
        SourceRow(TRANSIT, "procurement", "http://fixturetransit.ca/procurement?x=1", "verified"),
        SourceRow(TRANSIT, "strategic_plan", "https://fixturetransit.ca/plan", "verified"),
        SourceRow(LIBRARY, "budget", "https://fixture.ca/budget", "candidate"),
        SourceRow(STRAY, "budget", "https://fixture.ca/arena", "verified"),
    ]
    graph.domains = {
        "fixture.ca": DomainRow("fixture.ca", "verified", official=True),
        "fixturetransit.ca": DomainRow("fixturetransit.ca", "verified", official=True),
        "fixturebia.ca": DomainRow("fixturebia.ca", "verified", official=True),
    }
    graph.assignments = [
        AssignmentRow(
            "find_sources",
            TRANSIT,
            "finished",
            "complete",
            "Found procurement. No tender page.",
        ),
        AssignmentRow(
            "find_sources", LIBRARY, "finished", "complete", "The library buys through the town."
        ),
    ]
    return graph


@pytest.fixture
def card(rules: countries.CountryRules) -> scorer.Scorecard:
    files = {"fixture": subject_file()}
    cards = scorer.score_files(subject_graph(), rules, files, {})
    assert len(cards) == 1
    return cards[0]


def test_institutions_are_matched_by_homepage_then_name_and_typed(card: scorer.Scorecard):
    tally = card.tallies[FIND_INSTITUTIONS].only(exclude=(PARENT,))
    assert (tally.hits, tally.misses, tally.false_positives) == (2, 1, 1)
    buckets = tally.buckets
    assert buckets["found (verified)"] == 1  # the transit, by homepage
    assert buckets["found (needs_review)"] == 1  # the library, in review as expected
    assert buckets["not found"] == 1  # the fire service
    assert buckets["out of scope, saved"] == 1  # the BIA
    assert buckets["unlabelled"] == 1  # the arena
    assert buckets["duplicate"] == 1  # the library's twin
    assert tally.recall == pytest.approx(2 / 3)
    assert tally.precision == pytest.approx(2 / 3)


def test_parent_links_are_scored_from_the_saved_parent(card: scorer.Scorecard):
    tally = card.tallies[FIND_INSTITUTIONS].only((PARENT,))
    lines = "\n".join(tally.lines)
    assert "+ fixture-transit under town-of-fixture" in lines
    assert "- fixture-library under town-of-fixture: no parent saved" in lines
    assert (tally.hits, tally.misses, tally.false_positives) == (1, 1, 0)
    # The BIA's parent is not labelled, so it is not judged; the whole measure adds up.
    whole = card.tallies[FIND_INSTITUTIONS]
    assert (whole.hits, whole.misses, whole.false_positives) == (3, 2, 1)
    assert whole.groups[PARENT] == (1, 1)


def test_homepages_are_judged_for_found_institutions(card: scorer.Scorecard):
    tally = card.tallies[FIND_HOMEPAGE].only((HOMEPAGE,))
    assert tally.buckets["verified (own_domain)"] == 1  # the transit's
    assert tally.buckets["candidate, not verified"] == 1  # the library's, claimed only
    assert tally.buckets["institution not found"] == 1  # the fire service
    assert (tally.hits, tally.misses, tally.false_positives) == (1, 2, 0)


def test_domains_are_judged_on_their_outcome(card: scorer.Scorecard):
    tally = card.tallies[FIND_HOMEPAGE].only((DOMAIN,))
    assert tally.buckets["confirm, as expected"] == 1
    # The BIA: a miss and a false positive.
    assert tally.buckets["expected reject, got confirm"] == 1
    assert (tally.hits, tally.misses, tally.false_positives) == (1, 1, 1)
    # A reject trap no page led to: nothing decided wrongly, so counted in neither and in no
    # group.
    whole = card.tallies[FIND_HOMEPAGE]
    assert whole.buckets[scorer.TRAP_NOT_MET] == 1
    assert scorer.OUTCOME_NOT_SURFACED not in whole.buckets
    assert (whole.hits, whole.misses, whole.false_positives) == (2, 3, 1)


def test_sources_accept_alternates_reported_absences_and_covering_pages(card: scorer.Scorecard):
    tally = card.tallies[FIND_SOURCES]
    lines = "\n".join(tally.lines)
    assert "+ town-of-fixture/budget" in lines
    assert "+ fixture-transit/procurement" in lines  # the alternate, scheme and query aside
    assert "- fixture-transit/board_meeting: not found" in lines
    assert "+ fixture-transit/tender (absent): named in the summary" in lines
    assert "+ fixture-library/budget (absent): town-of-fixture's page saved" in lines
    assert "- fixture-library/tender (absent): the summary does not name it" in lines
    assert "x 'FTC' (transit_agency, verified)/strategic_plan" in lines  # not in the dataset
    assert (tally.hits, tally.misses, tally.false_positives) == (4, 2, 1)
    assert tally.groups["budget"] == (2, 0)


def test_an_absence_listed_in_types_not_found_is_reported(rules: countries.CountryRules):
    graph = subject_graph()
    graph.assignments = [
        AssignmentRow(
            "find_sources", LIBRARY, "finished", "complete", "Looked everywhere.", ("tender",)
        ),
    ]
    (card,) = scorer.score_files(graph, rules, {"fixture": subject_file()}, {})
    lines = "\n".join(card.tallies[FIND_SOURCES].lines)
    assert "+ fixture-library/tender (absent): listed in types_not_found" in lines


def test_sources_the_type_does_not_list_are_reported_but_not_scored(
    rules: countries.CountryRules,
):
    """A transit agency is not asked for an annual report or its leadership, nor a library for a
    strategic plan: found, missed or saved without a label, they stay out of recall and
    precision."""
    data = subject_file().model_dump(by_alias=True, mode="json")
    data["sources"] += [
        {
            "institution": "fixture-transit",
            "source_type": "annual_report",
            "url": "https://fixturetransit.ca/reports",
            "evidence": {"url": "https://fixturetransit.ca/reports", "quote": "Reports"},
        },
        {
            "institution": "fixture-transit",
            "source_type": "leadership",
            "url": "https://fixturetransit.ca/team",
            "evidence": {"url": "https://fixturetransit.ca/team", "quote": "Team"},
        },
    ]
    graph = subject_graph()
    graph.sources += [
        SourceRow(TRANSIT, "annual_report", "https://fixturetransit.ca/reports/", "verified"),
        SourceRow(LIBRARY, "strategic_plan", "https://fixture.ca/library/plan", "verified"),
    ]
    (card,) = scorer.score_files(graph, rules, {"fixture": SubjectFile.model_validate(data)}, {})
    tally = card.tallies[FIND_SOURCES]
    assert tally.buckets["extra, found"] == 1
    assert tally.buckets["extra, not found"] == 1
    assert tally.buckets["extra, not in dataset"] == 1
    assert (tally.hits, tally.misses, tally.false_positives) == (4, 2, 1)  # as without them


def test_a_subject_missing_from_the_database_is_all_misses(rules: countries.CountryRules):
    files = {"fixture": subject_file()}
    cards = scorer.score_files(Graph(), rules, files, {})
    assert cards[0].notes
    assert "not in the database" in cards[0].notes[0]
    assert all(t.hits == 0 for t in cards[0].tallies.values())
    assert cards[0].tallies[FIND_INSTITUTIONS].only(exclude=(PARENT,)).misses == 3


# --- A places file against a graph ---


def municipal_list() -> PlaceList:
    return PlaceList.model_validate(
        {
            "place": "Ontario",
            "source": {"url": "https://example.test/list"},
            "expected_counts": {"total": 4},
            "municipalities": [
                {
                    "name": "Durham, Regional Municipality of",
                    "tier": "upper",
                    "level": "region",
                    "parent": "Ontario",
                    "homepage": "https://www.durham.ca/",
                    "homepage_host": "own_domain",
                },
                {
                    "name": "Ajax, Town of",
                    "tier": "lower",
                    "level": "municipality",
                    "parent": "Durham, Regional Municipality of",
                    "official_code": "3518005",
                    "homepage": "https://www.ajax.ca/en/index.aspx",
                    "homepage_host": "own_domain",
                    "listed_homepage": "http://www.townofajax.com/",
                    "candidate_domains": [
                        {"domain": "ajax.ca", "expected": "confirm", "reason": "current"},
                        {"domain": "townofajax.com", "expected": "reject", "reason": "old"},
                    ],
                },
                {
                    "name": "Brock, Township of",
                    "tier": "lower",
                    "level": "municipality",
                    "parent": "Durham, Regional Municipality of",
                    "homepage": "https://www.townshipofbrock.ca/",
                    "homepage_host": "own_domain",
                },
                {
                    "name": "Pelee, Township of",
                    "tier": "single",
                    "level": "municipality",
                    "parent": "Ontario",
                    "homepage": None,
                    "homepage_host": "none",
                },
            ],
        }
    )


DURHAM, AJAX, BROCK, EXTRA = ids(4)
DURHAM_GOV, AJAX_GOV, BROCK_GOV = ids(3)


def list_graph() -> Graph:
    graph = Graph()
    graph.places = {
        ONTARIO: PlaceRow(
            ONTARIO, "province_territory", None, None, None, "verified", ("Ontario",)
        ),
        DURHAM: PlaceRow(
            DURHAM,
            "region",
            ONTARIO,
            DURHAM_GOV,
            None,
            "verified",
            ("Regional Municipality of Durham", "Durham"),
        ),
        AJAX: PlaceRow(
            AJAX, "municipality", DURHAM, AJAX_GOV, "3518005", "verified", ("Town of Ajax", "Ajax")
        ),
        # Saved under the province instead of its region.
        BROCK: PlaceRow(
            BROCK, "municipality", ONTARIO, BROCK_GOV, None, "verified", ("Township of Brock",)
        ),
        # "Pelee" bare, like the dataset's Township of Pelee, but a city: another body.
        EXTRA: PlaceRow(EXTRA, "municipality", ONTARIO, None, None, "verified", ("City of Pelee",)),
    }
    graph.institutions = {
        DURHAM_GOV: InstitutionRow(
            DURHAM_GOV,
            DURHAM,
            "regional_government",
            "verified",
            "https://www.durham.ca/en/",
            None,
            ("Regional Municipality of Durham",),
        ),
        AJAX_GOV: InstitutionRow(
            AJAX_GOV, AJAX, "municipal_government", "verified", None, None, ("Town of Ajax",)
        ),
        BROCK_GOV: InstitutionRow(
            BROCK_GOV,
            BROCK,
            "municipal_government",
            "verified",
            "https://brock.example/",
            None,
            ("Township of Brock",),
        ),
    }
    graph.homepages = {
        DURHAM_GOV: (HomepageRow(DURHAM_GOV, "https://www.durham.ca/en/", "verified"),),
        # The list's link, claimed, not yet verified.
        AJAX_GOV: (HomepageRow(AJAX_GOV, "http://www.townofajax.com/", "candidate"),),
        BROCK_GOV: (HomepageRow(BROCK_GOV, "https://brock.example/", "verified"),),
    }
    graph.domains = {
        "durham.ca": DomainRow("durham.ca", "verified", official=True),
        "ajax.ca": DomainRow("ajax.ca", "candidate", official=True),
        "townofajax.com": DomainRow("townofajax.com", "rejected", official=True),
        "townshipofbrock.ca": DomainRow("townshipofbrock.ca", "needs_review", official=True),
    }
    return graph


def test_a_list_is_scored_on_its_governments_homepages_and_domains(
    rules: countries.CountryRules,
):
    """The loader made the places from the register, so the agent is scored on each government's
    homepage and the domain decisions that leave it with one. A municipality is matched by its
    code when both sides have one, else by name at its level under its parent."""
    (card,) = scorer.score_files(list_graph(), rules, {}, {"list": municipal_list()})
    assert card.kind == "list"
    assert list(card.tallies) == [FIND_HOMEPAGE]
    pages = card.tallies[FIND_HOMEPAGE].only((HOMEPAGE,))
    assert pages.buckets["verified"] == 1  # Durham
    assert pages.buckets["candidate"] == 1  # Ajax, the list's link, matched by code
    assert pages.buckets["wrong homepage"] == 1  # Brock
    assert (pages.hits, pages.misses, pages.false_positives) == (2, 1, 1)
    domains = card.tallies[FIND_HOMEPAGE].only((DOMAIN,))
    assert domains.buckets["confirm, as expected"] == 1  # durham.ca, the default candidate
    assert domains.buckets["reject, as expected"] == 1  # townofajax.com
    assert domains.buckets[scorer.OUTCOME_UNDECIDED] == 1  # ajax.ca
    assert domains.buckets["expected confirm, got review"] == 1  # townshipofbrock.ca


# --- Reporting ---


def test_report_and_json_carry_the_totals_and_the_gates(rules: countries.CountryRules):
    cards = scorer.score_files(
        subject_graph(),
        rules,
        {"fixture": subject_file()},
        {"list": municipal_list()},
    )
    text = scorer.render(cards, details=True)
    assert "== fixture (draft)" in text
    assert "== totals" in text
    assert (
        "institutions: find_institutions recall on the subject files >= 95%:  67% (2/3) fail"
        in text
    )
    # The list was scored against the subject's graph, which holds none of its governments.
    assert (
        "homepages: find_homepage recall over homepage on the list files >= 99%:   0% (0/3)" in text
    )
    assert "+ fixture-transit (transit_agency)" in text
    assert "[parent 1/2]" in text
    document = scorer.as_json(cards)
    assert document["totals"]["find_institutions"]["hits"] == 3
    assert document["totals"]["find_institutions"]["groups"]["parent"] == {"hits": 1, "misses": 1}
    assert document["files"]["fixture"]["measures"]["find_homepage"]["buckets"]["trap not met"] == 1
    # Three of four gated sources found: 75%, under the 90% floor.
    assert [gate["verdict"] for gate in document["gates"]] == ["fail", "fail", "fail"]


def test_a_tally_records_the_bucket_of_every_miss_and_false_positive(card: scorer.Scorecard):
    tally = card.tallies[FIND_HOMEPAGE]
    misses = tally.misses_json()
    assert {entry["bucket"] for entry in misses} == {
        "candidate, not verified",
        "institution not found",
        "expected reject, got confirm",
    }
    assert all(set(entry) == {"line", "bucket", "group"} for entry in misses)
    assert [entry["bucket"] for entry in tally.false_positives_json()] == [
        "expected reject, got confirm"
    ]
