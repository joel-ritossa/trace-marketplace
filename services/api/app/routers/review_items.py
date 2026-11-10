import logging

import asyncpg
from fastapi import APIRouter, Query

from app.analysis.agent.judge import _citable as citable_spans
from app.analysis.agent.turns import split
from app.auth import CurrentUser
from app.clients import db
from app.errors import ApiError
from app.queries import analysis as analysis_q
from app.queries import review_items as review_items_q
from app.routers.traces import request_finalize, trace_analysis, visible_or_404
from app.schemas.analysis import TraceAnalysis, TurnLabelsRequest
from app.schemas.review import (
    ReviewContext,
    ReviewItemListResponse,
    ReviewItemResponse,
    ReviewListStatus,
    ReviewTraceSummary,
)

logger = logging.getLogger(__name__)

# No shared prefix: the collection lives at /review-items, the turn relabel
# hangs off the trace.
router = APIRouter()


def _item(row: asyncpg.Record) -> ReviewItemResponse:
    return ReviewItemResponse(
        review_item_id=str(row["id"]),
        trace_id=str(row["trace_id"]),
        upload_id=str(row["upload_id"]),
        upload_filename=row["upload_filename"],
        context=ReviewContext.model_validate(row["context"]),
        status=row["status"],
        created_at=row["created_at"],
        trace=ReviewTraceSummary(
            trace_id=str(row["trace_id"]),
            name=row["trace_name"],
            status=row["trace_status"],
            started_at=row["trace_started_at"],
            duration_ms=row["trace_duration_ms"],
        ),
        resolved_at=row["resolved_at"],
        resolved_by=str(row["resolved_by"]) if row["resolved_by"] else None,
    )


@router.get("/review-items", response_model=ReviewItemListResponse)
async def list_review_items(
    user: CurrentUser,
    status: ReviewListStatus = "open",
    upload_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ReviewItemListResponse:
    """The caller's items on own traces, oldest first (3_api.md). upload_id
    backs the digest notification's filtered-queue link."""
    try:
        rows, total = await review_items_q.list_for_owner(
            db.pool(),
            user.id,
            status=status,
            upload_id=upload_id,
            limit=limit,
            offset=offset,
        )
    except asyncpg.DataError:  # upload_id not a UUID
        return ReviewItemListResponse(items=[], total=0)
    return ReviewItemListResponse(items=[_item(r) for r in rows], total=total)


@router.get("/review-items/{item_id}", response_model=ReviewItemResponse)
async def get_review_item(item_id: str, user: CurrentUser) -> ReviewItemResponse:
    row = await _owned_or_404(item_id, user)
    return _item(row)


@router.put("/traces/{trace_id}/turns/{turn_index}/labels", response_model=TraceAnalysis)
async def relabel_turn(
    trace_id: str, turn_index: int, body: TurnLabelsRequest, user: CurrentUser
) -> TraceAnalysis:
    """Owner relabel of one turn (9_session-analysis.md Review): the turn
    becomes human-labeled and is never re-judged; the session arrays are
    recomputed, the review item closes once no uncertain turn is left, and
    a finalizing run re-rolls the session verdict up (judging nothing)."""
    row = await visible_or_404(trace_id, user)
    if not row["is_owner"]:
        raise ApiError("forbidden", "Only the owner can relabel a trace.", status=403)
    pool = db.pool()
    trace = await analysis_q.fetch_trace_input(pool, trace_id)
    turn = next((t for t in split(trace) if t.index == turn_index), None) if trace else None
    if turn is None:
        raise ApiError("not_found", "Turn not found.", status=404)
    # The judge's citation rule: llm/tool spans inside the turn.
    citable = citable_spans(turn)
    foreign = [i for label in body.failure_modes for i in label.span_ids if i not in citable]
    if foreign:
        raise ApiError(
            "invalid_request",
            f"Span ids are not llm/tool spans in turn {turn_index}: {foreign}.",
            status=422,
        )
    labels = [("task_category", value, [], None) for value in body.task_categories] + [
        ("failure_mode", label.value, label.span_ids, label.reason) for label in body.failure_modes
    ]
    if not await analysis_q.relabel(
        pool, trace_id, turn_index, outcome=body.outcome, labels=labels, owner_id=user.id
    ):
        raise ApiError(
            "analysis_pending", "This turn has not been analyzed yet; try again later.", status=409
        )
    # The session verdict is stale now; the finalizing run re-rolls it up
    # and fires matching (subscription trigger (c), 3_api.md) after. Best-
    # effort: the relabel is committed, and the sweep finalizes stale traces.
    try:
        await request_finalize(trace_id)
    except Exception:
        logger.exception("relabel: failed to enqueue finalization for trace %s", trace_id)
    return await trace_analysis(await visible_or_404(trace_id, user))


async def _owned_or_404(item_id: str, user: CurrentUser) -> asyncpg.Record:
    try:
        row = await review_items_q.get_for_owner(db.pool(), item_id, user.id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        # 404 (not 403): items on others' traces are indistinguishable from
        # absent ones. A deleted trace cascades its items here too.
        raise ApiError("not_found", "Review item not found.", status=404)
    return row
