from public_atlas.jobs.worker import concurrency_for, parse_args


def test_the_worker_serves_every_queue_or_the_ones_named_in_queue_order():
    assert parse_args([]) == ["default", "assignment", "parse"]
    assert parse_args(["--queues", "parse,default"]) == ["default", "parse"]


def test_a_worker_that_parses_runs_one_job_at_a_time():
    assert concurrency_for(["parse"], 4) == 1
    assert concurrency_for(["assignment"], 4) == 4
