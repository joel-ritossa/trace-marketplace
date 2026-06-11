#!/usr/bin/env python3
"""Shared loaders + the action-token alphabet.

Action tokens reduce a behavior skeleton to a discrete sequence: role-tagged
text markers, tool calls by name, results bucketed by size with error flags.
This is the input for the order-aware methods (n-gram TF-IDF, sequence
alignment) — no natural language survives.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

LAB = Path(__file__).parent
DATA = LAB / "data"
ANOMALY_DATA = LAB.parent / "anomaly-lab" / "data"

DATA.mkdir(exist_ok=True)


def load_key() -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    for name in (".env.local", ".env"):
        env = LAB.parents[1] / name
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            if line.startswith("OPENAI_API_KEY=") and line.split("=", 1)[1].strip():
                key = line.split("=", 1)[1].strip().strip('"')
                os.environ["OPENAI_API_KEY"] = key
                return key
    raise SystemExit("no OPENAI_API_KEY in env, .env.local, or .env")


def load_renderings() -> list[dict]:
    return [json.loads(line) for line in (ANOMALY_DATA / "renderings.jsonl").open()]


def load_skeletons() -> list[dict]:
    return [json.loads(line) for line in (ANOMALY_DATA / "skeletons.jsonl").open()]


def load_ids() -> list[str]:
    return json.loads((ANOMALY_DATA / "ids.json").read_text())


# --- action tokens ----------------------------------------------------------

_CALL_RE = re.compile(r"CALL ([\w.\-]+)\(")
_TEXT_RE = re.compile(r"text\((\d+)ch\)")
_RESULT_RE = re.compile(r"RESULT\((\d+)ch\)( ERRORISH)?")


def _size_bucket(n: int) -> str:
    return "S" if n < 200 else ("M" if n < 2000 else "L")


def line_tokens(line: str) -> list[str]:
    """One skeleton line -> action tokens."""
    out: list[str] = []
    if line.startswith("[finish=length]"):
        return ["FINISH_LEN"]
    if line.startswith("[SPAN ERROR]"):
        return ["SPAN_ERR"]
    if line.startswith("["):  # non-llm span, e.g. "[other] name"
        return ["SPAN:" + line.strip("[]").split("]")[0].split()[0]]
    role, _, rest = line.partition(": ")
    role_tag = {"USER": "U", "ASSISTANT": "A", "SYSTEM": "S", "TOOL": "T"}.get(role, "?")
    for part in rest.split(" | "):
        m = _CALL_RE.match(part)
        if m:
            out.append(f"CALL:{m.group(1)}")
            continue
        m = _RESULT_RE.match(part)
        if m:
            tok = "RES_ERR" if m.group(2) else "RES"
            out.append(f"{tok}_{_size_bucket(int(m.group(1)))}")
            continue
        m = _TEXT_RE.search(part)
        if m:
            out.append(f"{role_tag}:TXT_{_size_bucket(int(m.group(1)))}")
            continue
        out.append(f"{role_tag}:OTHER")
    return out


def skeleton_tokens(skeleton: str) -> list[str]:
    toks: list[str] = []
    for line in skeleton.splitlines():
        if line.strip():
            toks.extend(line_tokens(line))
    return toks


def cap_sequence(toks: list[str], cap: int = 600) -> list[str]:
    """Middle-out truncation; keeps the opening and the ending behavior."""
    if len(toks) <= cap:
        return toks
    half = cap // 2
    return toks[:half] + ["..."] + toks[-half:]


def truncate_text(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    half = budget // 2
    return text[:half] + "\n[…middle elided…]\n" + text[-half:]
