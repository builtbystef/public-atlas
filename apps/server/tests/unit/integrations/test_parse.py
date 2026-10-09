"""The parser port on its in-memory implementation."""

import pytest

from public_atlas.config import Settings
from public_atlas.integrations.parse import (
    PAGE_SEPARATOR,
    DoclingParser,
    MemoryParser,
    ParsedDocument,
    ParseFailed,
    Parser,
    create_parser,
)


def test_a_document_joins_its_pages_with_form_feeds():
    document = ParsedDocument(pages=("one", "two"), parser="x", version="1")
    assert document.text == f"one{PAGE_SEPARATOR}two"
    assert (document.first, document.last, document.total, document.complete) == (1, 2, 2, True)


def test_a_range_of_a_document_knows_its_place_in_it():
    middle = ParsedDocument(pages=("eleven", "twelve"), parser="x", version="1", first=11, total=20)
    assert (middle.last, middle.complete) == (12, False)
    end = ParsedDocument(pages=("twenty",), parser="x", version="1", first=20, total=20)
    assert end.complete


def test_the_memory_parser_reads_text_and_splits_pages_on_form_feeds():
    parser: Parser = MemoryParser()
    parser.warm_up()
    document = parser.parse(b"# Hello\n\f\nSecond page\n", "hello.pdf")
    assert document.pages == ("# Hello", "Second page")
    assert (document.parser, document.version) == ("memory", "0")
    # The range size a retry asks for means nothing to it.
    assert parser.parse(b"# Hello\n\f\nSecond page\n", "hello.pdf", page_batch=1) == document


def test_the_memory_parser_parses_the_range_asked_for():
    data = b"one\ftwo\fthree"
    first = MemoryParser().parse(data, "three.pdf", limit=2)
    assert (first.pages, first.first, first.total, first.complete) == (("one", "two"), 1, 3, False)
    rest = MemoryParser().parse(data, "three.pdf", start=first.last + 1, limit=2)
    assert (rest.pages, rest.first, rest.total, rest.complete) == (("three",), 3, 3, True)
    assert MemoryParser().parse(data, "three.pdf", start=4, limit=2).pages == ()


def test_the_memory_parser_fails_on_bytes_that_are_not_text():
    with pytest.raises(ParseFailed, match=r"^scan\.pdf: not text"):
        MemoryParser().parse(b"\xff\xfe", "scan.pdf")


def test_the_settings_choose_the_parser_without_loading_docling():
    """Every process builds its resources; only the parse worker has Docling installed."""
    parser = create_parser(Settings(parse_provider="docling"))
    assert isinstance(parser, DoclingParser)
    assert (parser.timeout, parser.page_batch, parser.max_pages) == (180.0, 10, 500)
    assert isinstance(create_parser(Settings(parse_provider="memory")), MemoryParser)
