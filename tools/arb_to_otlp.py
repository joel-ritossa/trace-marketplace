#!/usr/bin/env python3
"""Convert an AgentRewardBench slice (McGill-NLP/agent-reward-bench, HF) into
OTLP JSON files plus a ground-truth labels sidecar — the B4 validation corpus.

Expert annotations come from the HF datasets-server rows API; full
trajectories are per-task JSON under cleaned/<benchmark>/<agent>/<exp_name>/.
Both are open access (no token). Output goes to devdata/benchmarks/arb/,
which is git-ignored: real benchmark traces stay out of the repo per
AGENTS.md.

Mapping (buildlog stage-2/B4 decision 4): one synthesized invoke_agent root
per trajectory; one chat LLM span per browsergym step — input messages carry
the goal (step 0) or the previous action's result (capped pruned axtree +
URL as a tool_call_response part), output messages carry the agent's
reasoning text plus the action as a tool_call part (browsergym actions are
tool invocations; the embedded-call shape lets loop detection see them);
token usage from step stats. A step's action error is reported by the
*next* step's last_action_error, so errors shift back one span.
Trajectories carry no absolute timestamps; synthetic deterministic ones are
derived from a fixed base so re-runs are byte-identical.

Output layout: OUT_DIR/traces/*.json + OUT_DIR/labels.json — the sidecar
lives outside the traces glob.

The slice is stratified: even across the four benchmarks, balanced across
Successful/Unsuccessful within each. Duplicate-annotator conflicts and the
lone "Unsure" row are excluded.

Usage:
    python3 tools/arb_to_otlp.py [--count 200] [--benchmark workarena] [--seed 0]
"""

import argparse
import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _otlp import attr_list

DATASET = "McGill-NLP/agent-reward-bench"
ROWS_URL = "https://datasets-server.huggingface.co/rows"
RESOLVE_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/main"
ANNOTATION_ROWS = 1408
PAGE_SIZE = 100
OUT_DIR = Path(__file__).parents[1] / "devdata" / "benchmarks" / "arb"

# Deterministic synthetic timeline: trajectories ship no absolute timestamps.
BASE_NANOS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z
STEP_NANOS = 10_000_000_000  # 10s apart
STEP_DURATION_NANOS = 9_000_000_000

OBS_CAP_CHARS = 4000
ERROR_CAP_CHARS = 1000

OUTCOME_BY_LABEL = {"Successful": "success", "Unsuccessful": "failure"}


def _hex_id(seed: str, length: int) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:length]


def fetch_annotations() -> list[dict]:
    rows: list[dict] = []
    for offset in range(0, ANNOTATION_ROWS + PAGE_SIZE, PAGE_SIZE):
        query = urllib.parse.urlencode(
            {
                "dataset": DATASET,
                "config": "annotations",
                "split": "full",
                "offset": offset,
                "length": PAGE_SIZE,
            }
        )
        with urllib.request.urlopen(f"{ROWS_URL}?{query}", timeout=120) as res:
            page = [r["row"] for r in json.load(res)["rows"]]
        if not page:
            break
        rows.extend(page)
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    """One row per trajectory; annotator conflicts on success are excluded."""
    by_key: dict[tuple, list[dict]] = {}
    for row in rows:
        key = (row["benchmark"], row["model_name"], row["exp_name"], row["task_id"])
        by_key.setdefault(key, []).append(row)
    kept = []
    for group in by_key.values():
        labels = {r["trajectory_success"] for r in group}
        if len(labels) == 1 and labels.issubset(OUTCOME_BY_LABEL):
            kept.append(group[0])
    return kept


