"""Codex rollout JSONL → per-turn session model (8_session-ingestion.md).

Record shapes (one JSON object per line, verified against real rollouts):
`session_meta` (cwd, session id), `turn_context` (model), `event_msg` (typed
UI events) and `response_item` (the model-facing items). Parsing notes:

- `event_msg`/`user_message` is the real typed ask. `response_item` user
  messages also carry injected AGENTS.md/environment preambles, so they only
  seed the llm prompt when no typed ask exists.
- Usage arrives as `event_msg`/`token_count` (one per model request,
  including requests that produced only tool calls), never on messages —
  per-turn sums land on the turn root span.
- Tool calls are generic: any `*_call` payload with a `call_id` opens a
  call and any `*_output` with the same id closes it (`function_call`,
  `custom_tool_call`, `tool_search_call`, …), so new Codex tool types keep
  parsing. `web_search_call` carries no call_id and no output record; it
  emits in place. Calls whose outputs never arrive (truncated logs) emit
  unpaired at the end.
- `reasoning` items carry human-readable `summary` blocks (the content
  itself is encrypted); summaries attach to the next assistant message as
  `gen_ai.reasoning`.
"""

from __future__ import annotations

import json

from app.importers.sessions.turns import SessionBuilder, llm_attrs, to_nanos, tool_attrs

RECORD_TYPES = {"session_meta", "turn_context", "event_msg", "response_item"}


def matches(records: list[dict]) -> bool:
    return any(r.get("type") in RECORD_TYPES for r in records)


def parse(records: list[dict], session_id: str) -> SessionBuilder:
    builder = SessionBuilder("codex", session_id)
    builder.provider = "openai"
    last_user: str | None = None
    reasoning: list[str] = []
    open_tools: dict[str, dict] = {}
    for record in records:
        rtype, payload = record.get("type"), record.get("payload") or {}
        ts = to_nanos(record["timestamp"]) if record.get("timestamp") else None
        if rtype == "session_meta":
            builder.cwd = payload.get("cwd")
            builder.session_id = payload.get("id") or builder.session_id
        elif rtype == "turn_context":
            builder.model = payload.get("model") or builder.model
        elif rtype == "event_msg":
            etype = payload.get("type")
            if etype == "user_message":
                builder.user_message(payload.get("message") or "")
                last_user = payload.get("message") or last_user
                reasoning = []  # never carry reasoning across turns
            elif etype == "token_count":
                usage = (payload.get("info") or {}).get("last_token_usage") or {}
                builder.add_turn_usage(
                    usage.get("input_tokens"),
                    usage.get("output_tokens"),
                    usage.get("total_tokens"),
                )
        elif rtype == "response_item":
            ptype = payload.get("type") or ""
            if ptype == "message":
                text = "\n".join(
                    c.get("text", "") for c in payload.get("content") or [] if isinstance(c, dict)
                ).strip()
                if payload.get("role") == "user":
                    # Preamble-laden echo of the ask; the typed ask wins.
                    last_user = last_user or text
                elif payload.get("role") == "assistant" and text:
                    attrs = llm_attrs(builder, last_user, text, None)
                    if reasoning:
                        attrs["gen_ai.reasoning"] = "\n\n".join(reasoning)
                        reasoning = []
                    builder.add("llm", "assistant turn", attrs, ts)
                    last_user = None
            elif ptype == "reasoning":
                reasoning.extend(
                    s["text"]
                    for s in payload.get("summary") or []
                    if isinstance(s, dict) and s.get("text")
                )
            elif ptype == "web_search_call":
                builder.add(
                    "tool", "web_search", tool_attrs("web_search", payload.get("action"), None), ts
                )
            elif ptype.endswith("_call") and payload.get("call_id"):
                name = payload.get("name") or ptype.removesuffix("_call")
                open_tools[payload["call_id"]] = {
                    "name": name,
                    "args": payload.get("arguments") or payload.get("input"),
                    "ts": ts,
                }
            elif ptype.endswith("_output") and payload.get("call_id"):
                call = open_tools.pop(payload["call_id"], None)
                output = payload.get("output", payload.get("tools"))
                if not isinstance(output, str):
                    output = json.dumps(output)
                name = call["name"] if call else ptype.removesuffix("_output")
                builder.add(
                    "tool",
                    name,
                    tool_attrs(name, call["args"] if call else None, output),
                    call["ts"] if call else ts,
                    end=ts,
                )
    # Calls whose outputs never arrived (truncated logs) emit unpaired.
    for call in open_tools.values():
        builder.add("tool", call["name"], tool_attrs(call["name"], call["args"], None), call["ts"])
    return builder
