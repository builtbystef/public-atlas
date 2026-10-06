"""File type detection and the words that give a bot check away."""

import pytest

from public_atlas.modules.evidence import media


@pytest.mark.parametrize(
    ("data", "header", "url", "media_type", "handling", "filename"),
    [
        (
            b"%PDF-1.7 ...",
            "application/octet-stream",
            "https://x/budget",
            "application/pdf",
            "parse",
            "budget.pdf",
        ),
        (b"plain words", None, "https://x/notes.txt", "text/plain", "text", "notes.txt"),
        (b"<!DOCTYPE html><html>", "text/plain", "https://x/p", "text/html", "parse", "p.html"),
        (
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
            None,
            "https://x/old",
            "application/msword",
            "unsupported",
            "old",
        ),
        (
            b"\x00\x01\x02",
            None,
            "https://x/blob",
            "application/octet-stream",
            "unsupported",
            "blob",
        ),
        (
            b"<rss>",
            "application/rss+xml",
            "https://x/feed",
            "application/rss+xml",
            "text",
            "feed.xml",
        ),
        (b"a,b\n1,2", "text/csv; charset=utf-8", "https://x/d.csv", "text/csv", "text", "d.csv"),
    ],
)
def test_the_file_type_comes_from_bytes_then_header_then_name(
    data: bytes, header: str | None, url: str, media_type: str, handling: str, filename: str
):
    detected = media.detect(data, header, url)
    assert (detected.media_type, detected.handling, detected.filename) == (
        media_type,
        handling,
        filename,
    )


@pytest.mark.parametrize(
    ("data", "marker"),
    [
        (b"<html><body><h1>Pardon Our Interruption</h1>", "pardon our interruption"),
        (b"<html><head><title>Just a moment...</title>", "just a moment..."),
        (b"<html><body>Council budget 2026: verify you are a resident", None),
        (b"%PDF-1.7 just a moment...", "just a moment..."),
    ],
)
def test_a_bot_check_page_is_known_by_its_words(data: bytes, marker: str | None):
    assert media.challenge_marker(data) == marker
