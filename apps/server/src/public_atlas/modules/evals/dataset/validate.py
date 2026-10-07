"""Validation: schema and cross-reference checks on every dataset file, against the country's
rules (its levels, the types expected at each, the sources expected per type, its platforms), so
the dataset and the agent can never disagree on a type."""

from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import ValidationError

from public_atlas.modules.countries.rules import CountryRules
from public_atlas.modules.evals.dataset.schema import (
    PLACES,
    SUBJECTS,
    Institution,
    Municipality,
    PlaceList,
    SubjectFile,
    host_of,
    on_domain,
)

type Loaded = tuple[dict[Path, SubjectFile], dict[Path, PlaceList], list[str]]


def all_files() -> list[Path]:
    return sorted(SUBJECTS.glob("*.yaml")) + sorted(PLACES.glob("*.yaml"))


def load_all(files: list[Path]) -> Loaded:
    """Each file as its model, with the errors of those that do not read."""
    subjects: dict[Path, SubjectFile] = {}
    lists: dict[Path, PlaceList] = {}
    errors: list[str] = []
    for path in files:
        try:
            raw = yaml.safe_load(path.read_text())
            if path.parent == PLACES:
                lists[path] = PlaceList.model_validate(raw)
            else:
                subjects[path] = SubjectFile.model_validate(raw)
        except (ValidationError, yaml.YAMLError) as exc:
            errors.append(f"{path.stem}: {exc}")
    return subjects, lists, errors


def listed_at(rules: CountryRules, institution_type: str, level: str) -> bool:
    """Whether the country expects the type at the level: as its government, or on the level's
    checklist."""
    found = rules.levels.get(level)
    if found is None:
        return False
    return (
        institution_type == found.government_institution_type
        or institution_type in found.expected_institution_types
    )


def validate_subject(  # noqa: C901, PLR0912, PLR0915 - one check after another
    slug: str, expected: SubjectFile, rules: CountryRules, all_keys: dict[str, set[str]]
) -> list[str]:
    errors: list[str] = []
    keys = [row.key for row in expected.institutions]
    by_key = {row.key: row for row in expected.institutions}

    def resolve(ref: str, where: str) -> Institution | None:
        if ":" in ref:
            other, key = ref.split(":", 1)
            if key not in all_keys.get(other, set()):
                errors.append(f"{where}: unknown cross-file ref {ref}")
            return None
        if ref not in by_key:
            errors.append(f"{where}: unknown institution {ref}")
        return by_key.get(ref)

    if len(keys) != len(set(keys)):
        errors.append(
            f"duplicate institution keys: {sorted({k for k in keys if keys.count(k) > 1})}"
        )
    if expected.subject.institution not in by_key:
        errors.append(f"subject.institution {expected.subject.institution} is not in institutions")
    if expected.subject.level not in rules.levels:
        errors.append(f"unknown level {expected.subject.level}")
    if expected.status == "reviewed" and not expected.reviewed_at:
        errors.append("status reviewed needs reviewed_at")
    if expected.subject.kind == "institution" and expected.subject.government_homepage is None:
        errors.append("an institution subject names its place's government_homepage")

    for inst in expected.institutions:
        where = f"institution {inst.key}"
        if inst.type not in rules.institution_types:
            errors.append(f"{where}: unknown type {inst.type}")
            continue
        unlisted = not listed_at(rules, inst.type, expected.subject.level)
        if unlisted and inst.expected != "review":
            errors.append(
                f"{where}: type {inst.type} is not listed under level {expected.subject.level}; "
                "set expected: review or move it to out_of_scope"
            )
        if inst.expected == "review" and not unlisted:
            errors.append(f"{where}: expected: review but {inst.type} is listed at this level")
        if (inst.homepage is None) != (inst.homepage_host == "none"):
            errors.append(f"{where}: homepage and homepage_host=none disagree")
        if inst.homepage_host == "own_domain" and inst.homepage:
            host = host_of(inst.homepage)
            if not any(on_domain(host, c.domain) for c in expected.candidate_domains):
                errors.append(f"{where}: own_domain {host} has no candidate_domains entry")
        if inst.parent is not None:
            resolve(inst.parent.institution, f"{where}: parent")
            if inst.parent.institution == inst.key:
                errors.append(f"{where}: its own parent")
        # Every source type of the institution's type must be either found or marked absent, so
        # a type nobody looked for is not mistaken for one that does not exist.
        covered = {s.source_type for s in expected.sources if s.institution == inst.key}
        covered |= {a.source_type for a in expected.absent_sources if a.institution == inst.key}
        missing = [t for t in rules.expected_source_types(inst.type) if t not in covered]
        if missing:
            errors.append(f"{where}: source types neither found nor marked absent: {missing}")

    for i, src in enumerate(expected.sources):
        where = f"source #{i} {src.institution}/{src.source_type}"
        resolve(src.institution, where)
        # Any source type the country knows counts: the institution type's own list is a floor,
        # not a ceiling.
        if src.source_type not in rules.source_types:
            errors.append(f"{where}: unknown source_type")
        host = host_of(src.url)
        platform = next((p for p in rules.platforms if on_domain(host, p)), None)
        if platform and src.platform != platform:
            errors.append(f"{where}: url is on {platform} but platform is {src.platform!r}")
    urls = [(s.institution, s.source_type, s.url) for s in expected.sources]
    if len(urls) != len(set(urls)):
        errors.append("duplicate source (same institution, type and url)")

    for i, absent in enumerate(expected.absent_sources):
        where = f"absent #{i} {absent.institution}/{absent.source_type}"
        resolve(absent.institution, where)
        if absent.covered_by:
            if absent.covered_by == absent.institution:
                errors.append(f"{where}: covered_by itself")
            resolve(absent.covered_by, where)
            if ":" not in absent.covered_by and not any(
                s.institution == absent.covered_by and s.source_type == absent.source_type
                for s in expected.sources
            ):
                errors.append(
                    f"{where}: covered_by {absent.covered_by} has no {absent.source_type} source"
                )
        if any(
            s.institution == absent.institution and s.source_type == absent.source_type
            for s in expected.sources
        ):
            errors.append(f"{where}: also listed as found")

    for candidate in expected.candidate_domains:
        resolve(candidate.institution, f"candidate_domain {candidate.domain}")

    return [f"{slug}: {e}" for e in errors]


