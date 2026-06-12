import logging

import asyncpg
from fastapi import APIRouter, Query, Response

from app.auth import CurrentUser
from app.clients import db
from app.errors import ApiError
from app.queries import analysis as analysis_q
from app.queries import review_items as review_items_q
from app.schemas.review import (
    ResolvedLabel,
    ReviewAnswer,
    ReviewContext,
    ReviewItemListResponse,
    ReviewItemResponse,
    ReviewListStatus,
    ReviewResolveRequest,
    ReviewResolveResponse,
    ReviewTraceSummary,
)
from app.worker.tasks import match_trace

logger = logging.getLogger(__name__)

# No shared prefix: the collection lives at /review-items, the owner-relabel
# creation hangs off the trace (3_api.md).
router = APIRouter()


def _item(row: asyncpg.Record) -> ReviewItemResponse:
    return ReviewItemResponse(
        review_item_id=str(row["id"]),
        trace_id=str(row["trace_id"]),
        upload_id=str(row["upload_id"]),
        upload_filename=row["upload_filename"],
        question_type=row["question_type"],
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
        answer=ReviewAnswer.model_validate(row["answer"]) if row["answer"] else None,
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


@router.post("/review-items/{item_id}/resolve", response_model=ReviewResolveResponse)
async def resolve_review_item(
    item_id: str, body: ReviewResolveRequest, user: CurrentUser
) -> ReviewResolveResponse:
    """Commit a (partial) human answer: answered fields land on
    `trace_analysis` with human provenance and confidence 1.0 (3_api.md)."""
    answer = {
        field: value
        for field in analysis_q.LABEL_FIELDS
        if (value := getattr(body, field)) is not None
    }
    try:
        status, item, updates = await review_items_q.resolve(db.pool(), item_id, user.id, answer)
    except asyncpg.DataError:  # not a UUID
        status, item, updates = "not_found", None, None
    if status == "not_found":
        raise ApiError("not_found", "Review item not found.", status=404)
    if status == "already_resolved":
        raise ApiError("already_resolved", "This review item is already resolved.", status=409)
    if status == "superseded":
        raise ApiError(
            "item_superseded",
            "This review item was superseded by a newer analysis run.",
            status=409,
        )
    if status == "analysis_pending":
        raise ApiError(
            "analysis_pending",
            "The trace's analysis is being rewritten; try again shortly.",
            status=409,
        )
    labels = {
        field: ResolvedLabel(
            value=updates[field],
            confidence=updates[f"{field}_confidence"],
            provenance=updates[f"{field}_provenance"],
        )
        for field in analysis_q.LABEL_FIELDS
        if updates is not None and updates.get(field) is not None
    }
    # Subscription trigger (c), 3_api.md: the resolve rewrote labels — a
    # relabel can newly satisfy a stored query, so re-evaluate matching when
    # the trace is listed. Best-effort like the analyze-complete kick:
    # matching is idempotent, a lost kick costs a notification, not
    # correctness (A4 decision 6).
    visibility = await db.pool().fetchval(
        "select visibility from traces where id = $1", item["trace_id"]
    )
    if visibility == "listed":
        try:
            await match_trace.kiq(str(item["trace_id"]))
        except Exception:
            logger.exception(
                "resolve: failed to enqueue matching for trace %s", item["trace_id"]
            )
    # Re-read with the trace summary for the uniform response shape.
    row = await _owned_or_404(item_id, user)
    return ReviewResolveResponse(item=_item(row), labels=labels)


# 201 on create, 200 on idempotent repeat (same pattern as acquire).
@router.post(
    "/traces/{trace_id}/review-items",
    response_model=ReviewItemResponse,
    responses={201: {"model": ReviewItemResponse, "description": "Review item created"}},
)
async def create_review_item(
    trace_id: str, user: CurrentUser, response: Response
) -> ReviewItemResponse:
    """Owner-initiated relabel (3_api.md): the existing open item or a fresh
    one with empty routing reasons. Owner only; 404-not-403 — review items
    are owner-scoped even on listed traces."""
    pool = db.pool()
    try:
        owned = await pool.fetchval(
            "select id from traces where id = $1 and owner_id = $2", trace_id, user.id
        )
    except asyncpg.DataError:  # not a UUID
        owned = None
    if owned is None:
        raise ApiError("not_found", "Trace not found.", status=404)
    current = await analysis_q.fetch_analysis(pool, trace_id)
    if current is None:
        # Resolve writes into the trace_analysis row (A3 decision 7); a
        # human-only row would have to invent llm_status.
        raise ApiError(
            "analysis_pending",
            "This trace has not been analyzed yet; relabel once analysis lands.",
            status=409,
        )
    context = {"verdict": review_items_q.verdict_snapshot(current), "reasons": []}
    item, created = await review_items_q.get_or_create_open(
        pool, trace_id=trace_id, context=context
    )
    response.status_code = 201 if created else 200
    row = await _owned_or_404(str(item["id"]), user)
    return _item(row)


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
