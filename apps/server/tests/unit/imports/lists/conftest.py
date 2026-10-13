"""What every list's rule tests share: a list module's files opened as the loader opens them,
from the lists cache (a missing fetched file is downloaded into it), with Docling for PDFs and
its parsed pages kept beside the cache so a PDF is parsed once per machine; a list's entries,
built once per session; and the places a country's lists load, looked up as the loader does,
with no database.

A list whose files cannot be had skips its tests, unless `PUBLIC_ATLAS_REQUIRE_LISTS=1` (as in
CI, where the cache is restored and warmed first): then they fail. The country and province
packages have conftests of their own for their rules."""

import json
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, NamedTuple, cast

import pytest

from public_atlas.config import Settings
from public_atlas.integrations.parse import DoclingParser, ParsedDocument, Parser
from public_atlas.integrations.storage.memory import MemoryObjectStore
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import SEEDS
from public_atlas.modules.evidence.service import content_hash
from public_atlas.modules.graph.models import IdentifierScheme, Place
from public_atlas.modules.imports import files, service
from public_atlas.modules.imports.entries import Citation, Code, Entry, PlaceEntry
from public_atlas.modules.imports.lists import LISTS

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

type OpenListFile = Callable[[files.ListFile], files.OpenedFile]
type SourcesOf = Callable[[ModuleType], dict[str, files.OpenedFile]]
type EntriesOf = Callable[[str], list[Entry]]
type RulesFor = Callable[[str], countries.CountryRules]
type LoadedPlacesOf = Callable[[str, tuple[str, ...]], "LoadedPlaces"]

# Each country's seed by its country code, the way a list module names its country.
SEED_BY_COUNTRY: dict[str, dict[str, Any]] = {
    seed["settings"]["country_code"]: seed for seed in SEEDS.values()
}


class CachedParser:
    """Docling, remembering what it parsed: a PDF's pages are kept as JSON under `parsed/` in
    the lists cache, by the file's hash and Docling's version, so the Manitoba directory's 55
    pages are parsed once and not on every test run."""

    name = "docling"

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir / "parsed"
        self._docling = DoclingParser(timeout=600, page_batch=10, max_pages=500)
        self.version = self._docling.version

    def warm_up(self) -> None:
        self._docling.warm_up()

    def parse(
        self,
        data: bytes,
        filename: str,
        *,
        start: int = 1,
        limit: int | None = None,
        page_batch: int | None = None,
        tables: bool = False,
    ) -> ParsedDocument:
        """Docling's parse, read back from the cache when this file and range were parsed."""
        rows = "-tables" if tables else ""
        path = self.cache_dir / f"{content_hash(data)}-{self.version}-{start}-{limit}{rows}.json"
        if path.exists():
            saved = json.loads(path.read_text())
            return ParsedDocument(
                pages=tuple(saved["pages"]),
                parser=self.name,
                version=self.version,
                first=saved["first"],
                total=saved["total"],
            )
        document = self._docling.parse(
            data, filename, start=start, limit=limit, page_batch=page_batch, tables=tables
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"pages": list(document.pages), "first": document.first, "total": document.total}
            )
        )
        return document


@pytest.fixture(scope="session")
def open_list_file(*, require_lists: bool) -> OpenListFile:
    """One list file, opened as the loader opens it, once for the session: a file several lists
    read (the census's) is opened for the first and kept. A PDF goes through Docling, loaded
    once for the session."""
    cache_dir = Settings().lists_cache_dir
    parsers: dict[str, Parser] = {}
    opened: dict[tuple[str, str, str | None], files.OpenedFile] = {}

    def unavailable(reason: str) -> None:
        """Fail when the lists are required, else skip."""
        if require_lists:
            pytest.fail(f"PUBLIC_ATLAS_REQUIRE_LISTS=1 and {reason}")
        pytest.skip(reason)

    def open_file(source: files.ListFile) -> files.OpenedFile:
        key = (source.name, source.url, source.sha256)
        if key in opened:
            return opened[key]
        try:
            if source.format is files.Format.PDF:
                parser = parsers.setdefault("docling", CachedParser(cache_dir))
            else:
                parser = None
            opened[key] = files.open_file(source, cache_dir, parser=parser)
        except files.ListFileError as exc:
            unavailable(f"the list's files are not cached and could not be fetched: {exc}")
        except ImportError as exc:  # pragma: no cover - the parse dependency group is not installed
            unavailable(f"the list has a PDF and Docling is not installed: {exc}")
        return opened[key]

    return open_file


@pytest.fixture(scope="session")
def sources_of(open_list_file: OpenListFile) -> SourcesOf:
    """A list module's files, opened as the loader opens them, by source name."""
    return lambda module: {source.name: open_list_file(source) for source in module.SOURCES}


