"""The lists cache as `lists fetch` and `lists pack` see it: every list's files fetched into it
or reported missing, packed into one archive, and unpacked from one."""

import tarfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import ClassVar

import pytest

from public_atlas.modules.evidence.service import content_hash
from public_atlas.modules.imports import service
from public_atlas.modules.imports.files import Format, ListFile, ListFileError, Retrieval

CSV = b"name,code\nElmwood,3501\n"
OTHER = b"name,code\nOakville,3502\n"


class _Handler(BaseHTTPRequestHandler):
    pages: ClassVar[dict[str, bytes]] = {}

    def do_GET(self) -> None:
        data = self.pages.get(self.path)
        if data is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/csv")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002, ARG002 - the base signature
        return


@pytest.fixture
def served() -> Iterator[str]:
    """A site serving `tiny.csv` and `other.csv`, by its base URL."""
    _Handler.pages = {"/tiny.csv": CSV, "/other.csv": OTHER}
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def fetched(name: str, data: bytes, url: str) -> ListFile:
    return ListFile(name=name, title=name, url=url, format=Format.CSV, sha256=content_hash(data))


def manual(name: str) -> ListFile:
    return ListFile(
        name=name,
        title=name,
        url="https://example.test/directory",
        format=Format.CSV,
        retrieval=Retrieval.MANUAL,
        instructions="Open the directory, choose Export, all rows, CSV.",
        filename_override=f"{name}.csv",
    )


def module(*sources: ListFile) -> ModuleType:
    found = ModuleType("tests.tiny")
    found.__dict__.update(COUNTRY="CA", SOURCES=sources, OVERRIDES={}, entries=lambda *_: [])
    return found


def put(file: ListFile, cache_dir: Path, data: bytes) -> Path:
    path = file.cache_path(cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_fetch_fills_the_cache_and_names_each_file_once(tmp_path: Path, served: str):
    tiny = fetched("tiny", CSV, f"{served}/tiny.csv")
    other = fetched("other", OTHER, f"{served}/other.csv")
    put(other, tmp_path, OTHER)
    export = manual("export")
    put(export, tmp_path, CSV)
    absent = manual("absent")
    gone = fetched("gone", b"gone", f"{served}/gone.csv")
    # `other` is read by both lists and counted for the first.
    modules = {"a/one": module(tiny, other, export), "a/two": module(other, absent, gone)}

    report = service.fetch_all(tmp_path, modules)

    assert report.cached == ["a/one/other", "a/one/export"]
    assert report.fetched == ["a/one/tiny"]
    assert report.missing == [f"a/two/absent: put it at {tmp_path / 'absent.csv'}"]
    assert len(report.failed) == 1
    assert report.failed[0].startswith(f"a/two/gone: gone: cannot fetch {served}/gone.csv: ")
    assert "404" in report.failed[0]
    assert not report.complete
    assert tiny.cache_path(tmp_path).read_bytes() == CSV
    assert not gone.cache_path(tmp_path).exists()
    assert report.render().splitlines()[:4] == [
        "2 files cached, 1 fetched",
        "  fetched a/one/tiny",
        "  failed: 1",
        f"    {report.failed[0].splitlines()[0]}",
    ]
    assert report.render().endswith(
        "  manual files not in the cache: 1 (`lists manifest` has the steps that obtain each)\n"
        f"    a/two/absent: put it at {tmp_path / 'absent.csv'}"
    )

    again = service.fetch_all(tmp_path, {"a/one": modules["a/one"]})
    assert (again.cached, again.fetched, again.complete) == (
        ["a/one/tiny", "a/one/other", "a/one/export"],
        [],
        True,
    )
    assert again.render() == "3 files cached, 0 fetched"


def test_fetch_replaces_a_cached_file_off_its_hash(tmp_path: Path, served: str):
    tiny = fetched("tiny", CSV, f"{served}/tiny.csv")
    put(tiny, tmp_path, b"stale")

    report = service.fetch_all(tmp_path, {"a/one": module(tiny)})

    assert (report.cached, report.fetched) == ([], ["a/one/tiny"])
    assert tiny.cache_path(tmp_path).read_bytes() == CSV


def test_pack_takes_every_file_or_refuses(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    archive = tmp_path / "out" / "lists.tar.gz"
    tiny = fetched("tiny", CSV, "https://example.test/tiny.csv")
    export = manual("export")
    absent = manual("absent")
    modules = {"a/one": module(tiny, export, absent)}
    put(tiny, cache_dir, b"stale")
    put(export, cache_dir, OTHER)
    with pytest.raises(ListFileError) as caught:
        service.pack(cache_dir, archive, modules)
    assert str(caught.value) == (
        "2 files cannot be packed, so the archive would be incomplete: "
        "a/one/absent: not in the cache; a/one/tiny: not the recorded hash"
    )
    assert not archive.exists()

    put(tiny, cache_dir, CSV)
    put(absent, cache_dir, CSV)
    tiny_name = f"tiny-{content_hash(CSV)[:12]}.csv"
    assert service.pack(cache_dir, archive, modules) == ["absent.csv", "export.csv", tiny_name]
    with tarfile.open(archive) as tar:
        assert sorted(tar.getnames()) == ["absent.csv", "export.csv", tiny_name]
        member = tar.extractfile(tiny_name)
        assert member is not None
        assert member.read() == CSV


def test_unpack_takes_only_the_files_the_lists_declare(tmp_path: Path):
    cache_dir = tmp_path / "cache"
    archive = tmp_path / "lists.tar.gz"
    tiny = fetched("tiny", CSV, "https://example.test/tiny.csv")
    export = manual("export")
    tiny_name = f"tiny-{content_hash(CSV)[:12]}.csv"
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / tiny_name).write_bytes(CSV)
    (sources / "export.csv").write_bytes(OTHER)
    (sources / "stranger.csv").write_bytes(b"no list declares me")
    (sources / "nested").mkdir()
    (sources / "nested" / "export.csv").write_bytes(b"not at the top")
    with tarfile.open(archive, "w:gz") as tar:
        for name in (tiny_name, "export.csv", "stranger.csv", "nested", "nested/export.csv"):
            tar.add(sources / name, arcname=name, recursive=False)
    # What is there is replaced.
    put(export, cache_dir, b"old export")

    unpacked, ignored = service.unpack(archive, cache_dir, {"a/one": module(tiny, export)})

    assert unpacked == ["export.csv", tiny_name]
    assert ignored == ["nested", "nested/export.csv", "stranger.csv"]
    assert sorted(path.name for path in cache_dir.iterdir()) == ["export.csv", tiny_name]
    assert export.cache_path(cache_dir).read_bytes() == OTHER
    assert tiny.cache_path(cache_dir).read_bytes() == CSV


def test_pack_and_unpack_round_trip(tmp_path: Path):
    tiny = fetched("tiny", CSV, "https://example.test/tiny.csv")
    export = manual("export")
    modules = {"a/one": module(tiny, export)}
    put(tiny, tmp_path / "here", CSV)
    put(export, tmp_path / "here", OTHER)
    archive = tmp_path / "lists.tar.gz"

    names = service.pack(tmp_path / "here", archive, modules)
    unpacked, ignored = service.unpack(archive, tmp_path / "there", modules)

    assert (unpacked, ignored) == (names, [])
    report = service.fetch_all(tmp_path / "there", modules)
    assert (report.cached, report.complete) == (["a/one/tiny", "a/one/export"], True)
