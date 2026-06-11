"""Family 2: the outcome judge — three composed LLM calls with
self-consistency voting (1_analysis.md).

Pure async over the trace input; the only I/O is `llm.complete`. The
outcome call is clean-room (no family-1 signals content in its prompt);
deterministic evidence appears only in the failure-mode prompt. The
disagreement confidence cap is applied here, before the verdict leaves the
analyzer, so every stored envelope already carries the capped value.

JUDGE_VERSION covers prompts + composition + voting config; renderer or
prompt changes bump it (2_data-model.md).
"""

import asyncio
from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field

from app.analysis import content, llm
from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.models import (
    FAILURE_MODES,
    TASK_CATEGORIES,
    JudgeVerdict,
    JudgeVote,
    Outcome,
    SignalsResult,
)
from app.analysis.prompts.judge import category, failure_mode, outcome
from app.analysis.rendering import render_trace, rendering_text
from app.analysis.routing import finalize_verdict
from app.analysis.signals import run_signals
from app.analysis.trace_input import TraceInput

JUDGE_VERSION = "7"

_MAX_EVIDENCE_ERROR_SPANS = 10

Call = Literal["outcome", "failure_mode", "category"]

# Prompt modules carry their own per-prompt versions (prompts/ convention);
# JUDGE_VERSION covers the ensemble (prompts + composition + voting
# config). Decoupled so one prompt can rev without the other two. The
# category entry is the unscoped (full taxonomy) build; a scoped trace
# overrides it per call (1_analysis.md Owner task scope).
_PROMPTS: dict[Call, str] = {
    "outcome": outcome.V3,
    "failure_mode": failure_mode.V4,
    "category": category.build_v2(TASK_CATEGORIES),
}

# Recorded value for a fm/category vote whose response failed validation:
# the vote (and its cost) stays auditable but never enters a fold numerator.
# Outcome malformed votes record as "indeterminate" — an abstention.
INVALID_VOTE = "invalid"


class _OutcomeVote(BaseModel):
    outcome: Outcome
    confidence: float = Field(ge=0, le=1)
    reasoning: str


class _FailureModeVote(BaseModel):
    failure_mode: str
    confidence: float = Field(ge=0, le=1)
    reasoning: str


class _CategoryVote(BaseModel):
    task_category: str
    confidence: float = Field(ge=0, le=1)
    reasoning: str


_SCHEMAS: dict[Call, type[BaseModel]] = {
    "outcome": _OutcomeVote,
    "failure_mode": _FailureModeVote,
    "category": _CategoryVote,
}
_VALUE_FIELDS: dict[Call, str] = {
    "outcome": "outcome",
    "failure_mode": "failure_mode",
    "category": "task_category",
}
# Closed vocabularies (None = the schema's Literal already enforces it).
_VOCABULARY: dict[Call, frozenset[str] | None] = {
    "outcome": None,
    "failure_mode": FAILURE_MODES,
    "category": TASK_CATEGORIES,
}


async def _one_vote(
    call: Call,
    user_text: str,
    settings: AnalysisSettings,
    *,
    system: str | None = None,
    vocabulary: frozenset[str] | None = None,
) -> JudgeVote:
    """`system`/`vocabulary` override the call's defaults — the owner-scoped
    category call passes both; everything else uses `_PROMPTS`/`_VOCABULARY`."""
    messages = [
        {"role": "system", "content": system if system is not None else _PROMPTS[call]},
        {"role": "user", "content": user_text},
    ]
    try:
        parsed, meta = await llm.complete(
            settings.judge_model, messages, _SCHEMAS[call], llm.SAMPLING_TEMPERATURE
        )
    except llm.MalformedResponse as exc:
        return _malformed_vote(call, exc.meta)
    value = getattr(parsed, _VALUE_FIELDS[call])
    if vocabulary is None:
        vocabulary = _VOCABULARY[call]
    if vocabulary is not None and value not in vocabulary:
        # Out-of-vocabulary (including outside the owner's scope) is a
        # malformed vote, not a new label.
        return _malformed_vote(call, meta)
    return JudgeVote(
        call=call,
        value=value,
        reasoning=parsed.reasoning,
        confidence=parsed.confidence,
        latency_ms=meta.latency_ms,
        input_tokens=meta.input_tokens,
        output_tokens=meta.output_tokens,
        cost_usd=meta.cost_usd,
    )


