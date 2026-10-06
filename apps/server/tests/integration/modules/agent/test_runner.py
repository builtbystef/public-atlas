"""The runner driven by a scripted model (spec section 7.4): a session runs the tools and ends
with the finishing tool; its calls are accounted for and written as events; a full window hands
off and the next session carries on; the budget ends an assignment `out_of_budget`; a job that
fails on its last attempt ends it `failed`; twenty sessions requeue it; a stopped run cancels it;
what it finishes spawns, and the pages nothing cites are pruned; a video is stored and noted."""

import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo
from pydantic_ai.usage import RequestUsage
from sqlalchemy import select

from public_atlas.jobs.context import Attempt, current_attempt
from public_atlas.modules.agent import runner, video
from public_atlas.modules.agent.models import AgentRunEvent, EventKind
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.descriptors import descriptor_for
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
    Run,
    Usage,
)
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.evidence.models import EvidenceKind, Snapshot
from public_atlas.modules.graph.models import EnteredBy

if TYPE_CHECKING:
    from collections.abc import Callable

    from tests.integration.conftest import Database, InlineConnector
    from tests.integration.modules.conftest import Build, Script, World

    from public_atlas.integrations.storage.memory import MemoryObjectStore
    from public_atlas.resources import Resources

FIND_SOURCES = AssignmentType.FIND_SOURCES
FIND_INSTITUTIONS = AssignmentType.FIND_INSTITUTIONS
WINDOW = descriptor_for(FIND_SOURCES).model.context_window


@pytest.fixture
def make(db: Database, world: World, build: type[Build]) -> Callable[..., Assignment]:
    """A queued assignment in the world's step-mode run, as a released one is."""

    def factory(
        assignment_type: AssignmentType = FIND_SOURCES,
        subject_id: uuid.UUID | None = None,
        *,
        budget_requests: int = 10,
    ) -> Assignment:
        async def create() -> Assignment:
            async with db.session() as session:
                row = await build.open_assignment(
                    session, world.run, assignment_type, subject_id or world.county.id
                )
                row.budget_requests = budget_requests
                row.budget_tokens = 10_000_000
                await session.commit()
                return row

        return db.run(create)

    return factory


@pytest.fixture
def reload(db: Database) -> Callable[[uuid.UUID], Assignment]:
    def read(assignment_id: uuid.UUID) -> Assignment:
        async def get() -> Assignment:
            async with db.session() as session:
                return await session.get_one(Assignment, assignment_id)

        return db.run(get)

    return read


@pytest.fixture
def events_of(db: Database) -> Callable[[uuid.UUID], list[AgentRunEvent]]:
    def read(assignment_id: uuid.UUID) -> list[AgentRunEvent]:
        async def get() -> list[AgentRunEvent]:
            async with db.session() as session:
                return await assignments.events_of(session, assignment_id)

        return db.run(get)

    return read


def test_a_session_runs_the_tools_accounts_for_its_calls_and_finishes(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
    events_of: Callable[[uuid.UUID], list[AgentRunEvent]],
    count_calls: Callable[[list[ModelMessage]], int],
):
    seen: list[str] = []

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        """status, a finish the checks refuse, then a finish that holds."""
        tools = {tool.name for tool in info.function_tools}
        assert {"navigate", "snapshot", "get_text", "status", "finish"} <= tools
        assert "search" not in tools
        calls = count_calls(messages)
        if calls == 0:
            return ModelResponse(parts=[ToolCallPart("status", {})])
        if calls == 1:
            returns = messages[-1].parts
            seen.append(str(getattr(returns[0], "content", "")))
            return ModelResponse(
                parts=[ToolCallPart("finish", {"summary": "Done.", "types_not_found": ["castle"]})]
            )
        assert isinstance(messages[-1].parts[0], RetryPromptPart)
        # The checklist: every source type expected of the county is named as not found.
        not_found = world.rules.expected_source_types(world.county.institution_type)
        return ModelResponse(
            parts=[
                TextPart("Finishing."),
                ToolCallPart(
                    "finish", {"summary": "Found the budget page.", "types_not_found": not_found}
                ),
            ],
            usage=RequestUsage(input_tokens=1000, cache_read_tokens=800, output_tokens=50),
        )

    res = scripted(script)
    assignment = make()
    assert db.run(runner.run_assignment, res, assignment.id) == "complete"

    row = reload(assignment.id)
    assert (row.status, row.result, row.summary) == (
        AssignmentStatus.FINISHED,
        AssignmentResult.COMPLETE,
        "Found the budget page.",
    )
    assert (row.sessions, row.requests_used) == (1, 3)
    # The scripted model estimates tokens for the responses given none; the last is as set.
    assert row.tokens_used >= 1050
    assert row.started_at is not None
    assert row.finished_at is not None
    assert row.handoff_note is None
    # `status` reported the subject's standing.
    assert "Saved in this assignment:" in seen[0]
    assert "Budget left: 9 requests" in seen[0]

    async def usage() -> list[Usage]:
        async with db.session() as session:
            return list(
                await session.scalars(
                    select(Usage).where(Usage.assignment_id == assignment.id).order_by(Usage.at)
                )
            )

    rows = db.run(usage)
    assert [(u.provider, u.purpose) for u in rows] == [("scripted", "find_sources")] * 3
    assert (rows[-1].units, rows[-1].cached_units) == (1050, 800)
    assert sum(u.units for u in rows) == row.tokens_used
    events = events_of(assignment.id)
    assert [(e.kind, e.tool) for e in events] == [
        (EventKind.PROMPT, None),
        (EventKind.PROMPT, None),
        (EventKind.TOOL_CALL, "status"),
        (EventKind.TOOL_RESULT, "status"),
        (EventKind.TOOL_CALL, "finish"),
        (EventKind.TOOL_RESULT, "finish"),
        (EventKind.TEXT, None),
        (EventKind.TOOL_CALL, "finish"),
        (EventKind.TOOL_RESULT, "finish"),
    ]
    assert events[0].content["role"] == "instructions"
    assert "Your goal:" in events[0].content["text"]
    assert "County of Elm" in events[1].content["text"]
    assert "names no source type the country lists" in events[5].content["retry"]
    assert events[8].content["content"] == "Assignment finished (complete)."
    assert all(e.session == 1 for e in events)


