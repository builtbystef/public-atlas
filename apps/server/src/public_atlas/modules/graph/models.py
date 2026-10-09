"""The graph (spec sections 4.1 to 4.3): one `entities` parent that holds what every verifiable
thing shares, five tables that extend it with joined-table inheritance, the attachments of
places and institutions, and the webpages the browser visited."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    DDL,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from public_atlas.db.base import Base, UUIDPrimaryKey, utcnow
from public_atlas.db.checked_strings import checked_string
from public_atlas.modules.countries.models import COUNTRY_CODE_LENGTH


class EntityKind(StrEnum):
    PLACE = "place"
    INSTITUTION = "institution"
    SOURCE = "source"
    DOMAIN = "domain"
    HOMEPAGE = "homepage"


class EntityStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"


class EnteredBy(StrEnum):
    """How a row got here. On every entity and every evidence row."""

    MANUAL = "manual"
    SCRIPT = "script"
    AGENT = "agent"


class ProcurementHandledBy(StrEnum):
    """Whether an institution buys on its own account or its parent buys for it."""

    SELF = "self"
    PARENT = "parent"


class SourceAccess(StrEnum):
    PUBLIC = "public"
    LOGIN = "login"


class DomainKind(StrEnum):
    # Trusted when verified.
    OFFICIAL = "official"
    # Anyone can publish on it: fetchable, never trusted.
    PLATFORM = "platform"


class IdentifierScheme(StrEnum):
    """Outside schemes a place or institution has a code in: Canada's Standard Geographical
    Classification and the code géographique of Quebec's Ministère des Affaires municipales et
    de l'Habitation (three digits for an MRC, which the census does not always count as a
    division); the United States' FIPS codes (state, county, place, county subdivision), the
    GNIS ids that survive a rename, the Census of Governments' unit ids, and the NCES and IPEDS
    ids of school districts and campuses."""

    STATCAN_SGC = "statcan_sgc"
    MAMH = "mamh"
    FIPS = "fips"
    GNIS = "gnis"
    CENSUS_GID = "census_gid"
    NCES = "nces"
    IPEDS = "ipeds"


class MetricName(StrEnum):
    POPULATION = "population"


# --- Entities ---


class Entity(UUIDPrimaryKey, Base):
    """A row here and a row in the child table with the same id; in code each is one object."""

    __tablename__ = "entities"

    kind: Mapped[EntityKind] = checked_string(EntityKind, "kind")
    # Every entity starts as a candidate; `status_changes.py` is the one place it moves from
    # there, and `entered_by` then says who moved it.
    status: Mapped[EntityStatus] = checked_string(
        EntityStatus, "status", default=EntityStatus.CANDIDATE
    )
    entered_by: Mapped[EnteredBy] = checked_string(EnteredBy, "entered_by")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __mapper_args__ = {"polymorphic_on": "kind"}


class Place(Entity):
    """A unit of the administrative hierarchy. Places nest."""

    __tablename__ = "places"

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    country_code: Mapped[str] = mapped_column(String(COUNTRY_CODE_LENGTH))
    administrative_level: Mapped[str] = mapped_column(Text)
    parent_place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id"), index=True)
    government_institution_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    __table_args__ = (
        # The level is one of this country's.
        ForeignKeyConstraint(
            ["country_code", "administrative_level"],
            ["administrative_levels.country_code", "administrative_levels.name"],
            onupdate="CASCADE",
        ),
    )
    __mapper_args__ = {"polymorphic_identity": EntityKind.PLACE}


class Institution(Entity):
    """A public body that exists and may buy things."""

    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    institution_type: Mapped[str] = mapped_column(
        ForeignKey("institution_types.name", onupdate="CASCADE"), index=True
    )
    # What the agent thought the type was, when the type is `other`.
    suggested_type: Mapped[str | None] = mapped_column(Text)
    place_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("places.id"), index=True)
    # The body it sits under: from the page that says so, or the place's government.
    parent_institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    procurement_handled_by: Mapped[ProcurementHandledBy] = checked_string(
        ProcurementHandledBy, "procurement_handled_by", default=ProcurementHandledBy.SELF
    )
    # The verified homepage. That its status is `verified`, and that no other institution's
    # verified homepage is on the same webpage, is kept by `status_changes.py`: the status lives
    # on `entities`, out of a constraint's reach.
    homepage_id: Mapped[uuid.UUID | None] = mapped_column(index=True)

    # The target of a place's government foreign key.
    __table_args__ = (UniqueConstraint("id", "place_id"),)
    __mapper_args__ = {"polymorphic_identity": EntityKind.INSTITUTION}


class Source(Entity):
    """A web page that carries procurement signals for one institution."""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    webpage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webpages.id"), index=True)
    source_type: Mapped[str] = mapped_column(ForeignKey("source_types.name", onupdate="CASCADE"))
    access: Mapped[SourceAccess] = checked_string(
        SourceAccess, "access", default=SourceAccess.PUBLIC
    )

    __table_args__ = (UniqueConstraint("webpage_id", "institution_id", "source_type"),)
    __mapper_args__ = {"polymorphic_identity": EntityKind.SOURCE}


class Domain(Entity):
    """A website address: the unit of trust and of the browser allowlist. Trusted when its status
    is `verified` and its kind is `official`."""

    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    # The column is `kind`; the attribute makes way for the entity's own `kind`.
    domain_kind: Mapped[DomainKind] = checked_string(DomainKind, "kind")

    __mapper_args__ = {"polymorphic_identity": EntityKind.DOMAIN}


class Homepage(Entity):
    """An institution's official starting page on the web: a claim, with a status, until
    verified."""

    __tablename__ = "homepages"

    id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), primary_key=True)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), index=True)
    webpage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("webpages.id"), index=True)
    # The trusted page that linked to it; null for a search result or a directory link.
    found_on_webpage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("webpages.id"))
    # Why the claim was rejected, for the briefing and the reviewer.
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    # Set when a verified homepage sits on a platform: the URL prefix whose pages vouch for this
    # institution (spec section 6.4).
    trusted_path: Mapped[str | None] = mapped_column(Text)

    # The target of an institution's homepage foreign key.
    __table_args__ = (UniqueConstraint("id", "institution_id"),)
    __mapper_args__ = {"polymorphic_identity": EntityKind.HOMEPAGE}


# Two rules the tables enforce, as foreign keys over two columns: a place's government is an
# institution whose place is that place, and an institution's homepage is one of its own. Added
# once every table exists, because each pair points at the other (hence `use_alter`), and the
# mapper reads a child table's keys to `entities` when its class is made.
Base.metadata.tables["places"].append_constraint(
    ForeignKeyConstraint(
        ["government_institution_id", "id"],
        ["institutions.id", "institutions.place_id"],
        use_alter=True,
    )
)
Base.metadata.tables["institutions"].append_constraint(
    ForeignKeyConstraint(
        ["homepage_id", "id"], ["homepages.id", "homepages.institution_id"], use_alter=True
    )
)


# --- Attachments to places and institutions ---
# Each has `place_id` and `institution_id`, exactly one of them set. The unique constraints
# treat nulls as equal, so one rule covers both owners.


def one_owner() -> CheckConstraint:
    return CheckConstraint("num_nonnulls(place_id, institution_id) = 1", name="one_owner")


class Alias(UUIDPrimaryKey, Base):
    """Every name a body goes by, in any language."""

    __tablename__ = "aliases"

    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id"), index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    # BCP 47.
    language: Mapped[str] = mapped_column(Text)
    is_acronym: Mapped[bool] = mapped_column(default=False)
    entered_by: Mapped[EnteredBy] = checked_string(EnteredBy, "entered_by")

    __table_args__ = (
        one_owner(),
        UniqueConstraint("place_id", "institution_id", "text", postgresql_nulls_not_distinct=True),
        # For duplicate matching.
        Index(
            "ix_aliases_text_trgm",
            "text",
            postgresql_using="gin",
            postgresql_ops={"text": "gin_trgm_ops"},
        ),
    )


# The trigram index needs the extension. `create_all` (the tests) creates it here; the migration
# creates it itself.
event.listen(Base.metadata, "before_create", DDL("CREATE EXTENSION IF NOT EXISTS pg_trgm"))


class Identifier(UUIDPrimaryKey, Base):
    """A code in an outside scheme."""

    __tablename__ = "identifiers"

    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id"), index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    scheme: Mapped[IdentifierScheme] = checked_string(IdentifierScheme, "scheme")
    value: Mapped[str] = mapped_column(Text)
    official_list_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("official_lists.id"))

    __table_args__ = (
        one_owner(),
        # One per owner and scheme.
        UniqueConstraint(
            "place_id", "institution_id", "scheme", postgresql_nulls_not_distinct=True
        ),
        # One owner per value.
        UniqueConstraint("scheme", "value"),
    )


class Metric(UUIDPrimaryKey, Base):
    __tablename__ = "metrics"

    place_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("places.id"), index=True)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id"), index=True
    )
    name: Mapped[MetricName] = checked_string(MetricName, "name")
    year: Mapped[int]
    value: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    official_list_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("official_lists.id"))

    __table_args__ = (
        one_owner(),
        UniqueConstraint(
            "place_id", "institution_id", "name", "year", postgresql_nulls_not_distinct=True
        ),
    )


class InstitutionServedPlace(Base):
    """The places a multi-place body serves, such as a conservation authority. Filled by scripts
    and reviewers, never by the agent."""

    __tablename__ = "institution_served_places"

    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id"), primary_key=True
    )
    place_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("places.id"), primary_key=True)


# --- The web ---


class Webpage(UUIDPrimaryKey, Base):
    """Any URL the browser or `read_file` opened or was refused, or a list file the loader read.
    A log, not a claim."""

    __tablename__ = "webpages"

    # Normalized.
    url: Mapped[str] = mapped_column(Text, unique=True)
    # Null until a domain row covers the host: a page on a site a search returned is captured
    # before the agent claims the site, and `ensure_webpage` attaches the domain once it exists.
    domain_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("domains.id"), index=True)
    redirects_to_url: Mapped[str | None] = mapped_column(Text)
    # Null when the loader wrote the row.
    first_seen_assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id"))
