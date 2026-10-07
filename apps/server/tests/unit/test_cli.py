import pytest

from public_atlas.cli import build_parser


def test_seed_takes_a_registered_country():
    args = build_parser().parse_args(["seed", "canada"])
    assert args.country == "canada"


def test_seed_refuses_an_unknown_country(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["seed", "atlantis"])
    assert "invalid choice" in capsys.readouterr().err


def test_load_list_is_a_dry_run_unless_applied():
    args = build_parser().parse_args(["load-list", "ontario_places"])
    assert (args.name, args.apply) == ("ontario_places", False)
    args = build_parser().parse_args(["load-list", "ontario_places", "--apply"])
    assert args.apply is True


def test_load_list_refuses_an_unknown_list(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["load-list", "atlantis_places"])
    assert "invalid choice" in capsys.readouterr().err


def test_run_create_takes_a_filter_and_a_mode():
    args = build_parser().parse_args(
        [
            "run",
            "create",
            "pilot",
            "--mode",
            "auto",
            "--level",
            "municipality",
            "--level",
            "region",
            "--type",
            "library",
            "--assignment-type",
            "find_homepage",
            "--video",
        ]
    )
    assert (args.command, args.action, args.name, args.country, args.mode) == (
        "run",
        "create",
        "pilot",
        "CA",
        "auto",
    )
    assert (args.level, args.type, args.assignment_type, args.video) == (
        ["municipality", "region"],
        ["library"],
        ["find_homepage"],
        True,
    )
    held = build_parser().parse_args(["run", "create", "one"])
    assert (held.mode, held.level, held.video) == ("step", None, False)


def test_run_control_takes_a_run_id_and_release_its_choices():
    run_id = "01a111f5-b766-7646-9e2d-7f71b935bb68"
    for action in ("pause", "resume", "stop", "show"):
        args = build_parser().parse_args(["run", action, run_id])
        assert (args.action, str(args.run_id)) == (action, run_id)
    args = build_parser().parse_args(
        ["run", "release", run_id, "--limit", "3", "--type", "find_sources", "--assignment", run_id]
    )
    assert (args.limit, args.type, args.assignment) == (3, "find_sources", [run_id])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "pause", "not-an-id"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "release", run_id, "--type", "find_castles"])


def test_worker_takes_the_queues_to_serve(capsys):
    args = build_parser().parse_args(["worker", "--queues", "parse,assignment"])
    assert args.queues == ["assignment", "parse"]
    assert build_parser().parse_args(["worker"]).queues is None
    with pytest.raises(SystemExit):
        build_parser().parse_args(["worker", "--queues", "mail"])
    assert "unknown queue: mail" in capsys.readouterr().err


def test_eval_commands_take_their_choices(tmp_path):
    args = build_parser().parse_args(["eval", "validate", "--subject", "mcgarry"])
    assert (args.command, args.action, args.subject) == ("eval", "validate", ["mcgarry"])
    args = build_parser().parse_args(["eval", "score", "--evals", "--details"])
    assert (args.action, args.evals, args.details, args.json) == ("score", True, True, None)
    out = tmp_path / "scores.json"
    args = build_parser().parse_args(
        [
            "eval",
            "run",
            "--subject",
            "mcgarry",
            "--subject",
            "oakville",
            "--types",
            "find_institutions",
            "find_sources",
            "--keep",
            "--no-worker",
            "--queues",
            "assignment,default",
            "--json",
            str(out),
        ]
    )
    assert args.subject == ["mcgarry", "oakville"]
    assert args.types == ["find_institutions", "find_sources"]
    assert (args.keep, args.no_worker, args.queues, args.json) == (
        True,
        True,
        ["default", "assignment"],
        out,
    )
    plain = build_parser().parse_args(["eval", "run"])
    assert (plain.subject, plain.types, plain.keep, plain.no_worker, plain.queues) == (
        None,
        None,
        False,
        False,
        None,
    )
    with pytest.raises(SystemExit):
        build_parser().parse_args(["eval", "run", "--types", "find_castles"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["eval", "run", "--queues", "assignment,castles"])
