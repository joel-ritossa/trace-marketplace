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
    """Lost-job recovery and session finalization: re-enqueue uploads stuck
    past the timeout, analyses whose kick was lost, and session traces gone
    idle that are not final yet (analysis.due_ids).

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

    due = await analysis_q.due_ids(
        db.pool(),
        older_than_minutes=settings.sweep_stuck_after_minutes,
        idle_seconds=settings.analysis_idle_seconds,
    )
    for trace_id, finalize in due:
        await analyze_trace.kiq(trace_id, finalize=finalize)
    if due:
        logger.info("sweep: enqueued %d analysis run(s): %s", len(due), due)
    return {"requeued": len(stuck), "analysis_enqueued": len(due)}
