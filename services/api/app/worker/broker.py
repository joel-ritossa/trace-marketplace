from taskiq import TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app import db
from app.config import settings

broker = ListQueueBroker(settings.redis_url).with_result_backend(
    RedisAsyncResultBackend(settings.redis_url, result_ex_time=300)
)


# WORKER_* events fire only in the worker process; the API manages its own
# pool in the FastAPI lifespan. Tasks share db.pool() exactly like routes do.
@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _worker_startup(_: TaskiqState) -> None:
    await db.open_pool()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _worker_shutdown(_: TaskiqState) -> None:
    await db.close_pool()
