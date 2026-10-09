"""The eval dataset as shipped: every file reads under its schema, passes the cross-reference
checks against the Canada seed's rules, and holds the ten subjects and 25 governments of spec
section 10."""

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.evals import dataset

SUBJECTS = 10
GOVERNMENTS = 25


@pytest.fixture(scope="module")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(canada.SEED)


def test_every_file_reads_and_validates(rules: countries.CountryRules):
    files = dataset.all_files()
    assert dataset.validate_files(files, rules) == []
    subjects, lists, errors = dataset.load_all(files)
    assert errors == []
    assert len(subjects) == SUBJECTS
    assert len(lists) == 1
    assert all(s.subject.kind == "place" for s in subjects.values())
    (places,) = lists.values()
    assert len(places.municipalities) == GOVERNMENTS


def test_parent_labels_replace_relationships(rules: countries.CountryRules):
    """Every labelled parent is an institution of its file."""
    subjects, _, _ = dataset.load_all(dataset.all_files())
    labelled = 0
    for expected in subjects.values():
        keys = {row.key for row in expected.institutions}
        for row in expected.institutions:
            if row.parent is None:
                continue
            labelled += 1
            assert row.parent.institution in keys or ":" in row.parent.institution
            assert row.parent.evidence.quote
    assert labelled > 0


def test_a_wrong_label_is_refused(rules: countries.CountryRules):
    subjects, _, _ = dataset.load_all(dataset.files_named(["mcgarry"], lists_by_default=False))
    (expected,) = subjects.values()
    data = expected.model_dump(by_alias=True, mode="json")
    # A library at a region is a known type at an unlisted level: it must be expected in review.
    data["subject"]["level"] = "region"
    broken = dataset.SubjectFile.model_validate(data)
    errors = dataset.validate_subject("mcgarry", broken, rules, {})
    assert any("is not listed under level region" in error for error in errors)
    # A homepage with no candidate domain to verify it on.
    data = expected.model_dump(by_alias=True, mode="json")
    data["institutions"][0]["homepage_host"] = "own_domain"
    broken = dataset.SubjectFile.model_validate(data)
    errors = dataset.validate_subject("mcgarry", broken, rules, {})
    assert any("has no candidate_domains entry" in error for error in errors)


def test_files_are_chosen_by_stem():
    files = dataset.files_named(["mcgarry", "ontario-municipalities"], lists_by_default=False)
    assert [path.stem for path in files] == ["mcgarry", "ontario-municipalities"]
    subjects_only = dataset.files_named([], lists_by_default=False)
    assert all(path.parent == dataset.SUBJECTS for path in subjects_only)
    everything = dataset.files_named([], lists_by_default=True)
    assert any(path.parent == dataset.PLACES for path in everything)
    with pytest.raises(ValueError, match="unknown subject"):
        dataset.files_named(["atlantis"], lists_by_default=False)


def test_the_quick_set_is_five_subjects_and_the_places_file():
    quick = dataset.quick_files()
    assert [path.stem for path in quick] == [*dataset.QUICK_SUBJECTS, "ontario-municipalities"]
    assert quick[-1].parent == dataset.PLACES
    assert set(dataset.QUICK_SUBJECTS) < {path.stem for path in dataset.all_files()}


def test_the_version_follows_the_files_contents():
    version = dataset.version()
    assert len(version) == dataset.VERSION_LENGTH
    assert version == dataset.version()
    assert version != dataset.version(dataset.files_named(["mcgarry"], lists_by_default=False))
