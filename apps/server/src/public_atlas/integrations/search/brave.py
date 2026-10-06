"""Brave Search API (https://api.search.brave.com/app/documentation/web-search): one HTTP
request per call."""

import httpx

from public_atlas.integrations.search.base import SearchFailed, SearchResult

ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
TIMEOUT = 20.0
# The most results one request returns.
MAX_COUNT = 20


class BraveSearcher:
    name = "brave"

    def __init__(self, api_key: str, *, http: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        # Tests pass a client with a mock transport.
        self._http = http

    async def search(self, query: str, *, count: int) -> list[SearchResult]:
        client = self._http or httpx.AsyncClient()
        try:
            response = await client.get(
                ENDPOINT,
                params={"q": query, "count": min(count, MAX_COUNT)},
                headers={"Accept": "application/json", "X-Subscription-Token": self._api_key},
                timeout=TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise SearchFailed(f"search unavailable: {exc}") from exc
        finally:
            if self._http is None:
                await client.aclose()
        if response.status_code != httpx.codes.OK:
            raise SearchFailed(f"search answered {response.status_code}")
        results = response.json().get("web", {}).get("results", [])
        return [
            SearchResult(
                url=result.get("url", ""),
                title=result.get("title", ""),
                snippet=result.get("description", ""),
            )
            for result in results
            if result.get("url")
        ]
