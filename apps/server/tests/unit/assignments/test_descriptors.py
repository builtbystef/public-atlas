"""One descriptor per assignment type, each whole: a subject kind, the tools with the finishing
ones among them, a goal, a checklist, a budget and a model (spec sections 7.2, 7.4 and 8.4)."""

from public_atlas.integrations.browser import TOOLS as BROWSING
from public_atlas.modules.assignments.descriptors import (
    DESCRIPTORS,
    HANDOFF_MODEL,
    Checklist,
    descriptor_for,
)
from public_atlas.modules.assignments.models import AssignmentType
from public_atlas.modules.graph.models import EntityKind

# The findings of spec section 8.1, by name.
FINDINGS = {
    "read_file",
    "search",
    "save_institution",
    "save_homepage",
    "save_source",
    "confirm_domain",
    "reject_domain",
    "domain_moved",
    "status",
    "request_review",
    "finish",
}


def test_every_type_has_a_whole_descriptor():
    assert set(DESCRIPTORS) == set(AssignmentType)
    for assignment_type in AssignmentType:
        descriptor = descriptor_for(assignment_type)
        assert descriptor.type is assignment_type
        assert set(descriptor.tools) <= set(BROWSING) | FINDINGS
        assert descriptor.finishing_tools
        assert set(descriptor.finishing_tools) <= set(descriptor.tools)
        assert len(descriptor.goal) > 100
        assert descriptor.budget.requests > 0
        assert descriptor.budget.tokens > 0
        assert descriptor.model.context_window >= 100_000


def test_subjects_tools_and_checklists_follow_the_spec():
    homepage = descriptor_for(AssignmentType.FIND_HOMEPAGE)
    institutions = descriptor_for(AssignmentType.FIND_INSTITUTIONS)
    sources = descriptor_for(AssignmentType.FIND_SOURCES)
    assert homepage.subject_kind is EntityKind.INSTITUTION
    assert institutions.subject_kind is EntityKind.PLACE
    assert sources.subject_kind is EntityKind.INSTITUTION
    # Search and the domain decisions belong to `find_homepage` alone.
    for name in ("search", "confirm_domain", "reject_domain", "domain_moved"):
        assert name in homepage.tools
        assert name not in institutions.tools
        assert name not in sources.tools
    assert "save_source" in sources.tools
    assert institutions.checklist is Checklist.INSTITUTION_TYPES
    assert sources.checklist is Checklist.SOURCE_TYPES
    assert homepage.checklist is Checklist.NONE
    # Every type browses, reads files, can ask a human and can report its status.
    for descriptor in DESCRIPTORS.values():
        assert set(BROWSING) <= set(descriptor.tools)
        assert {"read_file", "status", "request_review"} <= set(descriptor.tools)


def test_the_models_are_luna_at_the_efforts_of_the_spec():
    for descriptor in DESCRIPTORS.values():
        assert descriptor.model.name == "gpt-6-luna"
        assert descriptor.model.reasoning_effort == "xhigh"
    assert (HANDOFF_MODEL.name, HANDOFF_MODEL.reasoning_effort) == ("gpt-6-luna", "medium")
