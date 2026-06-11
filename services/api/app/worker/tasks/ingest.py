import hashlib
import json
import logging

import httpx

from app.clients import db, storage
from app.dev import faults
from app.importers import otlp
from app.importers.errors import PermanentIngestError
from app.queries import spans as spans_q
from app.queries import traces as traces_q
from app.queries import uploads
from app.worker.broker import broker

logger = logging.getLogger(__name__)


@broker.task(retry_dlq="true")
async def ingest_upload(upload_id: str) -> None:
    """Fetch the raw payload, verify it, and rewrite its normalized rows.

    Idempotent by delete-and-rewrite: traces/spans for the upload are replaced
    in one transaction with the status flip, so any re-run (retry, sweep,
    duplicate delivery, concurrent worker) converges to the same outcome.

    TODO(trace-analysis): delete-and-reinsert mints new trace IDs on every
    re-run. Before derived analysis attaches to traces.id, switch to stable
    trace identity (upsert keyed on (upload_id, source_trace_id)).
    """
    pool = db.pool()
    upload = await uploads.get(pool, upload_id)
    if upload is None:
        logger.warning("ingest_upload: upload %s no longer exists; dropping", upload_id)
        return

    # Atomic claim: returns None if already complete (terminal), so a stale
    # duplicate delivery drops here instead of redoing the work.
    attempt = await uploads.mark_processing(pool, upload_id)
    if attempt is None:
        return
    try:
        await faults.trip(upload_id, attempt)
        try:
            raw = await storage.get(upload["storage_path"])
        except httpx.HTTPStatusError as exc:
            # The fetch is immutable, so a 4xx (Supabase returns 400/404 for a
            # missing object) will never succeed on retry; don't burn the
            # budget. 429 and 5xx stay transient.
            code = exc.response.status_code
            if exc.response.is_client_error and code != 429:
                raise PermanentIngestError(
                    f"Stored payload object is missing or unreadable (storage status {code})."
                ) from exc
            raise
        if hashlib.sha256(raw).hexdigest() != upload["sha256"]:
            raise PermanentIngestError("Stored payload does not match the recorded checksum.")
        try:
            payload = json.loads(raw)
        except ValueError as exc:
            raise PermanentIngestError("Stored payload is not parseable JSON.") from exc

        result = otlp.import_payload(payload)

        async with pool.acquire() as conn, conn.transaction():
            # Serialize concurrent runs of the same upload (see uploads.lock).
            await uploads.lock(conn, upload_id)
            await traces_q.delete_for_upload(conn, upload_id)
            for trace in result.traces:
                trace_id = await traces_q.insert(
                    conn,
                    upload_id=upload_id,
                    owner_id=str(upload["owner_id"]),
                    trace=trace,
                    source_format=otlp.SOURCE_FORMAT,
                    importer_version=otlp.IMPORTER_VERSION,
                )
                await spans_q.insert_many(conn, trace_id, trace.spans)
            await uploads.mark_complete(conn, upload_id, parse_warnings=result.parse_warnings)

        logger.info(
            "ingest_upload: upload %s complete (attempt %d, traces %d, spans %d, skipped %d)",
            upload_id,
            attempt,
            len(result.traces),
            sum(t.span_count for t in result.traces),
            (result.parse_warnings or {}).get("skipped_spans", 0),
        )
    except PermanentIngestError as exc:
        # Permanent: no retry, readable reason, done (6_architecture.md).
        await uploads.mark_failed(pool, upload_id, str(exc))
        logger.info("ingest_upload: upload %s permanently failed: %s", upload_id, exc)
