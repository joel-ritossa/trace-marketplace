"""Operator requeue for dead-lettered uploads: `make requeue UPLOAD=<id>`.

Resets the upload to received, marks its dead_letters rows requeued, and
enqueues a fresh ingest job.
"""

import asyncio
import sys

from app.clients import db
from app.queries import dead_letters, uploads
from app.worker.broker import broker
from app.worker.tasks import ingest_upload


async def _requeue(upload_id: str) -> int:
    await db.open_pool()
    await broker.startup()
    try:
        if not await uploads.reset_for_requeue(db.pool(), upload_id):
            print(f"upload {upload_id} not found or not in 'failed' status", file=sys.stderr)
            return 1
        await dead_letters.mark_requeued(db.pool(), upload_id)
        await ingest_upload.kiq(upload_id)
        print(f"upload {upload_id} reset and re-enqueued")
        return 0
    finally:
        await broker.shutdown()
        await db.close_pool()


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python -m app.cli.requeue <upload_id>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(_requeue(sys.argv[1])))


if __name__ == "__main__":
    main()
