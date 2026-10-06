"""The pure text checks behind every finding (spec section 6.2): whether a quote appears word
for word in a stored text, whether a page links to a URL, and whether a passage names an
entity. No database. The text normalization and the mojibake repair live in `shared.text`."""

import difflib
import html
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from public_atlas.integrations.parse import PAGE_SEPARATOR
from public_atlas.modules.graph.service import normalize_url
from public_atlas.shared.text import name_key, normalize_text

HTML = "text/html"
# Shorter than this is a stray word, not a phrase: "the" is on every page. Not a full sentence,
# because a directory entry ("City of Ajax") is the whole finding on a list page, and
# `mentions_any` already requires the quote to name the entity.
MIN_QUOTE_CHARS = 12
_HREF_VALUE = r"""(?:"([^"]*)"|'([^']*)'|([^\s>]+))"""
_HREF = re.compile(rf"href\s*=\s*{_HREF_VALUE}", re.IGNORECASE)
_ANCHOR = re.compile(
    rf"<a\b[^>]*?\bhref\s*=\s*{_HREF_VALUE}[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL
)
_TAG = re.compile(r"<[^>]+>")
# A URL written out in text: a spreadsheet or CSV cell, a PDF's footer. Stops at whitespace and
# at the characters that close a cell or a sentence around one.
_URL_TOKEN = re.compile(r"""(?:https?://|www\.)[^\s<>"'()\[\],;|]+""", re.IGNORECASE)
# `navigate` labels the page's title `Title:`; the label is not page text, so a quote that
# starts with it is the title.
_TITLE_LABEL = re.compile(r"^\s*title:\s*", re.IGNORECASE)
# Whole elements a reader never sees, dropped from a page's HTML before its text is read.
_UNREAD_ELEMENTS = re.compile(
    r"<(script|style|noscript|template|svg)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
PASSAGE_CONTEXT_WORDS = 3
# A best match this unlike the quote is noise, not a hint.
PASSAGE_MIN_RATIO = 0.5


@dataclass(frozen=True, slots=True)
class Found:
    """Where a quote is: the page of a multi-page text, or None in a single-page one."""

    page: int | None


def _squash(text: str) -> str:
    """Normalized text with no whitespace at all, so a block boundary the agent's view ran
    together ("325 Farr DriveP.O. Box") or the renderer broke still matches."""
    return normalize_text(text).replace(" ", "")


def _contains(haystack: str, needle: str) -> bool:
    return needle in normalize_text(haystack) or _squash(needle) in _squash(haystack)


def find_quote(text: str, quote: str) -> Found | None:
    """Where `quote` is in `text`, or None when it is not there, or is too short to count."""
    needle = normalize_text(_TITLE_LABEL.sub("", quote, count=1))
    if len(needle) < MIN_QUOTE_CHARS:
        return None
    pages = text.split(PAGE_SEPARATOR)
    if len(pages) == 1:
        return Found(page=None) if _contains(text, needle) else None
    for number, page in enumerate(pages, start=1):
        if _contains(page, needle):
            return Found(page=number)
    return None


def html_text(page_html: str) -> str:
    """The text a reader could see in a page's HTML, tags gone and entities resolved. Hidden
    elements are kept: a footer revealed on scroll is part of the page, and the browser's
    rendered text may have missed it."""
    stripped = _COMMENT.sub(" ", _UNREAD_ELEMENTS.sub(" ", page_html))
    return html.unescape(_TAG.sub(" ", stripped))


def closest_passage(text: str, quote: str) -> str | None:
    """The passage of `text` most like `quote`, with a few words of context on each side, or
    None when nothing comes close. Shown to the agent so it can copy the page's own wording."""
    words = normalize_text(text).split()
    needle = normalize_text(_TITLE_LABEL.sub("", quote, count=1))
    size = len(needle.split())
    if not words or size == 0:
        return None
    best_ratio, best_start = 0.0, 0
    for start in range(max(1, len(words) - size + 1)):
        window = " ".join(words[start : start + size])
        ratio = difflib.SequenceMatcher(None, window, needle).ratio()
        if ratio > best_ratio:
            best_ratio, best_start = ratio, start
    if best_ratio < PASSAGE_MIN_RATIO:
        return None
    first = max(0, best_start - PASSAGE_CONTEXT_WORDS)
    last = best_start + size + PASSAGE_CONTEXT_WORDS
    return " ".join(words[first:last])


def _resolves_to(raw_href: str, page_url: str, wanted: str) -> bool:
    raw = html.unescape(raw_href)
    if not raw or raw.startswith(("#", "javascript:", "mailto:", "tel:")):
        return False
    try:
        found = normalize_url(urljoin(page_url, raw.strip()))
    except ValueError:
        return False
    return same_address(found, wanted)


def same_address(first: str, second: str) -> bool:
    """Whether two URLs name the same page as a reader would: the scheme, a leading `www.` and
    a trailing slash aside."""

    def key(url: str) -> tuple[str, str, str]:
        parts = urlsplit(normalize_url(url))
        host = (parts.netloc or "").removeprefix("www.")
        return host, parts.path.rstrip("/"), parts.query

    return key(first) == key(second)


def link_in_html(page_html: str, page_url: str, target: str) -> bool:
    wanted = normalize_url(target)
    return any(
        _resolves_to(next(g for g in match.groups() if g is not None), page_url, wanted)
        for match in _HREF.finditer(page_html)
    )


def link_in_text(text: str, page_url: str, target: str) -> bool:
    """Whether a text (a file, not a page) names `target` as a URL: a spreadsheet's website
    column is its link. A bare `www.` address counts, with `http` assumed."""
    wanted = normalize_url(target)
    for match in _URL_TOKEN.finditer(text):
        token = match.group().rstrip(".:")
        if token.lower().startswith("www."):
            token = f"http://{token}"
        if _resolves_to(token, page_url, wanted):
            return True
    return False


def link_text(page_html: str, page_url: str, target: str) -> str | None:
    """The visible text of the first anchor to `target`, or None when no anchor with text links
    there (the link may still be in an `<area>` or a bare `href`; `link_in_html` says)."""
    wanted = normalize_url(target)
    for match in _ANCHOR.finditer(page_html):
        *hrefs, inner = match.groups()
        if not _resolves_to(next(g for g in hrefs if g is not None), page_url, wanted):
            continue
        text = " ".join(html.unescape(_TAG.sub(" ", inner)).split())
        if text:
            return text
    return None


def mentions_any(text: str, names: Iterable[str], *, key: Callable[[str], str] = name_key) -> bool:
    """Whether `text` contains one of `names` under `key`: the country's `Naming.key`, which
    knows what "&" stands for in its languages. The name-in-quote check of spec section 6.2."""
    haystack = key(text)
    return any(key(name) in haystack for name in names if name.strip())