def _malformed_vote(call: Call, meta: llm.CallMeta) -> JudgeVote:
    value = "indeterminate" if call == "outcome" else INVALID_VOTE
    return JudgeVote(
        call=call,
        value=value,
        latency_ms=meta.latency_ms,
        input_tokens=meta.input_tokens,
        output_tokens=meta.output_tokens,
        cost_usd=meta.cost_usd,
    )


async def _collect_votes(
    call: Call,
    user_text: str,
    settings: AnalysisSettings,
    *,
    system: str | None = None,
    vocabulary: frozenset[str] | None = None,
) -> list[JudgeVote]:
    # Settle every vote before re-raising the first error: gather without
    # return_exceptions would leave sibling calls running detached. Raising
    # the original exception (not an ExceptionGroup) preserves the typed
    # permanent/transient classification the worker keys on.
    results = await asyncio.gather(
        *(
            _one_vote(call, user_text, settings, system=system, vocabulary=vocabulary)
            for _ in range(settings.judge_votes)
        ),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return [r for r in results if isinstance(r, JudgeVote)]


def _self_report(votes: list[JudgeVote], confidence: float | None) -> float | None:
    """N=1 degrades to the model's self-reported confidence — vote share is
    always 1.0 there and says nothing. Malformed single votes report 0.0."""
    if len(votes) != 1:
        return confidence
    return votes[0].confidence if votes[0].confidence is not None else 0.0


def fold_outcome(votes: list[JudgeVote], consensus: float) -> tuple[Outcome, float, str | None]:
    """Strict majority over the consensus threshold or `indeterminate`
    (split / abstention-majority). Confidence = the final label's vote
    share; reasoning = the first vote matching the final label."""
    n = len(votes)
    counts = Counter(v.value for v in votes)
    label: Outcome = "indeterminate"
    for candidate in ("success", "failure"):
        if counts[candidate] / n > consensus:
            label = candidate  # type: ignore[assignment]
    confidence = counts[label] / n
    reasoning = next((v.reasoning for v in votes if v.value == label and v.reasoning), None)
    final = _self_report(votes, confidence)
    return label, final if final is not None else confidence, reasoning


def fold_failure_mode(votes: list[JudgeVote]) -> tuple[str, float]:
    """Plurality; a tie or no valid votes → `inconclusive` (the taxonomy's
    built-in abstention). Denominator stays N."""
    n = len(votes)
    counts = Counter(v.value for v in votes if v.value != INVALID_VOTE)
    label = "inconclusive"
    if counts:
        top = counts.most_common(1)[0][1]
        tied = [value for value, count in counts.items() if count == top]
        if len(tied) == 1:
            label = tied[0]
    confidence = counts.get(label, 0) / n
    final = _self_report(votes, confidence)
    return label, final if final is not None else confidence


def fold_category(votes: list[JudgeVote]) -> tuple[str | None, float | None]:
    """Plurality; ties break to the lexicographically smallest tied value
    (deterministic; a tie's share is low enough that the confidence knob
    routes it). No valid votes → null fields, fail open."""
    n = len(votes)
    counts = Counter(v.value for v in votes if v.value != INVALID_VOTE)
    if not counts:
        return None, None
    top = counts.most_common(1)[0][1]
    label = min(value for value, count in counts.items() if count == top)
    return label, _self_report(votes, counts[label] / n)


def _evidence_block(loop_kind: str | None, trace: TraceInput) -> str:
    """Deterministic evidence for the failure-mode prompt only: loop kind +
    error-span skeletons (name, status, error type — never bodies)."""
    lines = []
    if loop_kind:
        lines.append(f"- detected loop: {loop_kind}")
    error_spans = [s for s in trace.spans if s.status == "error"]
    for span in error_spans[:_MAX_EVIDENCE_ERROR_SPANS]:
        detail = f", {span.error_type}" if span.error_type else ""
        lines.append(f"- error span: {span.kind} {span.name} ({span.status}{detail})")
    if len(error_spans) > _MAX_EVIDENCE_ERROR_SPANS:
        lines.append(f"- …and {len(error_spans) - _MAX_EVIDENCE_ERROR_SPANS} more error spans")
    if not lines:
        return ""
    return "Deterministic evidence:\n" + "\n".join(lines) + "\n\n"


def _category_text(user_message: str | None, tool_names: list[str]) -> str:
    return (
        f"First user message:\n{user_message or '(none recorded)'}\n\n"
        f"Tools used: {', '.join(tool_names) if tool_names else '(none)'}"
    )


async def run_judge(
    trace: TraceInput,
    settings: AnalysisSettings,
    signals: SignalsResult | None = None,
) -> JudgeVerdict | None:
    """`signals` lets a caller that already ran family 1 (the route CLI,
    A2's worker) pass its result in; omitted, the judge computes its own —
    run_signals is pure, so the two can never disagree."""
    if not llm.llm_configured(settings.judge_model):
        return None  # keyless: inapplicable, no fake output

    rendered = render_trace(trace, RendererConfig.from_settings(settings))
    rendering = rendering_text(rendered.messages)
    if signals is None:
        signals = await run_signals(trace, settings)

    # The category call depends only on the goal surface, never on the
    # outcome fold — only the failure-mode call is gated on outcome. The
    # outcome→failure-mode chain and the category votes therefore run
    # concurrently (same calls, same prompts; latency, not composition).
    async def outcome_chain() -> tuple[list[JudgeVote], list[JudgeVote]]:
        outcome_votes = await _collect_votes("outcome", rendering, settings)
        fm_votes: list[JudgeVote] = []
        label, _, _ = fold_outcome(outcome_votes, settings.judge_consensus)
        if label == "failure":
            user_text = _evidence_block(signals.loop_kind, trace) + "Trace:\n" + rendering
            fm_votes = await _collect_votes("failure_mode", user_text, settings)
        return outcome_votes, fm_votes

    async def category_votes() -> list[JudgeVote] | None:
        user_message = content.first_user_message(trace.spans)
        if not user_message and not trace.tool_names:
            return None
        # Owner task scope (1_analysis.md): the scoped vocabulary always
        # includes "other"; unknown stored values are dropped, not trusted.
        scope = TASK_CATEGORIES & frozenset(trace.owner_task_categories or ())
        system = category.build_v2(scope | {"other"}) if scope else None
        vocabulary = (scope | {"other"}) if scope else None
        return await _collect_votes(
            "category",
            _category_text(user_message, trace.tool_names),
            settings,
            system=system,
            vocabulary=vocabulary,
        )

    # Settle both branches before re-raising the first error (the
    # _collect_votes convention): no orphaned sibling calls, and the
    # original typed exception survives for the worker's classification.
    results = await asyncio.gather(outcome_chain(), category_votes(), return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    (outcome_votes, fm_votes), cat_votes = results  # type: ignore[misc]

    outcome, outcome_confidence, reasoning = fold_outcome(outcome_votes, settings.judge_consensus)
    votes = list(outcome_votes)

    failure_mode: str | None = None
    failure_mode_confidence: float | None = None
    if fm_votes:
        votes.extend(fm_votes)
        failure_mode, failure_mode_confidence = fold_failure_mode(fm_votes)

    task_category: str | None = None
    task_category_confidence: float | None = None
    if cat_votes is not None:
        votes.extend(cat_votes)
        task_category, task_category_confidence = fold_category(cat_votes)

    verdict = JudgeVerdict(
        outcome=outcome,
        outcome_confidence=outcome_confidence,
        failure_mode=failure_mode,
        failure_mode_confidence=failure_mode_confidence,
        task_category=task_category,
        task_category_confidence=task_category_confidence,
        reasoning=reasoning,
        votes=votes,
        rendering_truncated=rendered.rendering_truncated,
    )
    # Cap applied before the verdict leaves the analyzer: no caller can
    # forget it, and every stored envelope confidence is the final value.
    return finalize_verdict(signals, verdict)
