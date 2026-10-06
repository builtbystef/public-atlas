"""The files an official list is read from: what a list module declares about each (`Source`),
fetching it once into a local cache and checking its hash, and turning it into lines of text
with one renderer per format. A CSV or spreadsheet is one line per row with the header first,
JSON is one line per record, a web page is its visible text; a ZIP names the member to use.
The text is what the snapshot stores, so a citation's line can be checked against it."""

import csv
import io
import json
import logging
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import IO, Any
from urllib.parse import unquote, urlsplit

import httpx
import openpyxl

from public_atlas.integrations.parse import Parser
from public_atlas.modules.evidence.service import content_hash

logger = logging.getLogger(__name__)

# Between the cells of a table's line.
CELL_SEPARATOR = " | "
DOWNLOAD_TIMEOUT = 120.0
# Tags whose text a reader does not see.
_HIDDEN = frozenset({"script", "style", "noscript", "template", "head"})
# Tags that start a new line of visible text.
_BLOCKS = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
        "header",
        "footer",
        "table",
        "ul",
        "ol",
        "dt",
        "dd",
        "blockquote",
        "pre",
        "hr",
    }
)


class Format(StrEnum):
    CSV = "csv"
    SPREADSHEET = "spreadsheet"
    JSON = "json"
    HTML = "html"
    # Parsed by the parser the loader is given (Docling where it is installed).
    PDF = "pdf"


MEDIA_TYPES = {
    Format.CSV: "text/csv",
    Format.SPREADSHEET: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    Format.JSON: "application/json",
    Format.HTML: "text/html",
    Format.PDF: "application/pdf",
}
ZIP_MEDIA_TYPE = "application/zip"
TABLE_FORMATS = frozenset({Format.CSV, Format.SPREADSHEET})


class ListFileError(Exception):
    """A source file cannot be read as the module declares it: it is missing, its hash is not
    the recorded one, or its format is not one the loader renders."""


@dataclass(frozen=True, slots=True)
class Source:
    """One file a list module reads: where it comes from and how to read it. The hash pins the
    release; a new release means a new hash and a review of the diff it makes."""

    # Unique among the lists; `official_lists.name` is `<module>/<name>`.
    name: str
    title: str
    url: str
    sha256: str
    format: Format
    # The file inside the ZIP at `url`, when it is one.
    member: str | None = None
    # Text formats only.
    encoding: str = "utf-8-sig"
    # Table formats: keep only these columns, in this order. For a wide file read for a few of
    # its columns; the stored text is the kept columns.
    columns: tuple[str, ...] | None = None
    # Table formats: one line per distinct row of the kept columns, first seen first. For a file
    # that repeats the rows of interest once per finer unit.
    distinct: bool = False

    @property
    def filename(self) -> str:
        """The file's own name, from its URL."""
        name = PurePosixPath(unquote(urlsplit(self.url).path)).name
        return name or self.name

    @property
    def media_type(self) -> str:
        return ZIP_MEDIA_TYPE if self.member else MEDIA_TYPES[self.format]

    def cache_path(self, cache_dir: Path) -> Path:
        suffix = PurePosixPath(self.filename).suffix
        return cache_dir / f"{self.name}-{self.sha256[:12]}{suffix}"


@dataclass(frozen=True, slots=True)
class Row:
    """One row of a table, with the line of the text it is."""

    line: int
    cells: dict[str, str]

    def __getitem__(self, column: str) -> str:
        return self.cells[column].strip()

    def get(self, column: str, default: str = "") -> str:
        return self.cells.get(column, default).strip()


@dataclass(frozen=True, slots=True)
class OpenedFile:
    """A source as `entries()` receives it: its bytes as fetched, its text as lines, and the
    rows (a table) or the parsed object (JSON) the lines were made from."""

    source: Source
    data: bytes
    sha256: str
    lines: list[str]
    rows: list[Row] = field(default_factory=list)
    document: Any = None

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def line(self, number: int) -> str:
        """The text's line `number`, counted from 1."""
        return self.lines[number - 1]


# --- Fetching ---


