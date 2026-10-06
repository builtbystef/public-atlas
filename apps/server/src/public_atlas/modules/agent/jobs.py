"""The daily purges (spec section 8.2): the videos of assignments finished more than
`video_keep_days` ago go from storage and their events say so; the events of assignments
finished more than `events_keep_days` ago go altogether. Findings, usage and the summary are
never purged."""

import logging
from datetime import timedelta

from sqlalchemy import delete, select

from public_atlas.db.base import utcnow
from public_atlas.jobs.tasks import task
from public_atlas.modules.agent.models import AgentRunEvent, EventKind
from public_atlas.modules.assignments.models import Assignment
from public_atlas.resources import Resources

logger = logging.getLogger(__name__)


@task("agent.purge_videos", cron="0 3 * * *")
async def purge_videos(res: Resources) -> int:
    """How many videos were purged. Each event keeps its row, with the time of the purge in
    place of the storage key, so the console can say a video existed."""
    cutoff = utcnow() - timedelta(days=res.settings.video_keep_days)
    async with res.session() as session:
        rows = await session.scalars(
            select(AgentRunEvent)
            .join(Assignment, Assignment.id == AgentRunEvent.assignment_id)
            .where(
                AgentRunEvent.kind == EventKind.VIDEO,
                AgentRunEvent.content.has_key("key"),
                Assignment.finished_at.is_not(None),
                Assignment.finished_at < cutoff,
            )
            .order_by(AgentRunEvent.id)
        )
        events = list(rows)
        keys = [str(event.content["key"]) for event in events]
        now = utcnow().isoformat()
        for event in events:
            event.content = {"purged_at": now, "size": event.content.get("size")}
        await session.commit()
    await _delete(res, keys)
    if events:
        logger.info(
            "Purged %d video(s) older than %d days", len(events), res.settings.video_keep_days
        )
    return len(events)


@task("agent.purge_events", cron="30 3 * * *")
async def purge_events(res: Resources) -> int:
    """How many events were deleted. A video not purged yet goes from storage with its event."""
    cutoff = utcnow() - timedelta(days=res.settings.events_keep_days)
    async with res.session() as session:
        old = select(Assignment.id).where(
            Assignment.finished_at.is_not(None), Assignment.finished_at < cutoff
        )
        keys = [
            str(content["key"])
            for content in await session.scalars(
                select(AgentRunEvent.content).where(
                    AgentRunEvent.assignment_id.in_(old),
                    AgentRunEvent.kind == EventKind.VIDEO,
                    AgentRunEvent.content.has_key("key"),
                )
            )
        ]
        result = await session.execute(
            delete(AgentRunEvent).where(AgentRunEvent.assignment_id.in_(old))
        )
        deleted = int(getattr(result, "rowcount", 0) or 0)
        await session.commit()
    await _delete(res, keys)
    if deleted:
        logger.info("Purged %d event(s) older than %d days", deleted, res.settings.events_keep_days)
    return deleted


async def _delete(res: Resources, keys: list[str]) -> None:
    """The rows are written already, so a store that fails here leaks a video, never a row."""
    for key in keys:
        try:
            await res.object_store.delete(key)
        except Exception:
            logger.exception("Could not delete video %s", key)
