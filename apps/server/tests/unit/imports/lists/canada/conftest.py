"""What Canada's lists' rule tests share: the country's rules, the cached files of a list
(fetched into the cache when they are not there; skipped when they cannot be), and a parser
for the lists read from PDFs, which keeps each file's parsed pages beside the lists cache so a
rule test parses a PDF once per machine. The provincial packages have conftests of their own
for the places their lists attach bodies to."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType

import pytest

from public_atlas.config import Settings
from public_atlas.integrations.parse import DoclingParser, ParsedDocument, Parser
from public_atlas.modules.countries import service as countries
from public_atlas.modules.countries.seeds import canada
from public_atlas.modules.evidence.service import content_hash
from public_atlas.modules.imports import files
from public_atlas.modules.imports.entries import PlaceEntry


@pytest.fixture(scope="package")
def rules() -> countries.CountryRules:
    return countries.rules_from_seed(canada.SEED)


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


def open_sources(module: ModuleType, parser: Parser | None = None) -> dict[str, files.OpenedFile]:
    cache_dir = Settings().lists_cache_dir
    if parser is None and any(source.format is files.Format.PDF for source in module.SOURCES):
        parser = CachedParser(cache_dir)
    try:
        return {
            source.name: files.open_file(source, cache_dir, parser=parser)
            for source in module.SOURCES
        }
    except files.ListFileError as exc:
        pytest.skip(f"the list's files are not cached and could not be fetched: {exc}")
    except ImportError as exc:  # pragma: no cover - the parse dependency group is not installed
        pytest.skip(f"the list has a PDF and Docling is not installed: {exc}")


@pytest.fixture(scope="package")
def sources_of() -> Callable[[ModuleType], dict[str, files.OpenedFile]]:
    """A list module's files, opened as the loader opens them."""
    return open_sources


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
