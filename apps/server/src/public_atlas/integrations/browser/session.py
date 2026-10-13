"""One agent session's Chromium: launch, the route guard that enforces the policy on every
request of every frame and on every redirect, tabs, popups and dialogs. Nothing starts until
`ensure_page` is first awaited, and leaving the session closes whatever was started."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Self
from urllib.parse import urljoin

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from public_atlas.integrations.browser.policy import (
    DATA_RESOURCE_TYPES,
    MAX_REDIRECTS,
    USER_AGENT,
    BrowserPolicy,
    Request,
    RequestKind,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Coroutine
    from contextlib import AbstractAsyncContextManager

    from playwright.async_api import (
        APIResponse,
        BrowserContext,
        Dialog,
        Page,
        Playwright,
        Route,
        WebSocketRoute,
    )
    from playwright.async_api import Browser as Chromium
    from playwright.async_api import Request as PlaywrightRequest

logger = logging.getLogger(__name__)

# Playwright's own default is one 30000ms deadline for everything. Split in two here: a missed
# element is usually a wrong selector and should fail fast, while a page load legitimately takes
# longer. `0` means no deadline, as it does for Playwright.
DEFAULT_ACTION_TIMEOUT_MS = 5_000
DEFAULT_NAVIGATION_TIMEOUT_MS = 60_000
# A tab is a live renderer process, and the page controls how many it opens. Past the limit a
# new one is closed, so a site that opens windows in a loop costs a bounded amount.
MAX_TABS = 8
# What Chromium reports for a request a route aborted; the guard records the refusal itself.
_ABORTED_FAILURE = "net::ERR_FAILED"
# Requests the guard continues as they are instead of fetching: a stream never ends, and a
# preflight or a beacon carries nothing a page reads. Their URL is checked like any other; a
# redirect of one is followed by Chromium unchecked.
_CONTINUED_RESOURCE_TYPES = frozenset({"eventsource", "preflight", "ping"})
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
# After these a browser repeats anything but a GET or HEAD as a GET without a body.
_METHOD_RESETTING_STATUSES = frozenset({301, 302, 303})
TOO_MANY_REDIRECTS = f"more than {MAX_REDIRECTS} redirects"
CHROMIUM_MISSING = (
    "Chromium is not installed. Run `playwright install chromium` (on a fresh Linux or CI image "
    "`playwright install --with-deps chromium`) and restart the worker."
)


class BrowserUnavailableError(RuntimeError):
    """No browser could be started."""


@dataclass(frozen=True, slots=True)
class Failure:
    """A request the route guard refused or Chromium could not complete, with its cause."""

    url: str
    reason: str


@dataclass(frozen=True, slots=True)
class Redirect:
    """A main-frame navigation of `page` that the server answered with a redirect, held back
    from Chromium: the tool that navigated makes the hop itself, so it is asked about like any
    navigation and the page ends at its real URL."""

    page: Page
    url: str
    to: str


def redirect_target(response: APIResponse) -> str | None:
    """Where a redirect response sends the browser, resolved as the browser would, or None
    when `response` is not one."""
    if response.status not in _REDIRECT_STATUSES:
        return None
    location = response.headers.get("location")
    if not location:
        return None
    return urljoin(response.url, location)


def request_kind(request: PlaywrightRequest, *, top_level: bool) -> RequestKind:
    """A document is a navigation only in the main frame; inside an embedded frame it is what
    loads a portal, which the policy treats differently."""
    if request.resource_type in DATA_RESOURCE_TYPES:
        return "data"
    if request.is_navigation_request():
        return "navigation" if top_level else "subframe"
    return "subresource"


class BrowserSession:
    """How a page is obtained, guarded and released."""

    def __init__(  # noqa: PLR0913 - one argument per setting
        self,
        policy: BrowserPolicy,
        *,
        headless: bool = True,
        chromium_sandbox: bool = True,
        user_agent: str = USER_AGENT,
        launch_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
        video_dir: Path | None = None,
    ) -> None:
        self.policy = policy
        self._headless = headless
        # On by default, unlike Playwright itself: nobody vetted the pages opened here. Off only
        # where the sandbox cannot start.
        self._chromium_sandbox = chromium_sandbox
        self._user_agent = user_agent
        self._launch_timeout_ms = launch_timeout_ms
        # Set when the run records video: one file per page, in this directory.
        self.video_dir = video_dir
        # The tab every tool acts on; None until the browser is launched.
        self.page: Page | None = None
        # Every open tab in opening order; the first is the one the session started on.
        self.pages: list[Page] = []
        # The last refused or failed request since `begin_operation`: Chromium's error page
        # names neither the destination nor the cause.
        self.last_failure: Failure | None = None
        # A main-frame redirect the guard held back, for the tool to make.
        self.redirect: Redirect | None = None
        self.launch_error: str | None = None
        self._driver_cm: AbstractAsyncContextManager[Playwright] | None = None
        self._driver: Playwright | None = None
        self._browser: Chromium | None = None
        self._context: BrowserContext | None = None
        self._event_tasks: set[asyncio.Task[None]] = set()
        self._launch_lock = asyncio.Lock()

    @property
    def version(self) -> str:
        return self._browser.version if self._browser is not None else "unknown"

    def begin_operation(self) -> None:
        """Forget the previous operation's failure and held redirect."""
        self.last_failure = None
        self.redirect = None

    def held_redirect(self, page: Page) -> Redirect | None:
        """The redirect the guard held back from `page`'s last navigation, if any."""
        if self.redirect is not None and self.redirect.page is page:
            return self.redirect
        return None

    def take_redirect(self, page: Page) -> Redirect | None:
        """The redirect held back for `page`, handed over once."""
        redirect = self.held_redirect(page)
        if redirect is not None:
            self.redirect = None
        return redirect

    # --- Launch ---

    async def ensure_page(self) -> Page:
        """The active page, launching Chromium on the first call. Tool calls in one model
        response run concurrently, so the launch is serialized under the lock."""
        if self.launch_error is not None:
            raise BrowserUnavailableError(self.launch_error)
        if self.page is None:
            async with self._launch_lock:
                if self.page is None and self.launch_error is None:
                    if self._driver_cm is None:
                        raise RuntimeError("the browser session is not entered")
                    await self._launch()
            if self.launch_error is not None:
                raise BrowserUnavailableError(self.launch_error)
            if self.page is None:
                raise BrowserUnavailableError("Browser failed to launch.")  # pragma: no cover
        return self.page

    async def _launch(self) -> None:
        """Start the driver and Chromium, then open the guarded page. Every step is bounded by
        `launch_timeout_ms` because all of it runs inside a tool call holding the operation
        lock."""
        if self._driver_cm is None:
            raise RuntimeError("the browser session is not entered")
        if self._driver is None:
            self._driver = await self._driver_cm.__aenter__()
        if self._browser is not None:
            # An attempt that connected and then failed to build its context left a browser.
            stale, self._browser = self._browser, None
            await self._bounded(stale.close())
        chromium = self._driver.chromium
        if not await asyncio.to_thread(Path(chromium.executable_path).exists):
            self.launch_error = CHROMIUM_MISSING
            logger.error(CHROMIUM_MISSING)
            return
        browser = await chromium.launch(
            headless=self._headless,
            chromium_sandbox=self._chromium_sandbox,
            timeout=self._launch_timeout_ms,
        )
        self._browser = browser
        # Service workers can make requests that context routes never see, so they are blocked.
        # Downloads are refused because `read_file` is how a document is read.
        context = await self._bounded(
            browser.new_context(
                service_workers="block",
                accept_downloads=False,
                user_agent=self._user_agent,
                record_video_dir=self.video_dir,
            )
        )
        self._context = context
        page = await self._bounded(context.new_page())
        await self._bounded(context.route("**/*", self._route_guard))
        # A network route never sees a WebSocket.
        await self._bounded(context.route_web_socket("**/*", self._websocket_guard))
        self._wire_page(page)
        self.pages.append(page)
        self.page = page

    async def _bounded[T](self, awaitable: Awaitable[T]) -> T:
        """Run a setup step that has no `timeout` parameter under `launch_timeout_ms`."""
        if self._launch_timeout_ms == 0:
            return await awaitable
        try:
            return await asyncio.wait_for(awaitable, self._launch_timeout_ms / 1000)
        except TimeoutError as exc:
            raise PlaywrightTimeoutError(f"Timeout {self._launch_timeout_ms}ms exceeded.") from exc

    # --- The fence ---

    async def _route_guard(self, route: Route, request: PlaywrightRequest) -> None:
        """Abort what the policy refuses and pass the rest. Every request of every type and
        frame reaches here before the browser moves, and so does every redirect: Chromium
        follows one without asking any route, so the guard fetches the response itself and
        reads where it leads before the browser may go there."""
        page: Page | None
        try:
            frame = request.frame
            page = frame.page
            top_level = frame == page.main_frame
        except PlaywrightError:
            # The frame is already gone; a top-level navigation is the strictest reading.
            page = None
            top_level = True
        kind = request_kind(request, top_level=top_level)
        asked = Request(
            url=request.url,
            kind=kind,
            resource_type=request.resource_type,
            top_level=top_level and kind == "navigation",
        )
        if (reason := await self.policy.decide(asked)) is not None:
            await self._refuse(route, request.url, reason)
            return
        if request.resource_type in _CONTINUED_RESOURCE_TYPES:
            await route.continue_()
            return
        try:
            response = await self._fetch(route, request, asked, page)
            if response is not None:
                await route.fulfill(response=response)
        except PlaywrightError as exc:
            await self._refuse(route, request.url, str(exc).splitlines()[0])

    async def _fetch(
        self, route: Route, request: PlaywrightRequest, asked: Request, page: Page | None
    ) -> APIResponse | None:
        """The response Chromium gets, every redirect on the way checked like the request that
        led to it. A refused hop aborts the request. An allowed main-frame hop is held for the
        tool to make, since a page's URL and history come from the navigation Chromium makes
        itself (a 204 commits nothing). Any other hop is followed here; a frame's document is
        then sent on to where the chain ended, so its links resolve against its real URL. None
        when the route is already answered."""
        timeout = self._launch_timeout_ms
        response = await route.fetch(max_redirects=0, timeout=timeout)
        url = request.url
        hops = 0
        while (hop := redirect_target(response)) is not None:
            if asked.top_level:
                if page is not None:
                    self.redirect = Redirect(page, request.url, hop)
                await route.fulfill(status=204)
                return None
            if (reason := await self.policy.decide(replace(asked, url=hop))) is not None:
                await self._refuse(route, hop, reason)
                return None
            hops += 1
            if hops > MAX_REDIRECTS:
                await self._refuse(route, hop, TOO_MANY_REDIRECTS)
                return None
            if response.status in _METHOD_RESETTING_STATUSES and request.method not in (
                "GET",
                "HEAD",
            ):
                response = await route.fetch(
                    url=hop, method="GET", post_data="", max_redirects=0, timeout=timeout
                )
            else:
                response = await route.fetch(url=hop, max_redirects=0, timeout=timeout)
            url = hop
        if asked.kind == "subframe" and url != request.url:
            # Chromium follows this one unchecked, to a URL checked just above.
            await route.fulfill(status=302, headers={"Location": url})
            return None
        return response

    async def _refuse(self, route: Route, url: str, reason: str) -> None:
        """Abort the request and record why, for the tool to report."""
        self.last_failure = Failure(url, reason)
        # The page may have gone while the response was fetched.
        with contextlib.suppress(PlaywrightError):
            await route.abort()

    async def _websocket_guard(self, websocket: WebSocketRoute) -> None:
        """`context.route` never sees a WebSocket, so without this a page could talk to
        `ws://127.0.0.1:<port>`. A socket is asked about as `data`, bounded by the allowlist."""
        reason = await self.policy.decide(
            Request(url=websocket.url, kind="data", resource_type="websocket", top_level=False)
        )
        if reason is not None:
            self.last_failure = Failure(websocket.url, reason)
            await websocket.close()
            return
        websocket.connect_to_server()

    # --- Page events ---

    def _wire_page(self, page: Page) -> None:
        """Every tab goes through here, or its popups and dialogs are not handled."""
        page.on("popup", self._on_popup)
        page.on("dialog", self._on_dialog)
        page.on("requestfailed", self._on_request_failed)
        page.on("close", self._on_page_closed)

    def _spawn(self, coro: Coroutine[object, object, None]) -> None:
        """Schedule async work from a synchronous page event, holding the task so it is not
        garbage collected mid-flight."""
        task = asyncio.create_task(coro)
        self._event_tasks.add(task)
        task.add_done_callback(self._event_task_done)

    def _event_task_done(self, task: asyncio.Task[None]) -> None:
        """Release the task, retrieving its exception so asyncio does not log it as unretrieved."""
        self._event_tasks.discard(task)
        if not task.cancelled():
            task.exception()

    def _on_popup(self, popup: Page) -> None:
        """Keep a tab the site opened, or close it when the session is full. The tab does not
        become active, so a popup cannot take the page out from under the running operation."""
        if len(self.pages) >= MAX_TABS:
            logger.info("Closing popup %s: the tab limit of %d is reached", popup.url, MAX_TABS)
            self._spawn(popup.close())
            return
        self._wire_page(popup)
        self.pages.append(popup)

    def _on_dialog(self, dialog: Dialog) -> None:
        """A dialog blocks the page until answered; it is always dismissed, as Playwright would
        without a handler, and logged."""
        logger.info("Dismissed %s dialog: %s", dialog.type, dialog.message)
        self._spawn(self._dismiss(dialog))

    async def _dismiss(self, dialog: Dialog) -> None:
        # The page may already be gone.
        with contextlib.suppress(PlaywrightError):
            await dialog.dismiss()

    def _on_request_failed(self, request: PlaywrightRequest) -> None:
        """Record a request Chromium could not complete. An abort is the route guard's, which
        recorded its own reason."""
        failure = request.failure or "failed"
        if failure == _ABORTED_FAILURE:
            return
        self.last_failure = Failure(request.url, failure)

    def _on_page_closed(self, closed: object) -> None:
        """Forget a closed tab; when it was active, the newest tab left becomes active."""
        self.pages = [page for page in self.pages if page is not closed]
        if self.page is closed and self.pages:
            self.page = self.pages[-1]

    # --- Tabs ---

    async def open_tab(self) -> Page:
        """A new blank tab, made active."""
        if self._context is None:
            raise RuntimeError("the browser is not launched")
        page = await self._context.new_page()
        self._wire_page(page)
        self.pages.append(page)
        self.page = page
        return page

    async def activate(self, page: Page) -> Page:
        """Make `page` the tab the tools act on."""
        self.page = page
        await page.bring_to_front()
        return page

    async def close_tab(self, page: Page) -> None:
        await page.close()
        # Repeated here rather than left to the `close` handler: whether Playwright has delivered
        # that event yet must not decide which tab the next tool call acts on.
        self._on_page_closed(page)

    # --- Lifetime ---

    async def __aenter__(self) -> Self:
        """Arm the session without starting anything."""
        self._driver_cm = async_playwright()
        self._driver = None
        self.launch_error = None
        self.last_failure = None
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, *_: object) -> None:
        """Release everything the session started. A teardown error is dropped when the run is
        already unwinding, since the caller's own exception is the one worth reporting."""
        driver_cm, self._driver_cm = self._driver_cm, None
        driver, self._driver = self._driver, None
        if self._event_tasks:
            for task in self._event_tasks:
                task.cancel()
            await asyncio.gather(*self._event_tasks, return_exceptions=True)
            self._event_tasks.clear()
        if driver_cm is None:  # pragma: no cover
            return
        try:
            browser, self._browser = self._browser, None
            self.page = None
            self.pages = []
            self._context = None
            if browser is not None:
                try:
                    await browser.close()
                finally:
                    await driver_cm.__aexit__(None, None, None)
            elif driver is not None:
                await driver_cm.__aexit__(None, None, None)
        except Exception:
            if exc_type is None:
                raise
