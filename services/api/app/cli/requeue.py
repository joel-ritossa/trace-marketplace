"""Operator requeue for dead-lettered work.

    python -m app.cli.requeue upload <id>   (also: make requeue UPLOAD=<id>)
    python -m app.cli.requeue trace <id>

Upload mode resets the upload to received, closes its ingestion dead
letters, and enqueues a fresh ingest job. Trace mode closes the trace's
analysis dead letters, resets the analysis budget, and enqueues a fresh
analyze job — the trace honestly returns to analysis `pending`.
"""

import asyncio
import sys

from app.clients import db
from app.queries import analysis as analysis_q
from app.queries import dead_letters, uploads
from app.worker.broker import broker
from app.worker.tasks import analyze_trace, ingest_upload


async def _requeue_upload(upload_id: str) -> int:
    if not await uploads.reset_for_requeue(db.pool(), upload_id):
        print(f"upload {upload_id} not found or not in a terminal status", file=sys.stderr)
        return 1
    await dead_letters.mark_requeued(db.pool(), upload_id)
    await ingest_upload.kiq(upload_id)
    print(f"upload {upload_id} reset and re-enqueued")
    return 0


async def _requeue_trace(trace_id: str) -> int:
    if await analysis_q.attempt_count(db.pool(), trace_id) is None:
        print(f"trace {trace_id} not found", file=sys.stderr)
        return 1
    await dead_letters.mark_requeued_for_trace(db.pool(), trace_id)
    await analysis_q.reset_attempts(db.pool(), trace_id)
    await analyze_trace.kiq(trace_id)
    print(f"trace {trace_id} analysis reset and re-enqueued")
    return 0


async def _run(kind: str, subject_id: str) -> int:
    await db.open_pool()
    await broker.startup()
    try:
        if kind == "upload":
            return await _requeue_upload(subject_id)
        return await _requeue_trace(subject_id)
    finally:
        await broker.shutdown()
        await db.close_pool()


def main() -> None:
    args = sys.argv[1:]
    # Bare-id form stays supported: `make requeue UPLOAD=<id>` predates modes.
    if len(args) == 1:
        args = ["upload", args[0]]
    if len(args) != 2 or args[0] not in ("upload", "trace"):
        print("usage: python -m app.cli.requeue [upload|trace] <id>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_run(args[0], args[1])))


if __name__ == "__main__":
    main()
