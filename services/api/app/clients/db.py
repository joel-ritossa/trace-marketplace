import json

import asyncpg

from app.config import settings

_pool: asyncpg.Pool | None = None


async def _init_connection(conn: asyncpg.Connection) -> None:
    # jsonb in/out as Python dicts instead of strings.
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def open_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=5, init=_init_connection
    )


async def close_pool() -> None:
    if _pool is not None:
        await _pool.close()


def pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized; open_pool() must run at startup")
    return _pool
