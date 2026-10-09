"""The eval dataset (spec section 10): ten hand-labelled Ontario subjects and a list of 25
governments, as YAML files beside this module, with their schema, validator and evidence check.
`README.md` holds the labelling rules. An eval run works the quick set by default, five
subjects chosen for coverage over size, and every file with `--all`."""

import hashlib
from pathlib import Path

from public_atlas.modules.evals.dataset.evidence import check_evidence, evidence_items
from public_atlas.modules.evals.dataset.schema import (
    PLACES,
    ROOT,
    SUBJECTS,
    AbsentSource,
    CandidateDomain,
    Evidence,
    HomepageHost,
    Institution,
    Key,
    MunicipalCandidate,
    Municipality,
    Name,
    Outcome,
    OutOfScope,
    Parent,
    PlaceList,
    Ref,
    Source,
    Subject,
    SubjectFile,
    Url,
    host_of,
    on_domain,
)
from public_atlas.modules.evals.dataset.validate import (
    all_files,
    listed_at,
    load_all,
    validate_files,
    validate_places,
    validate_subject,
)

VERSION_LENGTH = 12

# The subjects an eval run works unless told otherwise: a township of 579 people on a vendor's
# site, a French-majority town, a lower-tier city with bodies shared across its region, a
# county as the region level, and a bilingual mid-size city with its own utility. The big
# cities are left to `--all`: Toronto alone cost a third of the first full run.
QUICK_SUBJECTS = ("county-of-simcoe", "greater-sudbury", "hawkesbury", "kitchener", "mcgarry")


def version(files: list[Path] | None = None) -> str:
    """A short hash of the dataset's files, so two eval runs say whether they scored the same
    labels."""
    digest = hashlib.sha256()
    for path in files if files is not None else all_files():
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:VERSION_LENGTH]


def quick_files() -> list[Path]:
    """The quick set's subject files and every places file: what `eval run` works by default.
    A places file adds one `find_homepage` per listed government whose homepage no subject
    seeds, a few minutes each, and holds the dead, parked and hijacked domains that show the
    agent checking a list instead of trusting it."""
    return files_named(list(QUICK_SUBJECTS), lists_by_default=False) + sorted(PLACES.glob("*.yaml"))


def files_named(slugs: list[str], *, lists_by_default: bool) -> list[Path]:
    """The dataset files with these stems, or every subject file when none are named (and
    every places file too, with `lists_by_default`)."""
    available = {path.stem: path for path in all_files()}
    if not slugs:
        return [path for path in all_files() if lists_by_default or path.parent == SUBJECTS]
    unknown = [slug for slug in slugs if slug not in available]
    if unknown:
        raise ValueError(f"unknown subject(s): {', '.join(unknown)}; known: {', '.join(available)}")
    return [available[slug] for slug in slugs]


__all__ = [
    "PLACES",
    "QUICK_SUBJECTS",
    "ROOT",
    "SUBJECTS",
    "AbsentSource",
    "CandidateDomain",
    "Evidence",
    "HomepageHost",
    "Institution",
    "Key",
    "MunicipalCandidate",
    "Municipality",
    "Name",
    "OutOfScope",
    "Outcome",
    "Parent",
    "PlaceList",
    "Ref",
    "Source",
    "Subject",
    "SubjectFile",
    "Url",
    "all_files",
    "check_evidence",
    "evidence_items",
    "files_named",
    "host_of",
    "listed_at",
    "load_all",
    "on_domain",
    "quick_files",
    "validate_files",
    "validate_places",
    "validate_subject",
    "version",
]
