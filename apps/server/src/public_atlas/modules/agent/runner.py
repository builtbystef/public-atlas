"""Runs an assignment as fresh sessions until it ends (spec section 7.4). The budget is shared
across the sessions; a session that passes half the model's context window hands off with a
note; one job runs at most twenty sessions, then requeues itself; a job that fails on its last
attempt finishes the assignment `failed`. A session ends in one of three ways, collapsed into
one signal: a finishing tool set `ended`, the budget ran out (an exception), or the window
filled (a handoff)."""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace

from pydantic_ai import Agent, CallToolsNode, ModelRequestNode, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, ThinkingPart
from pydantic_ai.usage import UsageLimits
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.integrations.browser import create_browser
from public_atlas.jobs.context import current_attempt
from public_atlas.modules.agent import briefing, events, prompts, tools, video
from public_atlas.modules.agent.context import (
    Ended,
    SessionContext,
    SubjectMissingError,
    build_context,
)
from public_atlas.modules.assignments import lifecycle
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.descriptors import HANDOFF_MODEL, descriptor_for
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    Run,
    RunStatus,
    UsageKind,
)
from public_atlas.modules.evidence import service as evidence
from public_atlas.resources import Resources

logger = logging.getLogger(__name__)

HANDOFF_PROMPT = (
    "Your context is nearly full and this session ends now. Everything you saved is in the "
    "database already. Write a short handoff note for the next session on this assignment: "
    "what you were in the middle of, what is left to do, which pages to go to next, and any "
    "hunches. Plain text, no more than 300 words."
)
HANDOFF_FAILED = "The previous session ended with its context full; check status()."
# After this many sessions in one job the assignment is queued again, so others get a turn.
MAX_SESSIONS_PER_JOB = 20
# What the job returns when it put a paused run's assignment back.
PAUSED = "paused"
ERROR_LENGTH = 2000
ENDED_STATUSES = (AssignmentStatus.FINISHED, AssignmentStatus.CANCELLED)


class ModelUnavailableError(RuntimeError):
    """No model key is configured; the job fails and the queue retries it later."""


@dataclass(frozen=True, slots=True)
class SessionOutcome:
    """How a session left the assignment: ended, or to be continued from `handoff`."""

    ended: Ended | None
    handoff: str | None = None


# --- The job body ---


async def run_assignment(res: Resources, assignment_id: uuid.UUID) -> str:
    """A failed run is retried by the queue; on the last attempt the assignment finishes `failed`
    first, or it would stay `running` with no job left to run it."""
    try:
        return await _run(res, assignment_id)
    except Exception as exc:
        await record_failure(
            res, assignment_id, f"{type(exc).__name__}: {exc}", final=current_attempt.get().last
        )
        raise


async def _run(res: Resources, assignment_id: uuid.UUID) -> str:
    for _ in range(MAX_SESSIONS_PER_JOB):
        claimed = await _claim(res, assignment_id)
        if isinstance(claimed, str):
            return claimed
        assignment, run = claimed
        try:
            outcome = await run_session(res, assignment, run)
        except UsageLimitExceeded as exc:
            return await _finish(
                res, assignment_id, AssignmentResult.OUT_OF_BUDGET, f"Budget exhausted: {exc}"
            )
        except SubjectMissingError as exc:
            return await _finish(res, assignment_id, AssignmentResult.FAILED, str(exc))
        if outcome.ended is not None:
            return await _finish(res, assignment_id, outcome.ended.result, outcome.ended.summary)
        async with res.session() as session:
            row = await session.get_one(Assignment, assignment_id)
            row.handoff_note = outcome.handoff
            await session.commit()
    # Every session handed off and the assignment still runs: another job continues it once the
    # queue has had a turn. The row holds all the state.
    async with res.session() as session:
        row = await session.get_one(Assignment, assignment_id)
        await assignments.requeue(session, res.jobs, row)
        await session.commit()
    logger.info("Assignment %s queued again after %d sessions", assignment_id, MAX_SESSIONS_PER_JOB)
    return AssignmentStatus.QUEUED.value


async def _claim(res: Resources, assignment_id: uuid.UUID) -> tuple[Assignment, Run] | str:
    """Mark the assignment running and count the session, or return what the job ends with: the
    status it has already, `paused` when its run is paused (the job is put back), `cancelled`
    when its run was stopped."""
    async with res.session() as session:
        assignment = await session.get(Assignment, assignment_id)
        if assignment is None:
            return "gone"
        if assignment.status in ENDED_STATUSES:
            return assignment.status.value
        run = await session.get_one(Run, assignment.run_id)
        if run.status is RunStatus.STOPPED:
            # Stop cancelled what was held or queued; a running one finished its session.
            lifecycle.cancel(assignment)
            await session.commit()
            return AssignmentStatus.CANCELLED.value
        if run.status is RunStatus.PAUSED:
            await _put_back(res, session, assignment)
            await session.commit()
            return PAUSED
        if res.models is None:
            raise ModelUnavailableError(
                "PUBLIC_ATLAS_OPENAI_API_KEY is not set; assignments cannot run"
            )
        if assignment.status is AssignmentStatus.QUEUED:
            lifecycle.start(assignment)
        assignment.sessions += 1
        assignment.last_error = None
        await session.commit()
        return assignment, run


