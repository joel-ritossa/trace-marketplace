import re

import asyncpg
from fastapi import APIRouter, Query, Response

from app.auth import CurrentUser
from app.clients import db, storage
from app.errors import ApiError
from app.queries import spans as spans_q
from app.queries import traces as traces_q
from app.schemas.span import SpanDetailResponse, SpanListItem, SpanListResponse
from app.schemas.trace import (
    TraceDetailResponse,
    TraceListItem,
    TraceListResponse,
    TraceScope,
    TraceSort,
)

router = APIRouter(prefix="/traces")


@router.get("", response_model=TraceListResponse)
async def list_traces(
    user: CurrentUser,
    scope: TraceScope = "mine",
    sort: TraceSort = "created_at",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TraceListResponse:
    rows, total = await traces_q.list_owned(
        db.pool(), user.id, sort=sort, limit=limit, offset=offset
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
                owner_display_name=r["owner_display_name"],
                acquired=False,
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(trace_id: str, user: CurrentUser) -> TraceDetailResponse:
    row = await _owned_or_404(trace_id, user)
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
        source_format=row["source_format"],
        importer_version=row["importer_version"],
        created_at=row["created_at"],
        is_owner=True,
        acquired=False,
        can_download=True,
    )


@router.get("/{trace_id}/spans", response_model=SpanListResponse)
async def list_spans(
    trace_id: str,
    user: CurrentUser,
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SpanListResponse:
    await _owned_or_404(trace_id, user)
    rows, total = await spans_q.list_for_trace(db.pool(), trace_id, limit=limit, offset=offset)
    return SpanListResponse(spans=[_span_item(r) for r in rows], total=total)


@router.get("/{trace_id}/spans/{span_id}", response_model=SpanDetailResponse)
async def get_span(trace_id: str, span_id: str, user: CurrentUser) -> SpanDetailResponse:
    await _owned_or_404(trace_id, user)
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
    row = await _trace_with_upload_or_404(trace_id, user)
    data = await storage.get(row["storage_path"])
    # Same header hygiene as the uploads download: client-supplied filename.
    safe_name = re.sub(r'[^\x20-\x7e]|"', "", row["filename"]) or "trace.json"
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
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


async def _owned_or_404(trace_id: str, user: CurrentUser) -> asyncpg.Record:
    try:
        row = await traces_q.get_owned(db.pool(), trace_id, user.id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        # 404 (not 403) so callers can't probe for traces they can't see.
        raise ApiError("not_found", "Trace not found.", status=404)
    return row


async def _trace_with_upload_or_404(trace_id: str, user: CurrentUser) -> asyncpg.Record:
    try:
        row = await traces_q.get_owned_with_upload(db.pool(), trace_id, user.id)
    except asyncpg.DataError:
        row = None
    if row is None:
        raise ApiError("not_found", "Trace not found.", status=404)
    return row
