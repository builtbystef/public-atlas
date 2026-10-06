"""The browser tools the agent drives a page with, acting on the active tab of one session.
Each returns a typed result rendered to text at the tool edge. Every page the agent lands on is
handed to the capture hook as plain values once it has gone quiet, without the agent doing
anything."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING, Self

# `TargetClosedError` is not re-exported from `playwright.async_api` (through 1.63);
# `playwright._impl._errors` documents its classes as stable.
from playwright._impl._errors import TargetClosedError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from public_atlas.integrations.browser.base import CaptureHook, FrameLinks, SettledPage
from public_atlas.integrations.browser.policy import (
    BLANK_PAGE,
    USER_AGENT,
    BrowserPolicy,
    Request,
    url_host,
)
from public_atlas.integrations.browser.session import (
    DEFAULT_ACTION_TIMEOUT_MS,
    DEFAULT_NAVIGATION_TIMEOUT_MS,
    MAX_TABS,
    BrowserSession,
    BrowserUnavailableError,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

    from playwright.async_api import Page

logger = logging.getLogger(__name__)

# The tools, in the order the spec lists them (section 8.1); the adapter registers these names.
TOOLS = (
    "navigate",
    "snapshot",
    "click",
    "type_text",
    "press_key",
    "select_option",
    "hover",
    "scroll",
    "wait_for",
    "go_back",
    "go_forward",
    "tabs",
    "get_text",
    "screenshot",
)

DEFAULT_MAX_CONTENT_TOKENS = 4000
_CHARS_PER_TOKEN = 4
# One budget for the whole sweep of a page's child frames, so an unresponsive embed cannot
# spend the action's deadline.
_FRAME_TEXT_BUDGET_MS = 2_000
# How long a settled page is given for its scripts to go quiet before it is captured: ottawa.ca
# adds its eSCRIBE link after load.
QUIET_TIMEOUT_MS = 3000
# Child frames whose links are captured with the page, and links kept per frame.
MAX_FRAMES = 10
MAX_FRAME_LINKS = 2000
# Runs in a frame: its links as the browser resolved them, absolute, with their text.
_FRAME_LINKS = """(max) => Array.from(document.links).slice(0, max).map(
    (a) => [a.href, (a.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 300)])"""
# Chromium's own error page, where a navigation it could not complete lands.
_ERROR_PAGE_SCHEME = "chrome-error://"
# What Playwright says when a navigation turns out to be a file: the context refuses downloads.
_DOWNLOAD_STARTED = "Download is starting"
# Screenshots bypass the token budget, and 5 MB is the strictest per-image limit among model
# providers.
_MAX_SCREENSHOT_BYTES = 5_000_000
HTTP_TOO_MANY_REQUESTS = 429
# What `_scroll_script` reports: before, after and furthest.
_SCROLL_FIELDS = 3
# Pixel coordinates as `'x,y'`.
_COORDINATES = 2


# --- Results ---


@dataclass(frozen=True, slots=True)
class Text:
    """What a tool read: a page's text, a snapshot, a tab list."""

    content: str

    def __str__(self) -> str:
        return self.content


@dataclass(frozen=True, slots=True)
class Refusal:
    """Why the tool did nothing, for the model to act on."""

    reason: str

    def __str__(self) -> str:
        return f"Error: {self.reason}"


@dataclass(frozen=True, slots=True)
class Screenshot:
    url: str
    png: bytes

    def __str__(self) -> str:
        return f"Screenshot captured. URL: {self.url}"


type ToolResult = Text | Refusal | Screenshot


