#!/usr/bin/env python3
"""Convert your local coding-agent sessions (Codex, Claude Code, Cursor)
into OTLP JSON files the uploader accepts.

Reads the session logs each tool already writes on this machine, through
symlinks the script maintains under git-ignored devdata/sessions-src/:

    devdata/sessions-src/codex   → ~/.codex/sessions/        (rollout-*.jsonl)
    devdata/sessions-src/claude  → ~/.claude/projects/       (<session>.jsonl)
    devdata/sessions-src/cursor  → ~/.cursor/projects/       (agent-transcripts/*.jsonl)

The links always track the live directories, so every run converts the
current sessions; repoint a link (or replace it with a real directory) to
read from somewhere else. Output is one OTLP file per session into
git-ignored devdata/agent-sessions/
(real personal content never enters the repo). Each session becomes one
trace: a root invoke_agent span, one llm span per assistant turn (prompt +
completion via the generic input/output.value convention), and one tool span
per tool call (arguments + result). Long text fields are capped so files
stay well under the upload limit; subagent transcripts are skipped.

Cursor transcripts carry no timestamps — they are synthesized from the file
mtime at one second per event and marked `converted.synthesized_timestamps`.

Usage:
    tools/my_sessions.sh [--source codex,claude,cursor] [--hours 24] \
        [--count 10] [--min-spans 5] [--cap-chars 4000]

Only sessions touched in the last --hours are considered (default 24;
0 disables the window and converts from all history).
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _otlp import attr_list, to_nanos

OUT_DIR = Path(__file__).parents[1] / "devdata" / "agent-sessions"
SRC_DIR = Path(__file__).parents[1] / "devdata" / "sessions-src"

HOME_DIRS = {
    "codex": Path.home() / ".codex" / "sessions",
    "claude": Path.home() / ".claude" / "projects",
    "cursor": Path.home() / ".cursor" / "projects",
}

NANO = 1_000_000_000


def cap(text: str, cap_chars: int) -> str:
    if len(text) <= cap_chars:
        return text
    return text[:cap_chars] + f"… [truncated, {len(text)} chars total]"


def block_text(content, cap_chars: int) -> str:
    """Flatten an Anthropic-style content value (str or block list) to text."""
    if isinstance(content, str):
        return cap(content, cap_chars)
    if isinstance(content, list):
        parts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return cap("\n".join(p for p in parts if p), cap_chars)
    return ""


def user_query(text: str) -> str:
    """Cursor/system harnesses wrap the real ask in <user_query> tags."""
    if "<user_query>" in text:
        text = text.split("<user_query>", 1)[1].split("</user_query>", 1)[0]
    return " ".join(text.split())


class Session:
    """Generic intermediate: ordered llm/tool events → one OTLP trace."""

    def __init__(self, source: str, session_id: str, mtime_ns: int) -> None:
        self.source = source
        self.session_id = session_id
        self.mtime_ns = mtime_ns
        self.events: list[dict] = []  # {kind, name, ts_ns?, end_ns?, attrs, error}
        self.first_user: str | None = None
        self.cwd: str | None = None
        self.model: str | None = None
        self.provider: str | None = None

    def add(self, kind: str, name: str, attrs: dict, ts_ns: int | None = None,
            end_ns: int | None = None, error: str | None = None) -> None:
        self.events.append(
            {"kind": kind, "name": name, "attrs": attrs, "ts": ts_ns, "end": end_ns, "error": error}
        )

    def saw_user(self, text: str) -> None:
        if text and self.first_user is None:
            self.first_user = user_query(text)

    def to_otlp(self) -> dict | None:
        if not self.events:
            return None
        # Fill missing timestamps: walk from the last known one (or mtime) at
        # one second per event, so ordering survives without real clocks.
        synthesized = False
        base = next((e["ts"] for e in self.events if e["ts"]), self.mtime_ns - len(self.events) * NANO)
        for event in self.events:
            if event["ts"] is None:
                synthesized = True
                event["ts"] = base + NANO
            base = event["ts"]
        for i, event in enumerate(self.events):
            if event["end"] is None:
                nxt = self.events[i + 1]["ts"] if i + 1 < len(self.events) else None
                event["end"] = max(event["ts"] + NANO // 1000, nxt or event["ts"] + NANO)

        key = f"{self.source}:{self.session_id}"
        trace_id = hashlib.sha256(key.encode()).hexdigest()[:32]
        root_id = hashlib.sha256(f"root:{key}".encode()).hexdigest()[:16]
        title = self.first_user or f"{self.source} session"
        root = {
            "traceId": trace_id,
            "spanId": root_id,
            "name": f"{self.source}: {title}"[:120],
            "kind": 1,
            "startTimeUnixNano": str(min(e["ts"] for e in self.events)),
            "endTimeUnixNano": str(max(e["end"] for e in self.events)),
            "attributes": attr_list(
                {
                    "gen_ai.operation.name": "invoke_agent",
                    "gen_ai.agent.name": self.source,
                    "session.id": self.session_id,
                    "workspace.cwd": self.cwd,
                    "converted.synthesized_root": True,
                    "converted.synthesized_timestamps": synthesized or None,
                }
            ),
            "status": {"code": 1},
        }
        spans = [root]
        for i, event in enumerate(self.events):
            spans.append(
                {
                    "traceId": trace_id,
                    "spanId": hashlib.sha256(f"{key}:{i}".encode()).hexdigest()[:16],
                    "parentSpanId": root_id,
                    "name": event["name"],
                    "kind": 3,
                    "startTimeUnixNano": str(event["ts"]),
                    "endTimeUnixNano": str(event["end"]),
                    "attributes": attr_list(event["attrs"]),
                    "status": {"code": 2, "message": event["error"]} if event["error"] else {"code": 1},
                }
            )
        return {
            "resourceSpans": [
                {
                    "resource": {"attributes": attr_list({"service.name": f"{self.source}-cli"})},
                    "scopeSpans": [{"scope": {"name": "agent_sessions.converter"}, "spans": spans}],
                }
            ]
        }


def llm_attrs(session: Session, prompt: str | None, completion: str,
              usage: dict | None, cap_chars: int) -> dict:
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": session.provider,
        "gen_ai.request.model": session.model,
        "input.value": cap(prompt, cap_chars) if prompt else None,
        "output.value": cap(completion, cap_chars) if completion else None,
    }
    if usage:
        attrs["gen_ai.usage.input_tokens"] = usage.get("input_tokens")
        attrs["gen_ai.usage.output_tokens"] = usage.get("output_tokens")
    return attrs


def tool_attrs(name: str, arguments, result, cap_chars: int) -> dict:
    return {
        "gen_ai.operation.name": "execute_tool",
        "gen_ai.tool.name": name,
        "gen_ai.tool.call.arguments": cap(
            arguments if isinstance(arguments, str) else json.dumps(arguments), cap_chars
        ),
        "gen_ai.tool.call.result": cap(result, cap_chars) if result else None,
    }


# --- per-source parsers -----------------------------------------------------


def parse_codex(path: Path, cap_chars: int) -> Session | None:
    session = Session("codex", path.stem.removeprefix("rollout-"), path.stat().st_mtime_ns)
    session.provider = "openai"
    last_user: str | None = None
    open_tools: dict[str, dict] = {}
    for line in path.open():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        rtype, payload = record.get("type"), record.get("payload") or {}
        ts = to_nanos(record["timestamp"]) if record.get("timestamp") else None
        if rtype == "session_meta":
            if "subagent" in json.dumps(payload.get("source") or {}):
                return None  # top-level sessions only
            session.cwd = payload.get("cwd")
        elif rtype == "turn_context":
            session.model = payload.get("model") or session.model
        elif rtype == "event_msg" and payload.get("type") == "user_message":
            # The real typed ask; response_item user messages also carry
            # injected AGENTS.md/environment preambles, useless as a title.
            session.saw_user(payload.get("message") or "")
        elif rtype == "response_item":
            ptype = payload.get("type")
            if ptype == "message":
                text = "\n".join(
                    c.get("text", "") for c in payload.get("content") or [] if isinstance(c, dict)
                ).strip()
                if payload.get("role") == "user":
                    last_user = text
                elif payload.get("role") == "assistant" and text:
                    session.add(
                        "llm", "assistant turn",
                        llm_attrs(session, last_user, text, None, cap_chars), ts,
                    )
                    last_user = None
            elif ptype in ("function_call", "custom_tool_call"):
                name = payload.get("name") or "tool"
                open_tools[payload.get("call_id", "")] = {
                    "name": name, "args": payload.get("arguments") or payload.get("input"), "ts": ts,
                }
            elif ptype in ("function_call_output", "custom_tool_call_output"):
                call = open_tools.pop(payload.get("call_id", ""), None)
                output = payload.get("output")
                if not isinstance(output, str):
                    output = json.dumps(output)
                name = call["name"] if call else "tool"
                session.add(
                    "tool", name, tool_attrs(name, call["args"] if call else None, output, cap_chars),
                    call["ts"] if call else ts, end_ns=ts,
                )
            elif ptype == "web_search_call":
                session.add(
                    "tool", "web_search",
                    tool_attrs("web_search", payload.get("action"), None, cap_chars), ts,
                )
    return session


def parse_anthropic_style(path: Path, source: str, cap_chars: int) -> Session | None:
    """Claude Code and Cursor transcripts share the Anthropic block shape;
    Cursor just lacks timestamps, usage, and model ids."""
    session = Session(source, path.stem, path.stat().st_mtime_ns)
    if source == "claude":
        session.provider = "anthropic"
    last_user: str | None = None
    open_tools: dict[str, dict] = {}
    for line in path.open():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = record.get("type") or record.get("role")
        message = record.get("message") or {}
        ts = to_nanos(record["timestamp"]) if record.get("timestamp") else None
        if role == "user":
            content = message.get("content")
            text = block_text(content, cap_chars)
            if text:
                last_user = text
                session.saw_user(text)
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    call = open_tools.pop(block.get("tool_use_id", ""), None)
                    if call is None:
                        continue
                    session.add(
                        "tool", call["name"],
                        tool_attrs(call["name"], call["args"],
                                   block_text(block.get("content"), cap_chars), cap_chars),
                        call["ts"], end_ns=ts,
                        error="tool error" if block.get("is_error") else None,
                    )
        elif role == "assistant":
            session.model = message.get("model") or session.model
            text = block_text(message.get("content"), cap_chars)
            if text:
                session.add(
                    "llm", "assistant turn",
                    llm_attrs(session, last_user, text, message.get("usage"), cap_chars), ts,
                )
                last_user = None
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    open_tools[block.get("id") or f"tool-{len(open_tools)}"] = {
                        "name": block.get("name") or "tool", "args": block.get("input"), "ts": ts,
                    }
    # Cursor tool_use blocks often have no ids/results; emit them unpaired.
    for call in open_tools.values():
        session.add("tool", call["name"], tool_attrs(call["name"], call["args"], None, cap_chars),
                    call["ts"])
    return session


def link_sources(sources: set[str]) -> dict[str, Path]:
    """Maintain devdata/sessions-src/<source> symlinks to the live session
    dirs. A link the user replaced with a real dir (or repointed) is kept."""
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    roots: dict[str, Path] = {}
    for source in sources & HOME_DIRS.keys():
        link = SRC_DIR / source
        if not link.is_symlink() and not link.exists():
            target = HOME_DIRS[source]
            if not target.is_dir():
                continue
            link.symlink_to(target)
        if link.is_symlink() and not link.is_dir():  # broken link: retarget
            link.unlink()
            if not HOME_DIRS[source].is_dir():
                continue
            link.symlink_to(HOME_DIRS[source])
        if link.is_dir():
            roots[source] = link
    return roots


def discover(sources: set[str], hours: float) -> list[tuple[str, Path]]:
    roots = link_sources(sources)
    found: list[tuple[str, Path]] = []
    if "codex" in roots:
        found += [("codex", p) for p in roots["codex"].rglob("rollout-*.jsonl")]
    if "claude" in roots:
        found += [
            ("claude", p)
            for p in roots["claude"].glob("*/*.jsonl")
            if "subagents" not in p.parts
        ]
    if "cursor" in roots:
        found += [
            ("cursor", p)
            for p in roots["cursor"].glob("*/agent-transcripts/*/*.jsonl")
            if "subagents" not in p.parts
        ]
    cutoff = time.time() - hours * 3600 if hours else 0
    found = [(s, p) for s, p in found if p.stat().st_mtime >= cutoff]
    return sorted(found, key=lambda sp: sp[1].stat().st_mtime, reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="codex,claude,cursor",
                        help="comma-separated: codex, claude, cursor")
    parser.add_argument("--hours", type=float, default=24,
                        help="only consider sessions touched in the last N hours (0 = all history)")
    parser.add_argument("--count", type=int, default=10, help="most-recent sessions to convert")
    parser.add_argument("--min-spans", type=int, default=5, help="skip sessions smaller than this")
    parser.add_argument("--cap-chars", type=int, default=4000,
                        help="per-field text cap (keeps files small)")
    args = parser.parse_args()
    sources = {s.strip() for s in args.source.split(",")}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for source, path in discover(sources, args.hours):
        if written >= args.count:
            break
        try:
            session = (
                parse_codex(path, args.cap_chars)
                if source == "codex"
                else parse_anthropic_style(path, source, args.cap_chars)
            )
        except (OSError, KeyError, ValueError) as exc:
            print(f"skipping {path.name}: {exc}", file=sys.stderr)
            continue
        if session is None or len(session.events) + 1 < args.min_spans:
            continue
        otlp = session.to_otlp()
        span_count = len(session.events) + 1
        out = OUT_DIR / f"{source}-{session.session_id[:24]}-{span_count}spans.json"
        out.write_text(json.dumps(otlp))
        print(f"wrote {out.relative_to(Path.cwd())} ({span_count} spans, {out.stat().st_size / 1e3:.0f} KB)")
        written += 1
    if written == 0:
        print("no sessions matched (try --hours 0, --min-spans 2, or check the source dirs)",
              file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
