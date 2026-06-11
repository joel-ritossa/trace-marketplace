from app import db
from app.worker.broker import broker


@broker.task
async def ping() -> dict:
    """Slice 0 skeleton task: proves API -> Redis -> worker -> Postgres."""
    value = await db.pool().fetchval("select 1")
    return {"db_ok": value == 1}
