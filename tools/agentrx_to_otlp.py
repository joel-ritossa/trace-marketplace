#!/usr/bin/env python3
"""Convert the AgentRx benchmark (microsoft/AgentRx, HF — gated, CC-BY-4.0)
into OTLP JSON files plus a ground-truth labels sidecar — the failure-mode
half of the B4 validation corpus.

Two splits join trajectories to annotations: `tau_retail` (29 tool-calling
retail conversations; annotation ids need the `tau_retail_` prefix) and
`magentic_one` (44 annotated multi-agent web/file workflows out of 58
trajectory rows; unannotated trajectories are skipped).

Mapping (buildlog stage-2/B4 decision 5):

- tau_retail: one chat LLM span per assistant turn. System/user/tool
  messages since the previous assistant turn become the span's input
  messages; assistant content that parses as an OpenAI tool-call list
  becomes `tool_call` parts (ids preserved), and tool results pair back as
  `tool_call_response` parts FIFO — the embedded-call shape loop detection
  reads. Trailing non-assistant messages get a final no-response span so
  the trace's last evidence is never dropped.
- magentic_one: one chat LLM span per agent utterance (Orchestrator,
  WebSurfer, …), speaker recorded as `gen_ai.agent.name` and in the span
  name; `human` turns buffer as user input for the next span. No
  structured tool calls exist in this log shape.

Failure categories normalize through an explicit alias table (the dataset
uses freeform variants like "Instruction/Plan Adherence Failure" and
"Intent not supported"); every alias lands 1:1 in the spec taxonomy
(1_analysis.md) and an unknown string is a converter error, never a silent
remap. Ground truth never leaks into the trace: failure annotations exist
only in the sidecar, spans carry no error statuses derived from them.

Requires HF_TOKEN (env or .env.local) with the dataset's conditions
accepted at https://huggingface.co/datasets/microsoft/AgentRx.

Usage:
    python3 tools/agentrx_to_otlp.py [--split tau_retail|magentic_one]
"""

import argparse
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _otlp import attr_list

RESOLVE_URL = "https://huggingface.co/datasets/microsoft/AgentRx/resolve/main"
SPLITS = {
    # split -> (annotations file, trajectories file, annotation id prefix)
    "tau_retail": ("tau_retail.jsonl", "tau_retail_dataset.jsonl", "tau_retail_"),
    "magentic_one": ("magentic_one.jsonl", "magentic_dataset.jsonl", ""),
}
OUT_DIR = Path(__file__).parents[1] / "devdata" / "benchmarks" / "agentrx"

BASE_NANOS = 1_767_225_600_000_000_000  # 2026-01-01T00:00:00Z, ARB convention
STEP_NANOS = 10_000_000_000
STEP_DURATION_NANOS = 9_000_000_000
CONTENT_CAP_CHARS = 4000

# The spec taxonomy (1_analysis.md, mirrored from app FAILURE_MODES — tools/
# scripts stay stdlib-only; load_labels re-validates at agreement time).
# Keys are the dataset's category strings canonicalized by _canon().
CATEGORY_ALIASES = {
    "instruction plan adherence failure": "plan_adherence_failure",
    "instruction adherence failure": "plan_adherence_failure",
    "plan adherence failure": "plan_adherence_failure",
    "invention of new information": "invention_of_information",
    "invention of information": "invention_of_information",
    "invalid invocation": "invalid_invocation",
    "misinterpretation of tool output": "tool_output_misinterpretation",
    "tool output misinterpretation": "tool_output_misinterpretation",
    "intent plan misalignment": "intent_plan_misalignment",
    "underspecified user intent": "underspecified_intent",
    "underspecified intent": "underspecified_intent",
    "intent not supported": "intent_not_supported",
    "guardrails triggered": "guardrails_triggered",
    "system failure": "system_failure",
    "inconclusive": "inconclusive",
}


def _canon(category: str) -> str:
    return " ".join("".join(c if c.isalnum() else " " for c in category.lower()).split())


def normalize_category(category: str) -> str:
    canon = _canon(category)
    if canon not in CATEGORY_ALIASES:
        raise SystemExit(f"unknown AgentRx failure category {category!r} — alias table needs it")
    return CATEGORY_ALIASES[canon]


