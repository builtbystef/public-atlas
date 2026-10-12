"""The browser policy: the allowlist with subdomains, private addresses, the resource types
never fetched, the hosts a name resolves to, `robots.txt` with its `Crawl-delay`, and the pacing
shared by every session in the process."""

import asyncio
import socket
import time
from types import SimpleNamespace

import httpx
import pytest

from public_atlas.config import Settings
from public_atlas.integrations.browser import BrowserPolicy, Request, create_browser
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


def test_a_lookalike_suffix_is_not_a_subdomain():
    """`evilontario.ca` ends in the allowed domain's letters and is another site."""
    policy = BrowserPolicy(["ontario.ca"])
    for url in (
        "https://evilontario.ca/",
        "https://notontario.ca/page",
        "https://ontario.ca.evil.example/",
        "https://ontario.co/",
    ):
        assert policy.refuse(navigation(url)) == policy_module.NOT_ALLOWED, url
        assert policy.refuse(Request(url=url, kind="data")) == policy_module.NOT_ALLOWED, url
    for url in ("https://ontario.ca/", "https://www.ontario.ca/", "https://a.b.ontario.ca/x"):
        assert policy.refuse(navigation(url)) is None, url


def test_a_name_that_does_not_resolve_is_refused(monkeypatch: pytest.MonkeyPatch):
    """Whoever controls a name controls whether it answers, so no answer is a refusal, not a
    pass, and nothing is remembered about it."""
    monkeypatch.setattr(policy_module, "_resolution_cache", {})
    monkeypatch.setattr(policy_module, "_RESOLUTION_TIMEOUT", 0.05)

    async def resolve(host: str) -> tuple[str, ...]:
        if host == "slow.ontario.ca":
            await asyncio.sleep(5)
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(policy_module, "_getaddrinfo", resolve)
    policy = BrowserPolicy(["ontario.ca"], respect_robots=False, min_interval=0)

    async def decide() -> tuple[str | None, str | None, str | None]:
        return (
            await policy.decide(navigation("https://gone.ontario.ca/")),
            await policy.decide(navigation("https://slow.ontario.ca/")),
            await policy.decide(Request(url="https://gone.ontario.ca/api", kind="data")),
        )

    assert asyncio.run(decide()) == (policy_module.UNRESOLVED,) * 3
    assert policy_module._resolution_cache == {}  # noqa: SLF001 - the cache is the point


def test_ipv6_and_dot_localhost_addresses_are_refused(monkeypatch: pytest.MonkeyPatch):
    """Deny wins: every loopback, link-local, private and mapped form is refused even when the
    allowlist names it, as a literal and as what a name resolves to."""
    monkeypatch.setattr(policy_module, "_resolution_cache", {})

    async def resolve(host: str) -> tuple[str, ...]:
        return {"v6.ontario.ca": ("::1",), "lan.ontario.ca": ("fe80::1",)}.get(
            host, ("2606:4700::1111",)
        )

    monkeypatch.setattr(policy_module, "_getaddrinfo", resolve)
    policy = BrowserPolicy(
        ["ontario.ca", "foo.localhost", "localhost"], respect_robots=False, min_interval=0
    )
    for url in (
        "http://[::1]:8000/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.0.0.1]/",
        "http://foo.localhost/",
        "http://a.b.localhost:3000/",
        "http://LOCALHOST./",
    ):
        assert policy.refuse(navigation(url)) == policy_module.PRIVATE_ADDRESS, url
        assert (
            policy.refuse(Request(url=url, kind="subresource", resource_type="script"))
            == policy_module.PRIVATE_ADDRESS
        ), url
    # A public IPv6 literal is not private; it is only not on the allowlist.
    assert policy.refuse(navigation("http://[2606:4700::1111]/")) == policy_module.NOT_ALLOWED

    async def resolved() -> tuple[str | None, str | None, str | None]:
        return (
            await policy.decide(navigation("https://v6.ontario.ca/")),
            await policy.decide(navigation("https://lan.ontario.ca/")),
            await policy.decide(navigation("https://www.ontario.ca/")),
        )

    assert asyncio.run(resolved()) == (
        policy_module.PRIVATE_ADDRESS,
        policy_module.PRIVATE_ADDRESS,
        None,
    )


