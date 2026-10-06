"""Plain HTTP fetches under the policy: `robots.txt` and `read_file` follow redirects one checked
hop at a time, as the browser's route guard does."""

import asyncio

import httpx
import pytest

from public_atlas.integrations.browser import (
    MAX_REDIRECTS,
    BrowserPolicy,
    RedirectRefused,
    Request,
    get_within_policy,
)
from public_atlas.integrations.browser import policy as policy_module

ROBOTS = b"User-agent: PublicAtlas\nDisallow: /private\n"


def site(routes: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        return routes.get(str(request.url), httpx.Response(404))

    return httpx.MockTransport(handle)


def policy_for(*domains: str, http: httpx.AsyncClient | None = None) -> BrowserPolicy:
    return BrowserPolicy(
        list(domains), block_private_addresses=False, min_interval=0, respect_robots=True, http=http
    )


def test_a_redirect_is_followed_only_where_the_policy_allows():
    asyncio.run(_redirects_within_the_policy())


async def _redirects_within_the_policy() -> None:
    policy = policy_for("ontario.ca")
    transport = site(
        {
            "https://ontario.ca/a": httpx.Response(301, headers={"location": "/b"}),
            "https://ontario.ca/b": httpx.Response(
                302, headers={"location": "https://www.ontario.ca/c"}
            ),
            "https://www.ontario.ca/c": httpx.Response(200, content=b"here"),
            "https://ontario.ca/leak": httpx.Response(
                302, headers={"location": "https://evil.example/"}
            ),
            "https://evil.example/": httpx.Response(200, content=b"never fetched"),
            "https://ontario.ca/loop": httpx.Response(302, headers={"location": "/loop"}),
        }
    )
    async with httpx.AsyncClient(transport=transport) as client:
        response = await get_within_policy(
            client, policy, client.build_request("GET", "https://ontario.ca/a"), kind="data"
        )
        assert (str(response.url), response.content) == ("https://www.ontario.ca/c", b"here")

        with pytest.raises(RedirectRefused) as refused:
            await get_within_policy(
                client, policy, client.build_request("GET", "https://ontario.ca/leak"), kind="data"
            )
        assert (refused.value.url, refused.value.reason) == (
            "https://evil.example/",
            policy_module.NOT_ALLOWED,
        )

        with pytest.raises(httpx.TooManyRedirects, match=str(MAX_REDIRECTS)):
            await get_within_policy(
                client, policy, client.build_request("GET", "https://ontario.ca/loop"), kind="data"
            )


def test_robots_follows_a_redirect_within_the_policy_and_not_beyond_it():
    asyncio.run(_robots_within_the_policy())


async def _robots_within_the_policy() -> None:
    transport = site(
        {
            "https://ontario.ca/robots.txt": httpx.Response(
                301, headers={"location": "https://moved.example/robots.txt"}
            ),
            "https://moved.example/robots.txt": httpx.Response(200, content=ROBOTS),
            "https://leaky.example/robots.txt": httpx.Response(
                301, headers={"location": "https://evil.example/robots.txt"}
            ),
            "https://evil.example/robots.txt": httpx.Response(
                200, content=b"User-agent: *\nDisallow: /\n"
            ),
        }
    )
    async with httpx.AsyncClient(transport=transport) as client:
        policy = policy_for("ontario.ca", "moved.example", "leaky.example", http=client)
        # Followed: the moved file's rules apply to a top-level navigation.
        assert await policy.decide(Request("https://ontario.ca/private", "navigation")) == (
            policy_module.ROBOTS_DISALLOWED
        )
        assert await policy.decide(Request("https://ontario.ca/public", "navigation")) is None
        # Refused at the hop: the file is unreachable, which means no rules.
        assert await policy.decide(Request("https://leaky.example/x", "navigation")) is None
        # A data request is bounded by the allowlist, not by robots.txt.
        assert await policy.decide(Request("https://ontario.ca/private", "data")) is None


def test_a_malformed_redirect_is_a_refused_hop_not_a_crash():
    """httpx raises `InvalidURL`, not an `HTTPError`, for a hop built from a bad `Location`; a
    town's site sent one, and it took the session down with it."""
    policy = policy_for("ontario.ca")

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a":
            return httpx.Response(302, headers={"location": "https://ontario.ca/b"})
        raise httpx.InvalidURL("For absolute URLs, path must be empty or begin with '/'")

    async def fetch() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(RedirectRefused) as refused:
                await get_within_policy(
                    client, policy, client.build_request("GET", "https://ontario.ca/a"), kind="data"
                )
            assert refused.value.url == "https://ontario.ca/b"
            assert refused.value.reason.startswith("malformed redirect")

    asyncio.run(fetch())
