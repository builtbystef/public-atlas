"""Scoring one subject file: find the subject in the graph, then score its institutions and
their parents, its homepages and domain decisions, and its sources against what the file
expects."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field

from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evals.dataset import (
    AbsentSource,
    CandidateDomain,
    MunicipalCandidate,
    SubjectFile,
)
from public_atlas.modules.evals.dataset import Institution as ExpectedInstitution
from public_atlas.modules.evals.scorer.graph import (
    NEEDS_REVIEW,
    REJECTED,
    VERIFIED,
    Graph,
    InstitutionRow,
    PlaceRow,
)
from public_atlas.modules.evals.scorer.rules import (
    OUTCOME_NOT_SURFACED,
    OUTCOME_UNDECIDED,
    TRAP_NOT_MET,
    domain_outcome,
    find_domain,
    homepage_matches,
    listed,
    mentions_source_type,
    normalize_name,
    place_forms,
    site_of,
    source_key,
)
from public_atlas.modules.evals.scorer.tally import (
    DOMAIN,
    HOMEPAGE,
    MEASURES,
    PARENT,
    Scorecard,
    Tally,
)

FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
FIND_HOMEPAGE = AssignmentType.FIND_HOMEPAGE
FIND_SOURCES = AssignmentType.FIND_SOURCES
# How many saved rows a line names before stopping.
NAMED = 3


@dataclass(slots=True)
class SubjectMatch:
    """A subject file's entities in the database: its place, and each dataset institution's row
    by key, with how it was matched."""

    place: PlaceRow | None
    rows: dict[str, InstitutionRow] = field(default_factory=dict)
    how: dict[str, str] = field(default_factory=dict)


def find_place(
    graph: Graph,
    rules: CountryRules,
    name: str,
    *,
    level: str | None = None,
    parent_id: uuid.UUID | None = None,
) -> PlaceRow | None:
    """The place `name` names, at `level` when given. With several candidates, the one under
    `parent_id` wins, else the first found."""
    wanted = place_forms(rules, name)
    found = [
        row
        for row in graph.places.values()
        if (level is None or row.level == level)
        and row.status != REJECTED
        and any(wanted & place_forms(rules, text) for text in row.names)
    ]
    if not found:
        return None
    if parent_id is not None:
        under = [row for row in found if row.parent_id == parent_id]
        if under:
            return under[0]
    return found[0]


def _live(row: InstitutionRow) -> bool:
    return row.status != REJECTED


def match_institution(
    graph: Graph, expected: ExpectedInstitution, place_id: uuid.UUID | None
) -> tuple[InstitutionRow | None, str]:
    """The homepage first, then any name, in the subject's place before anywhere else (a shared
    body may be saved under another of its owners). Returns the row and how it matched."""
    homepages = [expected.homepage, *expected.homepage_alternates] if expected.homepage else []
    by_homepage = [
        row
        for row in graph.institutions.values()
        if _live(row)
        and row.homepage_url
        and any(homepage_matches(row.homepage_url, url) for url in homepages)
    ]
    if by_homepage:
        return _prefer(by_homepage, expected.type, place_id), "homepage"
    wanted = {normalize_name(name.text) for name in expected.names}
    by_name = [
        row
        for row in graph.institutions.values()
        if _live(row) and any(normalize_name(text) in wanted for text in row.names)
    ]
    here = [row for row in by_name if row.place_id == place_id]
    if here:
        return _prefer(here, expected.type, place_id), "name"
    if by_name:
        return _prefer(by_name, expected.type, place_id), "name, under another place"
    return None, ""


def _prefer(rows: list[InstitutionRow], type_: str, place_id: uuid.UUID | None) -> InstitutionRow:
    """Of several matching rows, one of the dataset's type in the subject's place, else one of
    its type, else the first."""
    return max(rows, key=lambda row: (row.type == type_, row.place_id == place_id))


def match_subject(graph: Graph, rules: CountryRules, expected: SubjectFile) -> SubjectMatch:
    subject = expected.subject
    if subject.kind == "place":
        place = find_place(graph, rules, subject.name, level=subject.level)
    else:
        place = find_place(graph, rules, subject.place, level=subject.level)
    match = SubjectMatch(place=place)
    place_id = place.id if place else None
    government_id = place.government_id if place is not None else None
    for expected_institution in expected.institutions:
        # The subject's own government is whatever the place points at, by any name.
        if (
            subject.kind == "place"
            and expected_institution.key == subject.institution
            and government_id is not None
            and government_id in graph.institutions
        ):
            match.rows[expected_institution.key] = graph.institutions[government_id]
            match.how[expected_institution.key] = "government"
            continue
        row, how = match_institution(graph, expected_institution, place_id)
        if row is not None:
            match.rows[expected_institution.key] = row
            match.how[expected_institution.key] = how
    return match


# --- Scoring a subject ---


class Refs:
    """Resolves `key` and `slug:key` references through every subject's match."""

    def __init__(
        self, slug: str, matches: dict[str, SubjectMatch], files: dict[str, SubjectFile]
    ) -> None:
        self.slug = slug
        self.matches = matches
        self.files = files

    def split(self, ref: str) -> tuple[str, str]:
        if ":" in ref:
            slug, key = ref.split(":", 1)
            return slug, key
        return self.slug, ref

    def row(self, ref: str) -> InstitutionRow | None:
        slug, key = self.split(ref)
        match = self.matches.get(slug)
        return match.rows.get(key) if match else None

    def expected_type(self, ref: str) -> str | None:
        slug, key = self.split(ref)
        file = self.files.get(slug)
        if file is None:
            return None
        found = file.institution(key)
        return found.type if found is not None else None

    def expected_sources(self, ref: str, source_type: str) -> list[str]:
        """The keys of the dataset's sources of `source_type` for `ref`, alternates included."""
        slug, key = self.split(ref)
        file = self.files.get(slug)
        if file is None:
            return []
        keys: list[str] = []
        for source in file.sources:
            if source.institution == key and source.source_type == source_type:
                keys.append(source_key(source.url))
                keys.extend(source_key(url) for url in source.alternates)
        return keys


