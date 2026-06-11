"""Shared session model: ordered llm/tool events split into per-turn traces,
emitted as an OTLP JSON payload for the one normalize path (8_session-ingestion.md).

A turn is one user message plus all assistant activity until the next user
message. Identity is deterministic — sha256 over (agent, session id, turn
index) — so re-uploads and re-ingests reproduce the same source trace ids.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.importers.errors import PermanentIngestError

NANO = 1_000_000_000


def to_nanos(iso: str) -> int:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * NANO)


def _any_value(value: Any) -> dict:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    if isinstance(value, list):
        return {"arrayValue": {"values": [_any_value(v) for v in value]}}
    return {"stringValue": value if isinstance(value, str) else str(value)}


def _attr_list(attributes: dict) -> list[dict]:
    return [{"key": k, "value": _any_value(v)} for k, v in attributes.items() if v is not None]


def clean_user_text(text: str) -> str:
    """Harnesses wrap the real ask in <user_query> tags; titles want one line."""
    if "<user_query>" in text:
        text = text.split("<user_query>", 1)[1].split("</user_query>", 1)[0]
    return " ".join(text.split())


@dataclass
class Event:
    kind: str  # llm | tool
    name: str
    attrs: dict[str, Any]
    ts: int | None = None  # unix nanos
    end: int | None = None
    error: str | None = None


@dataclass
class Turn:
    title: str | None
    events: list[Event] = field(default_factory=list)
    # Turn-level usage sums (Codex token_count events); rendered on the root
    # span — formats with per-message usage (Claude) put it on llm events.
    usage: dict[str, int] = field(default_factory=dict)


class SessionBuilder:
    """Accumulates parser events into turns; parsers stay format-only."""

    def __init__(self, agent: str, session_id: str) -> None:
        self.agent = agent
        self.session_id = session_id
        self.cwd: str | None = None
        self.provider: str | None = None
        self.model: str | None = None
        self.turns: list[Turn] = []
        self._current: Turn | None = None

    def user_message(self, text: str) -> None:
        title = clean_user_text(text)
        if not title:
            return
        if self._current is None or self._current.events:
            self._flush()
            self._current = Turn(title=title)
        elif not self._current.title:
            self._current.title = title
        # Consecutive user messages with no assistant activity between them
        # stay one turn, titled by the first ask.

    def add(
        self,
        kind: str,
        name: str,
        attrs: dict[str, Any],
        ts: int | None = None,
        end: int | None = None,
        error: str | None = None,
    ) -> None:
        if self._current is None:
            self._current = Turn(title=None)  # leading activity before any ask
        self._current.events.append(Event(kind, name, attrs, ts, end, error))

    def add_turn_usage(self, input_tokens: Any, output_tokens: Any, total_tokens: Any) -> None:
        """Accumulate one model request's usage onto the current turn."""
        if self._current is None:
            self._current = Turn(title=None)
        usage = self._current.usage
        for key, value in (
            ("input_tokens", input_tokens),
            ("output_tokens", output_tokens),
            ("total_tokens", total_tokens),
        ):
            if isinstance(value, int) and not isinstance(value, bool):
                usage[key] = usage.get(key, 0) + value

    def _flush(self) -> None:
        # A turn with no assistant activity (trailing unanswered ask) is not
        # a trace; drop it rather than emit an empty shell.
        if self._current is not None and self._current.events:
            self.turns.append(self._current)
        self._current = None

    def to_otlp(self, *, anchor_ns: int) -> dict:
        """One OTLP payload, one trace per turn.

        `anchor_ns` ends the synthesized-timestamp walk for logs that carry
        no clocks (Cursor); callers pass the upload's created_at so
        re-ingest stays deterministic (8_session-ingestion.md).
        """
        self._flush()
        if not self.turns:
            raise PermanentIngestError(
                f"Detected a {self.agent} session log but found no convertible turns."
            )

        # Fill missing timestamps across the whole session at one second per
        # event, so ordering survives without real timestamps.
        events = [e for turn in self.turns for e in turn.events]
        synthesized = any(e.ts is None for e in events)
        first = next((i for i, e in enumerate(events) if e.ts is not None), None)
        if first is None:
            # Fully clockless logs walk back from the anchor so the last
            # event's synthetic end lands exactly on it — never in the
            # upload's future.
            base = anchor_ns - (len(events) + 1) * NANO
            for event in events:
                event.ts = base + NANO
                base = event.ts
        else:
            # Leading clockless events walk backward from the first real
            # clock; later gaps walk forward from the previous event.
            for i in range(first - 1, -1, -1):
                events[i].ts = events[i + 1].ts - NANO
            for i in range(first + 1, len(events)):
                if events[i].ts is None:
                    events[i].ts = events[i - 1].ts + NANO
        for i, event in enumerate(events):
            if event.end is None:
                nxt = events[i + 1].ts if i + 1 < len(events) else None
                event.end = max(event.ts + NANO // 1000, nxt or event.ts + NANO)

        spans: list[dict] = []
        for turn_index, turn in enumerate(self.turns):
            key = f"{self.agent}:{self.session_id}:{turn_index}"
            trace_id = hashlib.sha256(key.encode()).hexdigest()[:32]
            root_id = hashlib.sha256(f"root:{key}".encode()).hexdigest()[:16]
            title = turn.title or f"{self.agent} session"
            spans.append(
                {
                    "traceId": trace_id,
                    "spanId": root_id,
                    "name": f"{self.agent}: {title}"[:120],
                    "kind": 1,
                    "startTimeUnixNano": str(min(e.ts for e in turn.events)),
                    "endTimeUnixNano": str(max(e.end for e in turn.events)),
                    "attributes": _attr_list(
                        {
                            "gen_ai.operation.name": "invoke_agent",
                            "gen_ai.agent.name": self.agent,
                            "session.id": self.session_id,
                            "turn.index": turn_index,
                            "workspace.cwd": self.cwd,
                            "converted.synthesized_root": True,
                            "converted.synthesized_timestamps": synthesized or None,
                            "gen_ai.usage.input_tokens": turn.usage.get("input_tokens"),
                            "gen_ai.usage.output_tokens": turn.usage.get("output_tokens"),
                            "gen_ai.usage.total_tokens": turn.usage.get("total_tokens"),
                        }
                    ),
                    "status": {"code": 1},
                }
            )
            for i, event in enumerate(turn.events):
                spans.append(
                    {
                        "traceId": trace_id,
                        "spanId": hashlib.sha256(f"{key}:{i}".encode()).hexdigest()[:16],
                        "parentSpanId": root_id,
                        "name": event.name,
                        "kind": 3,
                        "startTimeUnixNano": str(event.ts),
                        "endTimeUnixNano": str(event.end),
                        "attributes": _attr_list(event.attrs),
                        "status": (
                            {"code": 2, "message": event.error} if event.error else {"code": 1}
                        ),
                    }
                )

        return {
            "resourceSpans": [
                {
                    "resource": {"attributes": _attr_list({"service.name": f"{self.agent}-cli"})},
                    "scopeSpans": [{"scope": {"name": "importers.sessions"}, "spans": spans}],
                }
            ]
        }


def llm_attrs(
    builder: SessionBuilder, prompt: str | None, completion: str, usage: dict | None
) -> dict:
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": builder.provider,
        "gen_ai.request.model": builder.model,
        "input.value": prompt or None,
        "output.value": completion or None,
    }
    if usage:
        attrs["gen_ai.usage.input_tokens"] = usage.get("input_tokens")
        attrs["gen_ai.usage.output_tokens"] = usage.get("output_tokens")
    return attrs


def tool_attrs(name: str, arguments: Any, result: str | None) -> dict:
    return {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": name,
        "gen_ai.tool.call.arguments": (
            arguments if isinstance(arguments, str) else json.dumps(arguments)
        ),
        "gen_ai.tool.call.result": result or None,
    }
