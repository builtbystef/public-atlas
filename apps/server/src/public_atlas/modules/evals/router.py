"""The evals API (spec section 11, page 6): eval runs over time with their scores and cost. Read
only: a run is started from the command line."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from public_atlas.dependencies import SessionDep
from public_atlas.modules.evals import service
from public_atlas.modules.evals.schemas import EvalRunDetail, EvalRunOutput
from public_atlas.shared.pagination import Page

router = APIRouter(prefix="/eval-runs", tags=["evals"])


@router.get("")
async def list_eval_runs(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[EvalRunOutput]:
    """Every eval run, newest first."""
    items, total = await service.list_eval_runs(session, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{eval_run_id}")
async def read_eval_run(eval_run_id: uuid.UUID, session: SessionDep) -> EvalRunDetail:
    """One eval run with its scores per subject and assignment type."""
    return await service.read_eval_run(session, eval_run_id)
