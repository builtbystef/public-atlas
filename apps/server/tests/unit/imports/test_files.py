"""The loader's file layer: the cache and hash check, and one renderer per format."""

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import pytest

from public_atlas.integrations.parse import MemoryParser
from public_atlas.modules.evidence.service import content_hash
from public_atlas.modules.imports import files
from public_atlas.modules.imports.files import Format, ListFileError, Source

CSV = b"\xef\xbb\xbfname,code,note\nElmwood,3501,  a township \nOakville,3502,a town\n"


def source(data: bytes, **fields: Any) -> Source:
    defaults: dict[str, Any] = {
        "name": "tiny",
        "title": "A tiny list",
        "url": "https://example.test/lists/tiny.csv",
        "sha256": content_hash(data),
        "format": Format.CSV,
    }
    return Source(**{**defaults, **fields})


def test_a_csv_is_one_line_per_row_with_the_header_first():
    opened = files.render(source(CSV), CSV)
    assert opened.lines == [
        "name | code | note",
        "Elmwood | 3501 |   a township ",
        "Oakville | 3502 | a town",
    ]
    assert [row.line for row in opened.rows] == [2, 3]
    assert opened.rows[0]["note"] == "a township"
    assert opened.rows[1].get("missing", "none") == "none"
    assert opened.line(3) == "Oakville | 3502 | a town"
    assert opened.text == "\n".join(opened.lines)
    assert opened.sha256 == content_hash(CSV)


def test_columns_are_kept_in_order_and_repeats_dropped():
    data = b"a,b,c\n1,x,9\n2,x,8\n3,y,7\n"
    opened = files.render(source(data, columns=("c", "b"), distinct=False), data)
    assert opened.lines == ["c | b", "9 | x", "8 | x", "7 | y"]
    opened = files.render(source(data, columns=("b",), distinct=True), data)
    assert opened.lines == ["b", "x", "y"]
    assert [row.line for row in opened.rows] == [2, 3]
    with pytest.raises(ListFileError, match="no column"):
        files.render(source(data, columns=("zzz",)), data)


def test_a_zip_member_is_read_and_a_missing_one_refused():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inner/tiny.csv", CSV)
    data = buffer.getvalue()
    opened = files.render(
        source(data, url="https://example.test/tiny.zip", member="inner/tiny.csv"), data
    )
    assert opened.lines[1] == "Elmwood | 3501 |   a township "
    assert opened.source.media_type == files.ZIP_MEDIA_TYPE
    with pytest.raises(ListFileError, match="no member"):
        files.render(source(data, url="https://example.test/tiny.zip", member="nope.csv"), data)


def test_json_is_one_line_per_record():
    records = [{"name": "Elmwood", "code": 1}, {"code": 2, "name": "Oakville"}]
    data = json.dumps(records).encode()
    opened = files.render(source(data, format=Format.JSON, url="https://x.test/a.json"), data)
    assert opened.lines == ['{"code": 1, "name": "Elmwood"}', '{"code": 2, "name": "Oakville"}']
    assert opened.document == records
    assert opened.rows == []
    one = json.dumps({"only": True}).encode()
    assert files.render(source(one, format=Format.JSON), one).lines == ['{"only": true}']


def test_html_is_its_visible_text_one_line_per_block():
    html = (
        b"<html><head><title>T</title><style>p{}</style></head><body>"
        b"<h1>Elmwood</h1><p>A <b>township</b> in\n  Ontario.</p><script>x()</script>"
        b"<ul><li>One</li><li>Two</li></ul>tail</body></html>"
    )
    opened = files.render(source(html, format=Format.HTML, url="https://x.test/p"), html)
    assert opened.lines == ["Elmwood", "A township in Ontario.", "One", "Two", "tail"]


def test_a_spreadsheet_is_read_like_a_csv():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append(["name", "code"])
    sheet.append(["Elmwood", 3501])
    sheet.append(["Oakville", None])
    buffer = io.BytesIO()
    workbook.save(buffer)
    data = buffer.getvalue()
    opened = files.render(
        source(data, format=Format.SPREADSHEET, url="https://x.test/list.xlsx"), data
    )
    assert opened.lines == ["name | code", "Elmwood | 3501", "Oakville | "]
    assert opened.rows[0]["code"] == "3501"


def test_a_pdf_goes_through_the_parser_one_line_per_line_of_its_pages():
    data = b"Hospitals\nToronto General\fOttawa Civic\n"
    pdf = source(data, format=Format.PDF, url="https://x.test/list.pdf")
    with pytest.raises(ListFileError, match="needs a parser"):
        files.render(pdf, data)
    opened = files.render(pdf, data, parser=MemoryParser())
    assert opened.lines == ["Hospitals", "Toronto General", "Ottawa Civic"]
    assert opened.line(3) == "Ottawa Civic"


def test_the_hash_is_checked():
    wrong = source(CSV, sha256="0" * 64)
    with pytest.raises(ListFileError, match="not the recorded"):
        files.render(wrong, CSV)


def test_the_cache_is_read_when_the_hash_matches(tmp_path: Path):
    tiny = source(CSV)
    assert tiny.filename == "tiny.csv"
    path = tiny.cache_path(tmp_path)
    assert path.name == f"tiny-{tiny.sha256[:12]}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(CSV)
    assert files.fetch(tiny, tmp_path) == CSV
    assert files.open_source(tiny, tmp_path).rows[0]["name"] == "Elmwood"


def test_a_stale_cache_is_fetched_again_and_a_failed_fetch_is_an_error(tmp_path: Path):
    # Nothing listens on this port, so the fetch fails at once.
    unreachable = source(CSV, url="http://127.0.0.1:9/tiny.csv")
    unreachable.cache_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    unreachable.cache_path(tmp_path).write_bytes(b"stale")
    with pytest.raises(ListFileError, match="cannot fetch"):
        files.fetch(unreachable, tmp_path)
