"""Task-category eval — the category call's first independent measurement.

Corpus: the existing benchmark corpora (arb 200 + agentrx 73) plus the
golden session fixtures (claude/codex/cursor turns). Ground truth comes
only from defensible wholesale mappings — benchmarks whose every task is
one category (tau_retail customer-service agents, GAIA-style magentic_one
and assistantbench information-seeking) and session fixtures (coding).
webarena / visualwebarena / workarena are task-level mixed and stay
unlabeled rather than mislabeled; they still count toward routing rate.

Builds the exact production input (`_category_text` over
`first_user_message` + tool names, the same code path as run_judge) and
caches per (prompt, model, input-text) — so a content-extraction change
invalidates exactly the traces whose input it altered.

`--pre-fix` disables the generic-input fallback in `first_user_message`
to reproduce the pre-pass-4 evidence bug (sessions lose their ask).
`--scope a,b,c` runs with an owner task scope (hard scoping, task-scope
slice): the prompt and vocabulary shrink to the listed values + other.
`--votes N` overrides the vote count (default 3) — the confidence lattice
changes (N=5: 0.2 steps), so the report sweeps thresholds.

Run from services/api:  uv run python ../../sandbox/judge-eval/cat_eval.py
"""

import asyncio
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).parents[2]
sys.path.insert(0, str(REPO / "services" / "api"))

from app.analysis import content  # noqa: E402
from app.analysis.config import AnalysisSettings  # noqa: E402
from app.analysis.judge import _category_text, _collect_votes, fold_category  # noqa: E402
from app.analysis.models import TASK_CATEGORIES  # noqa: E402
from app.analysis.prompts.judge import category  # noqa: E402
from app.analysis.trace_input import TraceInput  # noqa: E402
from app.importers import sessions  # noqa: E402
from app.importers.otlp import import_payload  # noqa: E402
from app.redaction import OFFLINE_SALT  # noqa: E402

OUT = REPO / "out" / "cat-eval"
CONCURRENCY = 16
ROUTING_THRESHOLD = AnalysisSettings().confidence_threshold

# Wholesale benchmark → acceptable-category sets (verified by sampling task
# instructions); mixed benchmarks map to None and score routing rate only.
# Sets, not single labels: the 50-value taxonomy (task-scope slice) has
# legitimate fine-grained answers inside one corpus — a tau-bench agent does
# both account actions and support; an agent-session turn saying "now run
# the tests" is honestly testing_qa. The first value is the display primary.
SOFTWARE_ENGINEERING = (
    "coding",
    "debugging",
    "code_review",
    "testing_qa",
    "devops_infra",
    "ci_cd",
    "database_admin",
    "security_engineering",
    "ml_engineering",
    "technical_writing",
)
WEB_INFORMATION_SEEKING = (
    "web_research",
    "academic_research",
    "market_research",
    "competitive_analysis",
)
BENCHMARK_CATEGORY: dict[str, tuple[str, ...] | None] = {
    "tau_retail": ("customer_ops", "customer_support"),
    "magentic_one": WEB_INFORMATION_SEEKING,
    "assistantbench": WEB_INFORMATION_SEEKING,
    "webarena": None,
    "visualwebarena": None,
    "workarena": None,
}
SESSION_ANCHOR = datetime(2026, 6, 1, tzinfo=UTC)


def corpus() -> list[tuple[str, str, str | None, TraceInput]]:
    """(id, corpus name, acceptable categories | None, trace)."""
    items: list[tuple[str, str, tuple[str, ...] | None, TraceInput]] = []
    for dataset in ("arb", "agentrx"):
        root = REPO / "devdata" / "benchmarks" / dataset
        labels = json.loads((root / "labels.json").read_text())
        for path in sorted((root / "traces").glob("*.json")):
            result = import_payload(json.loads(path.read_text()), redaction_salt=OFFLINE_SALT)
            trace = TraceInput.from_import(result.traces[0])
            benchmark = labels[trace.source_trace_id]["benchmark"]
            items.append((path.stem, benchmark, BENCHMARK_CATEGORY[benchmark], trace))
    for path in sorted((REPO / "fixtures" / "golden").glob("*.jsonl")):
        records = sessions.parse_records(path.read_bytes())
        fmt = sessions.detect(records)
        payload = sessions.convert(fmt, records, session_id=path.stem, anchor=SESSION_ANCHOR)
        result = import_payload(payload, redaction_salt=OFFLINE_SALT)
        for i, imported in enumerate(result.traces):
            trace = TraceInput.from_import(imported)
            items.append((f"session-{path.stem}-{i}", "sessions", SOFTWARE_ENGINEERING, trace))
    return items


