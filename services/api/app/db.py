import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


async def open_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=5)


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized; open_pool() must run at startup")
    return _pool
