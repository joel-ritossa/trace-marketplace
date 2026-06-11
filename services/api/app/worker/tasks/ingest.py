import hashlib
import json
import logging
from pathlib import Path

import httpx

from app import obs, redaction
from app.clients import db, storage
from app.dev import faults
from app.importers import otlp, sessions
from app.importers.errors import PermanentIngestError
from app.queries import notifications as notifications_q
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
    (6_architecture.md, A2 amendment + A6): trace rows are upserted keyed on
    (owner_id, source_trace_id) — so traces.id survives a re-ingest *and* a
    re-upload of the same logical trace (the newest upload adopts the row),
    and analysis/acquisition rows never cascade away — spans are deleted and
    re-inserted per trace, and traces absent from the payload are dropped,
    all in one transaction with the status flip. Any re-run converges.
    """
    obs.bind(upload_id=upload_id)
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

        # Route by format (8_session-ingestion.md): OTLP flows through as-is;
        # session JSONL converts to a per-turn OTLP payload first, then both
        # share the one normalize path below. Detection re-reads the raw
        # bytes (not the upload row) so the result stays a pure function of
        # the stored payload.
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        if isinstance(payload, dict) and otlp.matches(payload):
            source_format, importer_version = otlp.SOURCE_FORMAT, otlp.IMPORTER_VERSION
        else:
            records = sessions.parse_records(raw)
            source_format = sessions.detect(records)
            if source_format is None:
                raise PermanentIngestError(
                    "Payload is not OTLP JSON or a supported agent-session log "
                    "(unsupported schema)."
                )
            importer_version = sessions.IMPORTER_VERSION
            payload = sessions.convert(
                source_format,
                records,
                session_id=Path(upload["filename"]).stem,
                # created_at is immutable per upload: re-ingest reproduces
                # identical synthesized timestamps for clockless logs.
                anchor=upload["created_at"],
            )

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
                    source_format=source_format,
                    importer_version=importer_version,
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
        # CLI failures fail unattended — surface them as a notification
        # (A3 decision 5; the query no-ops for web uploads). Best-effort:
        # the failure is already recorded, so this must not re-run the task.
        try:
            await notifications_q.upload_failed(pool, upload_id)
        except Exception:
            logger.exception(
                "ingest_upload: upload_failed notification for %s not delivered", upload_id
            )
