"""What every list's rule tests share: a list module's files opened as the loader opens them,
from the lists cache (a fetched file is downloaded into it when it is not there), with Docling
for the lists read from PDFs, which keeps each file's parsed pages beside the cache so a rule
test parses a PDF once per machine. A list whose files cannot be had skips its tests, unless
the suite is told the files must be there (`PUBLIC_ATLAS_REQUIRE_LISTS=1`, as in CI, where the
cache is restored and warmed first): then they fail. The country and province packages have
conftests of their own for their rules and the places their lists attach bodies to."""

import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from public_atlas.config import Settings
from public_atlas.integrations.parse import DoclingParser, ParsedDocument, Parser
from public_atlas.modules.evidence.service import content_hash
from public_atlas.modules.imports import files

type OpenListFile = Callable[[files.ListFile], files.OpenedFile]
type SourcesOf = Callable[[ModuleType], dict[str, files.OpenedFile]]


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


@pytest.fixture(scope="session")
def open_list_file(*, require_lists: bool) -> OpenListFile:
    """One list file, opened as the loader opens it, for the packages that keep a file several
    lists read open once. A PDF goes through Docling, loaded once for the session."""
    cache_dir = Settings().lists_cache_dir
    parsers: dict[str, Parser] = {}

    def unavailable(reason: str) -> None:
        if require_lists:
            pytest.fail(f"PUBLIC_ATLAS_REQUIRE_LISTS=1 and {reason}")
        pytest.skip(reason)

    def open_file(source: files.ListFile) -> files.OpenedFile:
        try:
            if source.format is files.Format.PDF:
                parser = parsers.setdefault("docling", CachedParser(cache_dir))
            else:
                parser = None
            return files.open_file(source, cache_dir, parser=parser)
        except files.ListFileError as exc:
            unavailable(f"the list's files are not cached and could not be fetched: {exc}")
        except ImportError as exc:  # pragma: no cover - the parse dependency group is not installed
            unavailable(f"the list has a PDF and Docling is not installed: {exc}")
        raise AssertionError  # pragma: no cover - `unavailable` never returns

    return open_file


@pytest.fixture(scope="session")
def sources_of(open_list_file: OpenListFile) -> SourcesOf:
    """A list module's files, opened as the loader opens them, by source name."""
    return lambda module: {source.name: open_list_file(source) for source in module.SOURCES}
