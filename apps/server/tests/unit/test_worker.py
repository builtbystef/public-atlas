"""The worker's command line: the queues it serves and how many jobs it runs at once."""

import pytest

from public_atlas.jobs.worker import concurrency_for, parse_args


def test_the_worker_serves_every_queue_or_the_ones_named_in_queue_order():
    assert parse_args([]) == ["default", "assignment", "parse"]
    assert parse_args(["--queues", "parse,default"]) == ["default", "parse"]
    assert parse_args(["--queues", " assignment "]) == ["assignment"]


def test_a_queue_that_does_not_exist_is_refused_by_name(capsys):
    with pytest.raises(SystemExit, match="2"):
        parse_args(["--queues", "parse,mail"])
    assert "unknown queue: mail (expected default, assignment, parse)" in capsys.readouterr().err


def test_a_worker_that_parses_runs_one_job_at_a_time():
    assert concurrency_for(["parse"], 4) == 1
    assert concurrency_for(["assignment"], 4) == 4
