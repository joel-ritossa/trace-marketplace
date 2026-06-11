"""Retry-with-DLQ middleware for ingestion and analysis tasks.

Transient failures re-kick with exponential backoff + jitter; exhaustion
writes a dead_letters row (6_architecture.md). Tasks opt in with the
retry_dlq label naming their scope — ``upload`` (first arg upload_id;
exhaustion also marks the upload failed) or ``trace`` (first arg trace_id;
the trace's analysis state derives `failed` from the dead letter itself,
and structurally permanent analysis errors dead-letter immediately).

The retry budget is a durable counter incremented by each claim
(`uploads.attempts` / `traces.analysis_attempts`) — not a message label. A
label would reset to zero whenever the sweep re-enqueues a lost job,
unbounding total work and making dead_letters.attempts lie. The requeue CLI
resets the counter for a fresh run.

The delayed re-kick is an in-process sleep, not a broker-scheduled message —
the Redis list broker has no delayed delivery. A worker crash during the wait
loses only that re-kick, and the stuck-job sweeps re-enqueue it.
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

from app.analysis import PermanentAnalysisError
from app.clients import db
from app.config import settings
from app.queries import analysis as analysis_q
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
        scope = message.labels.get("retry_dlq")
        if not scope:
            return

        subject_id = str(message.args[0] if message.args else next(iter(message.kwargs.values())))
        if scope == "trace":
            attempt = await analysis_q.attempt_count(db.pool(), subject_id)
        else:
            attempt = await uploads.attempt_count(db.pool(), subject_id)
        if attempt is None:
            logger.warning(
                "task %s %s=%s failed but the subject row is gone; dropping",
                message.task_name,
                scope,
                subject_id,
            )
            return

        # Structurally permanent analysis errors never succeed on retry;
        # dead-letter now so the trace surfaces `failed` instead of burning
        # budget (the analysis path has no status column to mark instead).
        permanent = scope == "trace" and isinstance(exception, PermanentAnalysisError)

        if not permanent and attempt < settings.ingest_max_attempts:
            delay = min(
                settings.ingest_retry_base_seconds * 2 ** (attempt - 1),
                settings.ingest_retry_cap_seconds,
            )
            delay += random.uniform(0, delay / 4)
            logger.info(
                "task %s %s=%s attempt %d/%d failed; retrying in %.1fs",
                message.task_name,
                scope,
                subject_id,
                attempt,
                settings.ingest_max_attempts,
                delay,
            )
            kick = asyncio.create_task(self._kick_later(message, attempt, delay))
            self._pending.add(kick)
            kick.add_done_callback(self._pending.discard)
        else:
            await self._dead_letter(message, exception, attempt, scope, subject_id)

    async def _kick_later(self, message: TaskiqMessage, attempt: int, delay: float) -> None:
        # Runs as a detached task: log failures or they vanish unobserved.
        # A lost re-kick is recovered by the stuck-job sweeps.
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
        scope: str,
        subject_id: str,
    ) -> None:
        logger.error(
            "task %s %s=%s failed terminally after %d attempt(s); dead-lettering",
            message.task_name,
            scope,
            subject_id,
            attempts,
        )
        tb_tail = "".join(traceback.format_exception(exception))[-2000:]
        pool = db.pool()
        if scope == "trace":
            upload_id = await pool.fetchval(
                "select upload_id from traces where id = $1", subject_id
            )
            if upload_id is None:
                logger.warning(
                    "task %s trace=%s deleted while failing; nothing to record against",
                    message.task_name,
                    subject_id,
                )
                return
            await dead_letters.insert(
                pool,
                upload_id=str(upload_id),
                trace_id=subject_id,
                task_name=message.task_name,
                attempts=attempts,
                last_error=str(exception),
                error_context={"traceback_tail": tb_tail},
            )
            # No status flip: analysis_state derives `failed` from the row.
            return
        await dead_letters.insert(
            pool,
            upload_id=subject_id,
            task_name=message.task_name,
            attempts=attempts,
            last_error=str(exception),
            error_context={"traceback_tail": tb_tail},
        )
        await uploads.mark_failed(
            pool,
            subject_id,
            f"Ingestion failed after {attempts} attempts: {exception}",
        )
