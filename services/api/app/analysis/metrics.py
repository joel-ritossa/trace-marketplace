"""Family 3: quality metric evals — owned critics + pinned RAGAS
collections behind applicability predicates (1_analysis.md).

Every metric is a pure async analyzer `(trace, settings) -> MetricResult |
None`; None = inapplicable (or keyless / fail-open), no row, never a
garbage score. Critics judge the full rendering with one structured call
each (the judge's call pattern); the RAGAS pair consumes the trace→sample
adapter through a litellm-backed LLM adapter, so litellm stays the only
provider-call site and every RAGAS-internal call carries cost metadata.

Reference-free only (hard constraint): Faithfulness and
AgentGoalAccuracyWithoutReference are the pinned RAGAS variants.

Privacy: nothing here logs. Renderings, samples, and raw outputs exist
only in memory; only the structured result leaves.
"""

import asyncio
import math
from collections import Counter
from collections.abc import Awaitable, Callable

from pydantic import BaseModel

from app.analysis import llm
from app.analysis.config import AnalysisSettings, RendererConfig
from app.analysis.models import MetricCall, MetricResult
from app.analysis.prompts.critics import (
    coherence,
    hallucination,
    harmfulness,
    helpfulness,
    relevancy,
)
from app.analysis.rendering import render_trace, rendering_text
from app.analysis.sample import TraceSample, trace_to_sample
from app.analysis.trace_input import TraceInput

# Per-metric versions (decision 8): a prompt or predicate change bumps the
# owning metric only. The RAGAS pair's version also covers the ragas pin.
METRIC_VERSIONS: dict[str, str] = {
    "hallucination": "3",
    "helpfulness": "1",
    "harmfulness": "1",
    "coherence": "1",
    "relevancy": "1",
    "faithfulness": "1",
    "goal_accuracy": "1",
}

_CRITIC_PROMPTS: dict[str, str] = {
    "hallucination": hallucination.V3,
    "helpfulness": helpfulness.V1,
    "harmfulness": harmfulness.V1,
    "coherence": coherence.V1,
    "relevancy": relevancy.V1,
}

# RAGAS metrics run once (their decomposition is internally multi-call);
# no voting, so deterministic decoding is the right default.
_RAGAS_TEMPERATURE = 0.0


class _CriticVote(BaseModel):
    flag: bool
    reason: str


def _meta_call(meta: llm.CallMeta) -> MetricCall:
    return MetricCall(**meta.model_dump())


async def _critic_vote(
    prompt: str, rendering: str, settings: AnalysisSettings
) -> tuple[_CriticVote | None, MetricCall]:
    """One sampled critic call; a malformed response is a dropped vote
    whose cost still rides the audit list."""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": rendering},
    ]
    try:
        parsed, meta = await llm.complete(
            settings.judge_model, messages, _CriticVote, llm.SAMPLING_TEMPERATURE
        )
    except llm.MalformedResponse as exc:
        return None, _meta_call(exc.meta)
    return parsed, _meta_call(meta)


def _fold_critic(votes: list[_CriticVote]) -> tuple[bool, str | None] | None:
    """Majority flag; a tie or no valid votes fails open (no row). Reason =
    the first vote matching the majority flag."""
    counts = Counter(v.flag for v in votes)
    if not counts or (len(counts) == 2 and counts[True] == counts[False]):
        return None
    flag = counts.most_common(1)[0][0]
    reason = next((v.reason for v in votes if v.flag == flag and v.reason), None)
    return flag, reason


