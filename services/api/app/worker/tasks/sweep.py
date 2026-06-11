import logging

from app.clients import db
from app.config import settings
from app.queries import analysis as analysis_q
from app.queries import uploads
from app.worker.broker import broker
from app.worker.tasks.analyze import analyze_trace
from app.worker.tasks.ingest import ingest_upload

logger = logging.getLogger(__name__)


@broker.task(schedule=[{"cron": "* * * * *"}])
async def sweep_stuck_uploads() -> dict:
    """Lost-job recovery: re-enqueue uploads stuck past the timeout, and
    analyses still pending past it (never analyzed, or re-ingested and never
    re-claimed; see analysis.stale_pending_ids) — `pending` means "it will
    arrive" (4_pages.md), so a lost analyze kick must be recovered, not
    shrugged at.

    Fired by the scheduler service every 60s. Safe to double-fire because
    both tasks are idempotent.
    """
    stuck = await uploads.stuck_ids(
        db.pool(), older_than_minutes=settings.sweep_stuck_after_minutes
    )
    for upload_id in stuck:
        await ingest_upload.kiq(upload_id)
    if stuck:
        logger.warning("sweep: re-enqueued %d stuck upload(s): %s", len(stuck), stuck)

    stale = await analysis_q.stale_pending_ids(
        db.pool(), older_than_minutes=settings.sweep_stuck_after_minutes
    )
    for trace_id in stale:
        await analyze_trace.kiq(trace_id)
    if stale:
        logger.warning("sweep: re-enqueued %d stale analysis run(s): %s", len(stale), stale)
    return {"requeued": len(stuck), "analysis_requeued": len(stale)}
