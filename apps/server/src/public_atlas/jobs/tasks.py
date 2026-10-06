"""`task`, the decorator that makes a job, and `defer`, which queues one."""

import functools
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Concatenate

from procrastinate import App, JobContext, RetryStrategy
from procrastinate.tasks import Task, configure_task
from procrastinate.types import JSONValue

from public_atlas.jobs import Queue, registry
from public_atlas.jobs.context import Attempt, Trace, running, trace
from public_atlas.resources import Resources, resources_of

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# For a job that fails on a flaky peer: five tries, the waits growing from a quarter of a minute
# to about four.
RETRY_ON_ERROR = RetryStrategy(max_attempts=5, wait=10, exponential_wait=4)

# Arguments after `Resources` are the job's, and must be JSON.
type JobFunction[**P, R] = Callable[Concatenate[Resources, P], Awaitable[R]]
# Positional arguments are not stored, so a task is always deferred with keywords.
type AnyTask = Task[Any, Any, Any]

# By task name: what to settle when a job will never run again because its worker died on the
# last attempt. Called by the stalled sweep with the job's arguments.
ABANDONED: dict[str, JobFunction[..., None]] = {}


def task(
    name: str,
    *,
    queue: Queue = "default",
    retry: RetryStrategy | None = None,
    cron: str | None = None,
    abandoned: JobFunction[..., None] | None = None,
) -> Callable[[JobFunction[..., Any]], AnyTask]:
    """Register a job. `cron` makes it periodic (every worker fires it, the database keeps each
    tick to one run). A run gets the worker's `Resources` first, then the arguments it was
    queued with, and runs under the request ID and trace that queued it (see context.py), with
    `current_attempt` saying whether a failure would be retried."""

    def decorator(func: JobFunction[..., Any]) -> AnyTask:
        @functools.wraps(func)
        async def run(
            context: JobContext, *, trace: Trace | None = None, **kwargs: JSONValue
        ) -> object:
            if cron is not None:
                # The tick, as Procrastinate sends it. No job here needs it.
                kwargs.pop("timestamp", None)
            job = context.job
            attempt = Attempt(job.attempts + 1, last=not retries_left(context.task, job.attempts))
            with running(name, job.id, trace, attempt):
                return await func(resources_of(context), **kwargs)

        registered: AnyTask = registry.task(
            name=name, queue=queue, pass_context=True, retry=retry or False
        )(run)
        if cron is not None:
            registered = registry.periodic(cron=cron)(registered)
        if abandoned is not None:
            ABANDONED[name] = abandoned
        return registered

    return decorator


def retries_left(task: AnyTask | None, attempts: int) -> bool:
    """Whether a failure after `attempts` runs would be retried, asked ahead of time so a job
    knows whether its run is the last. A task with no strategy, or none registered, is never
    retried."""
    strategy = task.retry_strategy if task is not None else None
    if strategy is None:
        return False
    limit = getattr(strategy, "max_attempts", None)
    return not limit or attempts < limit


async def defer(
    jobs: App,
    session: AsyncSession,
    task: AnyTask,
    *,
    queueing_lock: str | None = None,
    **kwargs: JSONValue,
) -> int:
    """Queue one run of `task` on `jobs`, in `session`'s transaction, and return its job ID.

    The job row is written on the session's own connection, so it is committed, or rolled back,
    with the rows it is about; a worker is notified at commit, never before. (Sessions run on
    psycopg, which is the connection Procrastinate accepts; this would not survive a change of
    driver.) Built through `jobs` rather than the task's own back-link, so the caller says
    which queue it means. With `queueing_lock`, a second defer while a job with that lock
    waits raises `AlreadyEnqueued`.
    """
    await session.flush()
    connection = await (await session.connection()).get_raw_connection()
    deferrer = configure_task(
        name=task.name,
        job_manager=jobs.job_manager,
        queue=task.queue,
        lock=task.lock,
        queueing_lock=queueing_lock or task.queueing_lock,
        connection=connection.driver_connection,
    )
    # `Trace` is `dict[str, str]`, which is not a `JSONValue` (dicts are invariant).
    carrier: dict[str, JSONValue] = {**trace()}
    return await deferrer.defer_async(trace=carrier, **kwargs)


__all__ = ["ABANDONED", "RETRY_ON_ERROR", "AnyTask", "JobFunction", "defer", "retries_left", "task"]
