"""One spelling for text that a page and a list write differently, and the keys two names are
compared by. Shared by the quote checks, the naming rules and the list loader."""

import re
import unicodedata

# Typographic punctuation a page and the agent's view of it spell differently.
_PUNCTUATION = str.maketrans(
    {
        0x2018: "'",  # left single quotation mark
        0x2019: "'",  # right single quotation mark, the apostrophe pages write
        0x201A: "'",
        0x201B: "'",
        0x201C: '"',
        0x201D: '"',
        0x201E: '"',
        0x2013: "-",  # en dash
        0x2014: "-",  # em dash
        0x2212: "-",  # minus sign
        0x00A0: " ",  # no-break space
    }
)
# UTF-8 bytes read as Windows-1252 or Latin-1: a lead byte (U+00C2 to U+00F4) and one to three
# continuation bytes, as either encoding shows them. Written as escapes the regex engine reads,
# so the characters themselves never appear here.
_CONTINUATION = (
    r"\u0080-\u00bf\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192\u02c6\u02dc"
    r"\u2013\u2014\u2018-\u201e\u2020-\u2022\u2026\u2030\u2039\u203a\u20ac\u2122"
)
_MOJIBAKE = re.compile(rf"[\u00c2-\u00f4][{_CONTINUATION}]{{1,3}}")
_AMPERSAND = re.compile(r"\s*&\s*")
_NAME_JOINERS = re.compile(r"[/\-]")


def repair_mojibake(text: str) -> str:
    """UTF-8 read as Windows-1252 or Latin-1 put right: "CafÃ©" means "Café", "ÐœÐ¾ÑÐºÐ²Ð°"
    means "Москва". A run that does not decode cleanly is left as it is."""

    def fix(match: re.Match[str]) -> str:
        run = match.group()
        try:
            return b"".join(_single_byte(char) for char in run).decode("utf-8")
        except UnicodeError:
            return run

    return _MOJIBAKE.sub(fix, text)


def _single_byte(char: str) -> bytes:
    """The byte a misreading turned into `char`: Windows-1252's, or Latin-1's for the bytes
    Windows-1252 leaves undefined."""
    try:
        return char.encode("cp1252")
    except UnicodeEncodeError:
        return char.encode("latin-1")


def normalize_text(text: str) -> str:
    """Case folded, whitespace collapsed, typographic punctuation evened out, mojibake
    repaired: the form two texts are compared in."""
    text = repair_mojibake(text).translate(_PUNCTUATION)
    return " ".join(unicodedata.normalize("NFKC", text).split()).casefold()


def name_key(text: str) -> str:
    """Normalized, with "&" a word of its own and the slashes and hyphens that join two place
    names read as spaces, so "Elm/Oak" and "Elm-Oak" are both "elm oak". What "&" stands for
    is a language's (`countries.naming.Naming.key`)."""
    text = _AMPERSAND.sub(" & ", normalize_text(text))
    return " ".join(_NAME_JOINERS.sub(" ", text).split())
