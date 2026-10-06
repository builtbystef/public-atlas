"""The hourly purge of the queue's own table. Product rows are purged by their modules' jobs."""

import logging
import math
from datetime import timedelta

from public_atlas.jobs.tasks import task
from public_atlas.resources import Resources

logger = logging.getLogger(__name__)


@task("jobs.purge_old_jobs", cron="0 * * * *")
async def purge_old_jobs(res: Resources) -> None:
    """A job that failed for good is kept for inspection (jobs/__init__.py) and removed once it
    is `purge_after` old."""
    await res.jobs.job_manager.delete_old_jobs(
        nb_hours=math.ceil(res.settings.purge_after / timedelta(hours=1)), include_failed=True
    )
    logger.info("Purged failed jobs older than %s", res.settings.purge_after)
