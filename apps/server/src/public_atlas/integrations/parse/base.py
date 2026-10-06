"""What a parser must provide, and the document it returns."""

from dataclasses import dataclass
from typing import Protocol

# Pages (or sheets) of a document are joined with this in a snapshot's stored text, so a quote's
# page is the count of form feeds before it.
PAGE_SEPARATOR = "\f"


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Markdown, one entry per page (PDF, Word) or sheet (spreadsheet), so a quote can be
    located. `parser` and `version` name the implementation that made it."""

    pages: tuple[str, ...]
    parser: str
    version: str

    @property
    def text(self) -> str:
        """The form the snapshot stores."""
        return PAGE_SEPARATOR.join(self.pages)


class ParseFailed(Exception):  # noqa: N818 - reads as the outcome it records
    """The file could not be parsed; the message is the reason saved with it."""


class Parser(Protocol):
    """Implement this to add a parser, then return it from `create_parser`. Sync and CPU-bound:
    the parse worker runs one job at a time, and nothing else runs a parser."""

    name: str
    version: str

    def warm_up(self) -> None:
        """Loads models now, so the first job does not pay for it."""
        ...

    def parse(self, data: bytes, filename: str, *, page_batch: int | None = None) -> ParsedDocument:
        """Raises `ParseFailed`. `filename` carries the format in its extension. `page_batch`
        asks for fewer pages in memory at a time than the parser's own setting; a parser that
        does not parse in ranges may ignore it."""
        ...