def fetch(source: Source, cache_dir: Path) -> bytes:
    """The file's bytes: from the cache when they are there with the right hash, else
    downloaded, checked and cached."""
    path = source.cache_path(cache_dir)
    if path.exists():
        data = path.read_bytes()
        if content_hash(data) == source.sha256:
            return data
        logger.warning("%s does not match %s's hash; fetching again", path, source.name)
    logger.info("fetching %s", source.url)
    try:
        response = httpx.get(source.url, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ListFileError(f"{source.name}: cannot fetch {source.url}: {exc}") from None
    data = response.content
    found = content_hash(data)
    if found != source.sha256:
        raise ListFileError(
            f"{source.name}: {source.url} has sha256 {found}, not the recorded {source.sha256}. "
            "A new release needs its hash recorded in the list module and the diff reviewed"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def open_source(source: Source, cache_dir: Path, *, parser: Parser | None = None) -> OpenedFile:
    return render(source, fetch(source, cache_dir), parser=parser)


# --- Rendering ---


def render(source: Source, data: bytes, *, parser: Parser | None = None) -> OpenedFile:
    """The file as lines of text, with its rows or parsed object. A PDF goes through `parser`,
    one line of text per line of its pages."""
    digest = content_hash(data)
    if digest != source.sha256:
        raise ListFileError(f"{source.name}: sha256 {digest} is not the recorded {source.sha256}")
    with _member(source, data) as stream:
        if source.format in TABLE_FORMATS:
            raw = (
                _csv_rows(stream, source.encoding)
                if source.format is Format.CSV
                else _sheet_rows(stream)
            )
            lines, rows = _table(source, raw)
            return OpenedFile(source=source, data=data, sha256=digest, lines=lines, rows=rows)
        if source.format is Format.JSON:
            document = json.loads(stream.read().decode(source.encoding))
            return OpenedFile(
                source=source,
                data=data,
                sha256=digest,
                lines=_json_lines(document),
                document=document,
            )
        if source.format is Format.HTML:
            text = stream.read().decode(source.encoding, errors="replace")
            return OpenedFile(source=source, data=data, sha256=digest, lines=visible_lines(text))
        if source.format is Format.PDF:
            if parser is None:
                raise ListFileError(f"{source.name}: a PDF list needs a parser")
            document = parser.parse(stream.read(), source.filename)
            lines = [line for page in document.pages for line in page.splitlines()]
            return OpenedFile(source=source, data=data, sha256=digest, lines=lines)
    raise ListFileError(f"{source.name}: no renderer for {source.format}")  # pragma: no cover


def _member(source: Source, data: bytes) -> IO[bytes]:
    """The bytes to read: the ZIP member, streamed, or the file itself."""
    if source.member is None:
        return io.BytesIO(data)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        return archive.open(source.member)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ListFileError(f"{source.name}: no member {source.member!r}: {exc}") from None


def _csv_rows(stream: IO[bytes], encoding: str) -> Iterator[list[str]]:
    reader = csv.reader(io.TextIOWrapper(stream, encoding=encoding, newline=""))
    yield from reader


def _sheet_rows(stream: IO[bytes]) -> Iterator[list[str]]:
    """The first worksheet, each cell as text."""
    workbook = openpyxl.load_workbook(io.BytesIO(stream.read()), read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        for row in sheet.iter_rows(values_only=True):
            yield ["" if cell is None else str(cell) for cell in row]
    finally:
        workbook.close()


def _table(source: Source, raw: Iterable[list[str]]) -> tuple[list[str], list[Row]]:
    """Lines and rows from a table: the header first, each row's cells joined, the columns kept
    as the source says and repeats dropped when it asks."""
    rows_iter = iter(raw)
    header = next(rows_iter, None)
    if header is None:
        raise ListFileError(f"{source.name}: the table is empty")
    header = [cell.strip() for cell in header]
    if source.columns is not None:
        try:
            keep = [header.index(column) for column in source.columns]
        except ValueError as exc:
            raise ListFileError(f"{source.name}: the table has no column {exc}") from None
        header = list(source.columns)
    else:
        keep = None
    lines = [CELL_SEPARATOR.join(header)]
    rows: list[Row] = []
    seen: set[tuple[str, ...]] = set()
    for raw_cells in rows_iter:
        cells = raw_cells if keep is None else [_cell(raw_cells, index) for index in keep]
        if source.distinct:
            key = tuple(cells)
            if key in seen:
                continue
            seen.add(key)
        lines.append(CELL_SEPARATOR.join(cells))
        rows.append(Row(line=len(lines), cells=dict(zip(header, cells, strict=False))))
    return lines, rows


def _cell(cells: list[str], index: int) -> str:
    return cells[index] if index < len(cells) else ""


def _json_lines(document: Any) -> list[str]:  # noqa: ANN401 - JSON is any value
    records = document if isinstance(document, list) else [document]
    return [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self._current: list[str] = []
        self._hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: ARG002
        if tag in _HIDDEN:
            self._hidden += 1
        if tag in _BLOCKS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _HIDDEN and self._hidden:
            self._hidden -= 1
        if tag in _BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if not self._hidden:
            self._current.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._current).split())
        if text:
            self.lines.append(text)
        self._current = []

    def close(self) -> None:
        super().close()
        self._flush()


def visible_lines(html: str) -> list[str]:
    """A page's visible text, one line per block."""
    parser = _VisibleText()
    parser.feed(html)
    parser.close()
    return parser.lines
