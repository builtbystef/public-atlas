"""What the browser reports to the app, as plain values: every page that settled and every
URL it refused. `modules/evidence/capture.py` fulfils the hook; it never sees a browser page."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FrameLinks:
    """The links inside one child frame of a page, as the browser resolved them."""

    url: str
    # (href, text) pairs.
    links: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SettledPage:
    """A page the browser landed on and let go quiet."""

    url: str
    title: str
    html: str
    # The rendered text of the main frame.
    text: str
    frames: tuple[FrameLinks, ...]
    # The tool that got there.
    action: str
    # What `navigate` was given, when the site sent the browser on from it.
    requested_url: str | None = None


class CaptureHook(Protocol):
    async def settled(self, page: SettledPage) -> None:
        """A page passed the policy after an action; store it here."""
        ...

    async def blocked(
        self, url: str, reason: str, *, action: str, requested_url: str | None = None
    ) -> None:
        """An attempt to leave the allowlist was refused; log it here. `url` is where the browser
        was at the time, `requested_url` what `navigate` was given."""
        ...
