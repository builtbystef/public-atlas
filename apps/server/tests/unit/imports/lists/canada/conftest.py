"""What Canada's lists' rule tests share: the country's rules and the count of sibling
namesakes a list's places must tell apart. The files of a list come from the fixtures every
list's tests share; the provincial packages have conftests of their own for the places their
lists attach bodies to."""

from collections.abc import Callable, Sequence

import pytest

from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.imports.entries import PlaceEntry


@pytest.fixture(scope="package")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(canada.SEED)


@pytest.fixture(scope="package")
def sibling_namesakes(  # noqa: C901 - the loader's matching, replayed step by step
    rules: countries.CountryRules,
) -> Callable[[Sequence[PlaceEntry]], int]:
    """What the loader tells apart, replayed over a list's places: two places under one parent
    whose plain name is a form of the other's must be bodies of different kinds by the
    designators around their names, else the loader would merge them. The number of such pairs,
    for the test to pin."""
    naming = rules.naming

    def kind(entry: PlaceEntry) -> set[int]:
        assert entry.government is not None, entry.name
        return naming.designators_in(
            naming.key(entry.government).replace(naming.key(entry.name), " ")
        )

    def count(entries: Sequence[PlaceEntry]) -> int:
        by_parent: dict[tuple[str, str | None, str | None], list[PlaceEntry]] = {}
        for entry in entries:
            by_parent.setdefault((entry.level, entry.parent, entry.parent_parent), []).append(entry)
        pairs = 0
        for siblings in by_parent.values():
            loaded: dict[str, list[PlaceEntry]] = {}
            for entry in sorted(siblings, key=lambda entry: entry.name):
                plain: set[str] = set()
                for text in (entry.name, *(alias.text for alias in entry.aliases)):
                    plain |= naming.plain_forms(text)
                for form in plain:
                    for earlier in loaded.get(form, []):
                        pair = (earlier.name, earlier.government, entry.name, entry.government)
                        assert kind(earlier), pair
                        assert kind(entry), pair
                        assert not kind(earlier) & kind(entry), pair
                        pairs += 1
                for text in (entry.name, *(alias.text for alias in entry.aliases)):
                    for form in naming.forms(text):
                        loaded.setdefault(form, []).append(entry)
        return pairs

    return count
