import logging
import re
from datetime import datetime
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Query, Response

from app.auth import CurrentUser
from app.clients import db, storage
from app.errors import ApiError
from app.queries import acquisitions as acquisitions_q
from app.queries import spans as spans_q
from app.queries import traces as traces_q
from app.schemas.span import SpanDetailResponse, SpanListItem, SpanListResponse
from app.schemas.trace import (
    AcquireResponse,
    TraceDetailResponse,
    TraceListItem,
    TraceListResponse,
    TraceScope,
    TraceSort,
    TraceUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces")


@router.get("", response_model=TraceListResponse)
async def list_traces(
    user: CurrentUser,
    scope: TraceScope = "mine",
    q: str | None = Query(default=None, max_length=200),
    provider: str | None = None,
    model: str | None = None,
    tool: str | None = None,
    has_errors: bool = False,
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    sort: TraceSort = "created_at",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TraceListResponse:
    rows, total = await traces_q.list_visible(
        db.pool(),
        user.id,
        scope=scope,
        q=q,
        provider=provider,
        model=model,
        tool=tool,
        has_errors=has_errors,
        date_from=date_from,
        date_to=date_to,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return TraceListResponse(
        traces=[
            TraceListItem(
                trace_id=str(r["id"]),
                name=r["name"],
                status=r["status"],
                started_at=r["started_at"],
                duration_ms=r["duration_ms"],
                span_count=r["span_count"],
                error_count=r["error_count"],
                provider=r["provider"],
                model=r["model"],
                created_at=r["created_at"],
                visibility=r["visibility"],
                tags=list(r["tags"]),
                description=r["description"],
                listed_at=r["listed_at"],
                owner_display_name=r["owner_display_name"],
                is_owner=r["is_owner"],
                acquired=r["acquired"],
                acquired_at=r["acquired_at"],
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(trace_id: str, user: CurrentUser) -> TraceDetailResponse:
    row = await _visible_or_404(trace_id, user)
    return _detail(row)


@router.patch("/{trace_id}", response_model=TraceDetailResponse)
async def update_trace(
    trace_id: str, body: TraceUpdateRequest, user: CurrentUser
) -> TraceDetailResponse:
    # Invisible traces 404; a listed trace's existence isn't secret, so a
    # non-owner editing one gets an honest 403.
    row = await _visible_or_404(trace_id, user)
    if not row["is_owner"]:
        raise ApiError("forbidden", "Only the owner can modify a trace.", status=403)

    fields = body.model_fields_set - {"confirm_ownership"}
    if not fields:
        raise ApiError(
            "invalid_request",
            "Provide at least one of: visibility, tags, description.",
            status=422,
        )
    # Only description is nullable; an explicit null elsewhere is invalid, not
    # "leave untouched" (which is spelled by omitting the field).
    for field in ("visibility", "tags"):
        if field in fields and getattr(body, field) is None:
            raise ApiError("invalid_request", f"{field} cannot be null.", status=422)
    if body.visibility == "listed" and not body.confirm_ownership:
        raise ApiError(
            "confirmation_required",
            "Listing requires confirming this data is yours to share.",
            status=422,
        )

    kwargs: dict = {}
    if "visibility" in fields:
        kwargs["visibility"] = body.visibility
    if "tags" in fields:
        kwargs["tags"] = body.tags
    if "description" in fields:
        kwargs["description"] = body.description
    updated = await traces_q.update_owned(db.pool(), trace_id, user.id, **kwargs)
    if updated is None:  # deleted out from under us
        raise ApiError("not_found", "Trace not found.", status=404)
    # Re-read through the visibility path for the relationship flags.
    return _detail(await _visible_or_404(trace_id, user))


@router.delete("/{trace_id}", status_code=204)
async def delete_trace(trace_id: str, user: CurrentUser) -> Response:
    try:
        deleted, orphaned_object = await traces_q.delete_owned(db.pool(), trace_id, user.id)
    except asyncpg.DataError:  # not a UUID
        deleted, orphaned_object = False, None
    if not deleted:
        # Listed traces aren't secret: non-owners get 403, invisible get 404.
        try:
            row = await traces_q.get_visible(db.pool(), trace_id, user.id)
        except asyncpg.DataError:
            row = None
        if row is not None:
            raise ApiError("forbidden", "Only the owner can delete a trace.", status=403)
        raise ApiError("not_found", "Trace not found.", status=404)
    if orphaned_object is not None:
        # After commit, best-effort: an orphaned storage object is tolerable
        # (invisible, content-addressed); a dangling uploads row is not.
        try:
            await storage.delete(orphaned_object)
        except Exception:
            logger.exception("failed to delete storage object %s", orphaned_object)
    return Response(status_code=204)


# 201 on create, 200 on idempotent repeat; both carry the same body.
@router.post(
    "/{trace_id}/acquire",
    response_model=AcquireResponse,
    responses={201: {"model": AcquireResponse, "description": "Acquisition created"}},
)
async def acquire_trace(trace_id: str, user: CurrentUser, response: Response) -> AcquireResponse:
    row = await _visible_or_404(trace_id, user)
    if row["is_owner"]:
        raise ApiError(
            "own_trace", "You already own this trace; ownership grants access.", status=409
        )
    acq = await acquisitions_q.create(db.pool(), user.id, trace_id)
    if acq is None:  # unlisted between the visibility check and the insert
        raise ApiError("not_listed", "This trace is no longer listed.", status=409)
    response.status_code = 201 if acq["created"] else 200
    return AcquireResponse(
        acquisition_id=str(acq["id"]),
        trace_id=str(acq["trace_id"]),
        price_usd=float(acq["price_usd"]),
        acquired_at=acq["acquired_at"],
    )


@router.get("/{trace_id}/spans", response_model=SpanListResponse)
async def list_spans(
    trace_id: str,
    user: CurrentUser,
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SpanListResponse:
    await _visible_or_404(trace_id, user)
    rows, total = await spans_q.list_for_trace(db.pool(), trace_id, limit=limit, offset=offset)
    return SpanListResponse(spans=[_span_item(r) for r in rows], total=total)


@router.get("/{trace_id}/spans/{span_id}", response_model=SpanDetailResponse)
async def get_span(trace_id: str, span_id: str, user: CurrentUser) -> SpanDetailResponse:
    await _visible_or_404(trace_id, user)
    try:
        row = await spans_q.get(db.pool(), trace_id, span_id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        raise ApiError("not_found", "Span not found.", status=404)
    base = _span_item(row)
    return SpanDetailResponse(
        **base.model_dump(), attributes=row["attributes"], events=row["events"]
    )


@router.get("/{trace_id}/download")
async def download_trace(trace_id: str, user: CurrentUser) -> Response:
    try:
        row = await traces_q.get_visible_with_upload(db.pool(), trace_id, user.id)
    except asyncpg.DataError:
        row = None
    if row is None:
        raise ApiError("not_found", "Trace not found.", status=404)
    if not (row["is_owner"] or row["acquired"]):
        raise ApiError(
            "acquisition_required",
            "Acquire this trace to download it.",
            status=403,
        )
    data = await storage.get(row["storage_path"])
    # Same header hygiene as the uploads download: client-supplied filename.
    safe_name = re.sub(r'[^\x20-\x7e]|"', "", row["filename"]) or "trace.json"
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


def _detail(row: asyncpg.Record) -> TraceDetailResponse:
    return TraceDetailResponse(
        trace_id=str(row["id"]),
        upload_id=str(row["upload_id"]),
        source_trace_id=row["source_trace_id"],
        name=row["name"],
        status=row["status"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        duration_ms=row["duration_ms"],
        span_count=row["span_count"],
        error_count=row["error_count"],
        provider=row["provider"],
        model=row["model"],
        service_name=row["service_name"],
        tool_names=list(row["tool_names"]),
        error_types=list(row["error_types"]),
        tags=list(row["tags"]),
        description=row["description"],
        visibility=row["visibility"],
        listed_at=row["listed_at"],
        owner_display_name=row["owner_display_name"],
        source_format=row["source_format"],
        importer_version=row["importer_version"],
        created_at=row["created_at"],
        is_owner=row["is_owner"],
        acquired=row["acquired"],
        can_download=row["is_owner"] or row["acquired"],
    )


def _span_item(row: asyncpg.Record) -> SpanListItem:
    return SpanListItem(
        span_id=str(row["id"]),
        source_span_id=row["source_span_id"],
        source_parent_span_id=row["source_parent_span_id"],
        name=row["name"],
        kind=row["kind"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        duration_ms=row["duration_ms"],
        status=row["status"],
        status_message=row["status_message"],
        error_type=row["error_type"],
        provider=row["provider"],
        model=row["model"],
        tool_name=row["tool_name"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        total_tokens=row["total_tokens"],
    )


async def _visible_or_404(trace_id: str, user: CurrentUser) -> asyncpg.Record:
    try:
        row = await traces_q.get_visible(db.pool(), trace_id, user.id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        # 404 (not 403) so callers can't probe for traces they can't see.
        raise ApiError("not_found", "Trace not found.", status=404)
    return row