async def _put_back(res: Resources, session: AsyncSession, assignment: Assignment) -> None:
    """The run is paused: the job goes back with a short delay and the assignment stays
    `queued` (spec section 7.1). One that was mid-way (its run paused between sessions) is
    queued again first; it resumes from its handoff note."""
    if assignment.status is AssignmentStatus.RUNNING:
        lifecycle.queue(assignment)
    await assignments.queue_job(session, res.jobs, assignment, delay=res.settings.paused_run_delay)
    logger.info("Run %s is paused: assignment %s put back", assignment.run_id, assignment.id)


async def _finish(
    res: Resources, assignment_id: uuid.UUID, result: AssignmentResult, summary: str | None
) -> str:
    """End the assignment with `result`, create the work its finish asks for (nothing after
    `failed`), and drop the stored copies of the pages nothing cites (spec section 8.2)."""
    async with res.session() as session:
        row = await session.get_one(Assignment, assignment_id)
        lifecycle.finish(row, result, summary=summary)
        spawned = await assignments.spawn_on_finish(session, res.jobs, row)
        keys = await evidence.prune_unreferenced(session, row.id)
        await session.commit()
    await evidence.delete_objects(res.object_store, keys)
    logger.info(
        "Assignment %s finished %s after %d session(s); %d spawned, %d objects pruned",
        assignment_id,
        result.value,
        row.sessions,
        len(spawned),
        len(keys),
    )
    return result.value


async def record_failure(
    res: Resources, assignment_id: uuid.UUID, error: str, *, final: bool
) -> None:
    """A run failed with `error`, or its worker died. When `final` no run follows, so the
    assignment finishes `failed`; nothing is spawned after it."""
    async with res.session() as session:
        row = await session.get(Assignment, assignment_id)
        if row is None or row.status in ENDED_STATUSES:
            return
        row.last_error = error[:ERROR_LENGTH]
        if final:
            if row.status is AssignmentStatus.QUEUED:
                # Crashed before claiming it: the one move to finished goes through running.
                lifecycle.start(row)
            lifecycle.finish(
                row,
                AssignmentResult.FAILED,
                summary=f"Failed on the last attempt: {error}"[:ERROR_LENGTH],
            )
            keys = await evidence.prune_unreferenced(session, row.id)
        else:
            keys = []
        await session.commit()
    await evidence.delete_objects(res.object_store, keys)


# --- One session ---


async def run_session(res: Resources, assignment: Assignment, run: Run) -> SessionOutcome:
    """One agent session with a fresh context. Whether the assignment ended, else the handoff
    note for the next session."""
    if res.models is None:  # pragma: no cover - `_run` checked
        raise ModelUnavailableError("no model is configured")
    descriptor = descriptor_for(assignment.type)
    async with res.session() as session:
        ctx = await build_context(session, res, assignment)
        prompt = await briefing.briefing(ctx, session)
    standing = prompts.instructions(ctx)
    ctx.capture = evidence.PageCapture(
        res.session_factory, res.object_store, assignment_id=assignment.id
    )
    recording = video.recording_dir() if run.record_video else None
    browser = create_browser(
        res.settings,
        ctx.allowed_domains,
        ctx.capture,
        allow_private=res.settings.browser_allow_private_addresses,
        video_dir=recording,
    )
    # `read_file` fetches under the browser's policy: one allowlist, one pacing, one robots.
    ctx.policy = browser.policy
    agent = Agent(
        res.models.model(descriptor.model),
        deps_type=SessionContext,
        name=f"atlas.{assignment.type.value}",
        instructions=standing,
        toolsets=[tools.toolset(ctx, browser)],
        model_settings=res.models.settings(
            descriptor.model, cache_key=f"atlas:{assignment.type.value}"
        ),
        retries=tools.TOOL_RETRIES,
    )
    limits = remaining_budget(assignment)
    threshold = descriptor.model.context_window // 2
    over_threshold = False
    messages: list[ModelMessage] = []
    pending: ModelMessage | None = None
    text_output = False
    try:
        async with browser:
            try:
                async with agent.iter(prompt, deps=ctx, usage_limits=limits) as agent_run:
                    try:
                        async for node in agent_run:
                            # `total_tokens` is input plus output; input counts cached tokens.
                            if (
                                isinstance(node, CallToolsNode)
                                and node.model_response.usage.total_tokens > threshold
                            ):
                                over_threshold = True
                            if isinstance(node, ModelRequestNode) and (
                                ctx.ended is not None or over_threshold
                            ):
                                # The tool returns are not in the history yet; without them the
                                # handoff run would see unanswered calls.
                                pending = node.request
                                break
                    finally:
                        # Whatever ended the loop, a budget exception included, every request
                        # made is accounted for.
                        messages = [*agent_run.all_messages(), *([pending] if pending else [])]
                        text_output = agent_run.result is not None
            finally:
                await account(res, assignment, messages, purpose=assignment.type.value)
    finally:
        videos = (
            await video.store_videos(
                res.object_store,
                recording,
                assignment_id=assignment.id,
                session_no=assignment.sessions,
            )
            if recording is not None
            else []
        )
        await write_session_events(res, assignment, messages, instructions=standing, videos=videos)
    if ctx.ended is not None:
        return SessionOutcome(ended=ctx.ended)
    if not over_threshold:
        # Stopped without a finishing tool and with context to spare: the next session keeps the
        # old note and tries again.
        logger.warning(
            "Session %d on %s ended without a finishing tool%s",
            assignment.sessions,
            assignment.id,
            " (the model answered with text)" if text_output else "",
        )
        return SessionOutcome(ended=None, handoff=assignment.handoff_note)
    note = await handoff(res, assignment, messages)
    return SessionOutcome(ended=None, handoff=note)