def describe(row: InstitutionRow) -> str:
    name = row.names[0] if row.names else str(row.id)
    return f"{name!r} ({row.type}, {row.status})"


def score_subject(
    graph: Graph,
    rules: CountryRules,
    slug: str,
    matches: dict[str, SubjectMatch],
    files: dict[str, SubjectFile],
) -> Scorecard:
    expected = files[slug]
    match = matches[slug]
    card = Scorecard(slug=slug, kind="subject", status=expected.status)
    for measure in MEASURES:
        card.tally(measure)
    if match.place is None:
        card.notes.append(
            f"{expected.subject.name} ({expected.subject.level}) is not in the database; "
            "everything below is a miss"
        )
    refs = Refs(slug, matches, files)
    _score_institutions(card.tally(FIND_INSTITUTIONS), graph, expected, match)
    _score_parents(card.tally(FIND_INSTITUTIONS), graph, expected, match, refs)
    _score_homepages(card.tally(FIND_HOMEPAGE), graph, expected, match)
    score_domains(card.tally(FIND_HOMEPAGE), graph, expected.candidate_domains)
    _score_sources(card.tally(FIND_SOURCES), graph, rules, expected, match, refs)
    return card


def _score_institutions(
    tally: Tally, graph: Graph, expected: SubjectFile, match: SubjectMatch
) -> None:
    subject = expected.subject
    for inst in expected.institutions:
        if inst.key == subject.institution:
            continue
        row = match.rows.get(inst.key)
        label = f"{inst.key} ({inst.type})"
        if row is None:
            tally.miss(f"{label}: not found", "not found", group=inst.type)
        elif row.type != inst.type:
            tally.miss(f"{label}: saved as {describe(row)}", "wrong type", group=inst.type)
        elif inst.expected == "review" and row.status != NEEDS_REVIEW:
            tally.miss(
                f"{label}: expected in review, saved {row.status}",
                f"expected review, saved {row.status}",
                group=inst.type,
            )
        else:
            how = match.how.get(inst.key, "")
            note = f", {how}" if how.startswith("name, under") else ""
            tally.hit(f"{label}: {describe(row)}{note}", f"found ({row.status})", group=inst.type)

    _score_traps(tally, graph, expected, match)


def _score_traps(tally: Tally, graph: Graph, expected: SubjectFile, match: SubjectMatch) -> None:
    """The precision side: `out_of_scope` entries saved anyway and, for a place's file, rows the
    file does not label. A trap counts only when it was saved under the subject's place: a
    school board under the province, a police service under the region or another place's own
    government is where the goal text says it belongs, and another file judges it."""
    matched_ids = {row.id for row in match.rows.values()}
    place = match.place
    if place is None:
        return
    # A trap's URL names it only off the dataset institutions' own sites: on one of those, a row
    # is a duplicate of the institution, not the trap.
    expected_sites = {site_of(i.homepage) for i in expected.institutions if i.homepage}
    expected_names = {normalize_name(n.text) for i in expected.institutions for n in i.names}
    for trap in expected.out_of_scope:
        wanted = normalize_name(trap.name)
        by_url = trap.url is not None and site_of(trap.url) not in expected_sites
        saved = [
            row
            for row in graph.institutions.values()
            if _live(row)
            and row.place_id == place.id
            and row.id not in matched_ids
            and (
                any(normalize_name(text) == wanted for text in row.names)
                or (
                    by_url
                    and trap.url is not None
                    and row.homepage_url is not None
                    and homepage_matches(row.homepage_url, trap.url)
                )
            )
        ]
        for row in saved:
            matched_ids.add(row.id)
            tally.false_positive(
                f"{trap.name}: saved as {describe(row)}; out of scope: {trap.reason.strip()}",
                "out of scope, saved",
            )
    if expected.subject.kind != "place":
        # A ministry's file labels its own slice of the province, not every body under it, so
        # what else is there cannot be judged.
        return
    for row in graph.institutions.values():
        if (
            _live(row)
            and row.place_id == place.id
            and row.id not in matched_ids
            and row.id != place.government_id
        ):
            if any(normalize_name(text) in expected_names for text in row.names):
                tally.unlabelled(
                    f"{describe(row)}: another row of an institution in the dataset", "duplicate"
                )
            else:
                tally.unlabelled(f"{describe(row)}: not in the dataset file either way")


