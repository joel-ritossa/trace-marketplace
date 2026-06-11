#!/usr/bin/env python3
"""LiteLLM wrapper recording per-call latency and cost.

Every call appends a record to a shared ledger; `ledger_summary()` rolls it
up per purpose (eval / explain / …) for the run's meta.json.
"""

import json
import os
import threading
import time
from pathlib import Path


def _load_key() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    env = Path(__file__).parents[2] / ".env.local"
    for line in env.read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip().strip('"')
            return
    raise SystemExit("no OPENAI_API_KEY")


_load_key()
import litellm  # noqa: E402 - key must be in env first

litellm.suppress_debug_info = True

LEDGER: list[dict] = []
_LOCK = threading.Lock()


def chat(prompt: str, purpose: str, model: str = "gpt-5-mini", json_mode: bool = False) -> str:
    kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
    t = time.perf_counter()
    r = litellm.completion(model=model, messages=[{"role": "user", "content": prompt}], **kwargs)
    latency = time.perf_counter() - t
    try:
        cost = litellm.completion_cost(r)
    except Exception:  # noqa: BLE001 - unknown model in price map
        cost = None
    with _LOCK:
        LEDGER.append({
            "purpose": purpose, "model": model, "latency_s": round(latency, 3),
            "prompt_tokens": r.usage.prompt_tokens, "completion_tokens": r.usage.completion_tokens,
            "cost_usd": cost,
        })
    return r.choices[0].message.content


def ledger_summary() -> dict:
    out: dict[str, dict] = {}
    for rec in LEDGER:
        s = out.setdefault(rec["purpose"], {"calls": 0, "cost_usd": 0.0, "latency_s": [],
                                            "prompt_tokens": 0, "completion_tokens": 0})
        s["calls"] += 1
        s["cost_usd"] += rec["cost_usd"] or 0.0
        s["latency_s"].append(rec["latency_s"])
        s["prompt_tokens"] += rec["prompt_tokens"]
        s["completion_tokens"] += rec["completion_tokens"]
    for s in out.values():
        lats = sorted(s.pop("latency_s"))
        s["cost_usd"] = round(s["cost_usd"], 4)
        s["latency_p50_s"] = lats[len(lats) // 2]
        s["latency_max_s"] = lats[-1]
    return out


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return json.loads(text)
