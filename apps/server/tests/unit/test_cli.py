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
