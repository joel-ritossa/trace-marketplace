import hashlib
import logging
import re
import secrets

import asyncpg
from fastapi import APIRouter, Query, Request, Response
from starlette.datastructures import UploadFile

from app import importers, obs
from app.auth import AuthUser, CurrentUser, UploadPrincipal
from app.clients import db, storage
from app.config import settings
from app.dev import faults
from app.errors import ApiError
from app.queries import traces, uploads
from app.schemas.upload import (
    UploadCreatedResponse,
    UploadListItem,
    UploadListResponse,
    UploadStatusResponse,
)
from app.worker.tasks import ingest_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads")


async def _read_single_file_part(request: Request) -> tuple[str, bytes]:
    """Enforce the spec contract: multipart with exactly one `file` part."""
    try:
        form = await request.form()
    except Exception:
        raise ApiError("invalid_request", "Body must be multipart/form-data.", status=422) from None
    parts = form.multi_items()
    if len(parts) != 1 or parts[0][0] != "file" or not isinstance(parts[0][1], UploadFile):
        raise ApiError(
            "invalid_request",
            "Send multipart/form-data with exactly one part named 'file'.",
            status=422,
        )
    file = parts[0][1]
    data = await file.read()
    return file.filename or "upload.json", data


@router.post("", status_code=201, response_model=UploadCreatedResponse)
async def create_upload(request: Request, user: UploadPrincipal) -> UploadCreatedResponse:
    # Validate the fault header before any side effects so an invalid value
    # can't leave behind a stored-but-never-enqueued upload.
    fault = request.headers.get("x-fault") if settings.dev_routes else None
    if fault and not faults.is_valid(fault):
        raise ApiError(
            "invalid_request",
            "X-Fault must be 'permanent', 'exhaust', or 'transient:N'.",
            status=422,
        )

    # Without Content-Length the multipart parser would consume an unbounded
    # chunked body before the size check; every real client sends it.
    declared = request.headers.get("content-length")
    if declared is None:
        raise ApiError("length_required", "Content-Length header is required.", status=411)
    if int(declared) > settings.upload_max_bytes + 4096:  # multipart overhead
        raise _too_large()

    filename, data = await _read_single_file_part(request)
    if len(data) > settings.upload_max_bytes:
        raise _too_large()

    source_format = importers.sniff_format(data)
    if source_format is None:
        raise ApiError(
            "unsupported_format",
            "Expected OTLP JSON ('resourceSpans') or a supported agent-session "
            "log (Codex, Claude Code, or Cursor JSONL).",
            status=422,
        )

    sha256 = hashlib.sha256(data).hexdigest()
    pool = db.pool()
    existing = await uploads.find_by_hash(pool, user.id, sha256)
    if existing is not None:
        raise _duplicate(str(existing["id"]))

    # Object first, row second: a failure in between leaves an orphan object
    # (harmless, sha-addressed) rather than a row pointing at nothing.
    path = storage.raw_path(user.id, sha256)
    await storage.put(path, data)
    try:
        upload_id = await uploads.create(
            pool,
            owner_id=user.id,
            filename=filename,
            size_bytes=len(data),
            sha256=sha256,
            storage_path=path,
            source_format=source_format,
            # Inferred from auth type, never client-set (2_data-model.md).
            source="cli" if user.via == "api_key" else "web",
            # Minted once at creation, immutable: keys the deterministic
            # placeholder HMAC across every (re-)ingest (7_redaction.md).
            redaction_salt=secrets.token_hex(16),
        )
    except asyncpg.UniqueViolationError:
        # Concurrent duplicate of the same file; surface the winner.
        existing = await uploads.find_by_hash(pool, user.id, sha256)
        raise _duplicate(str(existing["id"])) from None

    obs.bind(upload_id=str(upload_id))
    if fault:
        await faults.arm(str(upload_id), fault)

    # The committed row is the acceptance of record; a broker blip may delay
    # ingestion (the stuck-upload sweep re-enqueues it) but must not turn an
    # already-durable upload into a 500.
    try:
        await ingest_upload.kiq(str(upload_id))
    except Exception:
        logger.exception("upload %s: enqueue failed; sweep will recover", upload_id)
    logger.info(
        "upload %s created: %s, %d bytes, sha256=%s…", upload_id, filename, len(data), sha256[:12]
    )
    return UploadCreatedResponse(upload_id=str(upload_id), status="received", sha256=sha256)


@router.get("", response_model=UploadListResponse)
async def list_uploads(
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> UploadListResponse:
    rows, total = await uploads.list_owned(db.pool(), user.id, limit=limit, offset=offset)
    return UploadListResponse(
        uploads=[
            UploadListItem(
                upload_id=str(r["id"]),
                filename=r["filename"],
                size_bytes=r["size_bytes"],
                status=r["status"],
                source=r["source"],
                error_message=r["error_message"],
                redaction_counts=r["redaction_counts"],
                trace_ids=[str(t) for t in r["trace_ids"]],
                created_at=r["created_at"],
                processed_at=r["processed_at"],
            )
            for r in rows
        ],
        total=total,
    )


@router.get("/{upload_id}", response_model=UploadStatusResponse)
async def get_upload(upload_id: str, user: UploadPrincipal) -> UploadStatusResponse:
    row = await _owned_or_404(upload_id, user)
    trace_ids = (
        await traces.ids_for_upload(db.pool(), str(row["id"]))
        if row["status"] == "complete"
        else []
    )
    return UploadStatusResponse(
        upload_id=str(row["id"]),
        filename=row["filename"],
        status=row["status"],
        source=row["source"],
        error_message=row["error_message"],
        parse_warnings=row["parse_warnings"],
        redaction_counts=row["redaction_counts"],
        trace_ids=trace_ids,
        created_at=row["created_at"],
        processed_at=row["processed_at"],
    )


@router.get("/{upload_id}/download")
async def download_upload(upload_id: str, user: CurrentUser) -> Response:
    row = await _owned_or_404(upload_id, user)
    data = await storage.get(row["storage_path"])
    # Headers must be latin-1 with no control chars; the filename is
    # client-supplied, so strip to printable ASCII rather than 500 on encode.
    safe_name = re.sub(r'[^\x20-\x7e]|"', "", row["filename"]) or "upload.json"
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


async def _owned_or_404(upload_id: str, user: AuthUser) -> asyncpg.Record:
    try:
        row = await uploads.get_owned(db.pool(), upload_id, user.id)
    except asyncpg.DataError:  # not a UUID
        row = None
    if row is None:
        # 404 (not 403) so callers can't probe for other users' uploads.
        raise ApiError("not_found", "Upload not found.", status=404)
    return row


def _too_large() -> ApiError:
    limit_mb = settings.upload_max_bytes // (1024 * 1024)
    return ApiError("file_too_large", f"File exceeds the {limit_mb} MB limit.", status=413)


def _duplicate(existing_id: str) -> ApiError:
    return ApiError(
        "duplicate_upload",
        "You already uploaded this file.",
        status=409,
        details={"upload_id": existing_id},
    )
