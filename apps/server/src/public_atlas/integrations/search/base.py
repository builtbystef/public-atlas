"""What a search engine must provide, and the results it returns."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str


class Searcher(Protocol):
    """Implement this to add a search engine, then return it from `create_searcher`. One call
    is one request, whatever `count` asks for. The `site:` scoping and the filtering to allowed
    domains happen in the tool, not here, so every engine is held to the same rule. `name` keys
    the usage rows and the price list."""

    name: str

    async def search(self, query: str, *, count: int) -> list[SearchResult]: ...


class SearchFailed(Exception):  # noqa: N818 - reads as the outcome it reports
    """The engine did not answer. The message is what the tool tells the model."""
