"""The runs and assignments API (spec section 11, pages 1 and 2): start a run with a filter and
a mode, pause, resume and stop it, release held assignments, and read a run's progress and
cost; list assignments with filters and read one with its events, spend and result."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query

from public_atlas.dependencies import (
    DatabaseDep,
    ObjectStoreDep,
    ResourcesDep,
    SessionDep,
    SettingsDep,
)
from public_atlas.modules.agent.models import EventKind
from public_atlas.modules.assignments import service
from public_atlas.modules.assignments.models import (
    Assignment,
    AssignmentResult,
    AssignmentStatus,
    AssignmentType,
)
from public_atlas.modules.assignments.schemas import (
    AssignmentDetail,
    AssignmentOutput,
    EventOutput,
    FindingOutput,
    ReleaseInput,
    RunDetail,
    RunInput,
    RunOutput,
    SubjectOutput,
)
from public_atlas.modules.evidence import service as evidence
from public_atlas.modules.graph import service as graph
from public_atlas.modules.graph.models import Homepage, Source
from public_atlas.shared.pagination import Page

router = APIRouter(tags=["runs"])


async def _detail(session: SessionDep, run_id: uuid.UUID) -> RunDetail:
    run = await service.get_run(session, run_id)
    return RunDetail(
        **RunOutput.model_validate(run).model_dump(), progress=await service.progress(session, run)
    )


async def _outputs(session: SessionDep, rows: Sequence[Assignment]) -> list[AssignmentOutput]:
    """The assignments with their subjects named."""
    subjects = await service.subjects_of(session, rows)
    outputs: list[AssignmentOutput] = []
    for row in rows:
        output = AssignmentOutput.model_validate(row)
        subject = subjects.get(row.subject_id)
        if subject is not None:
            output.subject = SubjectOutput(id=subject.id, kind=subject.kind, name=subject.name)
        outputs.append(output)
    return outputs


@router.get("/runs")
async def list_runs(
    session: SessionDep,
    database: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[RunDetail]:
    """Every run in the database, newest first, each with its progress and cost. An eval run's
    row in the main database is only the record its scores hang from, with its assignments in
    the eval database, so the main database lists none."""
    runs, total = await service.list_runs(
        session, is_eval=False if database == "main" else None, limit=limit, offset=offset
    )
    progress = await service.progress_many(session, [run.id for run in runs])
    return Page(
        items=[
            RunDetail(**RunOutput.model_validate(run).model_dump(), progress=progress[run.id])
            for run in runs
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


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
    return await _outputs(session, released)


@router.get("/assignments")
async def list_assignments(  # noqa: PLR0913, PLR0917 - one argument per filter
    session: SessionDep,
    run_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[AssignmentStatus | None, Query()] = None,
    result: Annotated[AssignmentResult | None, Query()] = None,
    type: Annotated[AssignmentType | None, Query()] = None,  # noqa: A002 - the column's name
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AssignmentOutput]:
    """A page of assignments by creation, oldest first unless `order` is `desc`, with their
    subjects named."""
    filters = {
        "run_id": run_id,
        "status": status,
        "result": result,
        "assignment_type": type,
        "subject_id": subject_id,
    }
    rows = await service.list_assignments(
        session, newest_first=order == "desc", limit=limit, offset=offset, **filters
    )
    return Page(
        items=await _outputs(session, rows),
        total=await service.count_assignments(session, **filters),
        limit=limit,
        offset=offset,
    )


@router.get("/assignments/{assignment_id}")
async def read_assignment(assignment_id: uuid.UUID, session: SessionDep) -> AssignmentDetail:
    assignment = await service.get_assignment(session, assignment_id)
    (output,) = await _outputs(session, [assignment])
    return AssignmentDetail(
        **output.model_dump(), cost=await service.assignment_cost(session, assignment.id)
    )


@router.get("/assignments/{assignment_id}/events")
async def read_assignment_events(
    assignment_id: uuid.UUID, session: SessionDep, store: ObjectStoreDep, settings: SettingsDep
) -> list[EventOutput]:
    """Everything the agent saw, said and did, in order: the prompt, its words, its tool calls
    and their results, and the videos when recorded, each with a short-lived link to play it."""
    await service.get_assignment(session, assignment_id)
    outputs: list[EventOutput] = []
    for row in await service.events_of(session, assignment_id):
        output = EventOutput.model_validate(row)
        key = row.content.get("key") if row.kind is EventKind.VIDEO else None
        if key:
            output.video_url = await store.download_url(
                str(key), f"session-{row.session}-{row.position}.webm", settings.storage_url_ttl
            )
        outputs.append(output)
    return outputs


@router.get("/assignments/{assignment_id}/findings")
async def read_assignment_findings(
    assignment_id: uuid.UUID, session: SessionDep, store: ObjectStoreDep, settings: SettingsDep
) -> list[FindingOutput]:
    """What the assignment saved: every quote it recorded, with the entity the quote is for and
    a link to the stored page."""
    await service.get_assignment(session, assignment_id)
    rows = await evidence.findings_of(session, assignment_id)
    details = {
        detail.id: detail
        for detail in await evidence.evidence_details(
            session, store, {row.entity_id for row in rows}, url_ttl=settings.storage_url_ttl
        )
    }
    findings: list[FindingOutput] = []
    for row in rows:
        entity = await graph.entity_by_id(session, row.entity_id)
        detail = details.get(row.id)
        if entity is None or detail is None:  # pragma: no cover - the keys hold both
            continue
        institution_id = (
            entity.institution_id if isinstance(entity, Homepage | Source) else entity.id
        )
        findings.append(
            FindingOutput(
                evidence_id=row.id,
                entity_id=entity.id,
                entity_kind=entity.kind,
                entity_status=entity.status,
                label=await graph.label_of(session, entity),
                institution_id=institution_id if entity.kind != "place" else None,
                quote=row.quote,
                kind=row.kind.value,
                page_url=detail.page_url,
                link_url=row.link_url,
                snapshot_url=detail.snapshot_url,
            )
        )
    return findings
