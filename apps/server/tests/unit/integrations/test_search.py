"""The search port: one request per call, the results it returns, and the engine the settings
choose."""

import asyncio

import httpx
import pytest
from pydantic import SecretStr

from public_atlas.config import Settings
from public_atlas.integrations.search import (
    BraveSearcher,
    MemorySearcher,
    SearchFailed,
    SearchResult,
    create_searcher,
)
from public_atlas.integrations.search.brave import ENDPOINT, MAX_COUNT

ANSWER = {
    "web": {
        "results": [
            {
                "url": "https://www.elmwood.ca/",
                "title": "Township of Elmwood",
                "description": "Home",
            },
            {"title": "no url"},
            {"url": "https://example.org/x", "title": "Elsewhere", "description": "..."},
        ]
    }
}


def brave(handler) -> tuple[BraveSearcher, list[httpx.Request]]:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return handler(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    return BraveSearcher("key", http=client), sent


def test_one_call_is_one_request_with_the_key_and_a_capped_count():
    searcher, sent = brave(lambda _: httpx.Response(200, json=ANSWER))
    results = asyncio.run(searcher.search("Township of Elmwood", count=50))
    assert len(sent) == 1
    assert sent[0].url.copy_with(query=None) == httpx.URL(ENDPOINT)
    assert sent[0].url.params["q"] == "Township of Elmwood"
    assert sent[0].url.params["count"] == str(MAX_COUNT)
    assert sent[0].headers["X-Subscription-Token"] == "key"
    assert results == [
        SearchResult("https://www.elmwood.ca/", "Township of Elmwood", "Home"),
        SearchResult("https://example.org/x", "Elsewhere", "..."),
    ]


def test_an_engine_that_does_not_answer_fails_the_search():
    searcher, _ = brave(lambda _: httpx.Response(429))
    with pytest.raises(SearchFailed, match="answered 429"):
        asyncio.run(searcher.search("x", count=5))

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    searcher, _ = brave(down)
    with pytest.raises(SearchFailed, match="unavailable"):
        asyncio.run(searcher.search("x", count=5))


def test_the_memory_searcher_answers_with_what_it_was_given():
    searcher = MemorySearcher(
        [SearchResult("https://a", "A", ""), SearchResult("https://b", "B", "")]
    )
    assert asyncio.run(searcher.search("q", count=1)) == [SearchResult("https://a", "A", "")]
    assert searcher.queries == ["q"]


def test_the_settings_choose_the_engine():
    assert create_searcher(Settings(search_provider="none")) is None
    # Brave without a key is no engine at all.
    assert create_searcher(Settings(search_provider="brave", brave_api_key=None)) is None
    searcher = create_searcher(Settings(search_provider="brave", brave_api_key=SecretStr("k")))
    assert isinstance(searcher, BraveSearcher)
    assert searcher.name == "brave"
