"""`agent_run_events` (spec section 4.5): everything the agent saw, said and did in one session,
written as rows from the session's message list when it ends."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic_ai.messages import (
    BinaryContent,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from public_atlas.db.base import utcnow
from public_atlas.modules.agent.models import AgentRunEvent, EventKind

__all__ = ["events_from", "video_event", "write_events"]


def _jsonable(value: object) -> object:
    """JSON the column takes. An image (a screenshot) is noted, not stored: the row says what
    the model saw, the bytes stay out of the database."""
    if isinstance(value, BinaryContent):
        return f"<{value.media_type}, {len(value.data)} bytes>"
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return to_jsonable_python(value, fallback=str, serialize_unknown=True)


class _Events:
    """The rows of one session, numbered as they are added."""

    def __init__(self, assignment_id: uuid.UUID, session_no: int) -> None:
        self.assignment_id = assignment_id
        self.session_no = session_no
        self.rows: list[AgentRunEvent] = []

    def add(
        self, kind: EventKind, content: dict[str, Any], *, at: datetime, tool: str | None = None
    ) -> None:
        self.rows.append(
            AgentRunEvent(
                assignment_id=self.assignment_id,
                session=self.session_no,
                position=len(self.rows),
                kind=kind,
                tool=tool,
                content=content,
                at=at,
            )
        )

    def request(self, message: ModelRequest) -> None:
        for part in message.parts:
            match part:
                case UserPromptPart():
                    content = {"role": "user", "text": _jsonable(part.content)}
                    self.add(EventKind.PROMPT, content, at=part.timestamp)
                case SystemPromptPart():
                    content = {"role": "system", "text": part.content}
                    self.add(EventKind.PROMPT, content, at=part.timestamp)
                case ToolReturnPart():
                    content = {
                        "content": _jsonable(part.content),
                        "tool_call_id": part.tool_call_id,
                    }
                    self.add(EventKind.TOOL_RESULT, content, at=part.timestamp, tool=part.tool_name)
                case RetryPromptPart():
                    content = {"retry": _jsonable(part.content), "tool_call_id": part.tool_call_id}
                    self.add(EventKind.TOOL_RESULT, content, at=part.timestamp, tool=part.tool_name)
                case _:
                    continue

    def response(self, message: ModelResponse) -> None:
        for part in message.parts:
            match part:
                case TextPart():
                    self.add(EventKind.TEXT, {"text": part.content}, at=message.timestamp)
                case ToolCallPart():
                    content = {
                        "args": _jsonable(part.args_as_dict()),
                        "tool_call_id": part.tool_call_id,
                    }
                    self.add(
                        EventKind.TOOL_CALL, content, at=message.timestamp, tool=part.tool_name
                    )
                case _:
                    continue


def events_from(
    assignment_id: uuid.UUID,
    session_no: int,
    messages: Sequence[ModelMessage],
    *,
    instructions: str | None = None,
) -> list[AgentRunEvent]:
    """One row per thing in `messages`, in order: the instructions first when given, then each
    prompt, each of the model's texts and tool calls, and each tool result. Reasoning parts are
    left out: they are bound to the model that produced them."""
    events = _Events(assignment_id, session_no)
    if instructions is not None:
        first_at = next(
            (
                part.timestamp
                for message in messages
                if isinstance(message, ModelRequest)
                for part in message.parts
                if isinstance(part, UserPromptPart | SystemPromptPart)
            ),
            utcnow(),
        )
        events.add(EventKind.PROMPT, {"role": "instructions", "text": instructions}, at=first_at)
    for message in messages:
        if isinstance(message, ModelRequest):
            events.request(message)
        elif isinstance(message, ModelResponse):
            events.response(message)
    return events.rows


def video_event(
    assignment_id: uuid.UUID, session_no: int, position: int, *, key: str, size: int
) -> AgentRunEvent:
    """A recorded video of the session, by its storage key."""
    return AgentRunEvent(
        assignment_id=assignment_id,
        session=session_no,
        position=position,
        kind=EventKind.VIDEO,
        tool=None,
        content={"key": key, "size": size},
        at=utcnow(),
    )


async def write_events(session: AsyncSession, events: Sequence[AgentRunEvent]) -> None:
    session.add_all(events)
    await session.flush()