def test_a_full_window_hands_off_and_the_next_session_finishes(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
    events_of: Callable[[uuid.UUID], list[AgentRunEvent]],
    prompt_of: Callable[[list[ModelMessage]], str],
):
    briefings: list[str] = []

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = prompt_of(messages)
        if prompt.startswith("Your context is nearly full"):
            return ModelResponse(parts=[TextPart("Was reading the budget page; try the tenders.")])
        briefings.append(prompt)
        if "Handoff note from the previous session" in prompt:
            return ModelResponse(
                parts=[ToolCallPart("finish", {"summary": "Done after handoff.", **not_found})]
            )
        return ModelResponse(
            parts=[ToolCallPart("status", {})],
            usage=RequestUsage(input_tokens=WINDOW // 2 + 1, output_tokens=10),
        )

    not_found = {
        "types_not_found": world.rules.expected_source_types(world.county.institution_type)
    }
    res = scripted(script)
    assignment = make()
    assert db.run(runner.run_assignment, res, assignment.id) == "complete"
    row = reload(assignment.id)
    assert (row.status, row.result, row.sessions) == (
        AssignmentStatus.FINISHED,
        AssignmentResult.COMPLETE,
        2,
    )
    assert row.handoff_note == "Was reading the budget page; try the tenders."
    assert row.summary == "Done after handoff."
    assert len(briefings) == 2
    assert "try the tenders" in briefings[1]
    # The handoff request counts like any other: status, the note, then the finish.
    assert row.requests_used == 3
    events = events_of(assignment.id)
    assert {e.session for e in events} == {1, 2}
    # The first session's events end with the status call's result, before the handoff.
    first = [e for e in events if e.session == 1]
    assert [(e.kind, e.tool) for e in first[-2:]] == [
        (EventKind.TOOL_CALL, "status"),
        (EventKind.TOOL_RESULT, "status"),
    ]

    async def purposes() -> list[str]:
        async with db.session() as session:
            return list(
                await session.scalars(
                    select(Usage.purpose)
                    .where(Usage.assignment_id == assignment.id)
                    .order_by(Usage.at)
                )
            )

    assert sorted(db.run(purposes)) == ["find_sources", "find_sources", "handoff"]


def test_a_spent_budget_ends_the_assignment_before_any_request(
    db: Database,
    scripted: Callable[[Script], Resources],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
):
    calls = 0

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        nonlocal calls
        calls += 1
        return ModelResponse(parts=[ToolCallPart("status", {})])

    res = scripted(script)
    assignment = make(budget_requests=2)

    async def spend() -> None:
        async with db.session() as session:
            row = await session.get_one(Assignment, assignment.id)
            row.requests_used = 2
            await session.commit()

    db.run(spend)
    assert db.run(runner.run_assignment, res, assignment.id) == "out_of_budget"
    row = reload(assignment.id)
    assert calls == 0
    assert (row.status, row.result) == (AssignmentStatus.FINISHED, AssignmentResult.OUT_OF_BUDGET)
    assert row.summary is not None
    assert row.summary.startswith("Budget exhausted")


def test_a_budget_exhausted_mid_session_ends_the_assignment_out_of_budget(
    db: Database,
    scripted: Callable[[Script], Resources],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
):
    def stalling(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[ToolCallPart("status", {})])

    res = scripted(stalling)
    assignment = make(budget_requests=3)
    assert db.run(runner.run_assignment, res, assignment.id) == "out_of_budget"
    row = reload(assignment.id)
    assert (row.result, row.requests_used, row.sessions) == (AssignmentResult.OUT_OF_BUDGET, 3, 1)
    assert row.summary is not None
    assert row.summary.startswith("Budget exhausted")


def test_a_failed_job_ends_the_assignment_failed_on_the_last_attempt_only(
    db: Database,
    scripted: Callable[[Script], Resources],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
):
    def failing(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise RuntimeError("model down")

    res = scripted(failing)
    assignment = make()

    async def run_as(attempt: Attempt) -> None:
        token = current_attempt.set(attempt)
        try:
            await runner.run_assignment(res, assignment.id)
        finally:
            current_attempt.reset(token)

    with pytest.raises(RuntimeError, match="model down"):
        db.run(run_as, Attempt(1, last=False))
    row = reload(assignment.id)
    assert (row.status, row.result, row.sessions) == (AssignmentStatus.RUNNING, None, 1)
    assert row.last_error == "RuntimeError: model down"

    with pytest.raises(RuntimeError, match="model down"):
        db.run(run_as, Attempt(5, last=True))
    row = reload(assignment.id)
    assert (row.status, row.result, row.sessions) == (
        AssignmentStatus.FINISHED,
        AssignmentResult.FAILED,
        2,
    )
    assert row.summary == "Failed on the last attempt: RuntimeError: model down"
    assert row.finished_at is not None


def test_no_model_configured_fails_the_job_and_leaves_the_assignment_to_retry(
    db: Database,
    queue: InlineConnector,
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
):
    assert queue.resources is not None
    assert queue.resources.models is None
    assignment = make()
    with pytest.raises(runner.ModelUnavailableError):
        db.run(runner.run_assignment, queue.resources, assignment.id)
    row = reload(assignment.id)
    # Outside a job every attempt is the last, so it finishes `failed`, with the cause kept.
    assert (row.status, row.result) == (AssignmentStatus.FINISHED, AssignmentResult.FAILED)
    assert "OPENAI_API_KEY" in (row.last_error or "")


def test_a_job_that_hits_the_session_cap_queues_the_assignment_again(
    db: Database,
    world: World,
    queue: InlineConnector,
    scripted: Callable[[Script], Resources],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
    prompt_of: Callable[[list[ModelMessage]], str],
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(runner, "MAX_SESSIONS_PER_JOB", 1)

    def script(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        prompt = prompt_of(messages)
        if prompt.startswith("Your context is nearly full"):
            return ModelResponse(parts=[TextPart("Halfway down the list.")])
        if "Handoff note from the previous session" in prompt:
            not_found = world.rules.expected_source_types(world.county.institution_type)
            return ModelResponse(
                parts=[
                    ToolCallPart("finish", {"summary": "Second job.", "types_not_found": not_found})
                ]
            )
        return ModelResponse(
            parts=[ToolCallPart("status", {})],
            usage=RequestUsage(input_tokens=WINDOW, output_tokens=10),
        )

    res = scripted(script)
    assignment = make()
    # The first job requeues after one session; the inline queue runs the second at once.
    assert db.run(runner.run_assignment, res, assignment.id) == "queued"
    row = reload(assignment.id)
    assert (row.status, row.result, row.sessions, row.summary) == (
        AssignmentStatus.FINISHED,
        AssignmentResult.COMPLETE,
        2,
        "Second job.",
    )
    jobs = [
        job
        for job in queue.jobs.values()
        if job["task_name"] == assignments.RUN_ASSIGNMENT_TASK
        and job["args"]["assignment_id"] == str(assignment.id)
    ]
    assert [job["status"] for job in jobs] == ["succeeded"]


def test_a_stopped_run_cancels_a_running_assignment_after_its_session(
    db: Database,
    world: World,
    scripted: Callable[[Script], Resources],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
):
    def stopping(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        # The session hands off with a full window while someone stops the run.
        return ModelResponse(
            parts=[TextPart("note")]
            if "nearly full" in str(messages[-1])
            else [ToolCallPart("status", {})],
            usage=RequestUsage(input_tokens=WINDOW, output_tokens=1),
        )

    res = scripted(stopping)
    assignment = make()

    async def stop_between_sessions() -> None:
        async with db.session() as session:
            run = await session.get_one(Run, world.run.id)
            await assignments.stop_run(session, run)
            await session.commit()

    async def scenario() -> str:
        # Claim and run one session by hand, then let the runner find the run stopped.
        res_ = res
        async with res_.session() as session:
            row = await session.get_one(Assignment, assignment.id)
            assignments.lifecycle.start(row)
            row.sessions += 1
            await session.commit()
            run = await session.get_one(Run, row.run_id)
        outcome = await runner.run_session(res_, row, run)
        assert outcome.ended is None
        await stop_between_sessions()
        return await runner.run_assignment(res_, assignment.id)

    assert db.run(scenario) == "cancelled"
    assert reload(assignment.id).status is AssignmentStatus.CANCELLED


def test_finishing_spawns_the_homepage_searches_and_prunes_uncited_pages(
    db: Database,
    world: World,
    build: type[Build],
    object_store: MemoryObjectStore,
    scripted: Callable[[Script], Resources],
    finish_script: Callable[..., Script],
    make: Callable[..., Assignment],
    reload: Callable[[uuid.UUID], Assignment],
):
    """A `find_institutions` assignment that saved a library (with a quote from a page it
    opened) finishes: the library gets `find_homepage`, held in the step-mode run; the cited
    page keeps its stored copy and the page nothing cites loses its bytes."""
    res = scripted(finish_script("Found the library."))
    assignment = make(FIND_INSTITUTIONS, world.oakville.id)

    async def prepare() -> tuple[uuid.UUID, Snapshot, Snapshot]:
        async with db.session() as session:
            library = await build.candidate_institution(session, world.oakville, "Oakville Library")
            _, cited = await build.capture(
                session,
                object_store,
                "https://www.elmcounty.ca/oakville/libraries",
                "<html>Oakville Library serves Oakville</html>",
                "Oakville Library serves Oakville",
                assignment_id=assignment.id,
            )
            _, passed = await build.capture(
                session,
                object_store,
                "https://www.elmcounty.ca/oakville/about",
                "<html>About Oakville</html>",
                "About Oakville",
                assignment_id=assignment.id,
            )
            await evidence.add_evidence(
                session,
                entity_id=library.id,
                snapshot=cited,
                kind=EvidenceKind.APPEARS_ON,
                quote="Oakville Library serves Oakville",
                entered_by=EnteredBy.AGENT,
                assignment_id=assignment.id,
            )
            await session.commit()
            return library.id, cited, passed

    library_id, cited, passed = db.run(prepare)
    before = set(object_store.objects)
    assert db.run(runner.run_assignment, res, assignment.id) == "complete"
    assert reload(assignment.id).result is AssignmentResult.COMPLETE

    async def check() -> tuple[list[Assignment], Snapshot, Snapshot]:
        async with db.session() as session:
            spawned = await assignments.list_assignments(session, subject_id=library_id)
            return (
                spawned,
                await session.get_one(Snapshot, cited.id),
                await session.get_one(Snapshot, passed.id),
            )

    spawned, kept, pruned = db.run(check)
    assert [(a.type, a.status, a.parent_assignment_id, a.run_id) for a in spawned] == [
        (AssignmentType.FIND_HOMEPAGE, AssignmentStatus.HELD, assignment.id, world.run.id)
    ]
    assert kept.pruned_at is None
    assert kept.bytes_key in object_store.objects
    assert pruned.pruned_at is not None
    assert pruned.bytes_key not in object_store.objects
    # The uncited page's bytes and its text.
    assert len(before) - len(object_store.objects) == 2


def test_a_recording_run_stores_the_videos_and_notes_them(
    db: Database,
    world: World,
    object_store: MemoryObjectStore,
    scripted: Callable[[Script], Resources],
    finish_script: Callable[..., Script],
    make: Callable[..., Assignment],
    events_of: Callable[[uuid.UUID], list[AgentRunEvent]],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Chromium is not started by a scripted model that never browses, so the recording the
    browser would leave behind is put in the directory by hand; what follows is the runner's."""
    recording = tmp_path / "recording"
    recording.mkdir()
    (recording / "page.webm").write_bytes(b"webm bytes")
    (recording / "empty.webm").write_bytes(b"")
    monkeypatch.setattr(video, "recording_dir", lambda: recording)
    res = scripted(finish_script())

    async def record() -> None:
        async with db.session() as session:
            run = await session.get_one(Run, world.run.id)
            run.record_video = True
            await session.commit()

    db.run(record)
    assignment = make()
    assert db.run(runner.run_assignment, res, assignment.id) == "complete"
    events = events_of(assignment.id)
    videos = [event for event in events if event.kind is EventKind.VIDEO]
    assert len(videos) == 1
    key = video.video_key(assignment.id, 1, 0)
    assert videos[0].content == {"key": key, "size": len(b"webm bytes")}
    assert videos[0].position == len(events) - 1
    assert object_store.objects[key] == (b"webm bytes", "video/webm")
    # The recording directory is gone with its files.
    assert not recording.exists()
    shutil.rmtree(tmp_path, ignore_errors=True)
