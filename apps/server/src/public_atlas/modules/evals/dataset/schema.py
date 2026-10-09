"""The dataset's schema: subject files and place lists, read strictly. A subject file says what
a perfect run should yield for one place or ministry: its institutions with their homepages and
parents, its sources, the domains it should meet, and the bodies it must not save. A place list
says, for each government an official list names, the homepage and the domains `find_homepage`
is scored on."""

from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

from public_atlas.modules.graph.models import IdentifierScheme

ROOT = Path(__file__).resolve().parent
SUBJECTS = ROOT / "subjects"
PLACES = ROOT / "places"

Key = Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
# ISO 3166-1 alpha-2, as `country_settings.country_code`.
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
# `key` for this file, `slug:key` for another subject file.
Ref = Annotated[str, Field(pattern=r"^([a-z0-9-]+:)?[a-z0-9]+(-[a-z0-9]+)*$")]
Url = Annotated[str, Field(pattern=r"^https?://")]

type HomepageHost = Literal["trusted_domain", "own_domain", "platform", "none"]
type Outcome = Literal["confirm", "reject", "review"]

# The scheme a file's `official_code` is in, by country: the register the country's places list
# loads its codes from.
OFFICIAL_CODE_SCHEMES: dict[str, IdentifierScheme] = {
    "CA": IdentifierScheme.STATCAN_SGC,
    "US": IdentifierScheme.FIPS,
}


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.").rstrip(".")


def on_domain(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --- Subject files ---


class Evidence(Strict):
    """A verbatim quote from a trusted page that names the thing labelled."""

    url: Url
    quote: str = Field(min_length=3)
    kind: Literal["appears_on", "links_to"] = "appears_on"
    link_target: Url | None = None
    # "page 4", "sheet Tenders row 12".
    locator: str | None = None
    # Set when the script cannot read the page (bot wall, JS-only, PDF) and a human or a real
    # browser confirmed the quote: "browser 2026-09-29", "pdftotext 2026-09-29".
    manual_check: str | None = None

    @model_validator(mode="after")
    def links_to_has_target(self) -> Self:
        if self.kind == "links_to" and not self.link_target:
            raise ValueError("links_to evidence needs link_target")
        return self


class Name(Strict):
    text: str
    lang: str = Field(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]+)*$")
    is_acronym: bool = False


class Parent(Strict):
    """The body an institution sits under, as a page says it (spec section 9): scored from
    `parent_institution_id`. `label` is the page's own words ("agency of", "wholly owned by")."""

    institution: Ref
    label: str
    evidence: Evidence


class Institution(Strict):
    key: Key
    type: str
    names: list[Name] = Field(min_length=1)
    homepage: Url | None
    # The French twin, say, which has a path of its own.
    homepage_alternates: list[Url] = []
    # trusted_domain: on a domain already trusted when it is found, so the homepage is quoted
    # from the page itself. own_domain: a new domain, so `find_homepage` verifies it (list it in
    # `candidate_domains`). platform: on a third-party platform, verified by the link and the
    # name alone. none: no homepage of its own; `find_homepage` should end `no_homepage`.
    homepage_host: HomepageHost
    evidence: Evidence
    # Absent when no page says it; the agent's default (the place's government) is then not
    # judged.
    parent: Parent | None = None
    # review: a known type at a level the country does not list it under (a regional library).
    # The agent should save it, and it should land in review.
    expected: Literal["verified", "review"] = "verified"
    notes: str | None = None


class Source(Strict):
    institution: Ref
    source_type: str
    url: Url
    # Other URLs an agent may save for the same source and still be right.
    alternates: list[Url] = []
    platform: str | None = None
    access: Literal["public", "login"] = "public"
    evidence: Evidence
    notes: str | None = None


class AbsentSource(Strict):
    institution: Ref
    source_type: str
    # What was searched, and why it is judged absent.
    note: str
    # The body buys or budgets through this institution (a division through its city, a ministry
    # through the government-wide portal). The scorer accepts either the absence reported or
    # that institution's source of the same type saved for this one.
    covered_by: Ref | None = None


class CandidateDomain(Strict):
    domain: str
    institution: Ref
    expected: Outcome
    reason: str


class OutOfScope(Strict):
    name: str
    url: Url | None = None
    reason: str


class Subject(Strict):
    kind: Literal["place", "institution"]
    # The country whose seed gives the levels, types and platforms the file is read against.
    country_code: CountryCode
    name: str
    # The place's level, or that of the institution's place.
    level: str
    # Itself for a place subject; "Ontario" for a ministry.
    place: str
    parent: str | None = None
    tier: Literal["single", "upper", "lower"] | None = None
    # The place's code in the country's scheme (`OFFICIAL_CODE_SCHEMES`): Statistics Canada's CSD
    # or CD code, a FIPS code.
    official_code: str | None = None
    # The place's government, or the ministry itself.
    institution: Key
    # For an institution subject: the homepage of the place's government, which the harness
    # seeds verified so the place's `find_institutions` has a page to start from.
    government_homepage: Url | None = None


class SubjectFile(Strict):
    subject: Subject
    status: Literal["draft", "reviewed"]
    labelled_at: date
    reviewed_at: date | None = None
    # Domains already trusted when the subject's work begins.
    trusted_at_start: list[str]
    institutions: list[Institution]
    sources: list[Source] = []
    absent_sources: list[AbsentSource] = []
    candidate_domains: list[CandidateDomain] = []
    out_of_scope: list[OutOfScope] = []
    notes: str | None = None

    def institution(self, key: str) -> Institution | None:
        return next((row for row in self.institutions if row.key == key), None)


# --- Place lists ---


class MunicipalCandidate(Strict):
    domain: str
    expected: Outcome
    reason: str


class Municipality(Strict):
    name: str
    tier: Literal["single", "upper", "lower"]
    level: Literal["region", "municipality"]
    # "Ontario", or the upper tier's name.
    parent: str
    # city, town, township, county, region, ...
    municipal_status: str | None = None
    geographic_area: str | None = None
    official_code: str | None = None
    # The government's homepage, as it is served.
    homepage: Url | None = None
    homepage_host: Literal["own_domain", "platform", "none"]
    # The URL as the official list links it, only when the scorer would not match it to
    # `homepage`: another registrable domain, or a path the served page is not under.
    listed_homepage: Url | None = None
    # Omitted: the `homepage` domain alone, expected `confirm`. Given: the whole list.
    candidate_domains: list[MunicipalCandidate] | None = None
    names_fr: str | None = None

    def candidates(self) -> list[MunicipalCandidate]:
        """The candidate domains `find_homepage` is scored on for this government."""
        if self.candidate_domains is not None:
            return self.candidate_domains
        if self.homepage_host == "own_domain" and self.homepage:
            domain = host_of(self.homepage)
            return [MunicipalCandidate(domain=domain, expected="confirm", reason="its own domain")]
        return []


class PlaceList(Strict):
    country_code: CountryCode
    place: str
    # url, publisher, retrieved_at.
    source: dict[str, str]
    cross_checks: list[dict[str, str]] = []
    # A full list states its counts per tier; a sample of one (Ontario's) does not.
    expected_counts: dict[str, int] = {}
    municipalities: list[Municipality]
    notes: str | None = None
