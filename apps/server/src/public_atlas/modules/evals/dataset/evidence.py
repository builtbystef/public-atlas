"""The evidence check, a labelling aid: fetch each evidence URL and look for the quote on the
page, so a quote that is not verbatim is caught before the agent is scored against it."""

import asyncio
import html
import re
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path

import httpx

from public_atlas.modules.evals.dataset.schema import SUBJECTS, Evidence, SubjectFile
from public_atlas.modules.evals.dataset.validate import load_all

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0 Safari/537.36 PublicAtlas-evals/0.1"
)
CONCURRENT_FETCHES = 6
FETCH_TIMEOUT = 30.0
HTTP_ERROR = 400
QUOTE_PREVIEW = 80

type Status = str


class _Text(HTMLParser):
    """The visible text of a page, and its links."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hrefs: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        for name, value in attrs:
            if name == "href" and value and value.strip():
                self.hrefs.append(value.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def normalize(text: str) -> str:
    text = html.unescape(text)
    text = text.translate(
        str.maketrans(
            {
                "\u2019": "'",  # right single quotation mark
                "\u2018": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2013": "-",  # en dash
                "\u2014": "-",  # em dash
                "\xa0": " ",
            }
        )
    )
    text = re.sub(r"\s+", " ", text)
    # The parser's text pieces are joined with a space, so "<a>link</a>." reads "link ." until
    # this.
    text = re.sub(r" ([,.;:!?)\]])", r"\1", text)
    return re.sub(r"([(\[]) ", r"\1", text).strip().casefold()


def evidence_items(expected: SubjectFile) -> list[tuple[str, Evidence]]:
    items = [(f"institution {i.key}", i.evidence) for i in expected.institutions]
    items += [
        (f"parent of {i.key}", i.parent.evidence)
        for i in expected.institutions
        if i.parent is not None
    ]
    items += [(f"source {s.institution}/{s.source_type}", s.evidence) for s in expected.sources]
    return items


async def check_one(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, what: str, ev: Evidence
) -> tuple[Status, str]:
    status, msg = await _check_one(client, sem, what, ev)
    # A quote a human confirmed is not a failure on a page the script cannot read.
    if status != "ok" and ev.manual_check:
        return "manual", ""
    return status, msg


async def _check_one(
    client: httpx.AsyncClient, sem: asyncio.Semaphore, what: str, ev: Evidence
) -> tuple[Status, str]:
    async with sem:
        try:
            resp = await client.get(ev.url)
        except httpx.HTTPError as exc:
            return "error", f"{what}: {ev.url} {type(exc).__name__}"
    if resp.status_code >= HTTP_ERROR:
        return "error", f"{what}: {ev.url} HTTP {resp.status_code}"
    ctype = resp.headers.get("content-type", "")
    if "html" not in ctype:
        return "unchecked", f"{what}: {ev.url} ({ctype.split(';')[0]}), check by hand"
    parser = _Text()
    parser.feed(resp.text)
    body = normalize(" ".join(parser.parts))
    if normalize(ev.quote) not in body:
        preview = ev.quote[:QUOTE_PREVIEW]
        return (
            "missing",
            f"{what}: quote not on {ev.url} (JS-rendered page, or not verbatim): {preview!r}",
        )
    if ev.kind == "links_to":
        target = (ev.link_target or "").rstrip("/")
        hrefs = set()
        for h in parser.hrefs:
            try:
                hrefs.add(str(resp.url.join(h)).rstrip("/"))
            except httpx.InvalidURL:
                continue
        if target not in hrefs and not any(h.split("#")[0] == target for h in hrefs):
            return "missing", f"{what}: no link to {ev.link_target} on {ev.url}"
    return "ok", ""


async def check_evidence(files: list[Path], report: Callable[[str], None]) -> dict[Status, int]:
    """Fetch every evidence URL of the subject files among `files` and report each quote that
    is not on its page. The tally by status."""
    subjects, _, errors = load_all([f for f in files if f.parent == SUBJECTS])
    for error in errors:
        report(error)
    sem = asyncio.Semaphore(CONCURRENT_FETCHES)
    tally: dict[Status, int] = {}
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, follow_redirects=True, timeout=FETCH_TIMEOUT
    ) as client:
        for path, expected in subjects.items():
            items = evidence_items(expected)
            results = await asyncio.gather(*(check_one(client, sem, w, e) for w, e in items))
            for status, msg in results:
                tally[status] = tally.get(status, 0) + 1
                if msg:
                    report(f"{path.stem}: [{status}] {msg}")
    if errors:
        tally["invalid"] = len(errors)
    return tally
