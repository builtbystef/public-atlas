"""The periodic sweep for jobs whose worker died mid-run: retried, or failed and settled."""

import logging

from procrastinate.jobs import Status

from public_atlas.jobs.tasks import ABANDONED, retries_left, task
from public_atlas.resources import Resources

logger = logging.getLogger(__name__)


@task("jobs.retry_stalled", cron="*/10 * * * *")
async def retry_stalled(res: Resources) -> int:
    """A job whose worker died mid-run would stay running for good. Its worker's heartbeat has
    stopped, so the job is put back in the queue; every job is written to bear a second run. A
    job out of retries is marked failed instead and its task's `abandoned` hook settles what it
    left behind, so a poison file cannot loop and nothing waits on a run that never comes."""
    jobs = res.jobs
    stalled = list(await jobs.job_manager.get_stalled_jobs())
    requeued = 0
    for job in stalled:
        if retries_left(jobs.tasks.get(job.task_name), job.attempts):
            await jobs.job_manager.retry_job(job)
            requeued += 1
            continue
        await jobs.job_manager.finish_job(job, Status.FAILED, delete_job=False)
        logger.warning("Job %s (%s) stalled past its retries; failed", job.id, job.task_name)
        settle = ABANDONED.get(job.task_name)
        if settle is not None:
            arguments = {
                key: value
                for key, value in job.task_kwargs.items()
                if key not in ("trace", "timestamp")
            }
            await settle(res, **arguments)
    if stalled:
        logger.warning("Requeued %d of %d stalled jobs", requeued, len(stalled))
    return len(stalled)
