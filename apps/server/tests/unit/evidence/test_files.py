"""How `read_file` cuts a document's text into chunks, and renders what it returns."""

from public_atlas.modules.evidence import files
from public_atlas.modules.evidence.files import FileParsing, FileRefusal, FileText, Progress


def test_chunks_are_numbered_and_pages_are_marked():
    text = "first page\fsecond page"
    one = files.chunk_of("https://x/f.pdf", "application/pdf", text, chunk=1, size=30)
    assert isinstance(one, FileText)
    assert str(one).startswith("File: https://x/f.pdf (application/pdf, 2 page(s), chunk 1 of 2)")
    assert "read_file(url, chunk=2)" in str(one)
    assert "[page 1]\nfirst page" in one.body
    two = files.chunk_of("https://x/f.pdf", "application/pdf", text, chunk=2, size=30)
    assert isinstance(two, FileText)
    assert "chunk 2 of 2)" in str(two)
    assert "next chunk" not in str(two)
    assert "[page 2]" in one.body + two.body
    none = files.chunk_of("https://x/f.pdf", "application/pdf", text, chunk=3, size=30)
    assert isinstance(none, FileRefusal)
    assert str(none).startswith("Error: https://x/f.pdf has 2 chunk(s)")


def test_a_redirect_is_named_so_the_agent_quotes_the_url_that_answered():
    chunk = files.chunk_of(
        "https://x/new.pdf",
        "application/pdf",
        "text",
        chunk=1,
        size=30,
        requested_url="https://x/old.pdf",
    )
    assert str(chunk).startswith(
        "https://x/old.pdf redirected to https://x/new.pdf; quote it by that URL."
    )


def test_a_file_still_parsing_points_the_agent_at_status():
    assert "status()" in str(FileParsing("https://x/f.pdf"))
    more = str(FileParsing("https://x/f.pdf", pages=(11, 20)))
    assert more.startswith("Pages 11-20 of https://x/f.pdf are still being parsed")


def test_a_partly_parsed_file_says_how_far_it_goes_and_how_to_read_on():
    text = "first page\fsecond page"
    partial = Progress(parsed=2, total=9)
    last = files.chunk_of(
        "https://x/f.pdf", "application/pdf", text, chunk=2, size=30, progress=partial
    )
    assert isinstance(last, FileText)
    assert str(last).startswith(
        "File: https://x/f.pdf (application/pdf, 9 page(s), 2 parsed so far, chunk 2 of 2 so far)"
        ". Call read_file(url, chunk=3) to have the next pages parsed"
    )
    first = files.chunk_of(
        "https://x/f.pdf", "application/pdf", text, chunk=1, size=30, progress=partial
    )
    assert "chunk 1 of 2 so far). Call read_file(url, chunk=2) for the next chunk" in str(first)
    # The rest failed: the agent is told, and a chunk past the text names the reason.
    failed = Progress(parsed=2, total=9, error="page 3 is corrupt")
    stuck = files.chunk_of(
        "https://x/f.pdf", "application/pdf", text, chunk=2, size=30, progress=failed
    )
    assert "Pages 3-9 could not be parsed: page 3 is corrupt" in str(stuck)
    none = files.chunk_of(
        "https://x/f.pdf", "application/pdf", text, chunk=3, size=30, progress=failed
    )
    assert isinstance(none, FileRefusal)
    assert "pages 1-2 of 9; the rest could not be parsed: page 3 is corrupt" in str(none)
