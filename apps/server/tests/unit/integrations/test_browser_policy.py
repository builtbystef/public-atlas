"""The browser policy: the allowlist with subdomains, private addresses, the resource types
never fetched, and the pacing shared by every session in the process."""

import asyncio
import time

import pytest

from public_atlas.integrations.browser import BrowserPolicy, Request
from public_atlas.integrations.browser import policy as policy_module
from public_atlas.modules.graph.service import candidate_domain_name


def navigation(url: str) -> Request:
    return Request(url=url, kind="navigation")


def test_the_policy_covers_subdomains_and_nothing_else():
    allowed = ["ontario.ca", "bidsandtenders.ca", "ontario.ca"]
    policy = BrowserPolicy(allowed)
    assert policy.allowed_domains == ["ontario.ca", "bidsandtenders.ca"]
    # The policy keeps the list itself, so a `find_homepage` session can widen it.
    assert policy.allowed_domains is allowed
    assert policy.block_private_addresses is True
    assert policy.refuse(navigation("https://www.ontario.ca/page/x")) is None
    assert policy.refuse(navigation("https://toronto.bidsandtenders.ca/")) is None
    assert policy.refuse(navigation("https://toronto.ca/")) == policy_module.NOT_ALLOWED
    policy.allow("Toronto.ca")
    assert policy.refuse(navigation("https://toronto.ca/")) is None
    assert policy.refuse(navigation("http://169.254.169.254/")) == policy_module.PRIVATE_ADDRESS
    assert policy.refuse(navigation("http://localhost:8000/")) == policy_module.PRIVATE_ADDRESS
    # Deny wins: a private address on the allowlist is still refused.
    policy.allow("127.0.0.1")
    assert policy.refuse(navigation("http://127.0.0.1/")) == policy_module.PRIVATE_ADDRESS
    assert BrowserPolicy([], block_private_addresses=False).refuse(
        navigation("http://127.0.0.1/")
    ) == (policy_module.NOT_ALLOWED)


def test_a_candidate_domain_admits_the_apex_and_every_subdomain():
    """A first link to `www.toronto.ca` makes `toronto.ca` the candidate, so the site can redirect
    to the apex or to `en.toronto.ca` inside its own `find_homepage` assignment."""
    assert candidate_domain_name("www.toronto.ca") == "toronto.ca"
    policy = BrowserPolicy([candidate_domain_name("www.toronto.ca")])
    for url in ("https://www.toronto.ca/", "https://toronto.ca/", "https://en.toronto.ca/"):
        assert policy.refuse(navigation(url)) is None, url


def test_hosts_compare_in_their_idna_form():
    policy = BrowserPolicy(["münchen.de"])
    assert policy.refuse(navigation("https://www.xn--mnchen-3ya.de/")) is None
    assert policy.refuse(navigation("https://www.münchen.de/")) is None


def test_an_entry_that_never_matches_is_refused_up_front():
    with pytest.raises(ValueError, match="never matches"):
        BrowserPolicy(["*.ontario.ca"])
    with pytest.raises(ValueError, match="never matches"):
        BrowserPolicy([".ontario.ca"])


def test_what_the_allowlist_bounds_and_what_is_never_fetched():
    policy = BrowserPolicy(["ontario.ca"])
    # Scripts may not move data off the allowed sites.
    assert policy.refuse(Request(url="https://evil.example/api", kind="data")) == (
        policy_module.NOT_ALLOWED
    )
    # A page's passive assets and embedded frames load from anywhere public.
    assert (
        policy.refuse(
            Request(url="https://cdn.example/app.js", kind="subresource", resource_type="script")
        )
        is None
    )
    assert (
        policy.refuse(
            Request(url="https://escribe.example/portal", kind="subframe", top_level=False)
        )
        is None
    )
    # Images, fonts and media are never fetched.
    for resource_type in ("image", "font", "media"):
        request = Request(
            url="https://www.ontario.ca/x.png", kind="subresource", resource_type=resource_type
        )
        assert policy.refuse(request) == policy_module.UNREAD
    # Hostless URLs: refused as navigation, allowed as page content.
    assert policy.refuse(navigation("data:text/html,hi")) == policy_module.NO_HOST
    assert policy.refuse(Request(url="blob:abc", kind="subresource")) is None
    assert policy.refuse(navigation("about:blank")) is None


def test_navigations_on_one_host_are_paced_and_the_route_guards_second_ask_waits_no_more(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(policy_module, "_next_slot", {})
    policy = BrowserPolicy(
        ["example.ca"], block_private_addresses=False, respect_robots=False, min_interval=0.3
    )

    async def two_navigations() -> float:
        started = time.monotonic()
        for path in ("/", "/agency"):
            request = navigation(f"https://example.ca{path}")
            assert await policy.decide(request) is None
            assert await policy.decide(request) is None  # the route guard asks again
        return time.monotonic() - started

    elapsed = asyncio.run(two_navigations())
    assert 0.3 <= elapsed < 1.0


def test_a_throttled_host_rests_for_every_session(monkeypatch: pytest.MonkeyPatch):
    slots: dict[str, float] = {}
    monkeypatch.setattr(policy_module, "_next_slot", slots)
    policy = BrowserPolicy(["example.ca"], respect_robots=False)

    async def throttle_twice() -> tuple[str, str]:
        with_header = await policy.throttled("https://www.example.ca/list", "9")
        assert slots["www.example.ca"] >= time.monotonic() + 8
        without = await policy.throttled("https://www.example.ca/list", "soon")
        assert slots["www.example.ca"] >= time.monotonic() + policy_module.THROTTLE_BACKOFF - 1
        return with_header, without

    with_header, without = asyncio.run(throttle_twice())
    assert "429" in with_header
    assert "waits 9s" in with_header
    assert f"waits {policy_module.THROTTLE_BACKOFF:.0f}s" in without


def test_a_name_that_points_at_a_private_address_is_caught_when_resolved(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(policy_module, "_resolution_cache", {})

    async def resolve(host: str) -> tuple[str, ...]:
        return ("10.0.0.5",) if host == "internal.ontario.ca" else ("93.184.216.34",)

    monkeypatch.setattr(policy_module, "_getaddrinfo", resolve)
    policy = BrowserPolicy(["ontario.ca"], respect_robots=False, min_interval=0)

    async def decide() -> tuple[str | None, str | None]:
        return (
            await policy.decide(navigation("https://internal.ontario.ca/")),
            await policy.decide(navigation("https://www.ontario.ca/")),
        )

    assert asyncio.run(decide()) == (policy_module.PRIVATE_ADDRESS, None)