@pytest.fixture(scope="session")
def rules_for() -> RulesFor:
    """A country's rules from its seed, by the country code a list module names."""
    rules: dict[str, countries.CountryRules] = {}

    def rules_of(country_code: str) -> countries.CountryRules:
        if country_code not in rules:
            rules[country_code] = countries.rules_from_seed(SEED_BY_COUNTRY[country_code])
        return rules[country_code]

    return rules_of


@pytest.fixture(scope="session")
def entries_of(sources_of: SourcesOf, rules_for: RulesFor) -> EntriesOf:
    """A list's entries as `load-list` builds them, by the list's name, once for the session."""
    built: dict[str, list[Entry]] = {}

    def entries(name: str) -> list[Entry]:
        if name not in built:
            module = LISTS[name]
            built[name] = module.entries(sources_of(module), rules_for(module.COUNTRY))
        return built[name]

    return entries


# --- The places a country's lists load, as the loader finds them ---


class NamesakePair(NamedTuple):
    """Two places of one name under one parent the loader keeps apart, each by its government:
    the one loaded first, then the other."""

    name: str
    government: str | None
    other_name: str
    other_government: str | None


@dataclass
class _Loaded:
    """A loaded place: the entry it came from, the loader's row for it, and its parent."""

    entry: PlaceEntry
    known: service.Known
    parent: _Loaded | None
    # Its place in the loader's order, which `find` keeps.
    order: int
    children: list[_Loaded] = field(default_factory=list)


