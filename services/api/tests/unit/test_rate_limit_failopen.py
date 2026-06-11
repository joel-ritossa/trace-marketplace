"""Redis loss must not gate requests: the rate limiter fails open.

Rate-limit state is explicitly not state of record (6_architecture.md), so the
limiter's backing store going away should degrade to "no limiting", not 500s
on Postgres-only reads.
"""

import httpx
import pytest
from fastapi import FastAPI
from redis.exceptions import RedisError

from app.middleware import rate_limit
from app.middleware.rate_limit import RateLimitMiddleware


class _DownRedis:
    def register_script(self, _lua: str):
        async def script(keys: list, args: list):
            raise RedisError("connection refused")

        return script


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.setattr(rate_limit.redis, "client", lambda: _DownRedis())
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware)

    @app.get("/ping")
    async def ping() -> dict:
        return {"ok": True}

    return app


async def test_requests_pass_when_redis_is_down(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/ping")
    assert res.status_code == 200
    assert res.json() == {"ok": True}
