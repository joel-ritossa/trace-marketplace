"""FROZEN CONTRACT — analyzer result models (B0, 1_analysis.md).

These models are the seam between the analysis stream (B-slices) and the
platform stream (A-slices): analyzers return them, the worker persists them
into `analyzer_results.output` / promotes fields into `trace_analysis`
(2_data-model.md). Field names and types are frozen at B0 close; change is
additive or goes through a spec amendment recorded in the buildlog.
"""

from typing import Any, Literal

from pydantic import BaseModel

Outcome = Literal["success", "failure", "indeterminate"]
# Per-field provenance on trace_analysis columns (2_data-model.md). No result
# model carries it yet — A2's worker stamps it at persistence; part of the
# frozen contract vocabulary, not dead code.
Provenance = Literal["machine", "human_confirmed", "human"]
LoopKind = Literal["exact_repeat", "cycle", "stagnation"]

# failure_mode / task_category are text with app-level validation, no Literal:
# the taxonomies evolve additively without a contract break (1_analysis.md
# derived-field principles). These sets are the validators.
FAILURE_MODES = frozenset(
    {
        "plan_adherence_failure",
        "invention_of_information",
        "invalid_invocation",
        "tool_output_misinterpretation",
        "intent_plan_misalignment",
        "underspecified_intent",
        "intent_not_supported",
        "guardrails_triggered",
        "system_failure",
        "inconclusive",
    }
)

# Starting set; finalized against the dev/candidate datasets before B2 lock.
TASK_CATEGORIES = frozenset(
    {
        "web_research",
        "customer_ops",
        "coding",
        "data_analysis",
        "scheduling_planning",
        "content_generation",
        "retrieval_qa",
        "other",
    }
)


class SignalsResult(BaseModel):
    """Family 1 output. All catalog fields nullable — analyzers fail open;
    null means "no opinion", never a guess. Which fields get promoted into
    `trace_analysis` columns is B1's hit-rate-gated call."""

    has_retry_loop: bool | None = None
    loop_kind: LoopKind | None = None
    recovered_from_error: bool | None = None
    truncation_suspected: bool | None = None
    llm_call_count: int | None = None
    tool_call_count: int | None = None
    # Stored for routing auditability; never promoted, never user-facing,
    # never in the judge prompt. False means "no opinion", not "success".
    failure_suspected: bool = False


class JudgeVote(BaseModel):
    """One sampled run of one composed call — the stored audit artifact.
    Values are labels + reasoning snippets, never trace content."""

    call: Literal["outcome", "failure_mode", "category"]
    value: str
    reasoning: str | None = None


class JudgeVerdict(BaseModel):
    """Family 2 output: the three composed calls' labels with per-field
    confidence (vote share), plus the recorded votes."""

    outcome: Outcome | None = None
    outcome_confidence: float | None = None
    failure_mode: str | None = None
    failure_mode_confidence: float | None = None
    task_category: str | None = None
    task_category_confidence: float | None = None
    reasoning: str | None = None
    votes: list[JudgeVote] = []
    rendering_truncated: bool = False


class MetricResult(BaseModel):
    """Family 3 output, one per applicable metric. Inapplicable metrics
    produce no result at all — never a garbage score."""

    metric: str
    value: float | bool
    reason: str | None = None


class RenderedMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class RenderedTrace(BaseModel):
    """Renderer output: chronological OpenAI-style message list serving the
    judge and family 3. Deterministic for a fixed (trace, version, config)."""

    messages: list[RenderedMessage]
    rendering_truncated: bool
    renderer_version: str
    step_count: int
    elided_step_count: int

    @property
    def total_chars(self) -> int:
        return sum(len(m.content) for m in self.messages)


class AnalyzerRun(BaseModel):
    """Envelope mirroring `analyzer_results` columns 1:1. The runner dumps
    these; A2's worker persists them verbatim. `output` is the result
    model's dump (jsonb-shaped); the registry's result model re-validates."""

    analyzer: str
    analyzer_version: str
    model_id: str | None = None
    confidence: float | None = None
    output: dict[str, Any]
