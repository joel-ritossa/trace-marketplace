import hashlib
import json
import logging
from pathlib import Path

import httpx

from app import redaction
from app.clients import db, storage
from app.dev import faults
from app.importers import otlp
from app.importers.errors import PermanentIngestError
from app.queries import spans as spans_q
from app.queries import traces as traces_q
from app.queries import uploads
from app.worker.broker import broker
from app.worker.tasks.analyze import analyze_trace

logger = logging.getLogger(__name__)


@broker.task(retry_dlq="upload")
async def ingest_upload(upload_id: str) -> None:
    """Fetch the raw payload, verify it, and rewrite its normalized rows.

    Idempotent by delete-and-rewrite under stable trace identity
    (6_architecture.md, A2 amendment): trace rows are upserted keyed on
    (upload_id, source_trace_id) — so traces.id survives a re-ingest and
    analysis/acquisition rows never cascade away — spans are deleted and
    re-inserted per trace, and traces absent from the payload are dropped,
    all in one transaction with the status flip. Any re-run converges.
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

        salt = upload["redaction_salt"]
        result = otlp.import_payload(
            payload,
            redaction_salt=salt,
            fallback_name=Path(upload["filename"]).stem,
        )

        # Scrubbed payload artifact for the non-owner download boundary
        # (7_redaction.md). Same salt + ruleset as the rows above, so both
        # representations carry identical placeholders; the deterministic
        # scrub makes the upsert byte-identical on re-ingest. Written before
        # the DB transaction: a storage failure here retries transiently
        # without ever exposing rows whose artifact is missing.
        scrubbed_payload, redaction_counts = redaction.scrub_otlp_payload(payload, salt)
        await storage.put(
            storage.scrubbed_path(upload["storage_path"]),
            json.dumps(scrubbed_payload).encode(),
        )

        trace_ids: list[str] = []
        async with pool.acquire() as conn, conn.transaction():
            # Serialize concurrent runs of the same upload (see uploads.lock).
            await uploads.lock(conn, upload_id)
            for trace in result.traces:
                trace_id = await traces_q.upsert(
                    conn,
                    upload_id=upload_id,
                    owner_id=str(upload["owner_id"]),
                    trace=trace,
                    source_format=otlp.SOURCE_FORMAT,
                    importer_version=otlp.IMPORTER_VERSION,
                )
                await spans_q.delete_for_trace(conn, trace_id)
                await spans_q.insert_many(conn, trace_id, trace.spans)
                trace_ids.append(str(trace_id))
            await traces_q.delete_absent(conn, upload_id, trace_ids)
            await uploads.mark_complete(
                conn,
                upload_id,
                parse_warnings=result.parse_warnings,
                redaction_version=redaction.REDACTION_VERSION,
                redaction_counts=dict(redaction_counts) or None,
            )

        # Post-commit: every (re)ingest gets a fresh analysis run — analysis
        # is idempotent, so re-analysis keeps derived rows consistent with
        # the rewritten content (A2 decision 2). Best-effort: the ingest is
        # already complete, so a failed kick must not fail (and re-run) the
        # task — the stale-pending-analysis sweep recovers lost kicks.
        for trace_id in trace_ids:
            try:
                await analyze_trace.kiq(trace_id)
            except Exception:
                logger.exception(
                    "ingest_upload: failed to enqueue analysis for trace %s; sweep will recover",
                    trace_id,
                )

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