def stratify(rows: list[dict], count: int, seed: int) -> list[dict]:
    """Even across benchmarks; within each, balanced across outcome labels."""
    rng = random.Random(seed)
    pools: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        pools.setdefault((row["benchmark"], row["trajectory_success"]), []).append(row)
    for pool in pools.values():
        pool.sort(key=lambda r: (r["task_id"], r["exp_name"]))
        rng.shuffle(pool)
    benchmarks = sorted({b for b, _ in pools})
    per_benchmark = -(-count // len(benchmarks))  # ceil
    selected: list[dict] = []
    for benchmark in benchmarks:
        bench_pools = [pools.get((benchmark, label), []) for label in OUTCOME_BY_LABEL]
        taken = 0
        while taken < per_benchmark and any(bench_pools):
            for pool in bench_pools:
                if pool and taken < per_benchmark:
                    selected.append(pool.pop())
                    taken += 1
    return selected[:count]


def fetch_trajectory(row: dict, attempts: int = 3) -> dict | None:
    path = f"cleaned/{row['benchmark']}/{row['model_name']}/{row['exp_name']}/{row['task_id']}.json"
    url = f"{RESOLVE_URL}/{urllib.parse.quote(path)}"
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(url, timeout=120) as res:
                return json.load(res)
        except urllib.error.HTTPError as err:
            print(f"skip {row['task_id']} ({row['model_name']}): HTTP {err.code}", file=sys.stderr)
            return None
        except (urllib.error.URLError, OSError, TimeoutError) as err:
            # CDN hiccups (SSL EOF, resets) are routine on a 200-file pull.
            if attempt + 1 == attempts:
                print(f"skip {row['task_id']} ({row['model_name']}): {err}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def _cap(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[:cap] + "\n…[truncated by converter]"


def _observation(step: dict) -> str:
    parts = [f"URL: {step.get('url') or '(unknown)'}"]
    axtree = step.get("axtree_pruned") or step.get("axtree") or ""
    if axtree:
        parts.append("Page accessibility tree:\n" + _cap(axtree, OBS_CAP_CHARS))
    return "\n".join(parts)


def _parse_action(action: str) -> tuple[str, str] | None:
    """Browsergym action string → (name, raw args), e.g. fill('147', 'x')."""
    action = action.strip()
    open_paren = action.find("(")
    name = action[:open_paren] if open_paren > 0 else ""
    if name.isidentifier() and action.endswith(")"):
        return name, action[open_paren + 1 : -1]
    return None


def _output_parts(step: dict, call_id: str) -> list[dict]:
    reasoning = (step.get("reasoning") or "").strip()
    action = (step.get("action") or "").strip()
    parts: list[dict] = []
    text = reasoning.replace(action, "").strip() if action else reasoning
    if text:
        parts.append({"type": "text", "content": text})
    parsed = _parse_action(action) if action else None
    if parsed:
        name, args = parsed
        parts.append({"type": "tool_call", "id": call_id, "name": name, "arguments": {"raw": args}})
    elif action:
        parts.append({"type": "text", "content": f"Action: {action}"})
    return parts or [{"type": "text", "content": "(no action recorded)"}]


def convert(row: dict, trajectory: dict) -> dict:
    identity = f"arb:{row['exp_name']}:{row['task_id']}"
    trace_id = _hex_id(identity, 32)
    root_span_id = _hex_id(f"root:{identity}", 16)
    steps = trajectory.get("steps") or []
    model = trajectory.get("model") or row["model_name"]
    provider = model.split("/")[0] if "/" in model else None
    goal = (trajectory.get("goal") or "").strip()

    spans = []
    for i, step in enumerate(steps):
        start = BASE_NANOS + i * STEP_NANOS
        if i == 0:
            input_messages = [
                {"role": "user", "parts": [{"type": "text", "content": goal or "(no goal recorded)"}]}
            ]
        else:
            # The page state observed at step i is the result of step i-1's action.
            input_messages = [
                {
                    "role": "tool",
                    "parts": [
                        {
                            "type": "tool_call_response",
                            "id": f"step_{i - 1}",
                            "response": _observation(step),
                        }
                    ],
                }
            ]
        output_messages = [
            {
                "role": "assistant",
                "finish_reason": "stop",
                "parts": _output_parts(step, f"step_{i}"),
            }
        ]
        stats = step.get("stats") or {}
        # Browsergym reports the error of step i's action in step i+1.
        error = (steps[i + 1].get("last_action_error") or "").strip() if i + 1 < len(steps) else ""
        spans.append(
            {
                "traceId": trace_id,
                "spanId": _hex_id(f"step:{identity}:{step.get('num', i)}", 16),
                "parentSpanId": root_span_id,
                "name": f"chat {model}",
                "kind": 3,
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(start + STEP_DURATION_NANOS),
                "attributes": attr_list(
                    {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.provider.name": provider,
                        "gen_ai.request.model": model,
                        "gen_ai.usage.input_tokens": stats.get("input_tokens"),
                        "gen_ai.usage.output_tokens": stats.get("output_tokens"),
                        "gen_ai.input.messages": json.dumps(input_messages),
                        "gen_ai.output.messages": json.dumps(output_messages),
                        "arb.step": step.get("num", i),
                    }
                ),
                "status": (
                    {"code": 2, "message": _cap(error, ERROR_CAP_CHARS)} if error else {"code": 1}
                ),
            }
        )

    root = {
        "traceId": trace_id,
        "spanId": root_span_id,
        "name": f"{row['benchmark']} {row['task_id']}",
        "kind": 1,
        "startTimeUnixNano": str(BASE_NANOS),
        "endTimeUnixNano": str(BASE_NANOS + max(len(steps), 1) * STEP_NANOS),
        "attributes": attr_list(
            {
                "gen_ai.operation.name": "invoke_agent",
                "gen_ai.agent.name": row["model_name"],
                "arb.benchmark": row["benchmark"],
                "arb.task_id": row["task_id"],
                "arb.exp_name": row["exp_name"],
                "arb.synthesized_root": True,
            }
        ),
        "status": {"code": 1},
    }

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": attr_list({"service.name": "agent-reward-bench"})
                },
                "scopeSpans": [{"scope": {"name": "arb.converter"}, "spans": [root, *spans]}],
            }
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=200, help="trajectories to convert")
    parser.add_argument("--benchmark", help="restrict to one benchmark")
    parser.add_argument("--seed", type=int, default=0, help="sampling seed")
    args = parser.parse_args()

    rows = dedupe(fetch_annotations())
    if args.benchmark:
        rows = [r for r in rows if r["benchmark"] == args.benchmark]
    selected = stratify(rows, args.count, args.seed)
    print(f"{len(rows)} clean trajectories; converting {len(selected)}")

    traces_dir = OUT_DIR / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    labels_path = OUT_DIR / "labels.json"
    # Resume-friendly: keep labels for files already on disk, skip re-fetching them.
    labels: dict[str, dict] = json.loads(labels_path.read_text()) if labels_path.exists() else {}
    written = reused = 0
    for row in selected:
        agent_slug = row["model_name"].replace("/", "_")
        path = traces_dir / f"{row['task_id']}-{agent_slug}.json"
        if path.exists():
            reused += 1
            continue
        trajectory = fetch_trajectory(row)
        if trajectory is None:
            continue
        otlp = convert(row, trajectory)
        trace_id = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
        path.write_text(json.dumps(otlp))
        labels[trace_id] = {
            "dataset": "agent-reward-bench",
            "outcome": OUTCOME_BY_LABEL[row["trajectory_success"]],
            "looping": row["trajectory_looping"] == "Yes",
            "side_effect": row["trajectory_side_effect"] == "Yes",
            "benchmark": row["benchmark"],
            "task_id": row["task_id"],
            "agent": row["model_name"],
        }
        labels_path.write_text(json.dumps(labels, indent=2) + "\n")
        written += 1
        if written % 20 == 0:
            print(f"…{written}/{len(selected)}")
    print(
        f"wrote {written} OTLP files (+{reused} already present) + labels.json "
        f"to {OUT_DIR.relative_to(Path.cwd())}"
    )


if __name__ == "__main__":
    main()
