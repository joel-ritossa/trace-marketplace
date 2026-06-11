from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.clients import db, redis, storage
from app.config import settings
from app.obs import configure_logging
from app.worker.correlation import CorrelationMiddleware
from app.worker.retry_dlq import RetryDlqMiddleware

configure_logging()

# Correlation first so retry/DLQ log lines carry the propagated id.
broker = (
    ListQueueBroker(settings.redis_url)
    .with_result_backend(RedisAsyncResultBackend(settings.redis_url, result_ex_time=300))
    .with_middlewares(CorrelationMiddleware(), RetryDlqMiddleware())
)


# WORKER_* events fire only in the worker process; the API manages its own
# clients in the FastAPI lifespan. Tasks share db.pool() exactly like routes do.
@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _worker_startup(_: TaskiqState) -> None:
    await db.open_pool()
    await redis.open_client()
    await storage.open_client()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _worker_shutdown(_: TaskiqState) -> None:
    await storage.close_client()
    await redis.close_client()
    await db.close_pool()
