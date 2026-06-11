"""Integration fixtures. These tests hit the real local stack:

    supabase start  +  docker compose up  (api, worker, scheduler, redis)

Each test gets a fresh user so per-user rate-limit buckets and duplicate-hash
state never leak between tests.
"""

import os
import uuid

import asyncpg
import httpx
import pytest

from app.config import settings

API_URL = os.environ.get("API_URL", "http://localhost:8000")


async def signup_token() -> str:
    """Create a fresh user and return its access token."""
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{settings.supabase_url}/auth/v1/signup",
            json={
                "email": f"it-{uuid.uuid4().hex[:12]}@example.com",
                "password": "integration-test-pw",
            },
            headers={"apikey": settings.supabase_service_role_key},
        )
        res.raise_for_status()
        return res.json()["access_token"]


@pytest.fixture
async def token() -> str:
    return await signup_token()


@pytest.fixture
async def api(token: str):
    async with httpx.AsyncClient(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture
async def db():
    conn = await asyncpg.connect(settings.database_url)
    try:
        yield conn
    finally:
        await conn.close()


def otlp_payload(marker: str | None = None) -> bytes:
    """Minimal ingestable OTLP JSON (one valid span); marker makes the bytes
    (sha) unique. Since Slice 2 the worker parses payloads, so an empty
    resourceSpans would be a permanent ingest failure, not a completed upload."""
    import json

    payload: dict = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "ab" * 16,
                                "spanId": "cd" * 8,
                                "name": "integration test span",
                                "startTimeUnixNano": "1768471200000000000",
                                "endTimeUnixNano": "1768471201000000000",
                                "attributes": [],
                                "status": {"code": 1},
                            }
                        ]
                    }
                ]
            }
        ]
    }
    if marker:
        payload["_test_marker"] = marker
    return json.dumps(payload).encode()