class LoadedPlaces:
    """The places a country's lists load, found as `Loader` finds them, with no database: the
    seed's anchors (the country and its provinces or states) and then the places lists'
    entries in the loader's order, each under the parent `Loader._load_place` resolves for it
    and matched by name against the places before it as `Loader._match_place` matches, with
    the loader's own `_other_kind` telling a town from the village of its name. `find` is
    `Loader._find_place`, reading an index by name form instead of scanning the level; the
    lookup test checks the two agree. What the loader would skip or merge is kept, for a
    list's tests to assert there is none."""

    def __init__(self, rules: countries.CountryRules, seed: dict[str, Any]) -> None:
        self.rules = rules
        self.loader = service.Loader(
            # Never touched: the loader's naming and kind rules read `rules` alone.
            session=cast("AsyncSession", None),
            store=MemoryObjectStore(),
            rules=rules,
            list_name="loaded-places",
            files={},
            apply=False,
            report=service.LoadReport("loaded-places", applied=False),
        )
        self.rows: dict[uuid.UUID, Place] = {}
        self.known: dict[str, list[service.Known]] = {level: [] for level in rules.levels}
        self._by_level: dict[str, list[_Loaded]] = {level: [] for level in rules.levels}
        self._by_form: dict[str, dict[str, list[_Loaded]]] = {level: {} for level in rules.levels}
        self._by_code: dict[tuple[IdentifierScheme, str], _Loaded] = {}
        self._of_entry: dict[int, _Loaded] = {}
        # What the loader would do with an entry other than load it as a place of its own:
        # skip it, read it as the place holding its code, as a seed anchor or as an earlier
        # place of its name (`merged`, which a list's test asserts is empty).
        self.skipped: list[str] = []
        self.matched_by_code: list[tuple[str, str]] = []
        self.anchored: list[str] = []
        self.merged: list[tuple[str, str]] = []
        self.told_apart: list[NamesakePair] = []
        self._anchors = 0
        for anchor in seed["places"]:
            self._add(
                PlaceEntry(
                    name=anchor["name"],
                    level=anchor["level"],
                    parent=anchor.get("parent"),
                    government=anchor.get("government"),
                    # An anchor pins no code; the loader never reads it here.
                    code=Code(scheme=IdentifierScheme.STATCAN_SGC, value=f"seed:{anchor['name']}"),
                    citations={"place": Citation(source="seed", line=1)},
                )
            )

    def add(self, entries: Sequence[Entry]) -> None:
        """Load a list's places, in the order the loader takes them."""
        for entry in self.loader.ordered(entries):
            if isinstance(entry, PlaceEntry):
                self._add(entry)

    def _add(self, entry: PlaceEntry) -> None:
        """One entry as `Loader._match_place` takes it: the place holding its code, else the
        place at its level under the same parent that goes by its name, unless its government
        is a body of another kind; else a place of its own."""
        parent = self._parent_of(entry)
        if entry.parent is not None and parent is None:
            return
        coded = self._by_code.get((entry.code.scheme, entry.code.value))
        if coded is not None:
            if coded.entry.level != entry.level:
                self.skipped.append(
                    f"{entry.name}: code {entry.code.value} is held at another level"
                )
            else:
                self.matched_by_code.append((entry.name, coded.entry.name))
                self._of_entry[id(entry)] = coded
            return
        matched = self._namesakes(entry, parent)
        if len(matched) > 1:
            self.skipped.append(f"{entry.name}: {len(matched)} places go by that name")
            return
        if matched:
            if matched[0].order < self._anchors:
                self.anchored.append(entry.name)
            else:
                self.merged.append((entry.name, matched[0].entry.name))
            self._of_entry[id(entry)] = matched[0]
            return
        self._load(entry, parent)

    def _parent_of(self, entry: PlaceEntry) -> _Loaded | None:
        """`Loader._load_place`: the parent, by name at the levels above, under its own parent;
        skipped when it is not one loaded place."""
        if entry.parent is None:
            return None
        levels = self.rules.levels_above(entry.level)
        if entry.parent_level is not None:
            levels = [entry.parent_level]
        found = self._find(entry.parent, levels, parent=entry.parent_parent)
        if len(found) != 1:
            self.skipped.append(f"{entry.name}: {len(found)} places go by {entry.parent!r}")
            return None
        return found[0]

    def _namesakes(self, entry: PlaceEntry, parent: _Loaded | None) -> list[_Loaded]:
        """The loaded places at the entry's level, under its parent, that go by its name and
        whose government is a body of the same kind; the others are noted as told apart."""
        forms = self.loader._plain_forms([entry.name, *(alias.text for alias in entry.aliases)])  # noqa: SLF001
        namesakes = {
            id(other): other
            for form in forms
            for other in self._by_form[entry.level].get(form, [])
            if parent is None or other.parent is parent
        }
        matched = []
        for other in namesakes.values():
            if self.loader._other_kind(entry, other.known):  # noqa: SLF001
                self.told_apart.append(
                    NamesakePair(
                        other.entry.name, other.entry.government, entry.name, entry.government
                    )
                )
            else:
                matched.append(other)
        return matched

    def _load(self, entry: PlaceEntry, parent: _Loaded | None) -> None:
        """The entry as a new place: its row, its name forms and the indexes that find it."""
        row = Place(
            id=uuid.uuid7(),
            name=entry.name,
            country_code=self.rules.country_code,
            administrative_level=entry.level,
            parent_place_id=parent.known.row.id if parent is not None else None,
        )
        names = [entry.name, *(alias.text for alias in entry.aliases)]
        known = service.Known(row, self.loader._forms(names), entry.government)  # noqa: SLF001
        loaded = _Loaded(entry, known, parent, order=len(self.rows))
        if parent is not None:
            parent.children.append(loaded)
        self.rows[row.id] = row
        if entry.citations["place"].source == "seed":
            self._anchors += 1
        else:
            for code in (entry.code, *entry.codes):
                self._by_code[code.scheme, code.value] = loaded
        self.known[entry.level].append(loaded.known)
        self._by_level[entry.level].append(loaded)
        for form in loaded.known.forms:
            self._by_form[entry.level].setdefault(form, []).append(loaded)
        self._of_entry[id(entry)] = loaded

    def _find(self, name: str, levels: list[str], *, parent: str | None) -> list[_Loaded]:
        """`Loader._find_place`, returning every candidate instead of raising on two."""
        forms = self.rules.naming.forms(name)
        found: list[_Loaded] = []
        for level in levels:
            at_level = {
                id(loaded): loaded
                for form in forms
                for loaded in self._by_form.get(level, {}).get(form, [])
            }
            found.extend(sorted(at_level.values(), key=lambda loaded: loaded.order))
        if parent is not None and len(found) > 1:
            wanted = self.rules.naming.forms(parent)
            found = [
                loaded
                for loaded in found
                if loaded.parent is not None and loaded.parent.known.forms & wanted
            ]
        return found

    def find(self, name: str, level: str | None, parent: str | None) -> list[PlaceEntry]:
        """The loaded places that go by `name`, as the loader finds a place for an institution
        or a served place: at the level when one is given, else at any; under the parent when
        one is given. One is a match; none or several would skip the entry."""
        levels = list(self.rules.levels) if level is None else [level]
        return [loaded.entry for loaded in self._find(name, levels, parent=parent)]

    def names_at(self, level: str) -> frozenset[str]:
        return frozenset(loaded.entry.name for loaded in self._by_level[level])

    def under(self, place: PlaceEntry) -> list[PlaceEntry]:
        """The loaded places whose parent is `place`."""
        return [child.entry for child in self._of_entry[id(place)].children]


@pytest.fixture(scope="session")
def make_loaded_places() -> Callable[[countries.CountryRules, dict[str, Any]], LoadedPlaces]:
    """The lookup over places of a test's own, for the lookup's tests."""
    return LoadedPlaces


@pytest.fixture(scope="session")
def loaded_places_of(entries_of: EntriesOf, rules_for: RulesFor) -> LoadedPlacesOf:
    """The places a country's seed anchors and the named lists load, in that order, once per
    set of lists."""
    loaded: dict[tuple[str, tuple[str, ...]], LoadedPlaces] = {}

    def places(country: str, names: tuple[str, ...]) -> LoadedPlaces:
        if (country, names) not in loaded:
            found = LoadedPlaces(rules_for(country), SEED_BY_COUNTRY[country])
            for name in names:
                assert country == LISTS[name].COUNTRY, name
                found.add(entries_of(name))
            loaded[country, names] = found
        return loaded[country, names]

    return places