def _critic_runner(
    name: str,
) -> Callable[[TraceInput, AnalysisSettings], Awaitable[MetricResult | None]]:
    prompt = _CRITIC_PROMPTS[name]

    async def run(trace: TraceInput, settings: AnalysisSettings) -> MetricResult | None:
        if not llm.llm_configured(settings.judge_model):
            return None  # keyless: inapplicable, no fake output
        if not trace_to_sample(trace).response:
            return None  # critics need ≥1 LLM response span
        rendered = render_trace(trace, RendererConfig.from_settings(settings))
        rendering = rendering_text(rendered.messages)
        # Settle every vote before re-raising the first error (the judge's
        # gather discipline): typed permanent/transient classification
        # propagates intact for the worker's retry machinery.
        results = await asyncio.gather(
            *(_critic_vote(prompt, rendering, settings) for _ in range(settings.critic_votes)),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        pairs = [r for r in results if isinstance(r, tuple)]
        calls = [call for _, call in pairs]
        folded = _fold_critic([vote for vote, _ in pairs if vote is not None])
        if folded is None:
            return None
        flag, reason = folded
        return MetricResult(metric=name, value=flag, reason=reason, calls=calls)

    return run


def _ragas_llm(model: str):
    """A RAGAS v0.4 collections LLM that delegates to `llm.complete` —
    litellm stays the only provider layer (the stock `llm_factory` wants a
    native provider client, which the repo rule forbids). Accumulates
    per-call cost metadata in `calls`. ragas imports stay lazy: the package
    is heavy and only metric runs need it."""
    from ragas.llms.base import InstructorBaseRagasLLM

    class _LitellmRagasLLM(InstructorBaseRagasLLM):
        def __init__(self) -> None:
            self.calls: list[MetricCall] = []

        async def agenerate(self, prompt: str, response_model: type) -> object:
            parsed, meta = await llm.complete(
                model,
                [{"role": "user", "content": prompt}],
                response_model,
                _RAGAS_TEMPERATURE,
            )
            self.calls.append(_meta_call(meta))
            return parsed

        def generate(self, prompt: str, response_model: type) -> object:
            # Analyzers are pure async; the pinned collections metrics call
            # only `agenerate` from `ascore`.
            raise NotImplementedError("sync generation is never used")

    return _LitellmRagasLLM()


def _score_result(
    name: str, value: float, reason: str | None, calls: list[MetricCall]
) -> MetricResult | None:
    """NaN (RAGAS's no-statements path) fails open — not JSON-safe and not
    a score. Scores clamp to the metric's declared [0, 1] range."""
    if math.isnan(value):
        return None
    return MetricResult(
        metric=name, value=min(max(float(value), 0.0), 1.0), reason=reason, calls=calls
    )


async def run_faithfulness(trace: TraceInput, settings: AnalysisSettings) -> MetricResult | None:
    """Applicability (spec): retrieval spans. The pinned scorer also
    requires the question and response, so the predicate includes them —
    fail open, never a guess."""
    if not llm.llm_configured(settings.judge_model):
        return None
    sample = trace_to_sample(trace)
    if not (sample.retrieved_contexts and sample.response and sample.user_input):
        return None

    from ragas.metrics.collections import Faithfulness

    adapter = _ragas_llm(settings.judge_model)
    try:
        result = await Faithfulness(llm=adapter).ascore(
            user_input=sample.user_input,
            response=sample.response,
            retrieved_contexts=sample.retrieved_contexts,
        )
    except llm.MalformedResponse:
        return None
    return _score_result("faithfulness", result.value, result.reason, adapter.calls)


def _goal_messages(sample: TraceSample) -> list:
    """Our trace shape → RAGAS conversation messages: the user goal, each
    tool action as an AI call + tool output, the final response."""
    from ragas.messages import AIMessage, HumanMessage, ToolMessage

    messages: list = [HumanMessage(content=sample.user_input or "")]
    for tool_call in sample.tool_calls:
        invocation = f"[tool call] {tool_call.name}"
        if tool_call.arguments:
            invocation += f" {tool_call.arguments}"
        messages.append(AIMessage(content=invocation))
        if tool_call.result:
            messages.append(ToolMessage(content=tool_call.result))
    if sample.response:
        messages.append(AIMessage(content=sample.response))
    return messages


async def run_goal_accuracy(trace: TraceInput, settings: AnalysisSettings) -> MetricResult | None:
    """Applicability (spec): a discernible user goal — plus some workflow
    (a response or tool calls) for an end state to be inferable from."""
    if not llm.llm_configured(settings.judge_model):
        return None
    sample = trace_to_sample(trace)
    if not sample.user_input or not (sample.response or sample.tool_calls):
        return None

    from ragas.metrics.collections import AgentGoalAccuracyWithoutReference

    adapter = _ragas_llm(settings.judge_model)
    try:
        result = await AgentGoalAccuracyWithoutReference(llm=adapter).ascore(
            user_input=_goal_messages(sample)
        )
    except llm.MalformedResponse:
        return None
    return _score_result("goal_accuracy", result.value, result.reason, adapter.calls)


# name → runner, consumed by the registry's metric:<name> registrations.
METRIC_RUNNERS: dict[str, Callable[[TraceInput, AnalysisSettings], Awaitable[MetricResult | None]]]
METRIC_RUNNERS = {
    **{name: _critic_runner(name) for name in _CRITIC_PROMPTS},
    "faithfulness": run_faithfulness,
    "goal_accuracy": run_goal_accuracy,
}
