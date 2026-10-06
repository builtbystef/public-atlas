"""The agent's browser: a real Chromium behind one policy object (the allowlist with
subdomains, private addresses, `robots.txt`, pacing shared across sessions, the resource types
never fetched), the tools the agent drives it with, and the capture hook that receives every
page it lands on as plain values. `create_browser` builds one from the settings."""

from typing import TYPE_CHECKING

from public_atlas.integrations.browser.base import CaptureHook, FrameLinks, SettledPage
from public_atlas.integrations.browser.policy import (
    MAX_REDIRECTS,
    USER_AGENT,
    USER_AGENT_TOKEN,
    BrowserPolicy,
    RedirectRefused,
    Request,
    get_within_policy,
    is_ip_literal,
)
from public_atlas.integrations.browser.session import BrowserSession, BrowserUnavailableError
from public_atlas.integrations.browser.tools import TOOLS, Browser, Refusal, Screenshot, Text

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from public_atlas.config import Settings


def create_browser(
    settings: Settings,
    allowed_domains: Sequence[str],
    hook: CaptureHook | None,
    *,
    allow_private: bool = False,
    video_dir: Path | None = None,
) -> Browser:
    """The browser one agent session gets: its assignment's allowlist (kept by reference, so a
    `find_homepage` session can widen it), the pacing and `robots.txt` behaviour the settings
    set, and the hook that stores every page it lands on. `allow_private` exists only so tests
    can run against a local fixture server."""
    policy = BrowserPolicy(
        allowed_domains,
        block_private_addresses=not allow_private,
        respect_robots=settings.browser_respect_robots,
        min_interval=settings.browser_min_interval.total_seconds(),
    )
    return Browser(
        policy,
        hook=hook,
        max_content_tokens=settings.browser_max_content_tokens,
        chromium_sandbox=settings.browser_chromium_sandbox,
        video_dir=video_dir,
    )


__all__ = [
    "MAX_REDIRECTS",
    "TOOLS",
    "USER_AGENT",
    "USER_AGENT_TOKEN",
    "Browser",
    "BrowserPolicy",
    "BrowserSession",
    "BrowserUnavailableError",
    "CaptureHook",
    "FrameLinks",
    "RedirectRefused",
    "Refusal",
    "Request",
    "Screenshot",
    "SettledPage",
    "Text",
    "create_browser",
    "get_within_policy",
    "is_ip_literal",
]