def _hf_token() -> str:
    token = os.environ.get("HF_TOKEN")
    if not token:
        env_local = Path(__file__).parents[1] / ".env.local"
        if env_local.exists():
            for line in env_local.read_text().splitlines():
                if line.startswith("HF_TOKEN="):
                    token = line.split("=", 1)[1].strip()
    if not token:
        raise SystemExit(
            "HF_TOKEN missing (env or .env.local). AgentRx is gated: accept the "
            "conditions at https://huggingface.co/datasets/microsoft/AgentRx and "
            "use a read token."
        )
    return token


def fetch_jsonl(name: str, token: str) -> list[dict]:
    request = urllib.request.Request(
        f"{RESOLVE_URL}/{name}", headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(request, timeout=120) as res:
        return [json.loads(line) for line in res.read().decode().splitlines() if line.strip()]


def _hex_id(seed: str, length: int) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:length]


def _cap(text: str) -> str:
    """Head+tail cap: the end of long content is often the decisive evidence
    (a traceback's exception line — e.g. ResponsibleAIPolicyViolation at the
    bottom of a 10k-char autogen stack — or a final answer), so capping must
    never drop it."""
    text = text.strip()
    if len(text) <= CONTENT_CAP_CHARS:
        return text
    head, tail = CONTENT_CAP_CHARS - 1000, 1000
    return text[:head] + "\n…[truncated by converter]…\n" + text[-tail:]


def _flat_substeps(trajectory: dict) -> list[tuple[int, str, str]]:
    return [
        (step["index"], sub["role"], sub.get("content") or "")
        for step in trajectory["steps"]
        for sub in step["substeps"]
    ]


def _parse_tool_calls(content: str) -> list[dict] | None:
    """tau assistant turns that are an OpenAI tool-call list → tool_call
    parts; anything else (plain replies to the user) returns None."""
    text = content.strip()
    if not text.startswith("["):
        return None
    try:
        calls = json.loads(text)
    except ValueError:
        return None
    if not isinstance(calls, list) or not all(
        isinstance(c, dict) and c.get("type") == "function" for c in calls
    ):
        return None
    parts = []
    for call in calls:
        function = call.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except ValueError:
            arguments = {"raw": function.get("arguments")}
        parts.append(
            {
                "type": "tool_call",
                "id": call.get("id"),
                "name": function.get("name", "?"),
                "arguments": arguments,
            }
        )
    return parts


def _tau_spans(trajectory: dict) -> list[tuple[str, list[dict], list[dict], int]]:
    """(span name, input messages, output messages, step index) per span."""
    spans = []
    pending_inputs: list[dict] = []
    pending_call_ids: list[str | None] = []
    for index, role, content in _flat_substeps(trajectory):
        if role in ("system", "user"):
            pending_inputs.append(
                {"role": role, "parts": [{"type": "text", "content": _cap(content)}]}
            )
        elif role == "tool":
            call_id = pending_call_ids.pop(0) if pending_call_ids else None
            pending_inputs.append(
                {
                    "role": "tool",
                    "parts": [
                        {"type": "tool_call_response", "id": call_id, "response": _cap(content)}
                    ],
                }
            )
        elif role == "assistant":
            call_parts = _parse_tool_calls(content)
            if call_parts is not None:
                pending_call_ids.extend(part["id"] for part in call_parts)
                output_parts = call_parts
            else:
                output_parts = [{"type": "text", "content": _cap(content)}]
            output = [{"role": "assistant", "finish_reason": "stop", "parts": output_parts}]
            spans.append(("chat assistant", pending_inputs, output, index))
            pending_inputs = []
    if pending_inputs:  # trailing user/tool evidence after the last reply
        output = [
            {
                "role": "assistant",
                "finish_reason": "stop",
                "parts": [{"type": "text", "content": "(no response recorded)"}],
            }
        ]
        spans.append(("chat assistant", pending_inputs, output, len(trajectory["steps"])))
    return spans


def _magentic_spans(trajectory: dict) -> list[tuple[str, list[dict], list[dict], int]]:
    spans = []
    pending_inputs: list[dict] = []
    for index, role, content in _flat_substeps(trajectory):
        if role == "human":
            pending_inputs.append(
                {"role": "user", "parts": [{"type": "text", "content": _cap(content)}]}
            )
            continue
        output = [
            {
                "role": "assistant",
                "finish_reason": "stop",
                "parts": [{"type": "text", "content": _cap(content)}],
            }
        ]
        spans.append((f"chat {role}", pending_inputs, output, index))
        pending_inputs = []
    return spans


