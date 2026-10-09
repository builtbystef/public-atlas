"""The Docling parser on small hand-built PDFs. Marked `parse`: skipped unless Docling is
installed."""

import pytest

from public_atlas.integrations.parse import ParseFailed
from public_atlas.integrations.parse.docling import MODELS, DoclingParser, _glibc, ocr_params

pytestmark = pytest.mark.parse

TIMEOUT = 60.0
PAGE_BATCH = 2
MAX_PAGES = 3


@pytest.fixture(scope="module")
def parser() -> DoclingParser:
    return DoclingParser(timeout=TIMEOUT, page_batch=PAGE_BATCH, max_pages=MAX_PAGES)


def small_pdf(*texts: str) -> bytes:
    """A PDF with one page per text, each a line of Helvetica."""
    kids = " ".join(f"{4 + 2 * n} 0 R" for n in range(len(texts))).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [" + kids + b"] /Count %d >>" % len(texts),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for n, text in enumerate(texts):
        content = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R"
            b" /Resources << /Font << /F1 3 0 R >> >> >>" % (5 + 2 * n)
        )
        objects.append(b"<< /Length %d >>stream\n" % len(content) + content + b"\nendstream")
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)


def test_the_models_the_image_downloads_are_the_ones_the_converter_loads(parser: DoclingParser):
    assert MODELS == ("layout", "rapidocr")
    parser.warm_up()
    assert parser.converter is parser.converter


def test_a_pdf_parses_to_its_text(parser: DoclingParser):
    document = parser.parse(small_pdf("Hello Public Atlas"), "hello.pdf")
    assert len(document.pages) == 1
    assert "Hello Public Atlas" in document.pages[0]
    assert document.parser == "docling"
    assert document.version == parser.version


def test_a_long_pdf_is_parsed_in_ranges_of_pages_in_order(parser: DoclingParser):
    document = parser.parse(small_pdf("alpha", "beta", "gamma"), "three.pdf")
    assert [page.strip("# ") for page in document.pages] == ["alpha", "beta", "gamma"]


def test_a_smaller_range_for_one_file_gives_the_same_pages(parser: DoclingParser):
    """What the parse job asks for on a retry: one page per call, same result."""
    data = small_pdf("alpha", "beta", "gamma")
    assert (
        parser.parse(data, "three.pdf", page_batch=1).pages == parser.parse(data, "three.pdf").pages
    )


def test_a_range_is_parsed_from_its_start_and_knows_the_total(parser: DoclingParser):
    """What the parse job asks for: the first range when the file is fetched, the next when
    the agent reads past it."""
    data = small_pdf("alpha", "beta", "gamma")
    first = parser.parse(data, "three.pdf", limit=2)
    assert [page.strip("# ") for page in first.pages] == ["alpha", "beta"]
    assert (first.first, first.last, first.total, first.complete) == (1, 2, 3, False)
    rest = parser.parse(data, "three.pdf", start=3, limit=2, page_batch=1)
    assert [page.strip("# ") for page in rest.pages] == ["gamma"]
    assert (rest.first, rest.last, rest.total, rest.complete) == (3, 3, 3, True)


def test_a_page_with_no_text_keeps_its_number(parser: DoclingParser):
    """Docling's page-break export leaves an empty page out, which would make the page number of
    every quote after it one short."""
    document = parser.parse(small_pdf("first", "", "third"), "blank.pdf")
    assert [page.strip("# ") for page in document.pages] == ["first", "", "third"]


def test_a_pdf_over_the_page_cap_is_refused_with_its_page_count(parser: DoclingParser):
    with pytest.raises(ParseFailed, match="4 pages; files over 3 pages are not parsed"):
        parser.parse(small_pdf("one", "two", "three", "four"), "four.pdf")


def test_a_broken_file_fails_with_the_reason(parser: DoclingParser):
    with pytest.raises(ParseFailed, match="failure"):
        parser.parse(b"%PDF-1.4 this is not a pdf", "broken.pdf")


def test_ocr_stays_on_the_cpu_whatever_runtime_is_installed(parser: DoclingParser):
    params = ocr_params()
    assert params["EngineConfig.onnxruntime.use_cuda"] is False
    assert all(params[f"{model}.use_cuda"] is False for model in ("Det", "Cls", "Rec"))
    from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
    from docling.datamodel.pipeline_options import (  # noqa: PLC0415
        PdfPipelineOptions,
        RapidOcrOptions,
    )

    options = parser.converter.format_to_options[InputFormat.PDF].pipeline_options
    assert isinstance(options, PdfPipelineOptions)
    assert isinstance(options.ocr_options, RapidOcrOptions)
    assert options.ocr_options.rapidocr_params == params


def test_the_helper_pdf_is_well_formed():
    """So a parse failure points at Docling, not at the fixture."""
    data = small_pdf("x")
    assert data.startswith(b"%PDF-1.4")
    assert data.endswith(b"%%EOF\n")


def test_freed_memory_is_handed_back_after_a_range(parser: DoclingParser):
    """`_glibc` is None off Linux, and `release_memory` must work either way."""
    parser.release_memory()
    libc = _glibc()
    if libc is not None:
        assert libc.malloc_trim(0) in (0, 1)
