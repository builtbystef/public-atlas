"""The eval dataset (spec section 10): twelve hand-labelled Ontario subjects and a list of 25
governments, as YAML files beside this module, with their schema, validator and evidence check.
`README.md` holds the labelling rules."""

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


def version(files: list[Path] | None = None) -> str:
    """A short hash of the dataset's files, so two eval runs say whether they scored the same
    labels."""
    digest = hashlib.sha256()
    for path in files if files is not None else all_files():
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:VERSION_LENGTH]


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
    "validate_files",
    "validate_places",
    "validate_subject",
    "version",
]