def convert(split: str, trajectory: dict) -> dict:
    identity = f"agentrx:{split}:{trajectory['trajectory_id']}"
    trace_id = _hex_id(identity, 32)
    root_span_id = _hex_id(f"root:{identity}", 16)
    builder = _tau_spans if split == "tau_retail" else _magentic_spans
    step_spans = builder(trajectory)

    spans = []
    for i, (name, inputs, outputs, step_index) in enumerate(step_spans):
        start = BASE_NANOS + i * STEP_NANOS
        agent = name.removeprefix("chat ")
        spans.append(
            {
                "traceId": trace_id,
                "spanId": _hex_id(f"step:{identity}:{i}", 16),
                "parentSpanId": root_span_id,
                "name": name,
                "kind": 3,
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(start + STEP_DURATION_NANOS),
                "attributes": attr_list(
                    {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.agent.name": agent if agent != "assistant" else None,
                        "gen_ai.input.messages": json.dumps(inputs) if inputs else None,
                        "gen_ai.output.messages": json.dumps(outputs),
                        "agentrx.step": step_index,
                    }
                ),
                "status": {"code": 1},
            }
        )

    root = {
        "traceId": trace_id,
        "spanId": root_span_id,
        "name": f"{split} {trajectory['trajectory_id']}",
        "kind": 1,
        "startTimeUnixNano": str(BASE_NANOS),
        "endTimeUnixNano": str(BASE_NANOS + max(len(step_spans), 1) * STEP_NANOS),
        "attributes": attr_list(
            {
                "gen_ai.operation.name": "invoke_agent",
                "agentrx.split": split,
                "agentrx.trajectory_id": trajectory["trajectory_id"],
                "agentrx.synthesized_root": True,
            }
        ),
        "status": {"code": 1},
    }

    return {
        "resourceSpans": [
            {
                "resource": {"attributes": attr_list({"service.name": "agentrx"})},
                "scopeSpans": [{"scope": {"name": "agentrx.converter"}, "spans": [root, *spans]}],
            }
        ]
    }


def label_for(split: str, annotation: dict) -> dict:
    failures = annotation["failures"]
    categories = sorted({normalize_category(f["failure_category"]) for f in failures})
    root_id = (annotation.get("root_cause") or {}).get("failure_id") or annotation.get(
        "root_cause_failure_id"
    )
    root_category = None
    for failure in failures:
        if failure["failure_id"] == root_id:
            root_category = normalize_category(failure["failure_category"])
    return {
        "dataset": "agentrx",
        "outcome": "failure",
        "failure_categories": categories,
        "root_cause_category": root_category,
        "benchmark": split,
        "task_id": str(annotation["trajectory_id"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=sorted(SPLITS), help="restrict to one split")
    args = parser.parse_args()
    token = _hf_token()

    traces_dir = OUT_DIR / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)
    labels_path = OUT_DIR / "labels.json"
    labels: dict[str, dict] = json.loads(labels_path.read_text()) if labels_path.exists() else {}

    written = skipped = 0
    for split, (ann_file, traj_file, prefix) in SPLITS.items():
        if args.split and split != args.split:
            continue
        annotations = fetch_jsonl(ann_file, token)
        trajectories = {t["trajectory_id"]: t for t in fetch_jsonl(traj_file, token)}
        for annotation in annotations:
            trajectory = trajectories.get(f"{prefix}{annotation['trajectory_id']}")
            if trajectory is None:
                print(f"skip {split}/{annotation['trajectory_id']}: no trajectory", file=sys.stderr)
                skipped += 1
                continue
            otlp = convert(split, trajectory)
            trace_id = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"]
            slug = str(annotation["trajectory_id"]).replace("/", "_")
            (traces_dir / f"{split}-{slug}.json").write_text(json.dumps(otlp))
            labels[trace_id] = label_for(split, annotation)
            written += 1
    labels_path.write_text(json.dumps(labels, indent=2) + "\n")
    print(
        f"wrote {written} OTLP files (+{skipped} skipped) + labels.json "
        f"to {OUT_DIR.relative_to(Path.cwd())}"
    )


if __name__ == "__main__":
    main()
