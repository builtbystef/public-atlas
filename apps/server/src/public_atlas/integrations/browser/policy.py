"""Where the browser may go, decided in one place: the allowlist with subdomains, private and
link-local addresses (a hostname is resolved first), `robots.txt`, the pacing shared by every
session in the process, and the resource types never fetched. The browser's route guard, its
tools and the plain HTTP fetches of `read_file` and `robots.txt` all ask this object."""

import asyncio
import ipaddress
import logging
import socket
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import idna

logger = logging.getLogger(__name__)

# The product token `robots.txt` rules are matched against. It is not part of the user agent.
USER_AGENT_TOKEN = "PublicAtlas"  # noqa: S105 - a product token, not a secret
# A current Chrome string: ontario.ca's municipalities list shows "Unable to load data" to
# Playwright's HeadlessChrome default.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)
# Where a context starts, and where a refused navigation is bounced to.
BLANK_PAGE = "about:blank"

# `navigation` is the top-level document, `subframe` a document in an embedded frame, `data`
# whatever a script moves data with (`fetch`, XHR, EventSource, WebSocket, `sendBeacon`), and
# `subresource` the passive assets that render a page.
type RequestKind = Literal["navigation", "subframe", "data", "subresource"]
# Navigation keeps the agent on its sites; data requests keep a page's scripts from reading or
# posting elsewhere. Passive subresources are left alone because a page whose assets are
# aborted renders broken, and sub-frame documents because an embedded portal lives there.
ALLOWLIST_REACH: frozenset[str] = frozenset({"navigation", "data"})
# Playwright resource types that carry data rather than render the page; `ping` is `sendBeacon`.
DATA_RESOURCE_TYPES = frozenset({"fetch", "xhr", "eventsource", "websocket", "ping", "preflight"})
# Never fetched: a page's text and accessibility tree need none of these, and they are most of
# the requests a host's rate limit counts.
UNREAD_RESOURCE_TYPES = frozenset({"image", "media", "font"})

UNREAD = "not fetched: images, fonts and media are not needed to read a page"
PRIVATE_ADDRESS = "blocked private or link-local address"
UNRESOLVED = "host that did not resolve, so the private-address block could not clear it"
NO_HOST = "URL with no host"
NOT_ALLOWED = "domain not in allowed_domains"
ROBOTS_DISALLOWED = "disallowed by robots.txt"

ROBOTS_TIMEOUT = 10.0
# Seconds a host that answered 429 rests when it gave no usable `Retry-After`.
THROTTLE_BACKOFF = 120.0
# Hops `get_within_policy` follows before giving up; each hop is checked like the first.
MAX_REDIRECTS = 5

# The resolution cache duplicates one Chromium keeps anyway, so it is short and small. It
# cannot make the block airtight: Chromium resolves the name again before it connects, and a
# record that changes between the two lookups (DNS rebinding) is closed only by a proxy or a
# pinned resolver. The lookup is bounded because it runs inside the route guard.
_RESOLUTION_TTL = 30.0
_RESOLUTION_CACHE_MAX = 256
_RESOLUTION_TIMEOUT = 2.0
_resolution_cache: dict[str, tuple[float, tuple[str, ...]]] = {}

# When each host may next be navigated to, shared by every session in the process: a host sees
# them as one client, and two sessions pacing themselves separately looked like a burst to
# ontario.ca, which throttled the worker for minutes in the first crawl.
_next_slot: dict[str, float] = {}


@dataclass(frozen=True, slots=True)
class Request:
    """One request the browser (or a plain fetch) is about to make, as the policy sees it."""

    url: str
    kind: RequestKind
    # Playwright's own classification: `document`, `xhr`, `image`, `font` and so on.
    resource_type: str = "document"
    # Whether this is the main frame's own document rather than something inside the page.
    top_level: bool = True


def url_host(url: str) -> str | None:
    """The host policy checks run against, or None when there is none."""
    # WHATWG parsing, which Chromium applies, turns a backslash into `/`, so `urlparse` would
    # report a host the browser never connects to.
    if "\\" in url:
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        # Fails closed: a URL `urlparse` rejects is hostless rather than a crash.
        return None


def to_idna(host: str) -> str:
    """`host` in ASCII form, so Unicode and `xn--` spellings compare equal. A host that cannot
    be encoded (an IP literal, an empty label) is returned as it came."""
    host = host.rstrip(".")
    try:
        # UTS46 non-transitional is what Chromium applies.
        return idna.encode(host, uts46=True, transitional=False).decode("ascii")
    except idna.IDNAError, UnicodeError:
        return host


