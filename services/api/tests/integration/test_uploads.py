"""Upload validation matrix, ownership, and byte-identical raw download."""

import asyncio
import uuid

import httpx
import pytest

from tests.integration.conftest import API_URL, otlp_payload, signup_token

pytestmark = pytest.mark.asyncio


async def upload_file(
    api: httpx.AsyncClient, data: bytes, filename: str = "trace.json", **kwargs
) -> httpx.Response:
    return await api.post("/v1/uploads", files={"file": (filename, data)}, **kwargs)


async def wait_terminal(api: httpx.AsyncClient, upload_id: str, timeout: float = 30.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        res = await api.get(f"/v1/uploads/{upload_id}")
        res.raise_for_status()
        body = res.json()
        if body["status"] in ("complete", "failed"):
            return body
        await asyncio.sleep(0.5)
    raise AssertionError(f"upload {upload_id} never reached a terminal status")


async def test_upload_roundtrip(api: httpx.AsyncClient) -> None:
    data = otlp_payload(uuid.uuid4().hex)

    created = await upload_file(api, data, filename="roundtrip.json")
    assert created.status_code == 201
    body = created.json()
    upload_id = body["upload_id"]
    assert body["status"] == "received"

    status = await wait_terminal(api, upload_id)
    assert status["status"] == "complete"
    assert status["error_message"] is None

    listed = (await api.get("/v1/uploads")).json()
    assert any(u["upload_id"] == upload_id for u in listed["uploads"])

    download = await api.get(f"/v1/uploads/{upload_id}/download")
    assert download.status_code == 200
    assert download.content == data
    assert "roundtrip.json" in download.headers["content-disposition"]


async def test_duplicate_rejected(api: httpx.AsyncClient) -> None:
    data = otlp_payload(uuid.uuid4().hex)
    first = await upload_file(api, data)
    assert first.status_code == 201

    second = await upload_file(api, data)
    assert second.status_code == 409
    error = second.json()["error"]
    assert error["code"] == "duplicate_upload"
    assert error["details"]["upload_id"] == first.json()["upload_id"]


async def test_unparseable_bytes_rejected(api: httpx.AsyncClient) -> None:
    # A6 amendment: non-JSON bytes are just one more undetectable format.
    res = await upload_file(api, b"this is not json {")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "unsupported_format"


async def test_unsupported_format_rejected(api: httpx.AsyncClient) -> None:
    res = await upload_file(api, b'{"not_otlp": true}')
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "unsupported_format"


async def test_extra_parts_rejected(api: httpx.AsyncClient) -> None:
    res = await api.post(
        "/v1/uploads",
        files={"file": ("a.json", otlp_payload()), "other": ("b.json", b"{}")},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "invalid_request"


async def test_file_too_large_rejected(api: httpx.AsyncClient) -> None:
    res = await upload_file(api, b"x" * (25 * 1024 * 1024 + 1))
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "file_too_large"


async def test_uploads_are_owner_scoped(api: httpx.AsyncClient) -> None:
    data = otlp_payload(uuid.uuid4().hex)
    created = await upload_file(api, data)
    upload_id = created.json()["upload_id"]

    other_token = await signup_token()
    async with httpx.AsyncClient(
        base_url=api.base_url, headers={"Authorization": f"Bearer {other_token}"}
    ) as other:
        for path in (f"/v1/uploads/{upload_id}", f"/v1/uploads/{upload_id}/download"):
            res = await other.get(path)
            assert res.status_code == 404, path
        listed = (await other.get("/v1/uploads")).json()
        assert all(u["upload_id"] != upload_id for u in listed["uploads"])


async def test_unknown_upload_ids_404(api: httpx.AsyncClient) -> None:
    # Random UUID and non-UUID text both 404 (the latter exercises the
    # DataError branch instead of leaking a 500).
    for upload_id in (str(uuid.uuid4()), "not-a-uuid"):
        for path in (f"/v1/uploads/{upload_id}", f"/v1/uploads/{upload_id}/download"):
            res = await api.get(path)
            assert res.status_code == 404, path
            assert res.json()["error"]["code"] == "not_found"


async def test_unauthenticated_rejected() -> None:
    async with httpx.AsyncClient(base_url=API_URL) as anon:
        res = await anon.get("/v1/uploads")
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "unauthorized"
