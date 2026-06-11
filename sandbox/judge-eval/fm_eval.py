"""Failure-mode-only eval on the AgentRx corpus.

Runs the judge's failure_mode call unconditionally on every converted
AgentRx trace — ground truth says all 73 are failures, so bypassing the
outcome gate isolates the classifier under iteration and evaluates on the
full corpus instead of only the traces the outcome call happens to flag.

Builds the exact production input (rendering + deterministic evidence
block, same code paths as run_judge) and caches per-trace results keyed on
a hash of the active failure_mode prompt, so prompt revs never reuse stale
votes and re-scoring is free.

Run from services/api:  uv run python ../../sandbox/judge-eval/fm_eval.py
"""

import asyncio
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).parents[2]
sys.path.insert(0, str(REPO / "services" / "api"))

from app.analysis.config import AnalysisSettings, RendererConfig  # noqa: E402
from app.analysis.judge import (  # noqa: E402
    _PROMPTS,
    _collect_votes,
    _evidence_block,
    fold_failure_mode,
)
from app.analysis.rendering import render_trace, rendering_text  # noqa: E402
from app.analysis.signals import run_signals  # noqa: E402
from app.analysis.trace_input import TraceInput  # noqa: E402
from app.importers.otlp import import_payload  # noqa: E402
from app.redaction import OFFLINE_SALT  # noqa: E402

TRACES_DIR = REPO / "devdata" / "benchmarks" / "agentrx" / "traces"
LABELS = json.loads((REPO / "devdata" / "benchmarks" / "agentrx" / "labels.json").read_text())
OUT = REPO / "out" / "fm-eval"
CONCURRENCY = 8


async def judge_one(path: Path, settings: AnalysisSettings, sem: asyncio.Semaphore) -> dict:
    rev = _rev(settings)
    cache = OUT / rev / f"{path.stem}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    payload = json.loads(path.read_text())
    result = import_payload(payload, redaction_salt=OFFLINE_SALT)
    trace = TraceInput.from_import(result.traces[0])
    async with sem:
        signals = await run_signals(trace, settings)
        rendered = render_trace(trace, RendererConfig.from_settings(settings))
        user_text = (
            _evidence_block(signals.loop_kind, trace)
            + "Trace:\n"
            + rendering_text(rendered.messages)
        )
        votes = await _collect_votes("failure_mode", user_text, settings)
    label, confidence = fold_failure_mode(votes)
    row = {
        "trace": path.stem,
        "trace_id": trace.source_trace_id,
        "failure_mode": label,
        "confidence": confidence,
        "votes": [{"value": v.value, "reasoning": v.reasoning} for v in votes],
        "cost_usd": sum(v.cost_usd or 0 for v in votes),
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(row, indent=2))
    tmp.replace(cache)
    print(f"judged {path.stem}: {label}", file=sys.stderr)
    return row


def _rev(settings: AnalysisSettings) -> str:
    prompt_rev = hashlib.sha256(_PROMPTS["failure_mode"].encode()).hexdigest()[:8]
    return f"{prompt_rev}-{settings.judge_model.replace('/', '_')}"


def score(rows: list[dict], settings: AnalysisSettings) -> None:
    prompt_rev = _rev(settings)
    n = len(rows)
    root = any_match = 0
    confusion: Counter[tuple[str, str]] = Counter()
    for row in rows:
        label = LABELS[row["trace_id"]]
        human_root = label["root_cause_category"]
        judged = row["failure_mode"]
        confusion[human_root, judged] += 1
        root += judged == human_root
        any_match += judged == human_root or judged in label["failure_categories"]
    print(f"\nfm-eval — {n} traces, prompt rev {prompt_rev}")
    print(f"  root-cause match: {root / n:.1%} ({root}/{n})")
    print(f"  any-category match: {any_match / n:.1%} ({any_match}/{n})")
    print("\nconfusion (human root cause -> judge):")
    for (human, judged), count in confusion.most_common():
        mark = "  <== match" if human == judged else ""
        print(f"  {human:<32} -> {judged:<32} {count}{mark}")


async def main() -> None:
    settings = AnalysisSettings()
    sem = asyncio.Semaphore(CONCURRENCY)
    paths = sorted(TRACES_DIR.glob("*.json"))
    rows = await asyncio.gather(*(judge_one(p, settings, sem) for p in paths))
    score(list(rows), settings)


if __name__ == "__main__":
    asyncio.run(main())
