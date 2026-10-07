"""The `X-Database` header picks the database a request reads: the main one by default, the
eval database on request, and nothing else."""

import pytest

from public_atlas.dependencies import get_database
from public_atlas.shared.exceptions import UnprocessableError


def test_the_main_database_is_the_default():
    assert get_database(None) == "main"
    assert get_database("") == "main"
    assert get_database(" Main ") == "main"


def test_the_eval_database_is_asked_for_by_name():
    assert get_database("eval") == "eval"
    assert get_database("EVAL") == "eval"


def test_any_other_database_is_refused():
    with pytest.raises(UnprocessableError, match="main or eval"):
        get_database("test")
