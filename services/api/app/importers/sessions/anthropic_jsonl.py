"""Anthropic-block JSONL → session model (8_session-ingestion.md).

Claude Code and Cursor transcripts share this shape: records typed
`user`/`assistant` carrying a `message` whose content is a string or a list
of typed blocks (`text`, `thinking`, `tool_use`, `tool_result`). Differences
the parser absorbs (shapes verified against real logs):

- Claude Code splits one assistant API response across several records that
  share `message.id` (one block each, identical `usage`); responses group by
  id so each API call becomes exactly one llm event — including tool-only
  responses, which still carry usage. Cursor records have no message ids
  (or timestamps, usage, model ids) and group per record.
- Sub-agent ("sidechain") records that carry an `agentId` (Claude Code
  writes them to `<session>/subagents/`; the CLI uploads them bundled with
  the session) parse as their own event stream and nest under the tool call
  that spawned them, linked by the tool result's `toolUseResult.agentId`.
  Unlinked sidechains (older logs interleave them without an `agentId`) and
  meta records (`isMeta`, compaction summaries) are skipped, except meta
  peer messages and scheduled triggers, which still prompt the model.
- A turn opens when something asks the agent to act: a human ask
  (`turn.origin` `human`) or an outside event (`automated`; see
  `_prompt_origin`). Background work reporting back, interrupt markers and
  local slash commands stay model input but never open or title a turn.
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

import re
from typing import Any

from app.importers.sessions.turns import (
    Event,
    SessionBuilder,
    clean_user_text,
    flatten,
    llm_attrs,
    to_nanos,
    tool_attrs,
)

# Records that are not main-line conversation: sub-agent transcripts and
# meta/compaction records Claude Code writes into the same session file.
_SKIP_FLAGS = ("isSidechain", "isMeta", "isCompactSummary", "isVisibleInTranscriptOnly")
_SUBAGENT_SKIP = tuple(f for f in _SKIP_FLAGS if f != "isSidechain")
# Meta records that still prompt the model and can start a work cycle.
_META_PROMPTS = ("peer", "scheduled")
# Transcript markers and subagent hand-backs: never an ask (side-session
# reports are matched by their event tag, which follows the reminders). Local slash
# commands lead with <command-name>; skill commands (real asks) lead with
# <command-message>.
_PEER_PREFIX = "Another Claude session sent a message:"
_NOT_A_PROMPT = re.compile(
    r"\s*(?:\[Request interrupted by user|<local-command-|<command-name>"
    rf"|{_PEER_PREFIX}\s*<agent-message\b)"
)
_SIDE_REPORT = "<side-sessions-event>"
_SPAWN_TOOLS = ("Agent", "Task")
# A skill or custom-command slash command leads with <command-message>; its
# <command-name> is the skill.
_COMMAND_SKILL = re.compile(r"\s*<command-message>.*?<command-name>/?([^<]+)</command-name>", re.S)
_EVENT_LABELS = {
    "ci-monitor-event": "CI event",
    "cross-session-message": "Session message",
}
_EVENT_TAG = re.compile(rf"</?({'|'.join(_EVENT_LABELS)})\b[^>]*>")


def matches(records: list[dict]) -> bool:
    return any(
        (r.get("type") or r.get("role")) in ("user", "assistant")
        and isinstance(r.get("message"), dict)
        for r in records
    )


def _kind(record: dict) -> str | None:
    """Who produced a user record, as Claude Code tags it (`origin.kind`, or
    `turnOrigin` for scheduled triggers); None when untagged."""
    origin = record.get("origin")
    if isinstance(origin, dict):
        return origin.get("kind", "human")
    return "scheduled" if record.get("turnOrigin") == "scheduled" else None


def _prompt_origin(record: dict, text: str, origin_tagged: bool) -> str | None:
    """`human`, `automated` (an outside event asking the agent to act: CI
    monitor, cross-session messages, scheduled triggers, a
    prompt from the session that started this one), or None for model input
    that asks nothing new: the agent's own background work reporting back
    (task notifications, subagent hand-backs, side-session reports),
    interrupt markers, local slash commands. Logs that carry `origin` tag
    every human ask, so an untagged record there is harness-produced; logs
    without it count every user record as human."""
    kind = _kind(record)
    if kind == "task-notification" or _NOT_A_PROMPT.match(text) or _SIDE_REPORT in text:
        return None
    if kind == "human" or (kind is None and not origin_tagged):
        return "human"
    return "automated"


def _command_skill(text: str) -> str | None:
    match = _COMMAND_SKILL.match(text)
    return match.group(1).strip() if match else None


def _event_ask(text: str) -> str:
    """An outside event read as an ask: its own text, labelled by its tag."""
    text = clean_user_text(text).removeprefix(_PEER_PREFIX).strip()
    tag = _EVENT_TAG.search(text)
    if tag is None:
        return text
    return f"{_EVENT_LABELS[tag.group(1)]}: {_EVENT_TAG.sub(' ', text).strip()}"


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
    groups: dict[str, list[dict]] = {}
    main: list[dict] = []
    for record in records:
        agent_id = record.get("agentId") if record.get("isSidechain") else None
        (groups.setdefault(agent_id, []) if agent_id else main).append(record)

    builder = _parse_stream(main, SessionBuilder(agent, session_id), _SKIP_FLAGS)
    subagents = {
        agent_id: _parse_stream(recs, SessionBuilder(agent, agent_id), _SUBAGENT_SKIP)
        for agent_id, recs in groups.items()
    }
    _nest(builder.events(), subagents)
    return builder


def _nest(events: list[Event], subagents: dict[str, SessionBuilder]) -> None:
    """Attach each subagent's events under its spawning tool call (subagents
    can spawn subagents, so linked streams nest in turn)."""
    for event in flatten(events):
        if event.agent_id in subagents:
            sub = subagents.pop(event.agent_id)
            event.attrs["subagent.id"] = event.agent_id
            event.attrs["subagent.model"] = sub.model or event.attrs.get("subagent.model")
            event.children = sub.events()
            _nest(event.children, subagents)


def _call(name: str, args: Any, ts: int | None, user_skill: str | None) -> dict:
    """An open tool call: its display name and the skill/subagent attributes
    its input already determines (8_session-ingestion.md)."""
    call = {"name": name, "label": name, "args": args, "ts": ts, "attrs": {}}
    args = args if isinstance(args, dict) else {}
    if name == "Skill" and isinstance(args.get("skill"), str):
        skill = args["skill"].lstrip("/")
        call["label"] = f"Skill: {skill}"
        # The model re-invoking the skill the human's slash command already
        # expanded in this turn is the same use; the turn span records it.
        if skill != user_skill:
            call["attrs"] = {"skill.name": skill, "skill.source": "agent"}
    elif name in _SPAWN_TOOLS:
        prompt = args.get("prompt") if isinstance(args.get("prompt"), str) else ""
        description = (args.get("description") or prompt.strip().split("\n", 1)[0]).strip()
        call["label"] = f"Agent: {description}"
        call["attrs"] = {
            "subagent.description": description or None,
            "subagent.type": args.get("subagent_type"),
            "subagent.model": args.get("model"),
        }
    return call


def _tool_event(builder: SessionBuilder, call: dict, result: str | None, **kwargs: Any) -> Event:
    attrs = {**tool_attrs(call["name"], call["args"], result), **call["attrs"]}
    return builder.add("tool", call["label"], attrs, call["ts"], **kwargs)


def _parse_stream(
    records: list[dict], builder: SessionBuilder, skip_flags: tuple[str, ...]
) -> SessionBuilder:
    if builder.agent == "claude":
        builder.provider = "anthropic"
    origin_tagged = any(isinstance(r.get("origin"), dict) for r in records)
    last_user: str | None = None
    open_tools: dict[str, dict] = {}
    user_skill: str | None = None  # skill the current turn's slash command invoked
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
        if any(record.get(flag) for flag in skip_flags) and _kind(record) not in _META_PROMPTS:
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
                origin = _prompt_origin(record, text, origin_tagged)
                if origin == "human":
                    user_skill = _command_skill(text)
                    builder.user_message(text, skill=user_skill)
                elif origin == "automated":
                    user_skill = None
                    builder.user_message(_event_ask(text), origin)
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    call = open_tools.pop(block.get("tool_use_id", ""), None)
                    if call is None:
                        continue
                    event = _tool_event(
                        builder,
                        call,
                        _block_text(block.get("content")),
                        end=ts,
                        error="tool error" if block.get("is_error") else None,
                    )
                    spawned = record.get("toolUseResult")
                    if isinstance(spawned, dict) and isinstance(spawned.get("agentId"), str):
                        event.agent_id = spawned["agentId"]
                        if call["name"] in _SPAWN_TOOLS:
                            event.attrs["subagent.background"] = spawned.get("isAsync") or None
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
                        open_tools[block["id"]] = _call(name, block.get("input"), ts, user_skill)
                    else:
                        # No id means no tool_result will ever pair back
                        # (the Cursor shape) — emit the call in place.
                        builder.add("tool", name, tool_attrs(name, block.get("input"), None), ts)
    flush_response()
    # Id'd calls whose results never arrived (truncated logs) emit unpaired.
    for call in open_tools.values():
        _tool_event(builder, call, None)
    return builder