def remaining_budget(assignment: Assignment) -> UsageLimits:
    """Raises `UsageLimitExceeded` when nothing is left, so a spent assignment never makes a
    request."""
    requests = assignment.budget_requests - assignment.requests_used
    tokens = assignment.budget_tokens - assignment.tokens_used
    if requests <= 0 or tokens <= 0:
        raise UsageLimitExceeded(
            f"{assignment.requests_used} of {assignment.budget_requests} requests and "
            f"{assignment.tokens_used} of {assignment.budget_tokens} tokens used before the "
            "session started"
        )
    return UsageLimits(request_limit=requests, total_tokens_limit=tokens)


async def account(
    res: Resources, assignment: Assignment, messages: Sequence[ModelMessage], *, purpose: str
) -> None:
    """Record every model response in `messages` as usage and add it to the assignment's spend.
    `assignment` is updated in memory too, so a handoff that follows starts from the spend so
    far."""
    responses = [message for message in messages if isinstance(message, ModelResponse)]
    if not responses:
        return
    async with res.session() as session:
        row = await session.get_one(Assignment, assignment.id)
        tokens = 0
        for response in responses:
            usage = response.usage
            units = usage.input_tokens + usage.output_tokens
            tokens += units
            await assignments.record_usage(
                session,
                assignment_id=row.id,
                kind=UsageKind.MODEL,
                provider=response.model_name or "unknown",
                purpose=purpose,
                units=units,
                cached_units=usage.cache_read_tokens,
                output_units=usage.output_tokens,
                at=response.timestamp,
            )
        row.requests_used += len(responses)
        # The same sum as Pydantic AI's `total_tokens`, which the usage limit is checked against.
        row.tokens_used += tokens
        await session.commit()
        assignment.requests_used = row.requests_used
        assignment.tokens_used = row.tokens_used


async def write_session_events(
    res: Resources,
    assignment: Assignment,
    messages: Sequence[ModelMessage],
    *,
    instructions: str,
    videos: Sequence[tuple[str, int]],
) -> None:
    rows = events.events_from(
        assignment.id, assignment.sessions, messages, instructions=instructions
    )
    for key, size in videos:
        rows.append(
            events.video_event(assignment.id, assignment.sessions, len(rows), key=key, size=size)
        )
    async with res.session() as session:
        await events.write_events(session, rows)
        await session.commit()


async def handoff(res: Resources, assignment: Assignment, messages: Sequence[ModelMessage]) -> str:
    """Ask the handoff model for the note the next session starts from. The request counts
    against the assignment's spend but the budget does not gate it: the note is wanted most
    when the budget is nearly gone. On failure the next session is told to start from
    `status()`."""
    if res.models is None:  # pragma: no cover - `_run` checked
        return HANDOFF_FAILED
    writer = Agent(
        res.models.model(HANDOFF_MODEL),
        output_type=str,
        name="atlas.handoff",
        model_settings=res.models.settings(
            HANDOFF_MODEL, cache_key="atlas:handoff", send_item_ids=False
        ),
    )
    try:
        result = await writer.run(HANDOFF_PROMPT, message_history=without_reasoning(messages))
    except Exception:
        logger.exception("Handoff note for %s failed", assignment.id)
        return HANDOFF_FAILED
    await account(res, assignment, result.new_messages(), purpose="handoff")
    return result.output


def without_reasoning(messages: Sequence[ModelMessage]) -> list[ModelMessage]:
    """The history minus the model's reasoning parts: encrypted reasoning is bound to the model
    that produced it, and the handoff may run on another."""
    stripped: list[ModelMessage] = []
    for message in messages:
        if not isinstance(message, ModelResponse):
            stripped.append(message)
            continue
        parts = [part for part in message.parts if not isinstance(part, ThinkingPart)]
        if parts:
            stripped.append(replace(message, parts=parts))
    return stripped
