"""Upload token bucket. The real limits are too generous to burst through
cheaply in a test (60/min refills faster than sequential uploads drain it), so
drive the bucket state directly in Redis and assert the deny and refill paths.
"""

import time

import httpx
import jwt
import pytest
import redis.asyncio as aioredis

from app.config import settings
from tests.integration.conftest import otlp_payload
from tests.integration.test_uploads import upload_file

pytestmark = pytest.mark.asyncio


async def test_upload_bucket_denies_and_refills(api: httpx.AsyncClient, token: str) -> None:
    sub = jwt.decode(token, options={"verify_signature": False})["sub"]
    r = aioredis.from_url(settings.redis_url)
    try:
        # Drained bucket: next upload is rejected with a Retry-After.
        await r.hset(f"rl:upload:{sub}", mapping={"tokens": 0, "ts": time.time()})
        limited = await upload_file(api, otlp_payload("rate-limited"))
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert int(limited.headers["retry-after"]) >= 1

        # Same bucket two minutes later: refill admits the request again.
        await r.hset(f"rl:upload:{sub}", mapping={"tokens": 0, "ts": time.time() - 120})
        ok = await upload_file(api, otlp_payload("rate-limit-refilled"))
        assert ok.status_code == 201
    finally:
        await r.aclose()