def test_resolution_is_cached_for_the_ttl_then_asked_again(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(policy_module, "_resolution_cache", {})
    monkeypatch.setattr(policy_module, "_next_slot", {})
    clock = [1000.0]
    monkeypatch.setattr(policy_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    asked: list[str] = []

    async def resolve(host: str) -> tuple[str, ...]:
        asked.append(host)
        return ("93.184.216.34",)

    monkeypatch.setattr(policy_module, "_getaddrinfo", resolve)
    policy = BrowserPolicy(["ontario.ca"], respect_robots=False, min_interval=0)

    async def decide_at(*moments: float) -> None:
        for moment in moments:
            clock[0] = moment
            assert await policy.decide(navigation("https://www.ontario.ca/")) is None

    # Looked up at 1000, reused within 30 seconds, asked again once those have passed.
    asyncio.run(decide_at(1000.0, 1029.0, 1031.0))
    assert asked == ["www.ontario.ca", "www.ontario.ca"]


def test_hosts_are_read_as_chromium_reads_them():
    """A URL is judged by the host the browser would connect to: userinfo is not the host, a
    backslash is a `/` to the browser, and what cannot be parsed has no host."""
    policy = BrowserPolicy(["ontario.ca"])
    assert policy.refuse(navigation("https://ontario.ca@evil.example/")) == (
        policy_module.NOT_ALLOWED
    )
    assert policy.refuse(navigation("https://evil.example#@ontario.ca/")) == (
        policy_module.NOT_ALLOWED
    )
    assert policy.refuse(navigation("https://user:pw@www.ontario.ca/")) is None
    assert policy.refuse(navigation("https://ontario.ca\\@evil.example/")) == policy_module.NO_HOST
    assert policy.refuse(navigation("https://evil.example\\.ontario.ca/")) == policy_module.NO_HOST
    assert policy.refuse(navigation("https://[::1")) == policy_module.NO_HOST


def test_two_sessions_on_one_host_take_consecutive_slots(monkeypatch: pytest.MonkeyPatch):
    slots: dict[str, float] = {}
    monkeypatch.setattr(policy_module, "_next_slot", slots)

    def session() -> BrowserPolicy:
        return BrowserPolicy(
            ["example.ca"], block_private_addresses=False, respect_robots=False, min_interval=0.2
        )

    first, second = session(), session()

    async def both_at_once() -> tuple[float, float]:
        started = time.monotonic()
        await asyncio.gather(
            first.decide(navigation("https://example.ca/a")),
            second.decide(navigation("https://example.ca/b")),
        )
        return time.monotonic() - started, slots["example.ca"] - started

    elapsed, reserved = asyncio.run(both_at_once())
    # The second waited one interval for the first; the host's next slot is one more on.
    assert 0.2 <= elapsed < 0.6
    assert 0.4 <= reserved < 0.8


def test_a_crawl_delay_slows_the_host(monkeypatch: pytest.MonkeyPatch):
    """`Crawl-delay` for this client (or for every client) stretches the host's interval when
    it is longer than the policy's own, up to a cap; one for another client, none, or
    `robots.txt` not respected leaves the interval alone."""
    slots: dict[str, float] = {}
    monkeypatch.setattr(policy_module, "_next_slot", slots)

    def reserved(robots: str, *, min_interval: float = 0.0, respect_robots: bool = True) -> float:
        """How far ahead one navigation reserves the host's next slot."""

        def handle(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text=robots)
            return httpx.Response(404)

        async def run() -> float:
            slots.clear()  # each case starts with a host that has never been visited
            async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
                policy = BrowserPolicy(
                    ["slow.example"],
                    block_private_addresses=False,
                    respect_robots=respect_robots,
                    min_interval=min_interval,
                    http=client,
                )
                started = time.monotonic()
                assert await policy.decide(navigation("https://slow.example/")) is None
                return slots["slow.example"] - started

        return asyncio.run(run())

    ours = "User-agent: PublicAtlas\nCrawl-delay: 3\n"
    assert 3.0 <= reserved(ours) < 3.5
    assert 2.0 <= reserved("User-agent: *\nCrawl-delay: 2\n") < 2.5
    assert 5.0 <= reserved(ours, min_interval=5.0) < 5.5
    cap = policy_module.MAX_CRAWL_DELAY
    assert cap <= reserved("User-agent: *\nCrawl-delay: 100000\n") < cap + 0.5
    assert 0.0 <= reserved("User-agent: Googlebot\nCrawl-delay: 9\n") < 0.5
    assert 0.0 <= reserved("User-agent: *\nDisallow: /private\n") < 0.5
    assert 0.0 <= reserved(ours, respect_robots=False) < 0.5


def test_create_browser_blocks_private_addresses_by_default():
    """The settings' default and the wiring both keep the block on; the switch that lifts it
    exists for a fixture server only."""
    settings = Settings(_env_file=None)
    assert settings.browser_allow_private_addresses is False
    browser = create_browser(settings, ["ontario.ca"], None)
    assert (
        browser.policy.block_private_addresses,
        browser.policy.respect_robots,
        browser.policy.min_interval,
    ) == (True, True, 3.0)
    assert browser.policy.refuse(navigation("http://169.254.169.254/")) == (
        policy_module.PRIVATE_ADDRESS
    )
    lifted = create_browser(settings, ["ontario.ca"], None, allow_private=True)
    assert lifted.policy.block_private_addresses is False
