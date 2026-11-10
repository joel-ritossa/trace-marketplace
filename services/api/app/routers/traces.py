import logging
import re
from collections.abc import Mapping
from typing import Annotated, Any

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
    AnalysisSignals,
    AnalyzeResponse,
    SessionAnalysis,
    TraceAnalysis,
    TurnAnalysis,
    TurnLabel,
)
from app.schemas.span import (
    AgentSpawn,
    AgentsResponse,
    SpanDetailResponse,
    SpanListItem,
    SpanListResponse,
    SubagentSummary,
)
from app.schemas.trace import (
    AcquireResponse,
    SimilarTraceItem,
    SimilarTracesResponse,
    SkillCount,
    SkillCountsResponse,
    SkillUse,
    TraceDetailResponse,
    TraceListItem,
    TraceListParams,
    TraceListResponse,
    TraceScope,
    TraceUpdateRequest,
)
from app.worker.tasks import analyze_trace, match_trace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces")


# Declared before the /{trace_id} routes so the static path wins.
@router.get("/skills", response_model=SkillCountsResponse)
async def list_skills(user: CurrentUser, scope: TraceScope = "mine") -> SkillCountsResponse:
    """Skill filter values: distinct skill names with trace counts over the
    same scope as the list (own / marketplace / acquired)."""
    rows = await traces_q.skill_counts(db.pool(), user.id, scope)
    return SkillCountsResponse(
        skills=[SkillCount(name=r["name"], trace_count=r["trace_count"]) for r in rows]
    )


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
        skill_names=list(r["skill_names"]),
        owner_display_name=r["owner_display_name"],
        is_owner=r["is_owner"],
        acquired=r["acquired"],
        acquired_at=r["acquired_at"],
        goal=r["goal"],
        outcome=r["outcome"],
        task_categories=list(r["task_categories"] or []),
        failure_modes=list(r["failure_modes"] or []),
        analysis_status=analysis_q.derive_status(
            r["llm_status"], r["analyzed_at"], r["analysis_attempts"]
        ),
        analysis_failed=r["analysis_failed"],
        has_open_review_item=r["open_review_item_id"] is not None,
        open_review_item_id=(
            str(r["open_review_item_id"]) if r["open_review_item_id"] is not None else None
        ),
    )


async def schedule_listing_hooks(trace_ids: list[str]) -> None:
    """What follows a visibility flip to listed (A4 decision 7,
    9_session-analysis.md): a trace that is not final — or was skipped for
    owner_opt_out, since listing is the consent act — is finalized first;
    matching arrives via the analysis-complete trigger so subscriptions see
    the finished verdict. Everything else fires the match task directly
    (trigger a). Best-effort: the listing is already committed; a lost kick
    costs a notification, not correctness."""
    if not trace_ids:
        return
    rows = await db.pool().fetch(
        """
        select t.id, t.analysis_attempts, ta.llm_status, ta.llm_skip_reason, ta.analyzed_at
        from traces t
        left join trace_analysis ta on ta.trace_id = t.id
        where t.id = any($1::uuid[]) and t.visibility = 'listed'
        """,
        trace_ids,
    )
    for r in rows:
        status = analysis_q.derive_status(r["llm_status"], r["analyzed_at"], r["analysis_attempts"])
        try:
            if status in ("pending", "in_progress") or r["llm_skip_reason"] == "owner_opt_out":
                await analyze_trace.kiq(str(r["id"]), finalize=True)
            else:
                await match_trace.kiq(str(r["id"]))
        except Exception:
            logger.exception("failed to enqueue listing hook for trace %s", r["id"])


@router.get("/{trace_id}", response_model=TraceDetailResponse)
async def get_trace(trace_id: str, user: CurrentUser) -> TraceDetailResponse:
    row = await visible_or_404(trace_id, user)
    return await _detail(row)


@router.patch("/{trace_id}", response_model=TraceDetailResponse)
async def update_trace(
    trace_id: str, body: TraceUpdateRequest, user: CurrentUser
) -> TraceDetailResponse:
    # Invisible traces 404; a listed trace's existence isn't secret, so a
    # non-owner editing one gets an honest 403.
    row = await visible_or_404(trace_id, user)
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
    return await _detail(await visible_or_404(trace_id, user))


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
    await visible_or_404(trace_id, user)
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


@router.post(
    "/{trace_id}/analyze",
    response_model=AnalyzeResponse,
    status_code=202,
    responses={200: {"model": AnalyzeResponse, "description": "Already final; nothing queued"}},
)
async def analyze_now(trace_id: str, user: CurrentUser, response: Response) -> AnalyzeResponse:
    """Owner-requested analysis (9_session-analysis.md): finalize now — the
    last turn and the roll-up included — whatever the idle state. Idempotent:
    a final trace queues nothing (200), and a run in flight gets the request
    noted instead of a second job."""
    row = await visible_or_404(trace_id, user)
    if not row["is_owner"]:
        raise ApiError("forbidden", "Only the owner can analyze a trace.", status=403)
    status = analysis_q.derive_status(
        row["llm_status"], row["analyzed_at"], row["analysis_attempts"]
    )
    if status == "final":
        response.status_code = 200
        return AnalyzeResponse(status=status, queued=False)
    await request_finalize(trace_id)
    return AnalyzeResponse(status=status, queued=True)


