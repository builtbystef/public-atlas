"""The document parser behind the `parse` queue: the port, the implementation the settings
choose, and the in-memory double."""

from typing import TYPE_CHECKING, Literal

from public_atlas.integrations.parse.base import PAGE_SEPARATOR, ParsedDocument, ParseFailed, Parser
from public_atlas.integrations.parse.docling import DoclingParser
from public_atlas.integrations.parse.memory import MemoryParser

if TYPE_CHECKING:
    from public_atlas.config import Settings

ParseProvider = Literal["docling", "memory"]


def create_parser(settings: Settings) -> Parser:
    """Building the Docling parser imports nothing of Docling: only `warm_up` and `parse` do,
    so every process can build its resources and only the parse worker needs the dependency."""
    match settings.parse_provider:
        case "docling":
            return DoclingParser(
                timeout=settings.parse_timeout.total_seconds(),
                page_batch=settings.parse_page_batch,
                max_pages=settings.parse_max_pages,
            )
        case "memory":
            return MemoryParser()


__all__ = [
    "PAGE_SEPARATOR",
    "DoclingParser",
    "MemoryParser",
    "ParseFailed",
    "ParseProvider",
    "ParsedDocument",
    "Parser",
    "create_parser",
]
