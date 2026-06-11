"""HIL routing: the disagreement cap and the four routing triggers —
pure functions over (signals, verdict), exhaustively deterministic."""

import pytest

from app.analysis.models import JudgeVerdict, SignalsResult
from app.analysis.routing import finalize_verdict, route

THRESHOLD = 0.7


def signals(failure_suspected: bool = False) -> SignalsResult:
    return SignalsResult(failure_suspected=failure_suspected)


def verdict(
    outcome: str = "success",
    outcome_confidence: float | None = 1.0,
    task_category_confidence: float | None = 1.0,
) -> JudgeVerdict:
    return JudgeVerdict(
        outcome=outcome,
        outcome_confidence=outcome_confidence,
        task_category="coding",
        task_category_confidence=task_category_confidence,
    )


# --- finalize_verdict (the confidence cap) ---


def test_cap_fires_on_disagreement() -> None:
    final = finalize_verdict(signals(failure_suspected=True), verdict(outcome_confidence=0.9))
    assert final.outcome_confidence == 0.5


def test_cap_never_raises_confidence() -> None:
    final = finalize_verdict(signals(failure_suspected=True), verdict(outcome_confidence=0.3))
    assert final.outcome_confidence == pytest.approx(0.3)


def test_cap_skips_judge_failure() -> None:
    final = finalize_verdict(
        signals(failure_suspected=True), verdict(outcome="failure", outcome_confidence=0.9)
    )
    assert final.outcome_confidence == pytest.approx(0.9)


def test_cap_skips_without_suspicion() -> None:
    final = finalize_verdict(signals(), verdict(outcome_confidence=0.9))
    assert final.outcome_confidence == pytest.approx(0.9)


def test_cap_leaves_null_confidence_alone() -> None:
    final = finalize_verdict(signals(failure_suspected=True), verdict(outcome_confidence=None))
    assert final.outcome_confidence is None


# --- route (the four triggers) ---


def test_confident_agreement_routes_nothing() -> None:
    assert route(signals(), verdict(), THRESHOLD) == []


def test_disagreement_trigger() -> None:
    reasons = route(signals(failure_suspected=True), verdict(outcome_confidence=0.5), THRESHOLD)
    assert [r.code for r in reasons] == ["signals_judge_disagreement", "low_outcome_confidence"]


def test_indeterminate_trigger() -> None:
    reasons = route(signals(), verdict(outcome="indeterminate", outcome_confidence=1.0), THRESHOLD)
    assert [r.code for r in reasons] == ["outcome_indeterminate"]


def test_low_outcome_confidence_trigger() -> None:
    reasons = route(signals(), verdict(outcome_confidence=0.69), THRESHOLD)
    assert [r.code for r in reasons] == ["low_outcome_confidence"]
    assert "0.69" in reasons[0].message and "0.70" in reasons[0].message


def test_confidence_at_threshold_does_not_route() -> None:
    assert route(signals(), verdict(outcome_confidence=0.7), THRESHOLD) == []


def test_low_category_confidence_trigger() -> None:
    reasons = route(signals(), verdict(task_category_confidence=0.2), THRESHOLD)
    assert [r.code for r in reasons] == ["low_task_category_confidence"]


def test_null_confidence_never_routes() -> None:
    reasons = route(
        signals(), verdict(outcome_confidence=None, task_category_confidence=None), THRESHOLD
    )
    assert reasons == []


def test_stacked_triggers_in_spec_order() -> None:
    reasons = route(
        signals(failure_suspected=True),
        verdict(outcome="indeterminate", outcome_confidence=0.33, task_category_confidence=0.33),
        THRESHOLD,
    )
    # Disagreement needs judge success, so it stays out; the rest stack.
    assert [r.code for r in reasons] == [
        "outcome_indeterminate",
        "low_outcome_confidence",
        "low_task_category_confidence",
    ]
