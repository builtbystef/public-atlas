"""Web search for the `find_homepage` assignment: the port, the engine the settings choose, and
the in-memory double. Every call is one request to the engine, which bills per request; the
caller records it as usage (`assignments.service.record_usage`)."""

from typing import TYPE_CHECKING, Literal

from public_atlas.integrations.search.base import Searcher, SearchFailed, SearchResult
from public_atlas.integrations.search.brave import BraveSearcher
from public_atlas.integrations.search.memory import MemorySearcher

if TYPE_CHECKING:
    from public_atlas.config import Settings

SearchProvider = Literal["brave", "none"]


def create_searcher(settings: Settings) -> Searcher | None:
    """None when no engine is configured: the agent then has no `search` tool and browses the
    directories instead."""
    match settings.search_provider:
        case "brave":
            if settings.brave_api_key is None:
                return None
            return BraveSearcher(settings.brave_api_key.get_secret_value())
        case "none":
            return None


__all__ = [
    "BraveSearcher",
    "MemorySearcher",
    "SearchFailed",
    "SearchProvider",
    "SearchResult",
    "Searcher",
    "create_searcher",
]
