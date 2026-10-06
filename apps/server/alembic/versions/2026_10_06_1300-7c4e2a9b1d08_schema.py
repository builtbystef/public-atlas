"""schema

The graph, its evidence, the country tables and the work (spec section 4).

Revision ID: 7c4e2a9b1d08
Revises: 5b1a0c2d9e3f
Create Date: 2026-10-06 13:00:00
"""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

if TYPE_CHECKING:
    from collections.abc import Sequence

revision: str = "7c4e2a9b1d08"
down_revision: str | Sequence[str] | None = "5b1a0c2d9e3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def checked(table: str, column: str, values: list[str], *, nullable: bool = False) -> sa.Column:
    """A checked string: text with a constraint listing the enum's values, as
    `db/checked_strings.py` declares it. Adding a value is a migration that drops
    `ck_<table>_<column>` and creates it with the new list."""
    listed = ", ".join(f"'{value}'" for value in values)
    constraint = sa.CheckConstraint(f"{column} IN ({listed})", name=op.f(f"ck_{table}_{column}"))
    return sa.Column(column, sa.Text(), constraint, nullable=nullable)


def upgrade() -> None:  # noqa: PLR0915 - one statement per table
    # For the trigram index on aliases.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "country_settings",
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("naming_rules", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("country_code", name=op.f("pk_country_settings")),
    )
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        checked("entities", "kind", ["place", "institution", "source", "domain", "homepage"]),
        checked("entities", "status", ["candidate", "verified", "rejected", "needs_review"]),
        checked("entities", "entered_by", ["manual", "script", "agent"]),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_entities")),
    )
    op.create_table(
        "institution_types",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_institution_types")),
    )
    op.create_table(
        "source_types",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_source_types")),
    )
    op.create_table(
        "administrative_levels",
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("government_institution_type", sa.Text(), nullable=False),
        sa.Column("expected_institution_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["country_code"],
            ["country_settings.country_code"],
            name=op.f("fk_administrative_levels_country_code_country_settings"),
        ),
        sa.ForeignKeyConstraint(
            ["government_institution_type"],
            ["institution_types.name"],
            name=op.f("fk_administrative_levels_government_institution_type_institution_types"),
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint("country_code", "name", name=op.f("pk_administrative_levels")),
    )
    op.create_table(
        "country_institution_types",
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("institution_type", sa.Text(), nullable=False),
        sa.Column("expected_source_types", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("name_pattern", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["country_code"],
            ["country_settings.country_code"],
            name=op.f("fk_country_institution_types_country_code_country_settings"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_type"],
            ["institution_types.name"],
            name=op.f("fk_country_institution_types_institution_type_institution_types"),
            onupdate="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "country_code", "institution_type", name=op.f("pk_country_institution_types")
        ),
    )
    op.create_table(
        "domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        checked("domains", "kind", ["official", "platform"]),
        sa.ForeignKeyConstraint(["id"], ["entities.id"], name=op.f("fk_domains_id_entities")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_domains")),
        sa.UniqueConstraint("name", name=op.f("uq_domains_name")),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        checked("runs", "mode", ["step", "auto"]),
        checked("runs", "status", ["active", "paused", "stopped"]),
        sa.Column("filter", postgresql.JSONB(), nullable=False),
        sa.Column("is_eval", sa.Boolean(), nullable=False),
        sa.Column("record_video", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["country_code"],
            ["country_settings.country_code"],
            name=op.f("fk_runs_country_code_country_settings"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
    )
    op.create_table(
        "assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        checked("assignments", "type", ["find_homepage", "find_institutions", "find_sources"]),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        checked("assignments", "status", ["held", "queued", "running", "finished", "cancelled"]),
        checked(
            "assignments",
            "result",
            [
                "complete",
                "complete_with_gaps",
                "out_of_budget",
                "needs_review",
                "no_homepage",
                "failed",
            ],
            nullable=True,
        ),
        sa.Column("budget_requests", sa.Integer(), nullable=False),
        sa.Column("budget_tokens", sa.Integer(), nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False),
        sa.Column("handoff_note", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("types_not_found", postgresql.JSONB(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("parent_assignment_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_assignment_id"],
            ["assignments.id"],
            name=op.f("fk_assignments_parent_assignment_id_assignments"),
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_assignments_run_id_runs")),
        sa.ForeignKeyConstraint(
            ["subject_id"], ["entities.id"], name=op.f("fk_assignments_subject_id_entities")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
    )
    op.create_index(
        "ix_assignments_open_subject_type",
        "assignments",
        ["subject_id", "type"],
        unique=True,
        postgresql_where=sa.text("status IN ('held', 'queued', 'running')"),
    )
    op.create_index("ix_assignments_run_id", "assignments", ["run_id"])
    op.create_index("ix_assignments_status", "assignments", ["status"])
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_version", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("settings", postgresql.JSONB(), nullable=False),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f("fk_eval_runs_run_id_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_runs")),
    )
    op.create_table(
        "places",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("administrative_level", sa.Text(), nullable=False),
        sa.Column("parent_place_id", sa.Uuid(), nullable=True),
        sa.Column("government_institution_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["country_code", "administrative_level"],
            ["administrative_levels.country_code", "administrative_levels.name"],
            name=op.f("fk_places_country_code_administrative_levels"),
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(["id"], ["entities.id"], name=op.f("fk_places_id_entities")),
        sa.ForeignKeyConstraint(
            ["parent_place_id"], ["places.id"], name=op.f("fk_places_parent_place_id_places")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_places")),
    )
    op.create_index("ix_places_government_institution_id", "places", ["government_institution_id"])
    op.create_index("ix_places_parent_place_id", "places", ["parent_place_id"])
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("session", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        checked(
            "agent_run_events", "kind", ["prompt", "text", "tool_call", "tool_result", "video"]
        ),
        sa.Column("tool", sa.Text(), nullable=True),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_agent_run_events_assignment_id_assignments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_run_events")),
        sa.UniqueConstraint(
            "assignment_id", "session", "position", name=op.f("uq_agent_run_events_assignment_id")
        ),
    )
    op.create_table(
        "blocked_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_blocked_attempts_assignment_id_assignments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_blocked_attempts")),
    )
    op.create_index("ix_blocked_attempts_assignment_id", "blocked_attempts", ["assignment_id"])
    op.create_table(
        "eval_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("eval_run_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        checked(
            "eval_scores", "assignment_type", ["find_homepage", "find_institutions", "find_sources"]
        ),
        sa.Column("recall", sa.Float(), nullable=False),
        sa.Column("precision", sa.Float(), nullable=False),
        sa.Column("misses", postgresql.JSONB(), nullable=False),
        sa.Column("false_positives", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["eval_run_id"], ["eval_runs.id"], name=op.f("fk_eval_scores_eval_run_id_eval_runs")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_scores")),
    )
    op.create_index("ix_eval_scores_eval_run_id", "eval_scores", ["eval_run_id"])
    op.create_table(
        "institutions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("institution_type", sa.Text(), nullable=False),
        sa.Column("suggested_type", sa.Text(), nullable=True),
        sa.Column("place_id", sa.Uuid(), nullable=False),
        sa.Column("parent_institution_id", sa.Uuid(), nullable=True),
        checked("institutions", "procurement_handled_by", ["self", "parent"]),
        sa.Column("homepage_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["id"], ["entities.id"], name=op.f("fk_institutions_id_entities")),
        sa.ForeignKeyConstraint(
            ["institution_type"],
            ["institution_types.name"],
            name=op.f("fk_institutions_institution_type_institution_types"),
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_institution_id"],
            ["institutions.id"],
            name=op.f("fk_institutions_parent_institution_id_institutions"),
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["places.id"], name=op.f("fk_institutions_place_id_places")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_institutions")),
        sa.UniqueConstraint("id", "place_id", name=op.f("uq_institutions_id")),
    )
    op.create_index("ix_institutions_homepage_id", "institutions", ["homepage_id"])
    op.create_index("ix_institutions_institution_type", "institutions", ["institution_type"])
    op.create_index(
        "ix_institutions_parent_institution_id", "institutions", ["parent_institution_id"]
    )
    op.create_index("ix_institutions_place_id", "institutions", ["place_id"])
    op.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("rule", sa.Text(), nullable=False),
        sa.Column("question", postgresql.JSONB(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=True),
        checked("review_items", "status", ["open", "approved", "rejected", "merged"]),
        sa.Column("raised_by_assignment_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["entities.id"], name=op.f("fk_review_items_entity_id_entities")
        ),
        sa.ForeignKeyConstraint(
            ["raised_by_assignment_id"],
            ["assignments.id"],
            name=op.f("fk_review_items_raised_by_assignment_id_assignments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_items")),
    )
    op.create_index("ix_review_items_entity_id", "review_items", ["entity_id"])
    op.create_index("ix_review_items_kind", "review_items", ["kind"])
    op.create_index("ix_review_items_status", "review_items", ["status"])
    op.create_table(
        "usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=False),
        checked("usage", "kind", ["model", "search"]),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("cached_units", sa.Integer(), nullable=False),
        sa.Column("cost", sa.Numeric(12, 6), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignment_id"], ["assignments.id"], name=op.f("fk_usage_assignment_id_assignments")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage")),
    )
    op.create_index("ix_usage_assignment_id", "usage", ["assignment_id"])
    op.create_table(
        "webpages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain_id", sa.Uuid(), nullable=False),
        sa.Column("redirects_to_url", sa.Text(), nullable=True),
        sa.Column("first_seen_assignment_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["domains.id"], name=op.f("fk_webpages_domain_id_domains")
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_assignment_id"],
            ["assignments.id"],
            name=op.f("fk_webpages_first_seen_assignment_id_assignments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_webpages")),
        sa.UniqueConstraint("url", name=op.f("uq_webpages_url")),
    )
    op.create_index("ix_webpages_domain_id", "webpages", ["domain_id"])
    op.create_table(
        "aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.Uuid(), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("is_acronym", sa.Boolean(), nullable=False),
        checked("aliases", "entered_by", ["manual", "script", "agent"]),
        sa.CheckConstraint(
            "num_nonnulls(place_id, institution_id) = 1", name=op.f("ck_aliases_one_owner")
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_aliases_institution_id_institutions"),
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["places.id"], name=op.f("fk_aliases_place_id_places")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_aliases")),
        sa.UniqueConstraint(
            "place_id",
            "institution_id",
            "text",
            name=op.f("uq_aliases_place_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_aliases_institution_id", "aliases", ["institution_id"])
    op.create_index("ix_aliases_place_id", "aliases", ["place_id"])
    op.create_index(
        "ix_aliases_text_trgm",
        "aliases",
        ["text"],
        postgresql_using="gin",
        postgresql_ops={"text": "gin_trgm_ops"},
    )
    op.create_table(
        "homepages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("webpage_id", sa.Uuid(), nullable=False),
        sa.Column("found_on_webpage_id", sa.Uuid(), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("trusted_path", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["found_on_webpage_id"],
            ["webpages.id"],
            name=op.f("fk_homepages_found_on_webpage_id_webpages"),
        ),
        sa.ForeignKeyConstraint(["id"], ["entities.id"], name=op.f("fk_homepages_id_entities")),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_homepages_institution_id_institutions"),
        ),
        sa.ForeignKeyConstraint(
            ["webpage_id"], ["webpages.id"], name=op.f("fk_homepages_webpage_id_webpages")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_homepages")),
        sa.UniqueConstraint("id", "institution_id", name=op.f("uq_homepages_id")),
    )
    op.create_index("ix_homepages_institution_id", "homepages", ["institution_id"])
    op.create_index("ix_homepages_webpage_id", "homepages", ["webpage_id"])
    op.create_table(
        "institution_served_places",
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_institution_served_places_institution_id_institutions"),
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["places.id"], name=op.f("fk_institution_served_places_place_id_places")
        ),
        sa.PrimaryKeyConstraint(
            "institution_id", "place_id", name=op.f("pk_institution_served_places")
        ),
    )
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("webpage_id", sa.Uuid(), nullable=False),
        sa.Column("assignment_id", sa.Uuid(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=True),
        sa.Column("bytes_key", sa.Text(), nullable=False),
        sa.Column("text_key", sa.Text(), nullable=True),
        checked("snapshots", "text_status", ["ready", "parsing", "failed"]),
        sa.Column("text_error", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("pruned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_snapshots_assignment_id_assignments"),
        ),
        sa.ForeignKeyConstraint(
            ["webpage_id"], ["webpages.id"], name=op.f("fk_snapshots_webpage_id_webpages")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_snapshots")),
    )
    op.create_index("ix_snapshots_content_hash", "snapshots", ["content_hash"])
    op.create_index("ix_snapshots_webpage_id", "snapshots", ["webpage_id"])
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("webpage_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        checked("sources", "access", ["public", "login"]),
        sa.ForeignKeyConstraint(["id"], ["entities.id"], name=op.f("fk_sources_id_entities")),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_sources_institution_id_institutions"),
        ),
        sa.ForeignKeyConstraint(
            ["source_type"],
            ["source_types.name"],
            name=op.f("fk_sources_source_type_source_types"),
            onupdate="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["webpage_id"], ["webpages.id"], name=op.f("fk_sources_webpage_id_webpages")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint(
            "webpage_id", "institution_id", "source_type", name=op.f("uq_sources_webpage_id")
        ),
    )
    op.create_index("ix_sources_institution_id", "sources", ["institution_id"])
    op.create_index("ix_sources_webpage_id", "sources", ["webpage_id"])
    op.create_table(
        "evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        checked("evidence", "kind", ["appears_on", "links_to"]),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("locator", sa.Integer(), nullable=True),
        sa.Column("link_url", sa.Text(), nullable=True),
        sa.Column("assignment_id", sa.Uuid(), nullable=True),
        checked("evidence", "entered_by", ["manual", "script", "agent"]),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["assignments.id"],
            name=op.f("fk_evidence_assignment_id_assignments"),
        ),
        sa.ForeignKeyConstraint(
            ["entity_id"], ["entities.id"], name=op.f("fk_evidence_entity_id_entities")
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshots.id"], name=op.f("fk_evidence_snapshot_id_snapshots")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence")),
    )
    op.create_index("ix_evidence_entity_id", "evidence", ["entity_id"])
    op.create_index("ix_evidence_snapshot_id", "evidence", ["snapshot_id"])
    op.create_table(
        "official_lists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["snapshots.id"], name=op.f("fk_official_lists_snapshot_id_snapshots")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_lists")),
        sa.UniqueConstraint("name", "sha256", name=op.f("uq_official_lists_name")),
    )
    op.create_table(
        "identifiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.Uuid(), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        checked("identifiers", "scheme", ["statcan_sgc"]),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("official_list_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(place_id, institution_id) = 1", name=op.f("ck_identifiers_one_owner")
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_identifiers_institution_id_institutions"),
        ),
        sa.ForeignKeyConstraint(
            ["official_list_id"],
            ["official_lists.id"],
            name=op.f("fk_identifiers_official_list_id_official_lists"),
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["places.id"], name=op.f("fk_identifiers_place_id_places")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_identifiers")),
        sa.UniqueConstraint(
            "place_id",
            "institution_id",
            "scheme",
            name=op.f("uq_identifiers_place_id"),
            postgresql_nulls_not_distinct=True,
        ),
        sa.UniqueConstraint("scheme", "value", name=op.f("uq_identifiers_scheme")),
    )
    op.create_index("ix_identifiers_institution_id", "identifiers", ["institution_id"])
    op.create_index("ix_identifiers_place_id", "identifiers", ["place_id"])
    op.create_table(
        "metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("place_id", sa.Uuid(), nullable=True),
        sa.Column("institution_id", sa.Uuid(), nullable=True),
        checked("metrics", "name", ["population"]),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(20, 4), nullable=False),
        sa.Column("official_list_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "num_nonnulls(place_id, institution_id) = 1", name=op.f("ck_metrics_one_owner")
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name=op.f("fk_metrics_institution_id_institutions"),
        ),
        sa.ForeignKeyConstraint(
            ["official_list_id"],
            ["official_lists.id"],
            name=op.f("fk_metrics_official_list_id_official_lists"),
        ),
        sa.ForeignKeyConstraint(
            ["place_id"], ["places.id"], name=op.f("fk_metrics_place_id_places")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_metrics")),
        sa.UniqueConstraint(
            "place_id",
            "institution_id",
            "name",
            "year",
            name=op.f("uq_metrics_place_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_metrics_institution_id", "metrics", ["institution_id"])
    op.create_index("ix_metrics_place_id", "metrics", ["place_id"])
    op.create_foreign_key(
        op.f("fk_places_government_institution_id_institutions"),
        "places",
        "institutions",
        ["government_institution_id", "id"],
        ["id", "place_id"],
    )
    op.create_foreign_key(
        op.f("fk_institutions_homepage_id_homepages"),
        "institutions",
        "homepages",
        ["homepage_id", "id"],
        ["id", "institution_id"],
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_institutions_homepage_id_homepages"), "institutions")
    op.drop_constraint(op.f("fk_places_government_institution_id_institutions"), "places")
    op.drop_table("metrics")
    op.drop_table("identifiers")
    op.drop_table("official_lists")
    op.drop_table("evidence")
    op.drop_table("sources")
    op.drop_table("snapshots")
    op.drop_table("institution_served_places")
    op.drop_table("homepages")
    op.drop_table("aliases")
    op.drop_table("webpages")
    op.drop_table("usage")
    op.drop_table("review_items")
    op.drop_table("institutions")
    op.drop_table("eval_scores")
    op.drop_table("blocked_attempts")
    op.drop_table("agent_run_events")
    op.drop_table("places")
    op.drop_table("eval_runs")
    op.drop_table("assignments")
    op.drop_table("runs")
    op.drop_table("domains")
    op.drop_table("country_institution_types")
    op.drop_table("administrative_levels")
    op.drop_table("source_types")
    op.drop_table("institution_types")
    op.drop_table("entities")
    op.drop_table("country_settings")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
