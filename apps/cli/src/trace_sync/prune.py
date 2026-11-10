"""Session-log pruning before upload (5_cli.md).

Agent session logs are mostly bookkeeping the server's session importers
never read (prompt snapshots, API-request records, duplicate tool results,
Codex item echoes). Each record type is reduced to the fields those importers
use; everything else is dropped. Must stay in step with
`services/api/app/importers/sessions/` — a field the importer starts reading
has to be kept here too. Payloads with no recognized session record upload
unchanged.
"""

import json
from typing import Any

_CLAUDE_KEYS = (
    "type",
    "role",
    "message",
    "timestamp",
    "isSidechain",
    "isMeta",
    "isCompactSummary",
    "isVisibleInTranscriptOnly",
    "agentId",
    "origin",
)
_CODEX_EVENTS = ("user_message", "token_count")


def prune_jsonl(data: bytes) -> bytes:
    lines: list[bytes] = []
    recognized = False
    for line in data.splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        kept = _prune(record) if isinstance(record, dict) else None
        if kept:
            recognized = True
            lines.append(json.dumps(kept, ensure_ascii=False, separators=(",", ":")).encode())
    return b"\n".join(lines) + b"\n" if recognized else data


def _prune(record: dict) -> dict | None:
    """Pruned record; {} or None drops it."""
    rtype = record.get("type")
    if (rtype or record.get("role")) in ("user", "assistant") and isinstance(
        record.get("message"), dict
    ):
        return _prune_claude(record)
    payload = record.get("payload")
    if rtype in ("session_meta", "turn_context", "event_msg", "response_item") and isinstance(
        payload, dict
    ):
        return _prune_codex(rtype, payload, record.get("timestamp"))
    return None  # bookkeeping (Claude attachments, API records, Codex compaction, …)


def _prune_claude(record: dict) -> dict:
    kept = {k: record[k] for k in _CLAUDE_KEYS if k in record}
    spawned = record.get("toolUseResult")
    if isinstance(spawned, dict) and "agentId" in spawned:
        kept["toolUseResult"] = {"agentId": spawned["agentId"]}
    content = kept["message"].get("content")
    if isinstance(content, list):
        kept["message"] = {
            **kept["message"],
            "content": [_drop(b, "signature") if _is(b, "thinking") else b for b in content],
        }
    return kept


def _prune_codex(rtype: str, payload: dict, timestamp: Any) -> dict:
    if rtype == "session_meta":
        payload = {k: payload[k] for k in ("id", "cwd") if k in payload}
    elif rtype == "turn_context":
        payload = {k: payload[k] for k in ("model",) if k in payload}
    elif rtype == "event_msg":
        if payload.get("type") not in _CODEX_EVENTS:
            return {}
        if payload["type"] == "token_count":
            usage = (payload.get("info") or {}).get("last_token_usage")
            payload = {"type": "token_count", "info": {"last_token_usage": usage}}
        else:
            payload = {"type": "user_message", "message": payload.get("message")}
    else:
        payload = _drop(payload, "encrypted_content")
    kept: dict = {"type": rtype, "payload": payload}
    if timestamp is not None:
        kept["timestamp"] = timestamp
    return kept


def _is(block: Any, kind: str) -> bool:
    return isinstance(block, dict) and block.get("type") == kind


def _drop(obj: dict, key: str) -> dict:
    return {k: v for k, v in obj.items() if k != key}
