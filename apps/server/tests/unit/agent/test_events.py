"""A session's message list becomes rows: the instructions, each prompt, the model's words and
tool calls, and each tool result, in order; reasoning parts are left out."""

import uuid

from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from public_atlas.modules.agent.events import events_from, video_event
from public_atlas.modules.agent.models import EventKind


def test_events_follow_the_messages_in_order():
    assignment_id = uuid.uuid7()
    messages = [
        ModelRequest(parts=[UserPromptPart("Assignment: find_sources.")]),
        ModelResponse(
            parts=[
                ThinkingPart("secret reasoning"),
                TextPart("Looking at the homepage."),
                ToolCallPart("navigate", {"url": "https://www.elmcounty.ca/"}, tool_call_id="c1"),
            ],
            model_name="scripted",
        ),
        ModelRequest(
            parts=[
                ToolReturnPart("navigate", "Navigated to https://www.elmcounty.ca/", "c1"),
            ]
        ),
        ModelResponse(
            parts=[ToolCallPart("screenshot", '{"full_page": false}', tool_call_id="c2")],
            model_name="scripted",
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    "screenshot", BinaryContent(data=b"\x89PNG", media_type="image/png"), "c2"
                ),
                RetryPromptPart("quote not found", tool_name="save_source", tool_call_id="c3"),
            ]
        ),
    ]
    events = events_from(assignment_id, 2, messages, instructions="You are Public Atlas.")
    assert [event.position for event in events] == list(range(len(events)))
    assert all(event.assignment_id == assignment_id and event.session == 2 for event in events)
    assert [(event.kind, event.tool) for event in events] == [
        (EventKind.PROMPT, None),
        (EventKind.PROMPT, None),
        (EventKind.TEXT, None),
        (EventKind.TOOL_CALL, "navigate"),
        (EventKind.TOOL_RESULT, "navigate"),
        (EventKind.TOOL_CALL, "screenshot"),
        (EventKind.TOOL_RESULT, "screenshot"),
        (EventKind.TOOL_RESULT, "save_source"),
    ]
    assert events[0].content == {"role": "instructions", "text": "You are Public Atlas."}
    assert events[1].content == {"role": "user", "text": "Assignment: find_sources."}
    assert events[2].content == {"text": "Looking at the homepage."}
    # Arguments as a dict whether the model sent them as one or as JSON text.
    assert events[3].content["args"] == {"url": "https://www.elmcounty.ca/"}
    assert events[5].content["args"] == {"full_page": False}
    # An image is noted, not stored.
    assert events[6].content["content"] == "<image/png, 4 bytes>"
    assert events[7].content["retry"] == "quote not found"
    assert "secret reasoning" not in str([event.content for event in events])


def test_no_instructions_means_no_instructions_row():
    events = events_from(uuid.uuid7(), 1, [ModelRequest(parts=[UserPromptPart("hello")])])
    assert [event.kind for event in events] == [EventKind.PROMPT]


def test_a_video_event_carries_its_storage_key():
    event = video_event(uuid.uuid7(), 1, 9, key="videos/x/1/0.webm", size=1234)
    assert (event.kind, event.position, event.content) == (
        EventKind.VIDEO,
        9,
        {"key": "videos/x/1/0.webm", "size": 1234},
    )
