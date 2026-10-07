"""The evidence API: one quote in the context of the stored page it was taken from, for the
console to show a quote highlighted where the rules found it (spec section 11, page 4)."""

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from public_atlas.dependencies import ObjectStoreDep, SessionDep
from public_atlas.modules.evidence import service

router = APIRouter(prefix="/evidence", tags=["evidence"])


class QuoteContextOutput(BaseModel):
    evidence_id: uuid.UUID
    found: bool
    before: str
    quote: str
    after: str
    # The page of a file the quote is on, when the file has pages.
    page: int | None


@router.get("/{evidence_id}/context")
async def read_evidence_context(
    evidence_id: uuid.UUID, session: SessionDep, store: ObjectStoreDep
) -> QuoteContextOutput:
    """The quote with the text around it on the stored copy. `found` is false when the stored
    text no longer has the quote: the copy was pruned, or the quote matched the page's HTML."""
    row, context = await service.evidence_context(session, store, evidence_id)
    return QuoteContextOutput(
        evidence_id=row.id,
        found=context.found,
        before=context.before,
        quote=context.quote,
        after=context.after,
        page=context.page,
    )
