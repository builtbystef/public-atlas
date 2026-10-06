"""The findings: the typed functions the agent calls through the adapter in `tools.py` (spec
section 8.1). Each takes the run context and returns a typed result rendered to text at the
edge, or raises `FindingError` with what the model should do instead. Beside each tool is the
function that does the work on a session, which the tests call directly."""

from public_atlas.modules.agent.findings.domains import (
    MAX_CONFIRM_ATTEMPTS,
    Decided,
    DomainQuote,
    Quote,
    candidate_moved,
    confirm_candidate,
    confirm_domain,
    domain_moved,
    reject_candidate,
    reject_domain,
)
from public_atlas.modules.agent.findings.files import (
    MAX_SEARCHES,
    SearchOutcome,
    read_file,
    search,
    search_web,
)
from public_atlas.modules.agent.findings.homepages import (
    SavedHomepage,
    record_homepage,
    save_homepage,
)
from public_atlas.modules.agent.findings.institutions import (
    SavedInstitution,
    record_institution,
    save_institution,
)
from public_atlas.modules.agent.findings.session import (
    MAX_VISITED,
    Finished,
    Reviewed,
    Status,
    describe,
    expected_types,
    finish,
    finish_assignment,
    raise_item,
    remaining_checklist,
    request_review,
    saved_entities,
    status,
    status_of,
)
from public_atlas.modules.agent.findings.shared import (
    DECISION_NEW,
    DECISION_UNSURE,
    FindingError,
    LikelyDuplicates,
    in_session,
    visited_page,
)
from public_atlas.modules.agent.findings.sources import SavedSource, record_source, save_source

__all__ = [
    "DECISION_NEW",
    "DECISION_UNSURE",
    "MAX_CONFIRM_ATTEMPTS",
    "MAX_SEARCHES",
    "MAX_VISITED",
    "Decided",
    "DomainQuote",
    "FindingError",
    "Finished",
    "LikelyDuplicates",
    "Quote",
    "Reviewed",
    "SavedHomepage",
    "SavedInstitution",
    "SavedSource",
    "SearchOutcome",
    "Status",
    "candidate_moved",
    "confirm_candidate",
    "confirm_domain",
    "describe",
    "domain_moved",
    "expected_types",
    "finish",
    "finish_assignment",
    "in_session",
    "raise_item",
    "read_file",
    "record_homepage",
    "record_institution",
    "record_source",
    "reject_candidate",
    "reject_domain",
    "remaining_checklist",
    "request_review",
    "save_homepage",
    "save_institution",
    "save_source",
    "saved_entities",
    "search",
    "search_web",
    "status",
    "status_of",
    "visited_page",
]
