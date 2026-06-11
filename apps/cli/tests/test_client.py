"""Per-file outcome mapping over a mocked transport — no live stack."""

import json

import httpx
import pytest

from trace_sync import client as client_mod
from trace_sync.client import FatalError, SyncClient


def make_client(handler) -> SyncClient:
    c = SyncClient("http://test", "tmk_" + "a" * 32)
    c._http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": "Bearer tmk_test"},
    )
    return c


def error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message, "details": {}}}


@pytest.fixture
def trace_file(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text(json.dumps({"resourceSpans": []}))
    return path


def test_upload_complete(trace_file, monkeypatch):
    monkeypatch.setattr(client_mod, "POLL_INTERVAL_SECONDS", 0.0)
    statuses = iter(["processing", "complete"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"upload_id": "u1", "status": "received"})
        return httpx.Response(
            200,
            json={
                "status": next(statuses),
                "trace_ids": ["t1", "t2", "t3"],
                "error_message": None,
            },
        )

    outcome = make_client(handler).upload(trace_file)
    assert outcome.kind == "uploaded"
    assert outcome.detail == "uploaded (complete, 3 traces)"


def test_upload_ingestion_failed(trace_file):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"upload_id": "u1", "status": "received"})
        return httpx.Response(
            200,
            json={"status": "failed", "trace_ids": [], "error_message": "No spans found."},
        )

    outcome = make_client(handler).upload(trace_file)
    assert outcome.kind == "failed"
    assert outcome.detail == "failed: No spans found."  # verbatim error_message


def test_duplicate_is_skipped(trace_file):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json=error_body("duplicate_upload", "Already uploaded."))

    outcome = make_client(handler).upload(trace_file)
    assert outcome.kind == "skipped"
    assert outcome.detail == "already synced"


def test_rejection_is_failed_with_message(trace_file):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json=error_body("invalid_json", "File is not valid JSON."))

    outcome = make_client(handler).upload(trace_file)
    assert outcome.kind == "failed"
    assert outcome.detail == "failed: File is not valid JSON."
    assert not outcome.retryable  # server rejection: never re-offered


def test_429_honors_retry_after_then_succeeds(trace_file, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(client_mod.time, "sleep", sleeps.append)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    429, headers={"Retry-After": "7"}, json=error_body("rate_limited", "Slow down.")
                )
            return httpx.Response(201, json={"upload_id": "u1", "status": "received"})
        return httpx.Response(200, json={"status": "complete", "trace_ids": ["t1"]})

    outcome = make_client(handler).upload(trace_file)
    assert outcome.kind == "uploaded"
    assert 7.0 in sleeps


def test_network_error_is_per_file_failure(trace_file):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    outcome = make_client(handler).upload(trace_file)
    assert outcome.kind == "failed"
    assert outcome.retryable  # transport failure: watch may re-offer


def test_ingestion_failure_is_not_retryable(trace_file):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"upload_id": "u1", "status": "received"})
        return httpx.Response(
            200, json={"status": "failed", "trace_ids": [], "error_message": "No spans found."}
        )

    assert not make_client(handler).upload(trace_file).retryable


def test_preflight_rejects_bad_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json=error_body("unauthorized", "Invalid API key."))

    with pytest.raises(FatalError, match="Invalid API key"):
        make_client(handler).preflight()


def test_preflight_unreachable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(FatalError, match="cannot reach API"):
        make_client(handler).preflight()


def test_preflight_accepts_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json=error_body("not_found", "Upload not found."))

    make_client(handler).preflight()  # no raise
