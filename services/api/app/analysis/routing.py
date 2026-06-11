"""FROZEN CONTRACT — HIL routing reasons (B0, 1_analysis.md HIL Routing).

The reason *model* is frozen; the pure functions over it (B2) are the one
home for signals×verdict composition: the disagreement confidence cap and
the routing decision. The plain-language message is what
`review_items.context` records and the review UI shows.
"""

from typing import Literal

from pydantic import BaseModel

from app.analysis.models import JudgeVerdict, SignalsResult

RoutingReasonCode = Literal[
    "signals_judge_disagreement",
    "outcome_indeterminate",
    "low_outcome_confidence",
    "low_task_category_confidence",
]


class RoutingReason(BaseModel):
    model_config = {"frozen": True}

    code: RoutingReasonCode
    message: str


def _disagreement(signals: SignalsResult, verdict: JudgeVerdict) -> bool:
    return signals.failure_suspected and verdict.outcome == "success"


def finalize_verdict(signals: SignalsResult, verdict: JudgeVerdict) -> JudgeVerdict:
    """The confidence formula's hard cap (1_analysis.md): ≤ 0.5 when the
    structural signals suspect failure but the judge says success. Applied
    post-judge — the clean room governs prompts, not arithmetic. The capped
    value is what gets stored; the uncapped share is recoverable from the
    votes."""
    if _disagreement(signals, verdict) and verdict.outcome_confidence is not None:
        capped = min(0.5, verdict.outcome_confidence)
        return verdict.model_copy(update={"outcome_confidence": capped})
    return verdict


def route(
    signals: SignalsResult, verdict: JudgeVerdict, confidence_threshold: float
) -> list[RoutingReason]:
    """The four spec triggers, in spec order. Thresholds are strict (a
    confidence exactly at the threshold does not route); null confidence
    never matches a predicate, so it never triggers. Empty list = no
    review item."""
    reasons = []
    if _disagreement(signals, verdict):
        reasons.append(
            RoutingReason(
                code="signals_judge_disagreement",
                message="Structural signals suggest failure but the judge concluded success.",
            )
        )
    if verdict.outcome == "indeterminate":
        reasons.append(
            RoutingReason(
                code="outcome_indeterminate",
                message="The judge could not determine an outcome (abstention or split vote).",
            )
        )
    if verdict.outcome_confidence is not None and verdict.outcome_confidence < confidence_threshold:
        reasons.append(
            RoutingReason(
                code="low_outcome_confidence",
                message=(
                    f"Outcome confidence {verdict.outcome_confidence:.2f} is below "
                    f"the review threshold {confidence_threshold:.2f}."
                ),
            )
        )
    if (
        verdict.task_category_confidence is not None
        and verdict.task_category_confidence < confidence_threshold
    ):
        reasons.append(
            RoutingReason(
                code="low_task_category_confidence",
                message=(
                    f"Task-category confidence {verdict.task_category_confidence:.2f} is "
                    f"below the review threshold {confidence_threshold:.2f}."
                ),
            )
        )
    return reasons
