"""The runs and assignments API (spec section 11, pages 1 and 2): start a run with a filter and
a mode, pause, resume and stop it, release held assignments, and read a run's progress and
cost; list assignments with filters and read one with its events, spend and result."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from public_atlas.dependencies import ResourcesDep, SessionDep
from public_atlas.modules.assignments import service
from public_atlas.modules.assignments.models import AssignmentStatus, AssignmentType
from public_atlas.modules.assignments.schemas import (
    AssignmentDetail,
    AssignmentOutput,
    EventOutput,
    ReleaseInput,
    RunDetail,
    RunInput,
    RunOutput,
)

router = APIRouter(tags=["runs"])


async def _detail(session: SessionDep, run_id: uuid.UUID) -> RunDetail:
    run = await service.get_run(session, run_id)
    return RunDetail(
        **RunOutput.model_validate(run).model_dump(), progress=await service.progress(session, run)
    )


@router.get("/runs")
async def list_runs(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RunOutput]:
    """Every run, newest first."""
    runs = await service.list_runs(session, limit=limit, offset=offset)
    return [RunOutput.model_validate(run) for run in runs]


@router.post("/runs", status_code=201)
async def create_run(body: RunInput, session: SessionDep, resources: ResourcesDep) -> RunDetail:
    """Start a run: the work due for the subjects in its filter is created, held in step mode
    and queued in auto mode."""
    run = await service.create_run(
        session,
        resources.jobs,
        name=body.name,
        country_code=body.country_code,
        mode=body.mode,
        filter=body.filter,
        record_video=body.record_video,
    )
    await session.commit()
    return await _detail(session, run.id)


@router.get("/runs/{run_id}")
async def read_run(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    """The run with its assignments counted by status and result, and what it has cost."""
    return await _detail(session, run_id)


@router.post("/runs/{run_id}/pause")
async def pause_run(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    """The worker starts none of the run's assignments until it is resumed; running ones finish
    their session."""
    await service.pause_run(session, await service.get_run(session, run_id))
    await session.commit()
    return await _detail(session, run_id)


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    await service.resume_run(session, await service.get_run(session, run_id))
    await session.commit()
    return await _detail(session, run_id)


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: uuid.UUID, session: SessionDep) -> RunDetail:
    """Cancel everything held or queued; running assignments finish their session."""
    await service.stop_run(session, await service.get_run(session, run_id))
    await session.commit()
    return await _detail(session, run_id)


@router.post("/runs/{run_id}/release")
async def release_assignments(
    run_id: uuid.UUID, body: ReleaseInput, session: SessionDep, resources: ResourcesDep
) -> list[AssignmentOutput]:
    """Queue held assignments: a few at a time, of one type, or the ones named."""
    run = await service.get_run(session, run_id)
    released = await service.release(
        session,
        resources.jobs,
        run,
        limit=body.limit,
        assignment_type=body.assignment_type,
        assignment_ids=body.assignment_ids,
    )
    await session.commit()
    return [AssignmentOutput.model_validate(assignment) for assignment in released]


@router.get("/assignments")
async def list_assignments(  # noqa: PLR0913, PLR0917 - one argument per filter
    session: SessionDep,
    run_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[AssignmentStatus | None, Query()] = None,
    type: Annotated[AssignmentType | None, Query()] = None,  # noqa: A002 - the column's name
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AssignmentOutput]:
    rows = await service.list_assignments(
        session,
        run_id=run_id,
        status=status,
        assignment_type=type,
        subject_id=subject_id,
        limit=limit,
        offset=offset,
    )
    return [AssignmentOutput.model_validate(row) for row in rows]


@router.get("/assignments/{assignment_id}")
async def read_assignment(assignment_id: uuid.UUID, session: SessionDep) -> AssignmentDetail:
    assignment = await service.get_assignment(session, assignment_id)
    return AssignmentDetail(
        **AssignmentOutput.model_validate(assignment).model_dump(),
        cost=await service.assignment_cost(session, assignment.id),
    )


@router.get("/assignments/{assignment_id}/events")
async def read_assignment_events(
    assignment_id: uuid.UUID, session: SessionDep
) -> list[EventOutput]:
    """Everything the agent saw, said and did, in order: the prompt, its words, its tool calls
    and their results, and the videos when recorded."""
    await service.get_assignment(session, assignment_id)
    return [
        EventOutput.model_validate(row) for row in await service.events_of(session, assignment_id)
    ]
