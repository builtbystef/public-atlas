"""A search engine for tests that answers every query with the results it was given."""

from public_atlas.integrations.search.base import SearchResult


class MemorySearcher:
    name = "memory"

    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or []
        self.queries: list[str] = []

    async def search(self, query: str, *, count: int) -> list[SearchResult]:
        self.queries.append(query)
        return self.results[:count]