@dataclass(frozen=True, slots=True)
class _Deadlines:
    """The budgets one operation runs under, as time remaining. Both count down from the
    operation's start, so a tool call that makes several Playwright calls cannot spend its
    deadline once per call. A stage after a navigation takes the navigation budget."""

    action_ms: int
    navigation_ms: int
    started: float

    @property
    def action(self) -> int:
        return self._remaining(self.action_ms)

    @property
    def navigation(self) -> int:
        return self._remaining(self.navigation_ms)

    def _remaining(self, budget_ms: int) -> int:
        # `0` is Playwright's "no deadline", so it stays `0`. Every other budget keeps at least
        # 1ms: counting down to zero would remove the deadline just as it expires.
        if budget_ms == 0:
            return 0
        return max(1, budget_ms - int((monotonic() - self.started) * 1000))


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    marker = f"\n[... tool output truncated at {max_chars} characters]"
    if len(marker) >= max_chars:
        return text[:max_chars]
    return f"{text[: max_chars - len(marker)]}{marker}"


def _scroll_script(move: str) -> str:
    return (
        "(() => { const before = window.scrollY; " + move + "; return [before, window.scrollY, "
        'Math.max(0, document.documentElement.scrollHeight - window.innerHeight)].join("|"); })()'
    )


def _scroll_position(reported: object) -> str:
    """Where the page now sits, so a scroll that moved nothing reads differently from one that
    revealed new content and the model can tell that repeating it is pointless."""
    parts = reported.split("|") if isinstance(reported, str) else []
    if len(parts) != _SCROLL_FIELDS or not all(part.lstrip("-").isdigit() for part in parts):
        return ""  # pragma: no cover - `evaluate` returns what the expression built
    before, after, furthest = (int(part) for part in parts)
    if furthest == 0:
        return "The page has nothing to scroll."
    if after >= furthest:
        return "At the bottom of the page."
    if after == 0:
        return "At the top of the page."
    if after == before:
        return f"Position unchanged, {after} of {furthest} px down."
    return f"{after} of {furthest} px down."


