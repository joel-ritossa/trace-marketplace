import hashlib
import logging

from app.clients import db, storage
from app.dev import faults
from app.queries import uploads
from app.worker.broker import broker
from app.worker.errors import PermanentIngestError

logger = logging.getLogger(__name__)


@broker.task(retry_dlq="true")
async def ingest_upload(upload_id: str) -> None:
    """Slice 1: raw preservation only — fetch, verify, mark complete.

    Slice 2 adds parse + normalize (app.importers) + delete-and-rewrite of
    traces/spans here. Must stay idempotent: a re-run (retry, sweep, duplicate
    delivery) of any upload state converges to the same outcome.
    """
    pool = db.pool()
    upload = await uploads.get(pool, upload_id)
    if upload is None:
        logger.warning("ingest_upload: upload %s no longer exists; dropping", upload_id)
        return
    if upload["status"] == "complete":
        return

    attempt = await uploads.mark_processing(pool, upload_id)
    try:
        await faults.trip(upload_id, attempt)
        raw = await storage.get(upload["storage_path"])
        if hashlib.sha256(raw).hexdigest() != upload["sha256"]:
            raise PermanentIngestError("Stored payload does not match the recorded checksum.")
        await uploads.mark_complete(pool, upload_id)
        logger.info("ingest_upload: upload %s complete (attempt %d)", upload_id, attempt)
    except PermanentIngestError as exc:
        # Permanent: no retry, readable reason, done (6_architecture.md).
        await uploads.mark_failed(pool, upload_id, str(exc))
        logger.info("ingest_upload: upload %s permanently failed: %s", upload_id, exc)
