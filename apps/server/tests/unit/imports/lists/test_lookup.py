"""The lookup the list tests resolve places with answers as the loader does: on a small set of
places, `LoadedPlaces.find` and the loader's own `_find_place` agree on every name, level and
parent, and the loader's by-name match keeps a town and the municipal district of its name
apart while reading a place listed twice as one."""

import asyncio
from collections.abc import Callable
from typing import Any, cast

import pytest

from public_atlas.integrations.storage.memory import MemoryObjectStore
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.graph.models import IdentifierScheme, Place
from public_atlas.modules.imports import service
from public_atlas.modules.imports.entries import AliasEntry, Citation, Code, PlaceEntry


def place(
    name: str,
    level: str,
    parent: str,
    government: str | None = None,
    *,
    parent_parent: str | None = None,
    aliases: tuple[str, ...] = (),
    code: str | None = None,
) -> PlaceEntry:
    return PlaceEntry(
        name=name,
        aliases=tuple(AliasEntry(text=alias) for alias in aliases),
        level=level,
        parent=parent,
        parent_parent=parent_parent,
        government=government,
        code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=code or f"{level}:{name}:{parent}"),
        citations={"place": Citation(source="tiny", line=1)},
    )


# Two Hamiltons, told apart by parent; two Tabers under one parent, told apart by kind; one
# Oakville listed twice under two codes, and once more under its first code; a name with an
# alias and one with a period; a parent not loaded.
ENTRIES = [
    place("Northumberland", "region", "Ontario", "County of Northumberland"),
    place("Hamilton", "municipality", "Ontario", "City of Hamilton"),
    place("Hamilton", "municipality", "Northumberland", "Township of Hamilton"),
    place("Taber", "municipality", "Alberta", "Town of Taber", code="4802"),
    place("Taber", "municipality", "Alberta", "Municipal District of Taber", code="4803"),
    place("Oakville", "municipality", "Ontario", "Town of Oakville", code="3524001"),
    place("Oakville", "municipality", "Ontario", "Town of Oakville", code="3524002"),
    place("Town of Oakville", "municipality", "Ontario", "Town of Oakville", code="3524001"),
    place(
        "Grand-Sault",
        "municipality",
        "New Brunswick",
        "Town of Grand-Sault",
        aliases=("Grand Falls",),
    ),
    place("Sault Ste. Marie", "municipality", "Ontario", "City of Sault Ste. Marie"),
    place("Nowhere", "municipality", "Atlantis", "Town of Nowhere"),
]
QUERIES = [
    "Hamilton",
    "City of Hamilton",
    "Taber",
    "Town of Taber",
    "Oakville",
    "Grand Falls",
    "Sault Ste Marie",
    "Ontario",
    "Nowhere",
    "Elsewhere",
]
LEVELS = [None, "province_territory", "region", "municipality"]
PARENTS = [None, "Ontario", "Northumberland", "Canada", "Atlantis"]


class _Rows:
    """The one call `Loader._find_place` makes of its session: a parent row by id."""

    def __init__(self, rows: dict[Any, Place]) -> None:
        self.rows = rows

    async def get_one(self, _model: type[Place], key: Any) -> Place:
        return self.rows[key]


@pytest.fixture(scope="module")
def rules(rules_for) -> countries.CountryRules:
    return rules_for("CA")


@pytest.fixture(scope="module")
def loaded(rules: countries.CountryRules, make_loaded_places: Callable[..., Any]) -> Any:
    found = make_loaded_places(rules, canada.SEED)
    found.add(ENTRIES)
    return found


def test_the_loader_reads_the_tiny_list_as_the_lookup_says(loaded: Any) -> None:
    assert loaded.skipped == ["Nowhere: 0 places go by 'Atlantis'"]
    assert loaded.merged == [("Oakville", "Oakville")]
    assert loaded.matched_by_code == [("Town of Oakville", "Oakville")]
    assert loaded.anchored == []
    assert loaded.told_apart == [("Taber", "Town of Taber", "Taber", "Municipal District of Taber")]
    assert [entry.government for entry in loaded.find("Taber", "municipality", "Alberta")] == [
        "Town of Taber",
        "Municipal District of Taber",
    ]
    assert [entry.code.value for entry in loaded.find("Oakville", "municipality", None)] == [
        "3524001"
    ]
    assert [entry.parent for entry in loaded.find("Hamilton", None, None)] == [
        "Ontario",
        "Northumberland",
    ]
    assert [entry.parent for entry in loaded.find("Hamilton", "municipality", "Ontario")] == [
        "Ontario"
    ]
    assert [entry.name for entry in loaded.find("Grand Falls", None, None)] == ["Grand-Sault"]
    assert [entry.name for entry in loaded.find("Sault Ste Marie", "municipality", None)] == [
        "Sault Ste. Marie"
    ]
    assert loaded.find("Nowhere", None, None) == []
    assert [
        entry.name for entry in loaded.under(loaded.find("Northumberland", "region", None)[0])
    ] == ["Hamilton"]


def test_the_lookup_finds_places_as_the_loaders_find_place_does(
    rules: countries.CountryRules,
    loaded: Any,
) -> None:
    loader = service.Loader(
        session=cast("Any", _Rows(loaded.rows)),
        store=MemoryObjectStore(),
        rules=rules,
        list_name="tiny",
        files={},
        apply=False,
        report=service.LoadReport("tiny", applied=False),
    )
    loader.known = loaded.known

    async def by_the_loader(name: str, level: str | None, parent: str | None) -> list[str] | str:
        levels = list(rules.levels) if level is None else [level]
        try:
            found = await loader._find_place(name, levels, parent=parent)  # noqa: SLF001
        except service.Skip as skip:
            return str(skip)
        return [] if found is None else [found.name]

    compared = 0
    for name in QUERIES:
        for level in LEVELS:
            for parent in PARENTS:
                answer = loaded.find(name, level, parent)
                expected = asyncio.run(by_the_loader(name, level, parent))
                if isinstance(expected, str) and "sits under" in expected:
                    # The loader refuses a name none of whose places sits under the parent.
                    assert answer == [], (name, level, parent, expected)
                elif isinstance(expected, str):
                    assert len(answer) > 1, (name, level, parent, expected)
                else:
                    assert [entry.name for entry in answer] == expected, (name, level, parent)
                compared += 1
    assert compared == len(QUERIES) * len(LEVELS) * len(PARENTS)
