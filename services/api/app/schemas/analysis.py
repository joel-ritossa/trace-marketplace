"""Analysis view models (3_api.md GET /v1/traces/{id}/analysis).

Mirrored by the frontend types in apps/web/src/lib/api/traces.ts.
"""

from typing import Any, Literal

from pydantic import BaseModel

# Derived, never stored (2_data-model.md "Analysis state").
AnalysisState = Literal["pending", "complete", "skipped", "failed"]

SkipReason = Literal["not_configured", "owner_opt_out"]

Provenance = Literal["machine", "human_confirmed", "human"]


class LabelValue(BaseModel):
    value: str
    confidence: float | None
    provenance: Provenance


class AnalysisLabels(BaseModel):
    """Null field = the analyzer didn't produce it (fail open) or LLM
    analysis was skipped; null never matches a predicate."""

    outcome: LabelValue | None = None
    failure_mode: LabelValue | None = None
    task_category: LabelValue | None = None


class AnalysisSignals(BaseModel):
    """The promoted family-1 catalog. `failure_suspected` is deliberately
    absent: routing-internal, never user-facing (1_analysis.md)."""

    has_retry_loop: bool | None = None
    loop_kind: str | None = None
    recovered_from_error: bool | None = None
    truncation_suspected: bool | None = None
    llm_call_count: int | None = None
    tool_call_count: int | None = None


class AuditAnalyzer(BaseModel):
    analyzer: str
    analyzer_version: str
    model_id: str | None = None
    confidence: float | None = None
    # Judge-only audit artifacts (stored votes, renderer truncation flag).
    votes: list[dict[str, Any]] | None = None
    rendering_truncated: bool | None = None


class AnalysisAudit(BaseModel):
    analyzers: list[AuditAnalyzer]


class TraceAnalysisResponse(BaseModel):
    analysis_state: AnalysisState
    # Set exactly on skipped / failed respectively; the UI renders them
    # verbatim (4_pages.md "never a lie").
    skip_reason: SkipReason | None = None
    failed_reason: str | None = None
    labels: AnalysisLabels
    reasoning: str | None = None
    signals: AnalysisSignals | None = None
    metric_scores: dict[str, float | bool] | None = None
    # Owner-only (A3 decision 8): null for non-owners and when nothing is open.
    open_review_item_id: str | None = None
    audit: AnalysisAudit
