"""The daily purges: a video goes from storage `video_keep_days` after its assignment finished
and its event says so; the events go after `events_keep_days`; findings, usage and the summary
stay."""

import uuid
from dataclasses import replace
from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from public_atlas.db.base import utcnow
from public_atlas.jobs.tasks import AnyTask, defer
from public_atlas.modules.agent import events, video
from public_atlas.modules.agent.jobs import purge_events, purge_videos
from public_atlas.modules.agent.models import AgentRunEvent, EventKind
from public_atlas.modules.assignments import service as assignments
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
    Usage,
    UsageKind,
)

if TYPE_CHECKING:
    from tests.integration.conftest import Database, InlineConnector
    from tests.integration.modules.conftest import Build, World

    from public_atlas.integrations.storage.memory import MemoryObjectStore


async def run_now(db: Database, queue: InlineConnector, task: AnyTask) -> int:
    """Defer `task`; the inline worker runs it at once. The deferring session commits, as the
    API does, or closing it would roll back what the job wrote inside its savepoint."""
    assert queue.resources is not None
    async with db.session() as session:
        job_id = await defer(queue.resources.jobs, session, task)
        await session.commit()
    return job_id


def test_videos_then_events_are_purged_by_age_and_nothing_else_is(
    db: Database,
    queue: InlineConnector,
    object_store: MemoryObjectStore,
    world: World,
    build: type[Build],
):
    assert queue.resources is not None
    queue.resources = replace(
        queue.resources,
        settings=queue.resources.settings.model_copy(
            update={"video_keep_days": 7, "events_keep_days": 30}
        ),
    )

    async def prepare() -> tuple[uuid.UUID, uuid.UUID, str, str]:
        async with db.session() as session:
            old = await build.open_assignment(
                session,
                world.run,
                AssignmentType.FIND_SOURCES,
                world.county.id,
                status=AssignmentStatus.RUNNING,
            )
            assignments.lifecycle.finish(old, AssignmentResult.COMPLETE, summary="old summary")
            old.finished_at = utcnow() - timedelta(days=10)
            recent = await build.open_assignment(
                session,
                world.run,
                AssignmentType.FIND_HOMEPAGE,
                world.town.id,
                status=AssignmentStatus.RUNNING,
            )
            assignments.lifecycle.finish(recent, AssignmentResult.COMPLETE, summary="recent")
            old_key = video.video_key(old.id, 1, 0)
            recent_key = video.video_key(recent.id, 1, 0)
            for key in (old_key, recent_key):
                await object_store.put(key, b"webm", video.MEDIA_TYPE)
            await events.write_events(
                session,
                [
                    *events.events_from(old.id, 1, [], instructions="old instructions"),
                    events.video_event(old.id, 1, 1, key=old_key, size=4),
                    *events.events_from(recent.id, 1, [], instructions="recent instructions"),
                    events.video_event(recent.id, 1, 1, key=recent_key, size=4),
                ],
            )
            await assignments.record_usage(
                session,
                assignment_id=old.id,
                kind=UsageKind.MODEL,
                provider="gpt-6-luna",
                purpose="find_sources",
                units=10,
            )
            await session.commit()
            return old.id, recent.id, old_key, recent_key

    old_id, recent_id, old_key, recent_key = db.run(prepare)

    db.run(run_now, db, queue, purge_videos)

    async def rows(assignment_id: uuid.UUID) -> list[AgentRunEvent]:
        async with db.session() as session:
            return await assignments.events_of(session, assignment_id)

    old_events = db.run(rows, old_id)
    assert old_key not in object_store.objects
    assert recent_key in object_store.objects
    video_row = next(event for event in old_events if event.kind is EventKind.VIDEO)
    assert set(video_row.content) == {"purged_at", "size"}
    assert len(old_events) == 2
    assert all(
        event.content.get("key")
        for event in db.run(rows, recent_id)
        if event.kind is EventKind.VIDEO
    )

    async def age_the_recent_one() -> None:
        async with db.session() as session:
            row = await session.get_one(Assignment, recent_id)
            row.finished_at = utcnow() - timedelta(days=40)
            await session.commit()

    db.run(age_the_recent_one)
    db.run(run_now, db, queue, purge_events)

    async def after() -> tuple[int, int, Assignment, int]:
        async with db.session() as session:
            return (
                len(await assignments.events_of(session, old_id)),
                len(await assignments.events_of(session, recent_id)),
                await session.get_one(Assignment, old_id),
                len(
                    list(await session.scalars(select(Usage).where(Usage.assignment_id == old_id)))
                ),
            )

    old_count, recent_count, old_row, usage_count = db.run(after)
    # Only the one past 30 days loses its events, and its video goes with them; the one finished
    # 10 days ago keeps its events (its video went at 7 days).
    assert (old_count, recent_count) == (2, 0)
    assert recent_key not in object_store.objects
    # Findings, usage and the summary are never purged.
    assert old_row.summary == "old summary"
    assert usage_count == 1
