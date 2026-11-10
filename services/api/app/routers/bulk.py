"""Bulk trace operations (3_api.md): acquire, list/unlist, download. All
take ≤100 trace ids and return itemized results — partial success is
normal, never all-or-nothing. Each loops the stage-1 single-trace
primitive, so per-trace semantics are identical by construction (A4
decision 11).
"""

import json
import logging
import re
import zipfile
from collections.abc import Iterator
from tempfile import SpooledTemporaryFile

import asyncpg
import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.auth import CurrentUser
from app.clients import db, storage
from app.errors import ApiError
from app.queries import acquisitions as acquisitions_q
from app.queries import analysis as analysis_q
from app.queries import traces as traces_q
from app.routers.traces import schedule_listing_hooks, session_analysis, turn_analysis
from app.schemas.trace import (
    BulkAcquireItem,
    BulkAcquireRequest,
    BulkAcquireResponse,
    BulkDownloadRequest,
    BulkVisibilityItem,
    BulkVisibilityRequest,
    BulkVisibilityResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces")

_SPOOL_MAX_BYTES = 32 * 1024 * 1024  # past this the zip spills to disk


@router.post("/acquire", response_model=BulkAcquireResponse)
async def bulk_acquire(body: BulkAcquireRequest, user: CurrentUser) -> BulkAcquireResponse:
    pool = db.pool()
    results: list[BulkAcquireItem] = []
    for trace_id in body.trace_ids:
        results.append(
            BulkAcquireItem(trace_id=trace_id, status=await _acquire_one(pool, trace_id, user.id))
        )
    return BulkAcquireResponse(results=results)


async def _acquire_one(pool: asyncpg.Pool, trace_id: str, caller_id: str) -> str:
    try:
        row = await traces_q.get_visible(pool, trace_id, caller_id)
    except asyncpg.DataError:  # not a UUID
        return "not_found"
    if row is None:
        return "not_found"
    acq = await acquisitions_q.create(pool, caller_id, trace_id)
    if acq is None:  # unlisted between the visibility check and the insert
        return "not_listed"
    return "acquired" if acq["created"] else "already_acquired"


@router.post("/visibility", response_model=BulkVisibilityResponse)
async def bulk_visibility(body: BulkVisibilityRequest, user: CurrentUser) -> BulkVisibilityResponse:
    # Batched consent: one confirmation covering the named selection — the
    # same affirmative checkbox as the single listing, once for the batch.
    if body.visibility == "listed" and not body.confirm_ownership:
        raise ApiError(
            "confirmation_required",
            "Listing requires confirming this data is yours to share.",
            status=422,
        )
    pool = db.pool()
    results: list[BulkVisibilityItem] = []
    updated_ids: list[str] = []
    for trace_id in body.trace_ids:
        try:
            row = await traces_q.update_owned(pool, trace_id, user.id, visibility=body.visibility)
        except asyncpg.DataError:  # not a UUID
            row = None
        # not_found covers non-owned and absent alike — the bulk shape has
        # no 403 slot, consistent with the 404-not-403 rule.
        status = "updated" if row is not None else "not_found"
        if row is not None:
            updated_ids.append(trace_id)
        results.append(BulkVisibilityItem(trace_id=trace_id, status=status))
    if body.visibility == "listed":
        await schedule_listing_hooks(updated_ids)
    return BulkVisibilityResponse(results=results)


@router.post("/download")
async def bulk_download(body: BulkDownloadRequest, user: CurrentUser) -> StreamingResponse:
    """Zip of payloads + labels.jsonl (3_api.md). Payload entries dedupe by
    upload — traces from one upload share one storage object — and follow
    the redaction boundary per trace set: owner → raw object, acquirer →
    scrubbed artifact (A4 decision 12)."""
    pool = db.pool()
    rows: dict[str, asyncpg.Record] = {}
    missing: list[str] = []
    unacquired: list[str] = []
    for trace_id in body.trace_ids:
        try:
            row = await traces_q.get_visible_with_upload(pool, trace_id, user.id)
        except asyncpg.DataError:
            row = None
        if row is None:
            missing.append(trace_id)
        elif not (row["is_owner"] or row["acquired"]):
            unacquired.append(trace_id)
        else:
            rows[trace_id] = row
    if missing:
        raise ApiError("not_found", f"Traces not found: {', '.join(missing)}", status=404)
    if unacquired:
        raise ApiError(
            "acquisition_required",
            f"Acquire these traces to download them: {', '.join(unacquired)}",
            status=403,
        )

    labels = [await _label_line(pool, tid, user.id) for tid in rows]

    spool = SpooledTemporaryFile(max_size=_SPOOL_MAX_BYTES)
    archive = zipfile.ZipFile(spool, "w", zipfile.ZIP_DEFLATED)
    try:
        await _write_payloads(archive, rows.values())
        archive.writestr(
            "labels.jsonl",
            "".join(labels),
        )
    except Exception:
        archive.close()
        spool.close()
        raise
    archive.close()

    return StreamingResponse(
        _iter_spool(spool),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="traces-{len(rows)}.zip"',
        },
    )


async def _write_payloads(archive: zipfile.ZipFile, rows) -> None:
    """One entry per distinct (storage object, redaction variant); filename
    collisions across uploads get the storage hash suffixed."""
    seen_paths: set[str] = set()
    used_names: set[str] = set()
    for row in rows:
        path = (
            row["storage_path"] if row["is_owner"] else storage.scrubbed_path(row["storage_path"])
        )
        if path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            data = await storage.get(path)
        except httpx.HTTPStatusError as exc:
            # Acquirers need the scrubbed artifact; uploads ingested before
            # redaction shipped have none until re-ingested (same answer as
            # the single download).
            if exc.response.is_client_error and not row["is_owner"]:
                raise ApiError(
                    "not_found",
                    f"No scrubbed copy exists for trace {row['id']} yet; "
                    "ask the owner to re-ingest the upload.",
                    status=404,
                ) from exc
            raise
        archive.writestr(_entry_name(row["filename"], path, used_names), data)


def _entry_name(filename: str, path: str, used: set[str]) -> str:
    # Same hygiene as the single download's header (client-supplied
    # filename), plus path separators — zip entries must stay flat.
    safe = re.sub(r'[^\x20-\x7e]|["/\\]', "", filename) or "trace.json"
    if safe in used:
        stem, dot, ext = safe.rpartition(".")
        suffix = path.rsplit("/", 1)[-1].removesuffix(".json")[:12]
        safe = f"{stem}-{suffix}.{ext}" if dot else f"{safe}-{suffix}"
    used.add(safe)
    return safe


async def _label_line(pool: asyncpg.Pool, trace_id: str, caller_id: str) -> str:
    """One labels.jsonl line per requested trace: the session roll-up and
    the per-turn verdicts, the same shapes as the trace detail's analysis
    block. Unanalyzed traces get a pending session and no turns."""
    row = await traces_q.get_visible(pool, trace_id, caller_id)
    turns = await analysis_q.fetch_turns(pool, trace_id)
    session = session_analysis(row, await analysis_q.count_turns(pool, trace_id))
    line = {
        "trace_id": trace_id,
        "session": session.model_dump(mode="json"),
        "turns": [turn_analysis(t).model_dump(mode="json") for t in turns],
    }
    return json.dumps(line) + "\n"


def _iter_spool(spool: SpooledTemporaryFile, chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    try:
        spool.seek(0)
        while chunk := spool.read(chunk_size):
            yield chunk
    finally:
        spool.close()
