"""Shared async Redis client (rate limiting, fault-injection markers).

Same lifecycle pattern as app.clients.db: opened at startup by whichever process needs
it (API lifespan, worker startup event), accessed via client().
"""

from redis.asyncio import Redis

from app.config import settings

_client: Redis | None = None


async def open_client() -> None:
    global _client
    _client = Redis.from_url(settings.redis_url)


async def close_client() -> None:
    if _client is not None:
        await _client.aclose()


def client() -> Redis:
    if _client is None:
        raise RuntimeError("Redis client not initialized; open_client() must run at startup")
    return _client
