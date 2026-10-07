"""The eval database is the main database's settings on another database name."""

from pydantic import PostgresDsn

from public_atlas.config import Settings


def test_eval_settings_point_at_the_eval_database():
    settings = Settings(
        database_url=PostgresDsn("postgresql+psycopg://u:p@db:5432/public_atlas"),
        eval_database_name="public_atlas_evals",
    )
    assert settings.database_name == "public_atlas"
    assert settings.has_eval_database
    evals = settings.eval_settings()
    assert evals.database_name == "public_atlas_evals"
    assert str(evals.database_url) == "postgresql+psycopg://u:p@db:5432/public_atlas_evals"
    # Everything else is the same.
    assert evals.storage_bucket == settings.storage_bucket


def test_no_eval_database_when_it_is_the_main_one():
    settings = Settings(
        database_url=PostgresDsn("postgresql+psycopg://u:p@db:5432/public_atlas"),
        eval_database_name="public_atlas",
    )
    assert not settings.has_eval_database
