"""Anthropic-block JSONL → per-turn session model (8_session-ingestion.md).

Claude Code and Cursor transcripts share this shape: records typed
`user`/`assistant` carrying a `message` whose content is a string or a list
of typed blocks (`text`, `thinking`, `tool_use`, `tool_result`). Differences
the parser absorbs (shapes verified against real logs):

- Claude Code splits one assistant API response across several records that
  share `message.id` (one block each, identical `usage`); responses group by
  id so each API call becomes exactly one llm event — including tool-only
  responses, which still carry usage. Cursor records have no message ids
  (or timestamps, usage, model ids) and group per record.
- Claude Code interleaves sub-agent ("sidechain") transcripts and meta
  records (`isMeta`, compaction summaries) into the session file; both are
  skipped — they are not part of the main conversation.
- Anthropic usage splits input across `input_tokens` +
  `cache_read_input_tokens` + `cache_creation_input_tokens`; all three count
  toward the call's input.
- `thinking` blocks attach to their response's llm event as
  `gen_ai.reasoning`.
- Cursor `tool_use` blocks carry no ids and no `tool_result` ever arrives;
  they emit in place. Id'd calls pair with their `tool_result`.

Agent name is `claude` when any record carries a timestamp, else `cursor`.
"""

from __future__ import annotations

from typing import Any

from app.importers.sessions.turns import SessionBuilder, llm_attrs, to_nanos, tool_attrs

# Records that are not main-line conversation: sub-agent transcripts and
# meta/compaction records Claude Code writes into the same session file.
_SKIP_FLAGS = ("isSidechain", "isMeta", "isCompactSummary", "isVisibleInTranscriptOnly")


def matches(records: list[dict]) -> bool:
    return any(
        (r.get("type") or r.get("role")) in ("user", "assistant")
        and isinstance(r.get("message"), dict)
        for r in records
    )


def _block_text(content: Any) -> str:
    """Flatten a content value (str or block list) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def _usage(usage: Any) -> dict | None:
    """Anthropic usage → llm_attrs shape; cached input still counts as input."""
    if not isinstance(usage, dict):
        return None
    input_tokens = sum(
        usage.get(key) or 0
        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )
    return {"input_tokens": input_tokens or None, "output_tokens": usage.get("output_tokens")}


def parse(records: list[dict], session_id: str) -> SessionBuilder:
    agent = "claude" if any(r.get("timestamp") for r in records) else "cursor"
    builder = SessionBuilder(agent, session_id)
    if agent == "claude":
        builder.provider = "anthropic"
    last_user: str | None = None
    open_tools: dict[str, dict] = {}
    response: dict | None = None  # assistant API response being accumulated

    def flush_response() -> None:
        """Emit the accumulated response as one llm event. Tool-only
        responses still emit (their usage is real LLM spend); contentless
        usage-less groups (Cursor tool-only records) emit nothing."""
        nonlocal response, last_user
        if response is None:
            return
        text = "\n".join(response["texts"]).strip()
        if text or response["usage"] or response["thinking"]:
            attrs = llm_attrs(builder, last_user, text, response["usage"])
            if response["thinking"]:
                attrs["gen_ai.reasoning"] = "\n\n".join(response["thinking"])
            builder.add("llm", "assistant turn", attrs, response["ts"])
            last_user = None
        response = None

    for record in records:
        if any(record.get(flag) for flag in _SKIP_FLAGS):
            continue
        role = record.get("type") or record.get("role")
        message = record.get("message") or {}
        ts = to_nanos(record["timestamp"]) if record.get("timestamp") else None
        if role == "user":
            flush_response()
            content = message.get("content")
            text = _block_text(content)
            if text:
                last_user = text
                builder.user_message(text)
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    call = open_tools.pop(block.get("tool_use_id", ""), None)
                    if call is None:
                        continue
                    builder.add(
                        "tool",
                        call["name"],
                        tool_attrs(call["name"], call["args"], _block_text(block.get("content"))),
                        call["ts"],
                        end=ts,
                        error="tool error" if block.get("is_error") else None,
                    )
        elif role == "assistant":
            builder.model = message.get("model") or builder.model
            message_id = message.get("id")
            if response is not None and (message_id is None or response["id"] != message_id):
                flush_response()
            if response is None:
                response = {"id": message_id, "ts": ts, "texts": [], "thinking": [], "usage": None}
            response["usage"] = response["usage"] or _usage(message.get("usage"))
            text = _block_text(message.get("content"))
            if text:
                response["texts"].append(text)
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    if block.get("thinking"):
                        response["thinking"].append(block["thinking"])
            if message_id is None:
                # No id (Cursor): the record is the whole response. Flush
                # before its tool calls so the message precedes them in
                # event order — synthesized clocks follow that order.
                flush_response()
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = block.get("name") or "tool"
                    if block.get("id"):
                        open_tools[block["id"]] = {
                            "name": name,
                            "args": block.get("input"),
                            "ts": ts,
                        }
                    else:
                        # No id means no tool_result will ever pair back
                        # (the Cursor shape) — emit the call in place.
                        builder.add("tool", name, tool_attrs(name, block.get("input"), None), ts)
    flush_response()
    # Id'd calls whose results never arrived (truncated logs) emit unpaired.
    for call in open_tools.values():
        builder.add("tool", call["name"], tool_attrs(call["name"], call["args"], None), call["ts"])
    return builder
