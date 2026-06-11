"""The observability seam (app/obs.py): structured records carry the
correlation id and bound context, and the id propagates HTTP request →
task label → worker execution."""

import contextvars
import json
import logging

import httpx
import pytest
from fastapi import FastAPI
from taskiq.message import TaskiqMessage

from app import obs
from app.middleware.correlation import CorrelationIdMiddleware
from app.worker.correlation import CorrelationMiddleware


def _make_record(message: str = "hello") -> logging.LogRecord:
    return logging.LogRecord("test.logger", logging.INFO, __file__, 1, message, None, None)


def test_json_formatter_includes_correlation_and_bound_context() -> None:
    def scenario() -> dict:
        obs.correlation_id_var.set("cid-123")
        obs.bind(trace_id="t-1", upload_id="u-1")
        record = _make_record("analyzed")
        record.duration_ms = 42
        return json.loads(obs.JsonFormatter().format(record))

    payload = contextvars.copy_context().run(scenario)
    assert payload["message"] == "analyzed"
    assert payload["correlation_id"] == "cid-123"
    assert payload["trace_id"] == "t-1"
    assert payload["upload_id"] == "u-1"
    assert payload["duration_ms"] == 42
    assert payload["level"] == "INFO"


def test_bind_does_not_leak_across_contexts() -> None:
    contextvars.copy_context().run(lambda: obs.bind(trace_id="t-leak"))
    payload = obs.record_payload(_make_record())
    assert "trace_id" not in payload


def test_memory_handler_keeps_and_filters_records() -> None:
    handler = obs.MemoryLogHandler(capacity=2)

    def scenario() -> None:
        obs.correlation_id_var.set("cid-mem")
        handler.emit(_make_record("first"))
        handler.emit(_make_record("second"))
        handler.emit(_make_record("third"))  # evicts "first"

    contextvars.copy_context().run(scenario)
    assert [r["message"] for r in handler.records] == ["second", "third"]
    assert len(handler.for_correlation("cid-mem")) == 2
    assert handler.for_correlation("other") == []


def _message(labels: dict[str, str]) -> TaskiqMessage:
    return TaskiqMessage(task_id="1", task_name="analyze_trace", labels=labels, args=[], kwargs={})


def test_taskiq_middleware_stamps_and_restores_correlation_id() -> None:
    mw = CorrelationMiddleware()

    def send_side() -> str:
        obs.correlation_id_var.set("cid-req")
        return mw.pre_send(_message({})).labels["correlation_id"]

    label = contextvars.copy_context().run(send_side)
    assert label == "cid-req"

    def worker_side() -> tuple[str | None, dict]:
        mw.pre_execute(_message({"correlation_id": label}))
        return obs.get_correlation_id(), obs.record_payload(_make_record())

    cid, payload = contextvars.copy_context().run(worker_side)
    assert cid == "cid-req"
    assert payload["correlation_id"] == "cid-req"
    assert payload["task"] == "analyze_trace"


def test_taskiq_middleware_preserves_existing_label_and_mints_when_absent() -> None:
    mw = CorrelationMiddleware()
    kept = mw.pre_send(_message({"correlation_id": "cid-retry"}))
    assert kept.labels["correlation_id"] == "cid-retry"

    def no_context() -> str:
        return mw.pre_send(_message({})).labels["correlation_id"]

    minted = contextvars.copy_context().run(no_context)
    assert minted  # sweep/CLI kicks get a fresh id


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/ping")
    async def ping() -> dict:
        return {"correlation_id": obs.get_correlation_id()}

    return app


async def test_http_middleware_mints_and_echoes_id(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/ping")
    cid = res.headers["x-correlation-id"]
    assert cid
    assert res.json() == {"correlation_id": cid}


async def test_http_middleware_honors_safe_supplied_id(app: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/ping", headers={"X-Correlation-ID": "my-id_1"})
        assert res.headers["x-correlation-id"] == "my-id_1"
        # Unsafe values (they land in logs) are replaced, not echoed.
        res = await client.get("/ping", headers={"X-Correlation-ID": "bad id;drop"})
        assert res.headers["x-correlation-id"] != "bad id;drop"
