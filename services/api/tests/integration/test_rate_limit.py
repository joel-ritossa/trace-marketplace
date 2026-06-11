"""Upload token bucket: burst past the per-user upload limit returns 429."""

import uuid

import httpx
import pytest

from app.config import settings
from tests.integration.conftest import otlp_payload
from tests.integration.test_uploads import upload_file

pytestmark = pytest.mark.asyncio


async def test_upload_burst_rate_limited(api: httpx.AsyncClient) -> None:
    responses = []
    for _ in range(settings.rate_limit_upload_per_minute + 1):
        responses.append(await upload_file(api, otlp_payload(uuid.uuid4().hex)))

    assert all(r.status_code == 201 for r in responses[:-1])
    limited = responses[-1]
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1
