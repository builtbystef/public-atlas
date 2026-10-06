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


def test_the_memory_parser_reads_text_and_splits_pages_on_form_feeds():
    parser: Parser = MemoryParser()
    parser.warm_up()
    document = parser.parse(b"# Hello\n\f\nSecond page\n", "hello.pdf")
    assert document.pages == ("# Hello", "Second page")
    assert (document.parser, document.version) == ("memory", "0")
    # The range size a retry asks for means nothing to it.
    assert parser.parse(b"# Hello\n\f\nSecond page\n", "hello.pdf", page_batch=1) == document


def test_the_memory_parser_fails_on_bytes_that_are_not_text():
    with pytest.raises(ParseFailed, match=r"^scan\.pdf: not text"):
        MemoryParser().parse(b"\xff\xfe", "scan.pdf")


def test_the_settings_choose_the_parser_without_loading_docling():
    """Every process builds its resources; only the parse worker has Docling installed."""
    parser = create_parser(Settings(parse_provider="docling"))
    assert isinstance(parser, DoclingParser)
    assert (parser.timeout, parser.page_batch, parser.max_pages) == (180.0, 10, 500)
    assert isinstance(create_parser(Settings(parse_provider="memory")), MemoryParser)