async def judge_one(
    item_id: str,
    trace: TraceInput,
    settings: AnalysisSettings,
    sem: asyncio.Semaphore,
    system: str,
    vocabulary: frozenset[str],
) -> dict:
    user_message = content.first_user_message(trace.spans)
    if not user_message and not trace.tool_names:
        return {"trace": item_id, "skipped": True}
    user_text = _category_text(user_message, trace.tool_names)

    input_rev = hashlib.sha256(user_text.encode()).hexdigest()[:8]
    cache = OUT / _rev(settings, system) / f"{item_id}-{input_rev}.json"
    if cache.exists():
        return json.loads(cache.read_text())

    # Provider flakes under burst (observed: a bogus "headers too large"
    # BadRequest) misclassify as permanent — retry per trace, not per run.
    async with sem:
        for attempt in range(3):
            try:
                votes = await _collect_votes(
                    "category", user_text, settings, system=system, vocabulary=vocabulary
                )
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
    label, confidence = fold_category(votes)
    row = {
        "trace": item_id,
        "task_category": label,
        "confidence": confidence,
        "has_user_message": bool(user_message),
        "votes": [{"value": v.value, "reasoning": v.reasoning} for v in votes],
        "cost_usd": sum(v.cost_usd or 0 for v in votes),
    }
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(row, indent=2))
    tmp.replace(cache)
    print(f"judged {item_id}: {label} ({confidence})", file=sys.stderr)
    return row


def _rev(settings: AnalysisSettings, system: str) -> str:
    prompt_rev = hashlib.sha256(system.encode()).hexdigest()[:8]
    # Vote count joined only when non-default, keeping earlier 3-vote cache
    # dirs (pass 4 / task-scope runs) addressable.
    votes = "" if settings.judge_votes == 3 else f"-v{settings.judge_votes}"
    return f"{prompt_rev}-{settings.judge_model.replace('/', '_')}{votes}"


def score(
    items: list[tuple[str, str, tuple[str, ...] | None, TraceInput]],
    rows: list[dict],
    rev: str,
) -> None:
    n = routed = no_ask = 0
    per_corpus: dict[str, Counter] = {}
    confusion: Counter[tuple[str, str]] = Counter()
    for (_item_id, corpus_name, expected, _), row in zip(items, rows, strict=True):
        if row.get("skipped"):
            continue
        n += 1
        stats = per_corpus.setdefault(corpus_name, Counter())
        stats["n"] += 1
        confidence = row["confidence"]
        if confidence is not None and confidence < ROUTING_THRESHOLD:
            routed += 1
            stats["routed"] += 1
        if not row["has_user_message"]:
            no_ask += 1
            stats["no_ask"] += 1
        if expected is not None:
            stats["labeled"] += 1
            judged = row["task_category"]
            stats["correct"] += judged in expected
            confusion[expected[0], judged] += 1

    print(f"\ncat-eval — {n} traces, prompt rev {rev}")
    print(f"  routing rate (confidence < {ROUTING_THRESHOLD}): {routed / n:.1%} ({routed}/{n})")
    print(f"  missing goal surface (no user message): {no_ask / n:.1%} ({no_ask}/{n})")
    labeled = sum(s["labeled"] for s in per_corpus.values())
    correct = sum(s["correct"] for s in per_corpus.values())
    print(f"  accuracy on labeled subset: {correct / labeled:.1%} ({correct}/{labeled})")

    confidences = [r["confidence"] for r in rows if not r.get("skipped")]
    print("\nrouting rate by threshold (what-if):")
    for threshold in (0.5, 0.6, 0.7, 0.8):
        would_route = sum(1 for c in confidences if c is not None and c < threshold)
        print(f"  < {threshold}: {would_route / n:.1%} ({would_route}/{n})")
    print("\nper corpus (n / routed / accuracy-where-labeled):")
    for name, stats in sorted(per_corpus.items()):
        accuracy = (
            f"{stats['correct'] / stats['labeled']:.1%} ({stats['correct']}/{stats['labeled']})"
            if stats["labeled"]
            else "—"
        )
        print(f"  {name:<16} n={stats['n']:<4} routed={stats['routed']:<4} acc={accuracy}")
    print("\nconfusion (expected -> judged):")
    for (expected, judged), count in confusion.most_common():
        mark = "  <== match" if expected == judged else ""
        print(f"  {expected:<16} -> {judged:<20} {count}{mark}")


async def main() -> None:
    if "--pre-fix" in sys.argv:
        # Reproduce the pre-pass-4 evidence bug: no generic-input fallback.
        content._user_text_from_generic = lambda value: None  # type: ignore[assignment]
        print("pre-fix mode: generic-input fallback disabled", file=sys.stderr)
    allowed = frozenset(TASK_CATEGORIES)
    if "--scope" in sys.argv:
        raw = sys.argv[sys.argv.index("--scope") + 1].split(",")
        unknown = [v for v in raw if v not in TASK_CATEGORIES]
        if unknown:
            sys.exit(f"unknown categories in --scope: {unknown}")
        allowed = frozenset(raw) | {"other"}
        print(f"scoped mode: {sorted(allowed)}", file=sys.stderr)
    system = category.build_v2(allowed)
    votes = int(sys.argv[sys.argv.index("--votes") + 1]) if "--votes" in sys.argv else 3
    settings = AnalysisSettings(judge_votes=votes)
    sem = asyncio.Semaphore(CONCURRENCY)
    items = corpus()
    rows = await asyncio.gather(
        *(judge_one(i, t, settings, sem, system, allowed) for i, _, _, t in items)
    )
    score(items, list(rows), _rev(settings, system))


if __name__ == "__main__":
    asyncio.run(main())