def validate_places(slug: str, data: PlaceList, rules: CountryRules) -> list[str]:
    errors: list[str] = []
    names = [m.name for m in data.municipalities]
    if len(names) != len(set(names)):
        errors.append(f"duplicate names: {sorted({n for n in names if names.count(n) > 1})}")
    upper = {m.name for m in data.municipalities if m.tier == "upper"}
    # A sample may leave a lower tier's parent out, but a parent it does list must be upper-tier.
    not_upper = set(names) - upper | {data.place}
    for m in data.municipalities:
        if m.tier == "upper" and (m.level != "region" or m.parent != data.place):
            errors.append(f"{m.name}: upper-tier must be level region under {data.place}")
        if m.tier == "single" and (m.level != "municipality" or m.parent != data.place):
            errors.append(f"{m.name}: single-tier must be level municipality under {data.place}")
        if m.tier == "lower" and (m.level != "municipality" or m.parent in not_upper):
            errors.append(f"{m.name}: lower-tier parent {m.parent!r} is not an upper-tier")
        errors += validate_municipal_homepage(m, rules)
    counts = {
        t: sum(m.tier == t for m in data.municipalities) for t in ("single", "upper", "lower")
    }
    counts["total"] = len(data.municipalities)
    for k, v in data.expected_counts.items():
        if counts.get(k) != v:
            errors.append(f"expected {v} {k}, found {counts.get(k)}")
    return [f"{slug}: {e}" for e in errors]


def validate_municipal_homepage(  # noqa: C901 - one check after another
    m: Municipality, rules: CountryRules
) -> list[str]:
    """The same homepage rules as for an institution, plus the list's own fields."""
    errors: list[str] = []
    if (m.homepage is None) != (m.homepage_host == "none"):
        errors.append(f"{m.name}: homepage and homepage_host=none disagree")
    if m.homepage:
        host = host_of(m.homepage)
        on_platform = rules.is_platform(host)
        if on_platform != (m.homepage_host == "platform"):
            errors.append(f"{m.name}: {host} and homepage_host={m.homepage_host} disagree")
        if m.listed_homepage and host_of(m.listed_homepage) == host:
            listed, served = urlparse(m.listed_homepage).path, urlparse(m.homepage).path
            if listed.rstrip("/").startswith(served.rstrip("/")):
                errors.append(f"{m.name}: listed_homepage matches homepage; drop it")
    if m.candidate_domains is not None:
        if not m.candidate_domains:
            errors.append(f"{m.name}: candidate_domains is empty; omit it for the default")
        if m.homepage_host == "own_domain" and m.homepage:
            host = host_of(m.homepage)
            if not any(
                on_domain(host, c.domain) and c.expected == "confirm" for c in m.candidate_domains
            ):
                errors.append(f"{m.name}: own_domain {host} has no confirm entry")
        if m.listed_homepage and not any(
            on_domain(host_of(m.listed_homepage), c.domain) for c in m.candidate_domains
        ):
            errors.append(f"{m.name}: listed_homepage domain has no candidate_domains entry")
        domains = [c.domain for c in m.candidate_domains]
        if len(domains) != len(set(domains)):
            errors.append(f"{m.name}: duplicate candidate domain")
    return errors


def validate_files(files: list[Path], rules: CountryRules) -> list[str]:
    """Every error in `files`. Cross-file references need every subject's keys, even when
    validating one file."""
    everything, _, _ = load_all(sorted(SUBJECTS.glob("*.yaml")))
    all_keys = {p.stem: {i.key for i in g.institutions} for p, g in everything.items()}
    subjects, lists, errors = load_all(files)
    for path, expected in subjects.items():
        errors += validate_subject(path.stem, expected, rules, all_keys)
    for path, data in lists.items():
        errors += validate_places(path.stem, data, rules)
    return errors
