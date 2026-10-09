"""The shapes of places and institutions as the console reads them (spec section 11, page 3):
a table row, and a detail with aliases, parent, homepage, sources by type and every quote."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from public_atlas.modules.graph.models import (
    DomainKind,
    EnteredBy,
    EntityKind,
    EntityStatus,
    ProcurementHandledBy,
    SourceAccess,
)

# The columns an institution list can be ordered by.
InstitutionSort = Literal["name", "institution_type", "status", "created_at", "place", "population"]
# The columns a place list can be ordered by.
PlaceSort = Literal["name", "administrative_level", "population"]
SortOrder = Literal["asc", "desc"]


class PlaceRef(BaseModel):
    id: uuid.UUID
    name: str
    administrative_level: str


class InstitutionRef(BaseModel):
    id: uuid.UUID
    name: str
    institution_type: str
    status: EntityStatus


class PlaceOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country_code: str
    administrative_level: str
    parent_place_id: uuid.UUID | None
    government_institution_id: uuid.UUID | None
    status: EntityStatus
    entered_by: EnteredBy
    created_at: datetime
    # The newest population figure, when there is one.
    population: int | None


class PlaceDetail(PlaceOutput):
    # The places above it, nearest first.
    parents: list[PlaceRef]
    government: InstitutionRef | None


class InstitutionOutput(BaseModel):
    """An institution as the table lists it."""

    id: uuid.UUID
    name: str
    institution_type: str
    suggested_type: str | None
    status: EntityStatus
    entered_by: EnteredBy
    place: PlaceRef
    # The newest population figure of its place, when there is one.
    place_population: int | None
    parent_institution_id: uuid.UUID | None
    procurement_handled_by: ProcurementHandledBy
    homepage_id: uuid.UUID | None
    # The verified homepage's URL, when there is one.
    homepage_url: str | None
    created_at: datetime


class AliasOutput(BaseModel):
    text: str
    language: str
    is_acronym: bool
    entered_by: EnteredBy


class IdentifierOutput(BaseModel):
    scheme: str
    value: str


class MetricOutput(BaseModel):
    name: str
    year: int
    value: Decimal


class HomepageOutput(BaseModel):
    """A homepage claim: every claim an institution made, verified or not."""

    id: uuid.UUID
    url: str
    status: EntityStatus
    entered_by: EnteredBy
    found_on_url: str | None
    rejected_reason: str | None
    trusted_path: str | None
    domain: str | None
    domain_status: EntityStatus | None
    created_at: datetime


class SourceOutput(BaseModel):
    id: uuid.UUID
    url: str
    source_type: str
    access: SourceAccess
    status: EntityStatus
    entered_by: EnteredBy
    created_at: datetime


class EvidenceOutput(BaseModel):
    id: uuid.UUID
    # The institution itself, one of its homepages or one of its sources.
    entity_id: uuid.UUID
    quote: str
    kind: str
    locator: int | None
    link_url: str | None
    entered_by: str
    assignment_id: uuid.UUID | None
    page_url: str
    snapshot_id: uuid.UUID
    snapshot_url: str | None = Field(
        description="A short-lived download link to the stored page or file; null once pruned."
    )


class InstitutionDetail(InstitutionOutput):
    aliases: list[AliasOutput]
    identifiers: list[IdentifierOutput]
    metrics: list[MetricOutput]
    # The place and each place above it, nearest first.
    places: list[PlaceRef]
    parent: InstitutionRef | None
    # The bodies that sit under this one.
    children: list[InstitutionRef]
    served_places: list[PlaceRef]
    homepages: list[HomepageOutput]
    sources: list[SourceOutput]
    evidence: list[EvidenceOutput]


# --- The graph as a picture ---

# What an edge stands for: the foreign key it was read from.
GraphRelation = Literal["parent", "government", "place", "homepage", "source", "domain", "serves"]


class GraphNode(BaseModel):
    """One entity as the graph view draws it: what to call it, its kind and status, and the
    figure its size follows."""

    id: uuid.UUID
    kind: EntityKind
    # A name, or the URL of a homepage or a source.
    label: str
    status: EntityStatus
    # A place's newest population figure.
    population: int | None = None
    # An institution's number of sources, rejected ones aside.
    source_count: int | None = None
    administrative_level: str | None = None
    institution_type: str | None = None
    source_type: str | None = None
    domain_kind: DomainKind | None = None
    # What an expansion of a place would bring: the places directly under it and the
    # institutions in it, rejected ones aside.
    child_count: int | None = None
    institution_count: int | None = None
    # A place's coverage: whether it has a government, and whether that government has a
    # verified homepage.
    governed: bool | None = None
    online: bool | None = None
    # An institution's coverage: whether its homepage is verified, and how many homepage claims
    # it has, rejected ones aside, the verified one among them.
    has_homepage: bool | None = None
    homepage_count: int | None = None


class GraphAncestor(BaseModel):
    """A place above the root, for the breadcrumb."""

    id: uuid.UUID
    label: str


class GraphEdge(BaseModel):
    """A link between two nodes, from the row that holds the key to the row it points at."""

    source: uuid.UUID
    target: uuid.UUID
    relation: GraphRelation


class GraphOutput(BaseModel):
    root_id: uuid.UUID
    # The places above the root, from the country down; for an institution, its place's chain
    # and the place itself.
    ancestors: list[GraphAncestor]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool = Field(
        description="True when the whole graph was over the cap and only the places and their "
        "governments came back; the client expands a place or an institution on demand."
    )
