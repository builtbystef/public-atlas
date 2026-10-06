"""The `assignment` queue: one job per assignment, run by the agent."""

import uuid

from public_atlas.jobs.tasks import RETRY_ON_ERROR, task
from public_atlas.modules.agent import service as agent
from public_atlas.modules.assignments.service import RUN_ASSIGNMENT_TASK
from public_atlas.resources import Resources


async def abandoned(res: Resources, *, assignment_id: str) -> None:
    """The worker died on the job's last attempt: the assignment finishes `failed`, as it would
    had the run raised, instead of staying `running` for good."""
    await agent.record_failure(
        res,
        uuid.UUID(assignment_id),
        "The worker stopped while running this assignment",
        final=True,
    )


@task(RUN_ASSIGNMENT_TASK, queue="assignment", retry=RETRY_ON_ERROR, abandoned=abandoned)
async def run_assignment(res: Resources, *, assignment_id: str) -> str:
    return await agent.run_assignment(res, uuid.UUID(assignment_id))
