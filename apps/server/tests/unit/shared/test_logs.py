import json
import logging
from typing import TYPE_CHECKING

from public_atlas.shared.logs import JsonFormatter, RequestIdFilter, TextFormatter, request_id

if TYPE_CHECKING:
    from types import TracebackType

    ExcInfo = tuple[type[BaseException], BaseException, TracebackType | None]


def record(message: str, exc_info: ExcInfo | None = None) -> logging.LogRecord:
    rec = logging.LogRecord("public_atlas.tests", logging.INFO, __file__, 1, message, (), exc_info)
    RequestIdFilter().filter(rec)
    return rec


def test_text_lines_carry_a_utc_timestamp_and_the_request_id():
    token = request_id.set("report-1")
    try:
        line = TextFormatter().format(record("hello"))
    finally:
        request_id.reset(token)
    timestamp, rest = line.split(" ", 1)
    assert timestamp.endswith("Z")
    assert "T" in timestamp
    assert rest == "INFO [public_atlas.tests] [report-1] hello"


def test_json_lines_are_one_object_each():
    exc = ValueError("nope")
    rec = record("it broke", exc_info=(type(exc), exc, None))
    line = json.loads(JsonFormatter().format(rec))
    assert line["level"] == "INFO"
    assert line["logger"] == "public_atlas.tests"
    assert line["request_id"] == "-"
    assert line["message"] == "it broke"
    assert line["time"].endswith("Z")
    assert "ValueError: nope" in line["exception"]
    assert "\n" not in JsonFormatter().format(record("one\nline"))
