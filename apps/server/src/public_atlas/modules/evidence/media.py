"""What kind of file a download is, and what to do with it: read it as text, send it to the
parse queue, or refuse it."""

import io
import mimetypes
import zipfile
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from public_atlas.modules.evidence.quote_checks import HTML

type Handling = Literal["text", "parse", "unsupported"]

# Media types the parse queue handles, with the extension Docling reads the format from.
PARSED: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    HTML: ".html",
    "text/markdown": ".md",
}
# Structured text that needs no parser.
DIRECT: dict[str, str] = {
    "text/plain": ".txt",
    "text/csv": ".csv",
    # Open data portals serve CSV under this type too (data.ontario.ca does).
    "application/csv": ".csv",
    "application/json": ".json",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/rss+xml": ".xml",
    "application/atom+xml": ".xml",
}
UNSUPPORTED_NOTE = {
    "application/msword": "legacy .doc files are not parsed",
    "application/vnd.ms-excel": "legacy .xls files are not parsed",
    "application/zip": "archives are not parsed",
}
# What a bot check (Imperva, Cloudflare, Akamai, PerimeterX) says instead of the document,
# matched lower case. Such a page comes with HTTP 200: ottawa.ca served one to the sixth
# request for its budget book in half an hour.
CHALLENGE_MARKERS = (
    "pardon our interruption",
    "just a moment...",
    "checking your browser",
    "verify you are human",
    "enable javascript and cookies to continue",
    "attention required! | cloudflare",
    "request unsuccessful. incapsula",
    "access to this page has been denied",
)
CHALLENGE_SCAN = 8192
FILENAME_LENGTH = 200


@dataclass(frozen=True, slots=True)
class Detected:
    media_type: str
    filename: str
    handling: Handling


def detect(data: bytes, content_type: str | None, url: str) -> Detected:
    """The type from the first bytes first, the header second, the name last."""
    header = (content_type or "").split(";")[0].strip().lower() or None
    head = data[:2048].lstrip()
    media: str | None
    if data.startswith(b"%PDF-"):
        media = "application/pdf"
    elif data.startswith(b"PK\x03\x04"):
        media = _zip_type(data) or (header if header in PARSED else "application/zip")
    elif data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        media = header if header in UNSUPPORTED_NOTE else "application/msword"
    elif head[:15].lower().startswith((b"<!doctype html", b"<html")):
        media = HTML
    elif header and header != "application/octet-stream":
        media = header
    else:
        media, _ = mimetypes.guess_type(urlsplit(url).path)
    if media is None or media == "application/octet-stream":
        media = "text/plain" if _looks_like_text(data) else "application/octet-stream"
    if media.startswith("text/") and media not in PARSED and media not in DIRECT:
        media = "text/plain"
    return Detected(
        media_type=media, filename=filename_for(url, media), handling=handling_of(media)
    )


def handling_of(media: str) -> Handling:
    return "parse" if media in PARSED else "text" if media in DIRECT else "unsupported"


def _zip_type(data: bytes) -> str | None:
    try:
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    except zipfile.BadZipFile:
        return None
    for prefix, media in (
        ("word/", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("xl/", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("ppt/", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
    ):
        if any(name.startswith(prefix) for name in names):
            return media
    return None


def _looks_like_text(data: bytes) -> bool:
    sample = data[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode()
    except UnicodeDecodeError:
        return False
    return True


def filename_for(url: str, media: str) -> str:
    """The URL's last path segment with the extension the parser reads the format from."""
    name = urlsplit(url).path.rsplit("/", 1)[-1] or "file"
    extension = PARSED.get(media) or DIRECT.get(media) or ""
    if extension and not name.lower().endswith(extension):
        name += extension
    return name[:FILENAME_LENGTH]


def challenge_marker(data: bytes) -> str | None:
    text = data[:CHALLENGE_SCAN].decode(errors="replace").lower()
    return next((marker for marker in CHALLENGE_MARKERS if marker in text), None)