def _score_parents(
    tally: Tally, graph: Graph, expected: SubjectFile, match: SubjectMatch, refs: Refs
) -> None:
    """The parent links (spec section 9), from `parent_institution_id`: judged only where the
    file labels one."""
    for inst in expected.institutions:
        if inst.parent is None:
            continue
        label = f"{inst.key} under {inst.parent.institution}"
        row = match.rows.get(inst.key)
        if row is None:
            tally.miss(f"{label}: {inst.key} not found", "institution not found", group=PARENT)
            continue
        wanted = refs.row(inst.parent.institution)
        if wanted is None:
            tally.miss(
                f"{label}: {inst.parent.institution} not found", "parent not found", group=PARENT
            )
        elif row.parent_id == wanted.id:
            tally.hit(f"{label}: {describe(wanted)}", "parent found", group=PARENT)
        elif row.parent_id is None:
            tally.miss(f"{label}: no parent saved", "no parent", group=PARENT)
        else:
            saved = graph.institutions.get(row.parent_id)
            under = describe(saved) if saved is not None else str(row.parent_id)
            tally.wrong(f"{label}: saved under {under}", "wrong parent", group=PARENT)


def _score_homepages(
    tally: Tally, graph: Graph, expected: SubjectFile, match: SubjectMatch
) -> None:
    for inst in expected.institutions:
        if inst.key == expected.subject.institution:
            # The subject's government was seeded with its homepage; there is nothing to score.
            continue
        row = match.rows.get(inst.key)
        label = f"{inst.key}"
        wanted = [inst.homepage, *inst.homepage_alternates] if inst.homepage else []
        if row is None:
            if wanted:
                tally.miss(
                    f"{label}: institution not found", "institution not found", group=HOMEPAGE
                )
            continue
        if not wanted:
            if row.homepage_url:
                tally.wrong(
                    f"{label}: has no homepage, saved {row.homepage_url}",
                    "homepage for none",
                    group=HOMEPAGE,
                )
            else:
                tally.hit(f"{label}: no homepage, none saved", "none, as expected", group=HOMEPAGE)
            continue
        if row.homepage_url and any(homepage_matches(row.homepage_url, url) for url in wanted):
            tally.hit(
                f"{label}: {row.homepage_url}", f"verified ({inst.homepage_host})", group=HOMEPAGE
            )
        elif row.homepage_url:
            tally.wrong(
                f"{label}: saved {row.homepage_url}, expected {inst.homepage}",
                "wrong homepage",
                group=HOMEPAGE,
            )
        else:
            claimed = graph.claimed_urls(row.id)
            if any(homepage_matches(url, wanted_url) for url in claimed for wanted_url in wanted):
                tally.miss(
                    f"{label}: {inst.homepage} claimed, not verified",
                    "candidate, not verified",
                    group=HOMEPAGE,
                )
            else:
                tally.miss(
                    f"{label}: no homepage saved (expected {inst.homepage})",
                    "no homepage",
                    group=HOMEPAGE,
                )


def score_domains(
    tally: Tally, graph: Graph, candidates: Sequence[CandidateDomain | MunicipalCandidate]
) -> None:
    """Each candidate domain against what `find_homepage` decided about it."""
    for candidate in candidates:
        row = find_domain(graph, candidate.domain)
        outcome = domain_outcome(row)
        found_as = f" (as {row.name})" if row is not None and row.name != candidate.domain else ""
        label = f"{candidate.domain}{found_as}: expected {candidate.expected}"
        if outcome == candidate.expected:
            tally.hit(f"{label}, {outcome}", f"{outcome}, as expected", group=DOMAIN)
        elif outcome == OUTCOME_NOT_SURFACED and candidate.expected == "reject":
            tally.off_list(f"{label}, {outcome}", TRAP_NOT_MET)
        elif outcome in (OUTCOME_UNDECIDED, OUTCOME_NOT_SURFACED):
            tally.miss(f"{label}, {outcome}", outcome, group=DOMAIN)
        else:
            tally.wrong(
                f"{label}, got {outcome}; {candidate.reason.strip()}",
                f"expected {candidate.expected}, got {outcome}",
                group=DOMAIN,
            )


