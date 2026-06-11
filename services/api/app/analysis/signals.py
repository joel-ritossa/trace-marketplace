"""Family 1: deterministic signals (1_analysis.md).

Pure functions over normalized rows — no model calls, no I/O. Every catalog
field fails open: instrumentation that doesn't match expected conventions
yields null, never a guess. Loop detection runs over tool actions
(`content.tool_actions`); thresholds come from `AnalysisSettings`.
"""

import hashlib
import json
from collections import Counter
from typing import Any

from app.analysis.config import AnalysisSettings
from app.analysis.content import MAX_INDEXED_ATTRS, ToolAction, input_text, tool_actions
from app.analysis.models import LoopKind, SignalsResult
from app.analysis.trace_input import SpanInput, TraceInput

SIGNALS_VERSION = "1"

# Cycle parameters are spec-fixed (1_analysis.md): period <= 4, >= 2
# consecutive repetitions. Only the repeat/stagnation N is env-tunable.
_CYCLE_MAX_PERIOD = 4
_CYCLE_MIN_REPEATS = 2

_TRUNCATION_FINISH_REASONS = {"length", "max_tokens"}


def _normalize_args(arguments: Any) -> str:
    """Canonical text for an action's arguments: JSON re-dumped with sorted
    keys (key order never changes the signature); non-JSON text stripped."""
    if arguments is None:
        return ""
    if isinstance(arguments, str):
        text = arguments.strip()
        try:
            arguments = json.loads(text)
        except ValueError:
            return text
    return json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _signature(action: ToolAction) -> str:
    return f"{action.name}\x00{_sha(_normalize_args(action.arguments))}"


def _has_exact_repeat(signatures: list[str], n: int) -> bool:
    run, prev = 0, None
    for sig in signatures:
        run = run + 1 if sig == prev else 1
        prev = sig
        if run >= n:
            return True
    return False


def _has_cycle(signatures: list[str]) -> bool:
    for period in range(2, _CYCLE_MAX_PERIOD + 1):
        for start in range(len(signatures) - _CYCLE_MIN_REPEATS * period + 1):
            gram = signatures[start : start + period]
            # A uniform gram is exact-repeat territory, not a cycle.
            if len(set(gram)) < 2:
                continue
            if all(
                signatures[start + r * period : start + (r + 1) * period] == gram
                for r in range(1, _CYCLE_MIN_REPEATS)
            ):
                return True
    return False


def _has_stagnation(actions: list[ToolAction], n: int) -> bool:
    counts: Counter[tuple[str, str]] = Counter()
    for action in actions:
        if action.result is None:
            continue
        counts[(action.name, _sha(action.result))] += 1
    return any(count >= n for count in counts.values())


def detect_loop(actions: list[ToolAction], n: int) -> LoopKind | None:
    """Most-specific strategy wins when several fire — deterministic order."""
    signatures = [_signature(a) for a in actions]
    if _has_exact_repeat(signatures, n):
        return "exact_repeat"
    if _has_cycle(signatures):
        return "cycle"
    if _has_stagnation(actions, n):
        return "stagnation"
    return None


def _span_identity(span: SpanInput) -> tuple[str, ...]:
    """Retry identity: tool spans match on (tool, args signature); everything
    else on (kind, name)."""
    if span.kind == "tool":
        name = span.tool_name or span.name
        return ("tool", name, _sha(_normalize_args(input_text(span))))
    return (span.kind, span.name)


def _recovered_from_error(spans: list[SpanInput]) -> bool | None:
    error_indexes = [i for i, s in enumerate(spans) if s.status == "error"]
    if not error_indexes:
        return None  # nothing to recover from — no opinion
    if spans[-1].status == "error":
        return False  # no normal completion
    for i in error_indexes:
        identity = _span_identity(spans[i])
        if any(
            later.status != "error" and _span_identity(later) == identity
            for later in spans[i + 1 :]
        ):
            return True
    return False


def _finish_reasons(span: SpanInput) -> list[str]:
    value = span.attributes.get("gen_ai.response.finish_reasons")
    if isinstance(value, str):
        # Some emitters JSON-encode the array into a string attribute.
        try:
            value = json.loads(value)
        except ValueError:
            value = [value]
    if isinstance(value, list):
        return [v for v in value if isinstance(v, str)]
    reasons = []
    for i in range(MAX_INDEXED_ATTRS):  # Traceloop legacy flattened completions
        prefix = f"gen_ai.completion.{i}"
        if not any(key.startswith(prefix + ".") for key in span.attributes):
            break
        reason = span.attributes.get(f"{prefix}.finish_reason")
        if isinstance(reason, str) and reason:
            reasons.append(reason)
    return reasons


def _truncation_suspected(spans: list[SpanInput]) -> bool | None:
    llm_spans = [s for s in spans if s.kind == "llm"]
    if not llm_spans:
        return None
    final = llm_spans[-1]
    reasons = _finish_reasons(final)
    if reasons:
        return any(r.lower() in _TRUNCATION_FINISH_REASONS for r in reasons)
    max_tokens = final.attributes.get("gen_ai.request.max_tokens")
    # bool is an int subclass; a stray boolean attribute is not a token limit.
    if isinstance(max_tokens, int) and not isinstance(max_tokens, bool):
        if final.output_tokens is not None:
            return final.output_tokens >= max_tokens
    return None  # no finish evidence either way


async def run_signals(trace: TraceInput, settings: AnalysisSettings) -> SignalsResult:
    actions = tool_actions(trace.spans)
    loop_kind = detect_loop(actions, settings.loop_n) if actions else None
    has_retry_loop = (loop_kind is not None) if actions else None
    recovered = _recovered_from_error(trace.spans)
    truncation = _truncation_suspected(trace.spans)
    # True on strong negatives only; false means "no opinion", never
    # "success". Stored for routing auditability, never promoted.
    failure_suspected = bool(
        (trace.status == "error" and recovered is not True) or has_retry_loop or truncation
    )
    return SignalsResult(
        has_retry_loop=has_retry_loop,
        loop_kind=loop_kind,
        recovered_from_error=recovered,
        truncation_suspected=truncation,
        llm_call_count=sum(1 for s in trace.spans if s.kind == "llm"),
        tool_call_count=len(actions),
        failure_suspected=failure_suspected,
    )
