import logging

from app.clients import db
from app.config import settings
from app.queries import uploads
from app.worker.broker import broker
from app.worker.tasks.ingest import ingest_upload

logger = logging.getLogger(__name__)


@broker.task(schedule=[{"cron": "* * * * *"}])
async def sweep_stuck_uploads() -> dict:
    """Lost-job recovery: re-enqueue uploads stuck past the timeout.

    Fired by the scheduler service every 60s. Safe to double-fire because
    ingest_upload is idempotent.
    """
    stuck = await uploads.stuck_ids(
        db.pool(), older_than_minutes=settings.sweep_stuck_after_minutes
    )
    for upload_id in stuck:
        await ingest_upload.kiq(upload_id)
    if stuck:
        logger.warning("sweep: re-enqueued %d stuck upload(s): %s", len(stuck), stuck)
    return {"requeued": len(stuck)}