async def request_finalize(trace_id: str) -> None:
    """Get a finalizing run for the trace: noted on the lease when a run is
    in flight (the holder enqueues it on release, budget untouched),
    otherwise enqueued with a fresh attempt budget."""
    pool = db.pool()
    if await analysis_q.note_rerun_if_leased(pool, trace_id, True):
        return
    await analysis_q.reset_attempts(pool, trace_id)
    await analyze_trace.kiq(trace_id, finalize=True)


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
    await visible_or_404(trace_id, user)
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


@router.get("/{trace_id}/agents", response_model=AgentsResponse)
async def list_agents(trace_id: str, user: CurrentUser) -> AgentsResponse:
    """The subagent tree as a flat list, one item per spawn span in start
    order. Same visibility as the trace's spans (owner, or listed)."""
    await visible_or_404(trace_id, user)
    _, agents = spans_q.overview(await spans_q.skeleton(db.pool(), trace_id))
    verdicts = await analysis_q.fetch_subagents(db.pool(), trace_id)
    return AgentsResponse(
        agents=[AgentSpawn(**a, verdict=verdicts.get(a["span_id"])) for a in agents]
    )


@router.get("/{trace_id}/spans", response_model=SpanListResponse)
async def list_spans(
    trace_id: str,
    user: CurrentUser,
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> SpanListResponse:
    await visible_or_404(trace_id, user)
    rows, total = await spans_q.list_for_trace(db.pool(), trace_id, limit=limit, offset=offset)
    return SpanListResponse(spans=[_span_item(r) for r in rows], total=total)


@router.get("/{trace_id}/spans/{span_id}", response_model=SpanDetailResponse)
async def get_span(trace_id: str, span_id: str, user: CurrentUser) -> SpanDetailResponse:
    trace = await visible_or_404(trace_id, user)
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


def session_analysis(row: Mapping[str, Any], turn_count: int) -> SessionAnalysis:
    """The session block from a trace_analysis row (left-joined: all-null
    when unanalyzed) plus `analysis_attempts`."""
    status = analysis_q.derive_status(
        row["llm_status"], row["analyzed_at"], row["analysis_attempts"]
    )
    signals = None
    if row["llm_status"] is not None:
        signals = AnalysisSignals(**{f: row[f] for f in analysis_q.SIGNAL_FIELDS})
    return SessionAnalysis(
        status=status,
        turn_count=turn_count,
        skip_reason=row["llm_skip_reason"] if status == "skipped" else None,
        goal=row["goal"],
        outcome=row["outcome"],
        summary=row["summary"],
        task_categories=list(row["task_categories"] or []),
        failure_modes=list(row["failure_modes"] or []),
        analyzed_at=row["analyzed_at"],
        signals=signals,
    )


def turn_analysis(turn: Mapping[str, Any], origin: str, is_owner: bool) -> TurnAnalysis:
    """`uncertain` is review-queue content: owner-only."""
    return TurnAnalysis(
        turn_index=turn["turn_index"],
        origin=origin,
        outcome=turn["outcome"],
        summary=turn["summary"],
        uncertain=turn["uncertain"] if is_owner else None,
        provenance=turn["provenance"],
        signals=AnalysisSignals.model_validate(turn["signals"]),
        labels=[
            TurnLabel(
                field=lb["field"],
                value=lb["value"],
                span_ids=list(lb["span_ids"]),
                reason=lb["reason"],
            )
            for lb in turn["labels"]
        ],
    )


async def trace_analysis(row: Mapping[str, Any]) -> TraceAnalysis:
    """The detail analysis block for a `get_visible` row. Labels, reasons
    and cited span ids are visible to everyone who can see the trace — the
    same rule the judge reasoning always had; review content (the open item,
    `uncertain`) is owner-only."""
    pool = db.pool()
    trace_id = str(row["id"])
    dead_letter = await analysis_q.fetch_open_dead_letter(pool, trace_id)
    origins = await analysis_q.turn_origins(pool, trace_id)
    return TraceAnalysis(
        session=session_analysis(row, len(origins)),
        turns=[
            turn_analysis(t, origins.get(t["turn_index"], "human"), row["is_owner"])
            for t in await analysis_q.fetch_turns(pool, trace_id)
        ],
        failed_reason=dead_letter["last_error"] if dead_letter is not None else None,
        open_review_item_id=(
            str(row["open_review_item_id"])
            if row["is_owner"] and row["open_review_item_id"] is not None
            else None
        ),
    )


async def _detail(row: asyncpg.Record) -> TraceDetailResponse:
    skills, agents = spans_q.overview(await spans_q.skeleton(db.pool(), str(row["id"])))
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
        skill_names=list(row["skill_names"]),
        skills=[SkillUse.model_validate(u) for u in skills],
        subagents=SubagentSummary(**spans_q.subagent_summary(agents)),
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
        analysis=await trace_analysis(row),
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


async def visible_or_404(trace_id: str, user: CurrentUser) -> asyncpg.Record:
    try:
        row = await traces_q.get_visible(db.pool(), trace_id, user.id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        # 404 (not 403) so callers can't probe for traces they can't see.
        raise ApiError("not_found", "Trace not found.", status=404)
    return row
