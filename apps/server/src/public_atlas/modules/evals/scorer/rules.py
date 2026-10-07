"""The match rules: how a saved row is compared with what the dataset expects. Pure, so they are
tested without a database."""

from urllib.parse import unquote, urlsplit

from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evals.scorer.graph import (
    NEEDS_REVIEW,
    REJECTED,
    VERIFIED,
    DomainRow,
    Graph,
)
from public_atlas.shared.text import normalize_text


def normalize_name(text: str) -> str:
    return normalize_text(text)


def place_forms(rules: CountryRules, name: str) -> frozenset[str]:
    """The forms a place's name is compared in, by the country's naming rules, so "City of
    Elmwood", "Elmwood, City of" and "Elmwood" all meet."""
    return rules.naming.forms(name)


def listed(rules: CountryRules, institution_type: str, source_type: str) -> bool:
    """Whether the country asks for `source_type` from `institution_type`. A type the country
    does not use is scored on every source."""
    return institution_type not in rules.uses or source_type in rules.expected_source_types(
        institution_type
    )


def site_of(url: str) -> str:
    return (urlsplit(url.strip()).hostname or "").casefold().removeprefix("www.")


def same_site(a: str, b: str) -> bool:
    return bool(a) and bool(b) and (a == b or a.endswith("." + b) or b.endswith("." + a))


def homepage_matches(saved: str, expected: str) -> bool:
    """The same site (`www` aside, one may be a subdomain of the other) and a path that starts
    with the expected one."""
    if not same_site(site_of(saved), site_of(expected)):
        return False
    saved_path = unquote(urlsplit(saved).path).rstrip("/").casefold()
    expected_path = unquote(urlsplit(expected).path).rstrip("/").casefold()
    return saved_path == expected_path or saved_path.startswith(expected_path + "/")


def source_key(url: str) -> str:
    """The URL with what does not tell two spellings of one source apart stripped: the scheme,
    `www`, the trailing slash, the query and the fragment."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").casefold().removeprefix("www.")
    return host + unquote(parts.path).rstrip("/")


def mentions_source_type(summary: str | None, source_type: str) -> bool:
    """Whether a summary names a source type, as spelled (`capital_plan`) or in words ("capital
    plan", which "capital plans" contains)."""
    if not summary:
        return False
    haystack = normalize_name(summary)
    return source_type in haystack or source_type.replace("_", " ") in haystack


OUTCOME_UNDECIDED = "undecided"
OUTCOME_NOT_SURFACED = "not surfaced"
# A `reject` trap no page led the agent to: nothing was decided wrongly, so it is reported and
# counted in neither recall nor precision.
TRAP_NOT_MET = "trap not met"


def domain_outcome(row: DomainRow | None) -> str:
    """What the database decided about a domain, in the dataset's words. A verified domain that
    is not official (a platform) counts as `review`, like one sent to a human."""
    if row is None:
        return OUTCOME_NOT_SURFACED
    if row.status == VERIFIED:
        return "confirm" if row.official else "review"
    if row.status == REJECTED:
        return "reject"
    if row.status == NEEDS_REVIEW:
        return "review"
    return OUTCOME_UNDECIDED


def covers(name: str, other: str) -> bool:
    """Whether the domain `other` covers `name`: the same, or `name` sits under it."""
    return name == other or name.endswith("." + other)


def find_domain(graph: Graph, name: str) -> DomainRow | None:
    """The domain row for `name`, or else the longest one it is under or that is under it
    (`twp.beckwith.on.ca` saved as `beckwith.on.ca`)."""
    name = name.casefold()
    exact = graph.domains.get(name)
    if exact is not None:
        return exact
    related = [
        row for row in graph.domains.values() if covers(name, row.name) or covers(row.name, name)
    ]
    if not related:
        return None
    return max(related, key=lambda row: len(row.name))