class Browser:
    """One agent session's browser: the policy, the Chromium session and the tools. Enter it for
    the session; Chromium starts on the first tool call."""

    def __init__(  # noqa: PLR0913 - one argument per setting
        self,
        policy: BrowserPolicy,
        *,
        hook: CaptureHook | None = None,
        max_content_tokens: int = DEFAULT_MAX_CONTENT_TOKENS,
        action_timeout_ms: int = DEFAULT_ACTION_TIMEOUT_MS,
        navigation_timeout_ms: int = DEFAULT_NAVIGATION_TIMEOUT_MS,
        headless: bool = True,
        chromium_sandbox: bool = True,
        user_agent: str = USER_AGENT,
        video_dir: Path | None = None,
    ) -> None:
        self.policy = policy
        self.session = BrowserSession(
            policy,
            headless=headless,
            chromium_sandbox=chromium_sandbox,
            user_agent=user_agent,
            launch_timeout_ms=navigation_timeout_ms,
            video_dir=video_dir,
        )
        self._hook = hook
        self._max_content_tokens = max_content_tokens
        self._action_timeout_ms = action_timeout_ms
        self._navigation_timeout_ms = navigation_timeout_ms
        # Tool calls from one model response run concurrently; the page takes one at a time.
        self._operation_lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None, *exc: object) -> None:
        await self.session.__aexit__(exc_type, *exc)

    # --- Reading a page ---

    async def _frame_text(self, page: Page, budget_ms: int) -> list[str]:
        """The text of each child frame that has any: page-level reads stop at the frame
        boundary, so an embedded schedule is absent from `page.inner_text`."""
        texts: list[str] = []

        async def sweep() -> None:
            for frame in page.frames[1:]:
                try:
                    text = await frame.inner_text("body", timeout=budget_ms)
                except PlaywrightError:
                    continue
                if text.strip():
                    texts.append(f"[frame {frame.url}]\n{text}")

        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(sweep(), budget_ms / 1000)
        return texts

    async def _page_text(self, page: Page, timeout_ms: int) -> str:
        """The visible text of `page` and its child frames, within the token budget."""
        text = await page.inner_text("body", timeout=timeout_ms)
        budget = (
            _FRAME_TEXT_BUDGET_MS if timeout_ms == 0 else min(timeout_ms, _FRAME_TEXT_BUDGET_MS)
        )
        frames = await self._frame_text(page, budget)
        return self._bound("\n\n".join([text, *frames]))

    def _bound(self, text: str) -> str:
        return _truncate(text, self._max_content_tokens * _CHARS_PER_TOKEN)

    def _text(self, text: str) -> Text:
        return Text(self._bound(text))

    def _refusal(self, reason: str) -> Refusal:
        return Refusal(self._bound(reason))

    # --- Running an operation ---

    def _deadlines(self, timeout_ms: int | None) -> _Deadlines:
        """A per-call override replaces both budgets."""
        if timeout_ms is not None:
            return _Deadlines(action_ms=timeout_ms, navigation_ms=timeout_ms, started=monotonic())
        return _Deadlines(
            action_ms=self._action_timeout_ms,
            navigation_ms=self._navigation_timeout_ms,
            started=monotonic(),
        )

    async def _bounded[T](self, awaitable: Awaitable[T], timeout_ms: int) -> T:
        """Bound a Playwright call that has no `timeout` parameter."""
        if timeout_ms == 0:
            return await awaitable
        try:
            return await asyncio.wait_for(awaitable, timeout_ms / 1000)
        except TimeoutError as exc:
            raise PlaywrightTimeoutError(f"Timeout {timeout_ms}ms exceeded.") from exc

    def _playwright_error(self, action: str, exc: PlaywrightError, timeout_ms: int) -> Refusal:
        """A Playwright error as a result the model can act on, not an exception that ends the
        run."""
        if isinstance(exc, PlaywrightTimeoutError):
            return self._refusal(
                f"{action} timed out after {timeout_ms}ms. The element may not exist or the page "
                "may be slow; try a different selector, or navigate again. Content inside an "
                "iframe needs an `aria-ref=` handle from `snapshot`, not a CSS selector."
            )
        if isinstance(exc, TargetClosedError):
            if not self.session.pages:
                return self._refusal(
                    f"{action} failed: the active tab has closed. Open one with tabs('new')."
                )
            return self._refusal(f"{action} failed: the browser or page was closed unexpectedly.")
        return self._refusal(f"{action} failed: {exc}")

    async def _in_operation(
        self,
        action: str,
        timeout_ms: int | None,
        body: Callable[[Page, _Deadlines], Awaitable[ToolResult]],
        *,
        governed_by_navigation: bool = False,
    ) -> ToolResult:
        """Run `body` as one operation: exclusive use of the page, a validated deadline, the
        page itself (launching Chromium on the first call), and a Playwright or launch failure
        returned as a refusal instead of an exception that ends the run."""
        async with self._operation_lock:
            if timeout_ms is not None and timeout_ms <= 0:
                # `0` means no deadline to Playwright: fine as a configured default, refused as
                # a per-call override the model chooses.
                return self._refusal("timeout_ms must be greater than 0.")
            deadlines = self._deadlines(timeout_ms)
            reported = deadlines.navigation_ms if governed_by_navigation else deadlines.action_ms
            self.session.begin_operation()
            try:
                page = await self.session.ensure_page()
                return await body(page, deadlines)
            except PlaywrightError as exc:
                return self._playwright_error(action, exc, reported)
            except BrowserUnavailableError as exc:
                # Forgotten once reported, so the next call launches again.
                self.session.launch_error = None
                return self._refusal(str(exc))

    async def _enforce_navigation_policy(
        self, page: Page, action: str, timeout_ms: int
    ) -> Refusal | None:
        """After an action, bounce to `about:blank` when the page left the permitted set, so
        disallowed content never reaches the model. The route guard is the primary boundary;
        this is the second layer, since a click or a history move can navigate too."""
        if page.url.startswith(_ERROR_PAGE_SCHEME):
            await page.goto(BLANK_PAGE, timeout=timeout_ms)
            failure = self.session.last_failure
            cause = (
                "the navigation did not complete"
                if failure is None
                else f"{failure.reason}: {failure.url}"
            )
            return self._refusal(
                f"{action} loaded no page ({cause}); the browser is back at about:blank."
            )
        reason = await self.policy.decide(Request(url=page.url, kind="navigation"))
        if reason is None:
            return None
        blocked = page.url
        await page.goto(BLANK_PAGE, timeout=timeout_ms)
        return self._refusal(f"{action} reached a {reason}: {blocked}")

    async def _settle(
        self, page: Page, action: str, deadlines: _Deadlines, *, requested_url: str | None = None
    ) -> Refusal | None:
        """Let the navigation finish, re-check where it landed, and hand the page to the hook:
        every settled page is captured and every bounce logged."""
        await page.wait_for_load_state("domcontentloaded", timeout=deadlines.navigation)
        landed = page.url
        if landed.startswith(_ERROR_PAGE_SCHEME):
            failure = self.session.last_failure
            landed = (failure.url if failure is not None else None) or requested_url or landed
        refusal = await self._enforce_navigation_policy(page, action, deadlines.navigation)
        if self._hook is None:
            return refusal
        if refusal is None:
            await self._capture(self._hook, page, action, requested_url=requested_url)
        else:
            await self._hook.blocked(
                landed, refusal.reason, action=action, requested_url=requested_url
            )
        return refusal

    async def _capture(
        self, hook: CaptureHook, page: Page, action: str, *, requested_url: str | None
    ) -> None:
        """The page as plain values, once it has gone quiet."""
        url = page.url
        if url == BLANK_PAGE or not url_host(url):
            return
        try:
            await page.wait_for_load_state("networkidle", timeout=QUIET_TIMEOUT_MS)
        except PlaywrightError:
            logger.debug("%s did not go quiet in %d ms", url, QUIET_TIMEOUT_MS)
        html = await page.content()
        title = await page.title()
        try:
            text = await page.inner_text("body")
        except PlaywrightError:
            text = ""
        frames: list[FrameLinks] = []
        for frame in page.frames[1 : MAX_FRAMES + 1]:
            if not frame.url.startswith(("http://", "https://")):
                continue
            try:
                links = await frame.evaluate(_FRAME_LINKS, MAX_FRAME_LINKS)
            except PlaywrightError:
                links = []
            frames.append(FrameLinks(frame.url, tuple((str(href), str(t)) for href, t in links)))
        await hook.settled(
            SettledPage(
                url=url,
                title=title,
                html=html,
                text=text,
                frames=tuple(frames),
                action=action,
                requested_url=requested_url if requested_url != url else None,
            )
        )

    # --- The tools ---

    async def navigate(self, url: str, timeout_ms: int | None = None) -> ToolResult:
        """Open a URL and return the page's title and visible text, including the text of any
        embedded frames. Only the allowed domains open; a document (PDF, spreadsheet) opens
        with `read_file`, not here.

        Args:
            url: The full URL, e.g. `https://example.com/page`.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """
        reason = await self.policy.decide(Request(url=url, kind="navigation"))
        if reason is not None:
            # Refused before any operation, so a disallowed URL never launches Chromium.
            if self._hook is not None:
                await self._hook.blocked(url, reason, action="navigate")
            return self._refusal(f"{reason}: {url}")

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            try:
                response = await page.goto(url, timeout=deadlines.navigation)
            except PlaywrightError as exc:
                if _DOWNLOAD_STARTED not in str(exc):
                    raise
                return self._refusal(
                    f"{url} is a file download (a PDF or other document), not a web page. Open "
                    "it with read_file."
                )
            # A 429 is an error to the agent, not the block page's text as if it were the page;
            # the policy decides how long the host rests.
            if response is not None and response.status == HTTP_TOO_MANY_REQUESTS:
                reason = await self.policy.throttled(page.url, response.headers.get("retry-after"))
                if self._hook is not None:
                    await self._hook.blocked(page.url, reason, action="navigate")
                return self._refusal(reason)
            if refusal := await self._settle(page, "navigate", deadlines, requested_url=url):
                return refusal
            # Everything past the load runs on the navigation budget.
            title = await self._bounded(page.title(), deadlines.navigation)
            text = await self._page_text(page, deadlines.navigation)
            return self._text(f"URL: {page.url}\nTitle: {title}\n\n{text}")

        return await self._in_operation("navigate", timeout_ms, body, governed_by_navigation=True)

    async def snapshot(self, timeout_ms: int | None = None) -> ToolResult:
        """Return the page's accessibility tree with `aria-ref` handles for targeting. The
        cheapest way to read a page's structure: pass a handle back to `click`, `type_text`,
        `hover` or `get_text`. It includes iframe content that CSS selectors cannot reach;
        refs inside an embed look like `f1e4`.

        Args:
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            # `mode='ai'` adds `[ref=eN]` handles that the `aria-ref=` selector engine
            # resolves in the frame they came from.
            return self._text(await page.aria_snapshot(mode="ai", timeout=deadlines.action))

        return await self._in_operation("snapshot", timeout_ms, body)

    async def click(self, selector: str, timeout_ms: int | None = None) -> ToolResult:
        """Click an element and return the page's visible text afterwards.

        Args:
            selector: A CSS selector, an `aria-ref=` handle from `snapshot` (the most reliable
                way, and the only one that reaches inside an iframe), or pixel coordinates as
                `'x,y'`.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """
        coordinates: tuple[int, int] | None = None
        parts = selector.split(",", 1)
        if len(parts) == _COORDINATES:
            with contextlib.suppress(ValueError):
                coordinates = (int(parts[0]), int(parts[1]))

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            if coordinates is not None:
                await self._bounded(page.mouse.click(*coordinates), deadlines.action)
            else:
                await page.click(selector, timeout=deadlines.action)
            if (refusal := await self._settle(page, "click", deadlines)) is not None:
                return refusal
            text = await self._page_text(page, deadlines.navigation)
            return self._text(f"Clicked '{selector}'. URL: {page.url}\n\n{text}")

        return await self._in_operation("click", timeout_ms, body)

    async def type_text(
        self, selector: str, text: str, *, sequential: bool = False, timeout_ms: int | None = None
    ) -> ToolResult:
        """Type text into an input field, replacing any existing value. It does not submit:
        use `press_key('Enter')` for a form or search box.

        Args:
            selector: A CSS selector or an `aria-ref=` handle from `snapshot`.
            text: What to type.
            sequential: Send the text as key presses rather than setting the value in one
                step, for autocomplete and masked fields that react to each keystroke.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            if sequential:
                await page.fill(selector, "", timeout=deadlines.action)
                await page.locator(selector).press_sequentially(text, timeout=deadlines.action)
            else:
                await page.fill(selector, text, timeout=deadlines.action)
            after = await self._page_text(page, deadlines.action)
            return self._text(f"Typed into '{selector}'.\n\n{after}")

        return await self._in_operation("type_text", timeout_ms, body)

    async def press_key(
        self, key: str, selector: str | None = None, timeout_ms: int | None = None
    ) -> ToolResult:
        """Press a keyboard key, optionally focusing an element first: `Enter` to submit a
        search box, `Escape` to close an overlay, `Tab` to move between fields.

        Args:
            key: A Playwright key name, e.g. `Enter`, `Escape`, `Tab`, `ArrowDown`.
            selector: Element to focus before pressing; omit for whatever has focus.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            if selector is None:
                await self._bounded(page.keyboard.press(key), deadlines.action)
            else:
                await page.press(selector, key, timeout=deadlines.action)
            # Enter in a search box navigates, so the result is settled like a click.
            if (refusal := await self._settle(page, "press_key", deadlines)) is not None:
                return refusal
            text = await self._page_text(page, deadlines.navigation)
            return self._text(f"Pressed '{key}'.\n\n{text}")

        return await self._in_operation("press_key", timeout_ms, body)

    async def select_option(
        self, selector: str, values: list[str], timeout_ms: int | None = None
    ) -> ToolResult:
        """Choose one or more options in a `<select>` dropdown, which clicking does not open.

        Args:
            selector: A CSS selector for the `<select>`, or an `aria-ref=` handle.
            values: Option values (or labels) to select; one for a single-choice dropdown.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            selected = await page.select_option(selector, values, timeout=deadlines.action)
            if (refusal := await self._settle(page, "select_option", deadlines)) is not None:
                return refusal
            text = await self._page_text(page, deadlines.navigation)
            return self._text(f"Selected {selected} in '{selector}'.\n\n{text}")

        return await self._in_operation("select_option", timeout_ms, body)

    async def hover(self, selector: str, timeout_ms: int | None = None) -> ToolResult:
        """Hover over an element, revealing menus and tooltips that appear on hover.

        Args:
            selector: A CSS selector or an `aria-ref=` handle from `snapshot`.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            await page.hover(selector, timeout=deadlines.action)
            text = await self._page_text(page, deadlines.action)
            return self._text(f"Hovered '{selector}'.\n\n{text}")

        return await self._in_operation("hover", timeout_ms, body)

    async def scroll(
        self,
        direction: str,
        x: int | None = None,
        y: int | None = None,
        timeout_ms: int | None = None,
    ) -> ToolResult:
        """Scroll the page about one screenful and return its visible text. A long list needs
        `scroll('down')` repeated, collecting as you go: a feed that renders only the rows near
        the viewport drops the earlier ones.

        Args:
            direction: `up`, `down`, `left`, `right`, or `top` and `bottom` for the page's ends.
            x: With `y`, scroll the element under that point by a fixed step instead of the page.
            y: With `x`.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """
        # A screenful less a sliver of overlap, so consecutive scrolls skip no line.
        moves = {
            "up": "window.scrollBy(0, -window.innerHeight * 0.9)",
            "down": "window.scrollBy(0, window.innerHeight * 0.9)",
            "left": "window.scrollBy(-window.innerWidth * 0.9, 0)",
            "right": "window.scrollBy(window.innerWidth * 0.9, 0)",
            "top": "window.scrollTo(0, 0)",
            "bottom": "window.scrollTo(0, document.body.scrollHeight)",
        }
        deltas = {"up": (0, -300), "down": (0, 300), "left": (-300, 0), "right": (300, 0)}
        move = moves.get(direction.lower())
        if move is None:
            return self._refusal(
                f"invalid direction {direction!r}; use up/down/left/right/top/bottom"
            )
        delta = deltas.get(direction.lower())

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            if x is not None and y is not None and delta is not None:
                await self._bounded(page.mouse.move(x, y), deadlines.action)
                await self._bounded(page.mouse.wheel(*delta), deadlines.action)
                position = ""
            else:
                # `evaluate` has no `timeout` and hangs while the page's main thread is blocked.
                reported = await self._bounded(
                    page.evaluate(_scroll_script(move)), deadlines.action
                )
                position = f" {_scroll_position(reported)}"
            text = await self._page_text(page, deadlines.action)
            return self._text(f"Scrolled {direction}.{position}\n\n{text}")

        return await self._in_operation("scroll", timeout_ms, body)

    async def wait_for(
        self,
        selector: str | None = None,
        text: str | None = None,
        *,
        gone: bool = False,
        timeout_ms: int | None = None,
    ) -> ToolResult:
        """Wait for content to appear or disappear, then return the page's visible text. Pass
        exactly one of `selector` or `text`; `gone=True` waits out a spinner or overlay. The
        wait covers embedded frames too.

        Args:
            selector: A CSS selector (or an `aria-ref=` handle) to wait for.
            text: Visible text to wait for.
            gone: Wait for the match to disappear instead of appear.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """
        if text is not None and selector is None:
            # Quoted inside `:text()`, so a `>>` or a quote in the text cannot change the query.
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            query = f':text("{escaped}")'
        elif selector is not None and text is None:
            query = selector
        else:
            return self._refusal("wait_for requires exactly one of selector or text.")
        label = selector if selector is not None else text

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            await self._wait_in_any_frame(page, query, deadlines.action, gone=gone)
            after = await self._page_text(page, deadlines.action)
            return self._text(f"{'Gone' if gone else 'Found'} '{label}'.\n\n{after}")

        return await self._in_operation("wait_for", timeout_ms, body)

    async def _wait_in_any_frame(
        self, page: Page, query: str, timeout_ms: int, *, gone: bool
    ) -> None:
        """Wait until `query` matches in the main page or any child frame, or (`gone`) in none
        of them. Appearing is a race, first match wins; disappearing is awaited everywhere,
        since an absent element satisfies `hidden` at once."""
        state = "hidden" if gone else "visible"
        waits = [page.wait_for_selector(query, timeout=timeout_ms, state=state)]
        waits.extend(
            frame.wait_for_selector(query, timeout=timeout_ms, state=state)
            for frame in page.frames[1:]
        )
        tasks = [asyncio.ensure_future(wait) for wait in waits]
        if gone:
            try:
                await asyncio.gather(*tasks)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
            return
        failure: BaseException = PlaywrightTimeoutError(f"Timeout {timeout_ms}ms exceeded.")
        try:
            while tasks:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                tasks = list(pending)
                matched = False
                for task in done:
                    error = task.exception()
                    if error is None:
                        matched = True
                    else:
                        failure = error
                if matched:
                    return
        finally:
            for task in tasks:
                task.cancel()
        raise failure

    async def go_back(self, timeout_ms: int | None = None) -> ToolResult:
        """Go back in the browser history and return the page's visible text.

        Args:
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            if await page.go_back(timeout=deadlines.navigation) is None:
                return self._text("No previous page in browser history.")
            if (refusal := await self._settle(page, "go_back", deadlines)) is not None:
                return refusal
            text = await self._page_text(page, deadlines.navigation)
            return self._text(f"Went back. URL: {page.url}\n\n{text}")

        return await self._in_operation("go_back", timeout_ms, body, governed_by_navigation=True)

    async def go_forward(self, timeout_ms: int | None = None) -> ToolResult:
        """Go forward in the browser history and return the page's visible text.

        Args:
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            if await page.go_forward(timeout=deadlines.navigation) is None:
                return self._text("No next page in browser history.")
            if (refusal := await self._settle(page, "go_forward", deadlines)) is not None:
                return refusal
            text = await self._page_text(page, deadlines.navigation)
            return self._text(f"Went forward. URL: {page.url}\n\n{text}")

        return await self._in_operation("go_forward", timeout_ms, body, governed_by_navigation=True)

    async def tabs(  # noqa: C901 - one branch per action
        self, action: str = "list", index: int | None = None
    ) -> ToolResult:
        """List the open tabs, or switch to, open, or close one. A site opens a second tab for
        a `target="_blank"` link; every other tool acts on the active tab, so `select` it first.

        Args:
            action: `list`, `select`, `close` or `new`. A new tab starts blank and active.
            index: Which tab `select` and `close` act on, as `list` numbers them; `close`
                defaults to the active tab.
        """
        if action not in ("list", "select", "close", "new"):
            return self._refusal(f"unknown tabs action {action!r}; use list, select, close or new.")

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:  # noqa: C901, PLR0911
            session = self.session
            if action == "list":
                return self._text(await self._describe_tabs(page, deadlines))
            if action == "new":
                if len(session.pages) >= MAX_TABS:
                    return self._refusal(
                        f"the tab limit of {MAX_TABS} is reached. Close one first."
                    )
                await self._bounded(session.open_tab(), deadlines.action)
                return self._text(
                    f"Opened blank tab {len(session.pages) - 1} and made it active. "
                    "Load it with navigate."
                )
            if page not in session.pages:
                return self._refusal("the active tab has closed. Open one with tabs('new').")
            target = session.pages.index(page) if index is None else index
            if not 0 <= target < len(session.pages):
                return self._refusal(
                    f"no tab {target}. {len(session.pages)} open; list them with tabs."
                )
            if action == "close":
                if len(session.pages) == 1:
                    return self._refusal("the last tab cannot be closed.")
                closing = session.pages[target]
                await self._bounded(session.close_tab(closing), deadlines.action)
                active = page if closing is not page else session.pages[-1]
                return self._text(
                    f"Closed tab {target}. Active tab is now {session.pages.index(active)}."
                )
            selected = await self._bounded(
                session.activate(session.pages[target]), deadlines.action
            )
            refusal = await self._enforce_navigation_policy(selected, "tabs", deadlines.navigation)
            if refusal is not None:
                if self._hook is not None:
                    await self._hook.blocked(selected.url, refusal.reason, action="tabs")
                return refusal
            if self._hook is not None:
                # A selected tab is a page the agent sees; capture it like any other.
                await self._capture(self._hook, selected, "tabs", requested_url=None)
            text = await self._page_text(selected, deadlines.action)
            return self._text(f"Selected tab {target}. URL: {selected.url}\n\n{text}")

        return await self._in_operation("tabs", None, body)

    async def _describe_tabs(self, active: Page, deadlines: _Deadlines) -> str:
        """One line per open tab, marking the active one. A title that cannot be read does not
        fail the listing: tabs are often listed because one is misbehaving."""
        if not self.session.pages:
            return "No tabs open."
        lines: list[str] = []
        for position, page in enumerate(self.session.pages):
            try:
                title = await self._bounded(page.title(), deadlines.action)
            except PlaywrightError:
                title = "<title unavailable>"
            marker = " (active)" if page is active else ""
            lines.append(f"{position}{marker}: {title} -- {page.url}")
        return "\n".join(lines)

    async def get_text(
        self, selector: str | None = None, timeout_ms: int | None = None
    ) -> ToolResult:
        """Read the page's visible text, or one element's, to read a section of a large page
        that a full read would truncate.

        Args:
            selector: A CSS selector (main frame only) or an `aria-ref=` handle (reaches inside
                an iframe). Omit for the whole page, embedded frames included.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            if not selector:
                return self._text(await self._page_text(page, deadlines.action))
            try:
                text = await page.inner_text(selector, timeout=deadlines.action)
            except PlaywrightError as exc:
                return self._refusal(f"getting text from '{selector}' failed: {exc}")
            return self._text(text)

        return await self._in_operation("get_text", timeout_ms, body)

    async def screenshot(
        self, *, full_page: bool = False, timeout_ms: int | None = None
    ) -> ToolResult:
        """Capture a screenshot of the page, for visual checks only (charts, layout).

        Args:
            full_page: The full scrollable page when true, else the viewport.
            timeout_ms: Override the default timeout for this call, in milliseconds.
        """

        async def body(page: Page, deadlines: _Deadlines) -> ToolResult:
            png = await page.screenshot(full_page=full_page, timeout=deadlines.action)
            if len(png) > _MAX_SCREENSHOT_BYTES:
                return self._refusal(
                    f"screenshot is {len(png)} bytes, over the {_MAX_SCREENSHOT_BYTES} byte image "
                    "limit; capture the viewport (full_page=False) or scroll and capture sections."
                )
            return Screenshot(url=page.url, png=png)

        return await self._in_operation("screenshot", timeout_ms, body)
