"""Supabase Storage client for the private raw-traces bucket.

Thin httpx wrapper over the Storage HTTP API using the service role key. No
public URLs exist; every read goes through API access checks first.
"""

import httpx

from app.config import settings

BUCKET = "raw-traces"

_client: httpx.AsyncClient | None = None


async def open_client() -> None:
    global _client
    _client = httpx.AsyncClient(
        base_url=settings.supabase_storage_url,
        headers={"Authorization": f"Bearer {settings.supabase_service_role_key}"},
        timeout=30.0,
    )


async def close_client() -> None:
    if _client is not None:
        await _client.aclose()


def _http() -> httpx.AsyncClient:
    if _client is None:
        raise RuntimeError("Storage client not initialized; open_client() must run at startup")
    return _client


def raw_path(owner_id: str, sha256: str) -> str:
    return f"raw/{owner_id}/{sha256}.json"


def scrubbed_path(raw: str) -> str:
    """Path of the scrubbed payload artifact materialized at ingestion
    (7_redaction.md) — what non-owner downloads serve."""
    return "scrubbed/" + raw.removeprefix("raw/")


async def put(path: str, data: bytes) -> None:
    # Upsert keeps a retried upload request idempotent: the object content is
    # keyed by sha256, so rewriting it is always byte-identical.
    res = await _http().post(
        f"/object/{BUCKET}/{path}",
        content=data,
        headers={"Content-Type": "application/json", "x-upsert": "true"},
    )
    res.raise_for_status()


async def get(path: str) -> bytes:
    res = await _http().get(f"/object/{BUCKET}/{path}")
    res.raise_for_status()
    return res.content


async def delete(path: str) -> None:
    res = await _http().delete(f"/object/{BUCKET}/{path}")
    res.raise_for_status()