def is_blocked_address(host: str) -> bool:
    """Whether `host`, an IP literal or a loopback name, is not globally routable."""
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        not ip.is_global
        or ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host.rstrip("."))
    except ValueError:
        return False
    return True


async def resolve_host(host: str) -> tuple[str, ...] | None:
    """The addresses `host` resolves to, or None when the lookup did not answer. An unanswered
    lookup is a refusal, not a pass: whoever controls the name controls whether it answers."""
    now = time.monotonic()
    cached = _resolution_cache.get(host)
    if cached is not None and cached[0] > now:
        return cached[1]
    try:
        addresses = await asyncio.wait_for(_getaddrinfo(host), _RESOLUTION_TIMEOUT)
    except TimeoutError, OSError, UnicodeError:
        return None
    if len(_resolution_cache) >= _RESOLUTION_CACHE_MAX:
        _resolution_cache.clear()
    _resolution_cache[host] = (now + _RESOLUTION_TTL, addresses)
    return addresses


async def _getaddrinfo(host: str) -> tuple[str, ...]:  # pragma: no cover
    """The one place a real lookup happens, kept separate so a test can replace it."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return tuple(sorted({str(info[4][0]) for info in infos}))


def domain_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


class BrowserPolicy:
    """Deny wins: a blocked address is refused even when the allowlist names it."""

    def __init__(
        self,
        allowed_domains: Sequence[str],
        *,
        block_private_addresses: bool = True,
        respect_robots: bool = True,
        min_interval: float = 3.0,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        # A list is kept as the policy's own, not copied, so a session may widen it as it goes:
        # a `find_homepage` session adds its candidate and the sites its searches return.
        if isinstance(allowed_domains, list):
            allowed_domains[:] = dict.fromkeys(allowed_domains)
            self.allowed_domains = allowed_domains
        else:
            self.allowed_domains = list(dict.fromkeys(allowed_domains))
        for entry in self.allowed_domains:
            if "*" in entry or entry.startswith("."):
                raise ValueError(
                    f"allowed domain {entry!r} never matches a host: write the bare domain, "
                    "subdomains are included"
                )
        self.block_private_addresses = block_private_addresses
        self.respect_robots = respect_robots
        self.min_interval = min_interval
        # Tests pass a client with a mock transport, for `robots.txt`.
        self._http = http
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_paced_url: str | None = None

    def allow(self, domain: str) -> None:
        """Widen the allowlist for the rest of the session."""
        domain = domain.strip().lower()
        if domain and domain not in self.allowed_domains:
            self.allowed_domains.append(domain)

    def permits(self, host: str) -> bool:
        """Whether the allowlist admits `host`, subdomains included."""
        host = to_idna(host.lower())
        return any(
            domain_matches(host, to_idna(entry.strip().lower()))
            for entry in self.allowed_domains
            if entry.strip()
        )

    def refuse(self, request: Request) -> str | None:
        """Why the browser must not make this request, or None to allow it, from what the URL
        alone says. `about:blank` is always allowed. Other hostless URLs (`data:`, `blob:`) are
        refused as navigation and allowed as page content."""
        if request.url == BLANK_PAGE:
            return None
        host = url_host(request.url)
        if host is not None and self.block_private_addresses and is_blocked_address(host):
            return PRIVATE_ADDRESS
        if host is None:
            return None if request.kind in ("data", "subresource") else NO_HOST
        if request.kind == "subresource" and request.resource_type in UNREAD_RESOURCE_TYPES:
            return UNREAD
        if request.kind in ALLOWLIST_REACH and not self.permits(host):
            return NOT_ALLOWED
        return None

    async def decide(self, request: Request) -> str | None:  # noqa: PLR0911 - one per rule
        """Why the policy refuses `request`, or None: `refuse`, then the host's addresses, and
        for a top-level navigation `robots.txt` and the pacing of its host. Every enforcement
        point goes through here, so a name that points at a private address is caught wherever
        it is asked about."""
        if (reason := self.refuse(request)) is not None:
            return reason
        host = url_host(request.url)
        if host is None:
            return None
        if self.block_private_addresses and not is_ip_literal(host):
            addresses = await resolve_host(host)
            if addresses is None:
                return UNRESOLVED
            if any(is_blocked_address(address) for address in addresses):
                return PRIVATE_ADDRESS
        if request.kind != "navigation" or not request.top_level:
            return None
        # Host and port: a site on another port is another site to robots.txt and to pacing.
        parts = urlsplit(request.url)
        netloc = parts.netloc.rsplit("@", 1)[-1].lower()
        if self.respect_robots and not await self._robots_allow(netloc, request.url):
            return ROBOTS_DISALLOWED
        await self._pace(netloc, request.url)
        return None

    # --- robots.txt ---

    async def _robots_allow(self, netloc: str, url: str) -> bool:
        if netloc not in self._robots:
            self._robots[netloc] = await self._fetch_robots(netloc, urlsplit(url).scheme or "https")
        parser = self._robots[netloc]
        return parser is None or parser.can_fetch(USER_AGENT_TOKEN, url)

    async def _fetch_robots(self, netloc: str, scheme: str) -> RobotFileParser | None:
        """None when there is no usable `robots.txt`: no file or no answer means no rules, as
        crawlers read it. Fetched under the policy as a data request: bounded by the allowlist,
        not by `robots.txt` itself or the pacing."""
        client = self._http or httpx.AsyncClient()
        try:
            request = client.build_request(
                "GET",
                f"{scheme}://{netloc}/robots.txt",
                headers={"User-Agent": USER_AGENT},
                timeout=ROBOTS_TIMEOUT,
            )
            response = await get_within_policy(client, self, request, kind="data")
        except httpx.HTTPError as exc:
            # `RedirectRefused` included: an unreachable file means no rules.
            logger.info("robots.txt for %s not fetched: %s", netloc, exc)
            return None
        finally:
            if self._http is None:
                await client.aclose()
        if response.status_code != httpx.codes.OK:
            return None
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    # --- Pacing ---

    async def _pace(self, netloc: str, url: str) -> None:
        # The browser asks twice per navigation (the tool's check, then the route guard); the
        # second ask must not wait again.
        if url == self._last_paced_url:
            return
        self._last_paced_url = url
        # Reserve the slot before waiting for it, so two sessions that ask at once take
        # consecutive slots rather than the same one.
        now = time.monotonic()
        slot = max(now, _next_slot.get(netloc, 0.0))
        _next_slot[netloc] = slot + self.min_interval
        if slot > now:
            await asyncio.sleep(slot - now)

    async def throttled(self, url: str, retry_after: str | None) -> str:
        """Rest the host for `Retry-After` seconds when it gave a usable one, else
        `THROTTLE_BACKOFF`, for every session in the process; the reason the agent is told."""
        parts = urlsplit(url)
        netloc = parts.netloc.rsplit("@", 1)[-1].lower() or url
        backoff = float(retry_after) if retry_after and retry_after.isdigit() else THROTTLE_BACKOFF
        _next_slot[netloc] = max(_next_slot.get(netloc, 0.0), time.monotonic() + backoff)
        logger.warning("%s is throttling us; its next request waits %.0fs", netloc, backoff)
        return (
            f"{parts.hostname or url} answered 429 Too Many Requests: it is rate limiting this "
            f"client. Work on other sites and come back to it later. Its next request waits "
            f"{backoff:.0f}s."
        )


# --- Plain HTTP under the policy ---


class RedirectRefused(httpx.HTTPError):
    """A redirect led to a URL the policy refuses; the fetch stops there."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason}: {url}")
        self.url = url
        self.reason = reason


async def get_within_policy(
    client: httpx.AsyncClient,
    policy: BrowserPolicy,
    request: httpx.Request,
    *,
    kind: RequestKind = "navigation",
    stream: bool = False,
) -> httpx.Response:
    """Send `request`, following redirects one hop at a time and asking the policy about each
    hop first, as the browser's route guard does. The caller checked the first URL. Raises
    `RedirectRefused` for a hop the policy refuses or that is not a URL, and
    `httpx.TooManyRedirects` past `MAX_REDIRECTS`; with `stream`, the caller closes the response.
    """
    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = await client.send(request, stream=stream, follow_redirects=False)
        except httpx.InvalidURL as exc:
            # Not an `HTTPError`: httpx raises it for a hop built from a malformed `Location`.
            raise RedirectRefused(str(request.url), f"malformed redirect: {exc}") from exc
        if response.next_request is None:
            return response
        await response.aclose()
        # httpx built the hop as a browser would: same method, the headers it keeps across
        # hosts, and the first request's timeout.
        request = response.next_request
        url = str(request.url)
        if (reason := await policy.decide(Request(url=url, kind=kind))) is not None:
            raise RedirectRefused(url, reason)
    raise httpx.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects", request=request)
