import logging
import re
from typing import Annotated

import asyncpg
import httpx
from fastapi import APIRouter, Query, Response

from app.auth import CurrentUser
from app.clients import db, storage
from app.errors import ApiError
from app.queries import acquisitions as acquisitions_q
from app.queries import analysis as analysis_q
from app.queries import embeddings as embeddings_q
from app.queries import spans as spans_q
from app.queries import traces as traces_q
from app.schemas.analysis import (
    AnalysisAudit,
    AnalysisLabels,
    AnalysisSignals,
    AnalysisSummary,
    AuditAnalyzer,
    LabelValue,
    TraceAnalysisResponse,
)
from app.schemas.span import SpanDetailResponse, SpanListItem, SpanListResponse
from app.schemas.trace import (
    AcquireResponse,
    MetricKeysResponse,
    SimilarTraceItem,
    SimilarTracesResponse,
    TraceDetailResponse,
    TraceListItem,
    TraceListParams,
    TraceListResponse,
    TraceUpdateRequest,
)
from app.worker.tasks import analyze_trace, match_trace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces")


# Declared before the /{trace_id} routes so the static path wins.
@router.get("/metric-keys", response_model=MetricKeysResponse)
async def list_metric_keys(user: CurrentUser) -> MetricKeysResponse:
    return MetricKeysResponse(keys=await traces_q.metric_keys(db.pool(), user.id))


@router.get("", response_model=TraceListResponse)
async def list_traces(
    user: CurrentUser,
    params: Annotated[TraceListParams, Query()],
) -> TraceListResponse:
    rows, total, excluded = await traces_q.list_visible(
        db.pool(),
        user.id,
        scope=params.scope,
        filters=params,
        sort=params.sort,
        limit=params.limit,
        offset=params.offset,
    )
    return TraceListResponse(
        traces=[list_item(r) for r in rows],
        total=total,
        excluded_unanalyzed=excluded,
    )


def list_item(r: asyncpg.Record) -> TraceListItem:
    """One row→card mapping for every list surface (traces list + the
    subscription feed)."""
    return TraceListItem(
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
        outcome=r["outcome"],
        outcome_confidence=r["outcome_confidence"],
        outcome_provenance=r["outcome_provenance"],
        analysis_state=analysis_q.derive_state(r["llm_status"], r["analysis_failed"]),
        has_open_review_item=r["open_review_item_id"] is not None,
        open_review_item_id=(
            str(r["open_review_item_id"]) if r["open_review_item_id"] is not None else None
        ),
    )


async def schedule_listing_hooks(trace_ids: list[str]) -> None:
    """What follows a visibility flip to listed (A4 decision 7): an
    owner_opt_out-skipped trace re-enqueues analyze_trace — listing is the
    consent act and covers analysis; matching arrives via the
    analysis-complete trigger so subscriptions only see fully-analyzed
    traces. Everything else fires the match task directly (trigger a).
    Best-effort: the listing is already committed; a lost kick costs a
    notification, not correctness."""
    if not trace_ids:
        return
    rows = await db.pool().fetch(
        """
        select t.id, ta.llm_skip_reason
        from traces t
        left join trace_analysis ta on ta.trace_id = t.id
        where t.id = any($1::uuid[]) and t.visibility = 'listed'
        """,
        trace_ids,
    )
    for r in rows:
        task = analyze_trace if r["llm_skip_reason"] == "owner_opt_out" else match_trace
        try:
            await task.kiq(str(r["id"]))
        except Exception:
            logger.exception("failed to enqueue %s for trace %s", task.task_name, r["id"])


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
    if body.visibility == "listed":
        await schedule_listing_hooks([trace_id])
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
        # The scrubbed artifact rides along with its raw sibling.
        for path in (orphaned_object, storage.scrubbed_path(orphaned_object)):
            try:
                await storage.delete(path)
            except Exception:
                logger.exception("failed to delete storage object %s", path)
    return Response(status_code=204)


# 201 on create, 200 on idempotent repeat; both carry the same body.
@router.post(
    "/{trace_id}/acquire",
    response_model=AcquireResponse,
    responses={201: {"model": AcquireResponse, "description": "Acquisition created"}},
)
async def acquire_trace(trace_id: str, user: CurrentUser, response: Response) -> AcquireResponse:
    await _visible_or_404(trace_id, user)
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