def _score_sources(  # noqa: PLR0913, PLR0917
    tally: Tally,
    graph: Graph,
    rules: CountryRules,
    expected: SubjectFile,
    match: SubjectMatch,
    refs: Refs,
) -> None:
    # (institution id, type, key) of every source the dataset accepts; anything else saved on
    # these institutions is a false positive.
    accepted: set[tuple[uuid.UUID, str, str]] = set()
    for source in expected.sources:
        row = refs.row(source.institution)
        label = f"{source.institution}/{source.source_type}"
        if row is None:
            tally.miss(
                f"{label}: institution not found", "institution not found", group=source.source_type
            )
            continue
        keys = {source_key(source.url), *(source_key(url) for url in source.alternates)}
        accepted.update((row.id, source.source_type, key) for key in keys)
        saved = [
            s
            for s in graph.sources_of(row.id)
            if s.source_type == source.source_type and s.status != REJECTED
        ]
        found = [s for s in saved if source_key(s.url) in keys]
        expected_type = refs.expected_type(source.institution)
        if expected_type is not None and not listed(rules, expected_type, source.source_type):
            if found:
                tally.off_list(f"{label}: {found[0].url}", "extra, found")
            else:
                tally.off_list(f"{label}: not found ({source.url})", "extra, not found")
            continue
        if found:
            best = max(found, key=lambda s: s.status == VERIFIED)
            tally.hit(f"{label}: {best.url}", f"found ({best.status})", group=source.source_type)
        elif saved:
            others = ", ".join(s.url for s in saved[:NAMED])
            tally.miss(
                f"{label}: not found; saved instead: {others}",
                "not found",
                group=source.source_type,
            )
        else:
            tally.miss(f"{label}: not found ({source.url})", "not found", group=source.source_type)

    _score_absent(tally, graph, expected.absent_sources, refs, accepted)
    _score_extra_sources(tally, graph, rules, match, accepted)


def _score_absent(
    tally: Tally,
    graph: Graph,
    absent_sources: Sequence[AbsentSource],
    refs: Refs,
    accepted: set[tuple[uuid.UUID, str, str]],
) -> None:
    """An absence is a hit when the finish listed the type in `types_not_found` or the summary
    names it, or when the `covered_by` institution's source of that type was saved for this
    one."""
    for absent in absent_sources:
        row = refs.row(absent.institution)
        label = f"{absent.institution}/{absent.source_type} (absent)"
        if row is None:
            tally.miss(
                f"{label}: institution not found", "institution not found", group=absent.source_type
            )
            continue
        covering = (
            refs.expected_sources(absent.covered_by, absent.source_type)
            if absent.covered_by
            else []
        )
        accepted.update((row.id, absent.source_type, key) for key in covering)
        covered = [
            s
            for s in graph.sources_of(row.id)
            if s.source_type == absent.source_type
            and s.status != REJECTED
            and source_key(s.url) in covering
        ]
        summary = graph.summary_of(FIND_SOURCES, row.id)
        if covered:
            tally.hit(
                f"{label}: {absent.covered_by}'s page saved, {covered[0].url}",
                "covered",
                group=absent.source_type,
            )
        elif absent.source_type in graph.not_found_of(FIND_SOURCES, row.id):
            tally.hit(
                f"{label}: listed in types_not_found", "absence reported", group=absent.source_type
            )
        elif mentions_source_type(summary, absent.source_type):
            tally.hit(
                f"{label}: named in the summary", "absence reported", group=absent.source_type
            )
        elif summary is None:
            tally.miss(f"{label}: no find_sources summary", "no summary", group=absent.source_type)
        else:
            tally.miss(
                f"{label}: the summary does not name it",
                "absence not reported",
                group=absent.source_type,
            )


def _score_extra_sources(
    tally: Tally,
    graph: Graph,
    rules: CountryRules,
    match: SubjectMatch,
    accepted: set[tuple[uuid.UUID, str, str]],
) -> None:
    own = {row.id for row in match.rows.values()}
    for saved_source in graph.sources:
        if saved_source.institution_id not in own or saved_source.status == REJECTED:
            continue
        triple = (
            saved_source.institution_id,
            saved_source.source_type,
            source_key(saved_source.url),
        )
        if triple not in accepted:
            owner = graph.institutions[saved_source.institution_id]
            line = (
                f"{describe(owner)}/{saved_source.source_type}: {saved_source.url} "
                f"({saved_source.status}) is not in the dataset file"
            )
            if not listed(rules, owner.type, saved_source.source_type):
                tally.off_list(line, "extra, not in dataset")
                continue
            tally.false_positive(line, "not in dataset")
