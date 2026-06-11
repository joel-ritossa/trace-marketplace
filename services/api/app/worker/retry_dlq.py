"""Retry-with-DLQ middleware for ingestion tasks.

Transient failures re-kick with exponential backoff + jitter; exhaustion writes
a dead_letters row and marks the upload failed (6_architecture.md). Tasks opt
in with the retry_dlq label and upload_id as first argument.

The retry budget is `uploads.attempts` — the durable counter incremented by
each claim — not a message label. A label would reset to zero whenever the
sweep re-enqueues a lost job, unbounding total work per upload and making
dead_letters.attempts lie. The requeue CLI resets the counter for a fresh run.

The delayed re-kick is an in-process sleep, not a broker-scheduled message —
the Redis list broker has no delayed delivery. A worker crash during the wait
loses only that re-kick, and the stuck-upload sweep re-enqueues it.
"""

import asyncio
import logging
import random
import traceback
from typing import Any

from taskiq import TaskiqMiddleware
from taskiq.exceptions import NoResultError
from taskiq.kicker import AsyncKicker
from taskiq.message import TaskiqMessage
from taskiq.result import TaskiqResult

from app.clients import db
from app.config import settings
from app.queries import dead_letters, uploads

logger = logging.getLogger(__name__)


class RetryDlqMiddleware(TaskiqMiddleware):
    def __init__(self) -> None:
        super().__init__()
        # Strong refs so pending delayed re-kicks aren't garbage-collected.
        self._pending: set[asyncio.Task] = set()

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        if isinstance(exception, NoResultError):
            return
        if not message.labels.get("retry_dlq"):
            return

        upload_id = str(message.args[0] if message.args else message.kwargs["upload_id"])
        attempt = await uploads.attempt_count(db.pool(), upload_id)
        if attempt is None:
            logger.warning(
                "task %s upload=%s failed but the upload is gone; dropping",
                message.task_name,
                upload_id,
            )
            return

        if attempt < settings.ingest_max_attempts:
            delay = min(
                settings.ingest_retry_base_seconds * 2 ** (attempt - 1),
                settings.ingest_retry_cap_seconds,
            )
            delay += random.uniform(0, delay / 4)
            logger.info(
                "task %s upload=%s attempt %d/%d failed; retrying in %.1fs",
                message.task_name,
                upload_id,
                attempt,
                settings.ingest_max_attempts,
                delay,
            )
            kick = asyncio.create_task(self._kick_later(message, attempt, delay))
            self._pending.add(kick)
            kick.add_done_callback(self._pending.discard)
        else:
            await self._dead_letter(message, exception, attempt, upload_id)

    async def _kick_later(self, message: TaskiqMessage, attempt: int, delay: float) -> None:
        # Runs as a detached task: log failures or they vanish unobserved.
        # A lost re-kick is recovered by the stuck-upload sweep.
        try:
            await asyncio.sleep(delay)
            kicker: AsyncKicker[Any, Any] = AsyncKicker(
                task_name=message.task_name, broker=self.broker, labels=dict(message.labels)
            )
            await kicker.kiq(*message.args, **message.kwargs)
        except Exception:
            logger.exception(
                "task %s retry re-kick failed (attempt %d); sweep will recover",
                message.task_name,
                attempt,
            )

    async def _dead_letter(
        self,
        message: TaskiqMessage,
        exception: BaseException,
        attempts: int,
        upload_id: str,
    ) -> None:
        logger.error(
            "task %s upload=%s exhausted %d attempts; dead-lettering",
            message.task_name,
            upload_id,
            attempts,
        )
        tb_tail = "".join(traceback.format_exception(exception))[-2000:]
        pool = db.pool()
        await dead_letters.insert(
            pool,
            upload_id=upload_id,
            task_name=message.task_name,
            attempts=attempts,
            last_error=str(exception),
            error_context={"traceback_tail": tb_tail},
        )
        await uploads.mark_failed(
            pool,
            upload_id,
            f"Ingestion failed after {attempts} attempts: {exception}",
        )