@router.get("/{trace_id}/analysis", response_model=TraceAnalysisResponse)
async def get_trace_analysis(trace_id: str, user: CurrentUser) -> TraceAnalysisResponse:
    """The full analysis view for the trace-detail Analysis section
    (3_api.md). Owner or listed — same visibility rule as the trace."""
    trace = await _visible_or_404(trace_id, user)
    pool = db.pool()
    ta = await analysis_q.fetch_analysis(pool, trace_id)
    dead_letter = await analysis_q.fetch_open_dead_letter(pool, trace_id)
    state = analysis_q.derive_state(
        ta["llm_status"] if ta is not None else None, dead_letter is not None
    )

    labels = AnalysisLabels()
    signals = None
    metric_scores = None
    reasoning = None
    if ta is not None:
        labels = AnalysisLabels(
            **{
                field: (
                    LabelValue(
                        value=ta[field],
                        confidence=ta[f"{field}_confidence"],
                        provenance=ta[f"{field}_provenance"],
                    )
                    if ta[field] is not None
                    else None
                )
                for field in analysis_q.LABEL_FIELDS
            }
        )
        signals = AnalysisSignals(
            has_retry_loop=ta["has_retry_loop"],
            loop_kind=ta["loop_kind"],
            recovered_from_error=ta["recovered_from_error"],
            truncation_suspected=ta["truncation_suspected"],
            llm_call_count=ta["llm_call_count"],
            tool_call_count=ta["tool_call_count"],
        )
        metric_scores = ta["metric_scores"]

    analyzers = []
    summary = None
    for run in await analysis_q.fetch_results(pool, trace_id):
        output = run["output"]
        if run["analyzer"] == "judge":
            reasoning = output.get("reasoning")
        if run["analyzer"] == "summary":
            summary = AnalysisSummary(gist=output.get("gist"), steps=output.get("steps") or [])
        analyzers.append(
            AuditAnalyzer(
                analyzer=run["analyzer"],
                analyzer_version=run["analyzer_version"],
                model_id=run["model_id"],
                confidence=run["confidence"],
                votes=output.get("votes") if run["analyzer"] == "judge" else None,
                rendering_truncated=(
                    output.get("rendering_truncated") if run["analyzer"] == "judge" else None
                ),
            )
        )

    return TraceAnalysisResponse(
        analysis_state=state,
        skip_reason=ta["llm_skip_reason"] if ta is not None and state == "skipped" else None,
        failed_reason=dead_letter["last_error"] if dead_letter is not None else None,
        labels=labels,
        summary=summary,
        reasoning=reasoning,
        signals=signals,
        metric_scores=metric_scores,
        # Owner-only (A3 decision 8): a consumer reading a listed trace's
        # analysis never sees the owner's review backlog.
        open_review_item_id=(
            str(trace["open_review_item_id"])
            if trace["is_owner"] and trace["open_review_item_id"] is not None
            else None
        ),
        audit=AnalysisAudit(analyzers=analyzers),
    )


@router.get("/{trace_id}/similar", response_model=SimilarTracesResponse)
async def similar_traces(
    trace_id: str,
    user: CurrentUser,
    limit: int = Query(default=10, ge=1, le=50),
    min_similarity: float | None = Query(default=None, ge=0, le=1),
) -> SimilarTracesResponse:
    """Cosine nearest neighbors over the caller's visible traces
    (docs/proposals/similar-behavior.md). The anchor must itself be visible;
    an unembedded anchor returns anchor_embedded=false rather than 404 —
    "not analyzed yet" is a state, not an absence."""
    await _visible_or_404(trace_id, user)
    if not await embeddings_q.exists(db.pool(), trace_id):
        return SimilarTracesResponse(anchor_embedded=False, items=[])
    rows, total_above = await embeddings_q.similar_traces(
        db.pool(), user.id, trace_id, limit=limit, min_similarity=min_similarity
    )
    return SimilarTracesResponse(
        anchor_embedded=True,
        items=[
            SimilarTraceItem(**list_item(r).model_dump(), similarity=r["similarity"]) for r in rows
        ],
        total_above=total_above,
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
    trace = await _visible_or_404(trace_id, user)
    try:
        row = await spans_q.get(db.pool(), trace_id, span_id, include_raw=trace["is_owner"])
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        raise ApiError("not_found", "Span not found.", status=404)
    base = _span_item(row)
    attributes, events = row["attributes"], row["events"]
    # Owners see their original content (7_redaction.md); everyone else gets
    # the scrubbed columns. Pre-A5 spans have no span_raw row — fall through
    # to the stored (unscrubbed-at-the-time) columns.
    if trace["is_owner"] and row["raw_attributes"] is not None:
        attributes, events = row["raw_attributes"], row["raw_events"]
        base = base.model_copy(update={"status_message": row["raw_status_message"]})
    return SpanDetailResponse(**base.model_dump(), attributes=attributes, events=events)


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
    if row["is_owner"]:
        data = await storage.get(row["storage_path"])
    else:
        # Acquirers get the scrubbed artifact (7_redaction.md). Uploads
        # ingested before redaction shipped have none until re-ingested.
        try:
            data = await storage.get(storage.scrubbed_path(row["storage_path"]))
        except httpx.HTTPStatusError as exc:
            if exc.response.is_client_error:
                raise ApiError(
                    "not_found",
                    "No scrubbed copy exists for this trace yet; "
                    "ask the owner to re-ingest the upload.",
                    status=404,
                ) from exc
            raise
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
        total_tokens=row["total_tokens"],
        outcome=row["outcome"],
        outcome_confidence=row["outcome_confidence"],
        outcome_provenance=row["outcome_provenance"],
        analysis_state=analysis_q.derive_state(row["llm_status"], row["analysis_failed"]),
        has_open_review_item=row["open_review_item_id"] is not None,
        open_review_item_id=(
            str(row["open_review_item_id"]) if row["open_review_item_id"] is not None else None
        ),
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
