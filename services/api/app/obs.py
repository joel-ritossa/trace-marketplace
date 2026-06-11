"""Structured logging with correlation ids — the observability seam.

Every record renders as one JSON line on stdout; locally that's the terminal
or `docker compose logs`, and the same stream is what a shipper (CloudWatch
awslogs driver, Fluent Bit, …) collects unchanged. A dedicated CloudWatch
handler would slot into configure_logging() without touching call sites. A
small in-memory ring buffer additionally keeps the most recent records per
process for tests and debugging, and LOG_FILE adds a JSON-lines file sink —
the compose stack mounts ./logs and points each service at its own file so
logs are readable without docker.

Correlation: the HTTP middleware sets `correlation_id_var` per request, and
the worker correlation middleware carries it into task executions via a
taskiq label — so one id follows an upload from POST /v1/uploads through
ingest → analyze → match, across retries. Domain ids (upload_id, trace_id)
are bound with bind() and attached to every record in that context.

Privacy: this module only shapes records. The no-log rules for prompts, span
attributes, and raw payload bodies (AGENTS.md) hold at the call sites.
"""

import json
import logging
import sys
import time
import uuid
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_context_var: ContextVar[dict[str, Any] | None] = ContextVar("log_context", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


def bind(**fields: Any) -> None:
    """Attach fields (e.g. trace_id=…) to every log record in this context.

    Contextvars are copy-on-task, so binds inside a request or task execution
    never leak into sibling work.
    """
    merged = {**(_context_var.get() or {}), **{k: v for k, v in fields.items() if v is not None}}
    _context_var.set(merged)


@contextmanager
def stage(logger: logging.Logger, name: str) -> Iterator[None]:
    """Log a pipeline stage's completion (or failure) with its duration."""
    started = time.perf_counter()
    try:
        yield
    except BaseException:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.warning(
            "stage %s failed after %dms",
            name,
            elapsed_ms,
            extra={"stage": name, "duration_ms": elapsed_ms},
        )
        raise
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "stage %s done in %dms",
        name,
        elapsed_ms,
        extra={"stage": name, "duration_ms": elapsed_ms},
    )


# Attributes present on every LogRecord; anything else was passed via extra=.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName"}

_exc_formatter = logging.Formatter()


def record_payload(record: logging.LogRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
        "level": record.levelname,
        "logger": record.name,
        "message": record.getMessage(),
    }
    if (cid := correlation_id_var.get()) is not None:
        payload["correlation_id"] = cid
    payload.update(_context_var.get() or {})
    payload.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS})
    if record.exc_info and record.exc_info[0] is not None:
        payload["exception"] = _exc_formatter.formatException(record.exc_info)
    return payload


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(record_payload(record), default=str)


class MemoryLogHandler(logging.Handler):
    """Ring buffer of recent structured records (the in-process sink)."""

    def __init__(self, capacity: int) -> None:
        super().__init__()
        self.records: deque[dict[str, Any]] = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record_payload(record))

    def for_correlation(self, correlation_id: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r.get("correlation_id") == correlation_id]


memory_log = MemoryLogHandler(settings.log_buffer_records)

_configured = False


def configure_logging() -> None:
    """Install the JSON stdout handler + memory buffer on the root logger.

    Idempotent: called from both the API module and the worker broker module,
    whichever imports first wins.
    """
    global _configured
    if _configured:
        return
    _configured = True

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter())
    root.addHandler(stream)
    root.addHandler(memory_log)
    if settings.log_file:
        path = Path(settings.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file = logging.FileHandler(path)
        file.setFormatter(JsonFormatter())
        root.addHandler(file)
