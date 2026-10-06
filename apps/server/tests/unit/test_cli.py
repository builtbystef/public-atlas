import pytest

from public_atlas.cli import build_parser


def test_seed_takes_a_registered_country():
    args = build_parser().parse_args(["seed", "canada"])
    assert args.country == "canada"


def test_seed_refuses_an_unknown_country(capsys):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["seed", "atlantis"])
    assert "invalid choice" in capsys.readouterr().err
