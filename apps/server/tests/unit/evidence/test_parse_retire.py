"""A parse worker that has grown past its limit retires after the job; a retry parses one page
at a time."""

import os
import signal

import pytest

from public_atlas.jobs.context import Attempt
from public_atlas.modules.evidence import jobs


def test_a_worker_over_the_limit_asks_itself_to_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append((pid, sig)))
    assert jobs.retire_if_grown(2500, rss_mb=2600) is True
    assert sent == [(os.getpid(), signal.SIGTERM)]


def test_a_worker_within_the_limit_carries_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "kill", lambda *_: pytest.fail("must not signal"))
    assert jobs.retire_if_grown(2500, rss_mb=2500) is False
    assert jobs.retire_if_grown(2500, rss_mb=None) is False


def test_a_retry_parses_one_page_per_range():
    assert jobs.pages_per_range(Attempt(1, last=False)) is None
    assert jobs.pages_per_range(Attempt(2, last=True)) == 1
