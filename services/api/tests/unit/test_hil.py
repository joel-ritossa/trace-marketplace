"""A3 HIL pure logic: the provenance reason-filter, the canned-verdict fault
grammar, the resolve request's coherence validation, and the resolve
write-set arithmetic (label_updates / verdict_snapshot). The transactional
plumbing is integration-tested."""

import pytest
from pydantic import ValidationError

from app.analysis.routing import RoutingReason
from app.dev import faults
from app.queries.analysis import filter_reasons
from app.queries.review_items import label_updates, verdict_snapshot
from app.schemas.review import ReviewResolveRequest


def reasons(*codes: str) -> list[RoutingReason]:
    return [RoutingReason(code=code, message=f"msg {code}") for code in codes]


ALL_CODES = [
    "signals_judge_disagreement",
    "outcome_indeterminate",
    "low_outcome_confidence",
    "low_task_category_confidence",
]


# --- filter_reasons (decision 3: don't re-ask answered questions) ---


def test_machine_provenance_keeps_everything() -> None:
    provs = {"outcome": "machine", "failure_mode": None, "task_category": "machine"}
    assert filter_reasons(reasons(*ALL_CODES), provs) == reasons(*ALL_CODES)


def test_no_row_keeps_everything() -> None:
    assert filter_reasons(reasons(*ALL_CODES), {}) == reasons(*ALL_CODES)


@pytest.mark.parametrize("prov", ["human", "human_confirmed"])
def test_human_outcome_drops_outcome_reasons(prov: str) -> None:
    provs = {"outcome": prov, "task_category": "machine"}
    assert filter_reasons(reasons(*ALL_CODES), provs) == reasons("low_task_category_confidence")


@pytest.mark.parametrize("prov", ["human", "human_confirmed"])
def test_human_category_drops_category_reason(prov: str) -> None:
    provs = {"outcome": "machine", "task_category": prov}
    assert filter_reasons(reasons(*ALL_CODES), provs) == reasons(*ALL_CODES[:3])


def test_all_answered_drops_all() -> None:
    provs = {"outcome": "human", "task_category": "human_confirmed"}
    assert filter_reasons(reasons(*ALL_CODES), provs) == []


# --- canned-verdict fault grammar ---


@pytest.mark.parametrize(
    "spec",
    [
        "analyze:verdict:success:0.4",
        "analyze:verdict:failure:1.0",
        "analyze:verdict:indeterminate:0.95:coding:0.5",
        "analyze:permanent",  # the A2 grammar still validates
        "transient:2",
    ],
)
def test_fault_grammar_accepts(spec: str) -> None:
    assert faults.is_valid(spec)


@pytest.mark.parametrize(
    "spec",
    [
        "verdict:success:0.4",  # verdict is analysis-only
        "analyze:verdict:success",  # confidence required
        "analyze:verdict:maybe:0.4",  # not in the ternary
        "analyze:verdict:success:1.5",  # confidence out of range
        "analyze:verdict:success:0.4:coding",  # category needs its confidence
    ],
)
def test_fault_grammar_rejects(spec: str) -> None:
    assert not faults.is_valid(spec)


async def test_canned_verdict_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    async def armed(upload_id: str) -> str:
        return "analyze:verdict:failure:0.6:coding:0.3"

    monkeypatch.setattr(faults, "_armed_spec", armed)
    verdict = await faults.canned_verdict("u1")
    assert verdict is not None
    assert verdict.outcome == "failure"
    assert verdict.outcome_confidence == 0.6
    assert verdict.failure_mode == "inconclusive"  # failure gets a placeholder mode
    assert verdict.task_category == "coding"
    assert verdict.task_category_confidence == 0.3


async def test_canned_verdict_success_has_no_failure_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    async def armed(upload_id: str) -> str:
        return "analyze:verdict:success:0.4"

    monkeypatch.setattr(faults, "_armed_spec", armed)
    verdict = await faults.canned_verdict("u1")
    assert verdict is not None
    assert verdict.failure_mode is None
    assert verdict.task_category is None


async def test_non_verdict_spec_is_not_canned(monkeypatch: pytest.MonkeyPatch) -> None:
    async def armed(upload_id: str) -> str:
        return "analyze:permanent"

    monkeypatch.setattr(faults, "_armed_spec", armed)
    assert await faults.canned_verdict("u1") is None


async def test_verdict_spec_never_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    async def armed(upload_id: str) -> str:
        return "analyze:verdict:success:0.4"

    monkeypatch.setattr(faults, "_armed_spec", armed)
    await faults.trip_analysis("u1", attempt=1)  # must not raise


# --- ReviewResolveRequest coherence (the resolve boundary) ---


@pytest.mark.parametrize("outcome", ["success", "indeterminate"])
def test_resolve_request_rejects_failure_mode_with_non_failure_outcome(outcome: str) -> None:
    with pytest.raises(ValidationError):
        ReviewResolveRequest(outcome=outcome, failure_mode="inconclusive")


def test_resolve_request_allows_failure_mode_alone() -> None:
    # Refining a machine failure verdict without touching its outcome.
    ReviewResolveRequest(failure_mode="inconclusive")


def test_resolve_request_allows_failure_mode_with_failure() -> None:
    ReviewResolveRequest(outcome="failure", failure_mode="system_failure")


# --- label_updates (decision 6: the resolve write-set) ---


def row(**overrides) -> dict:
    base = {
        "outcome": "success",
        "outcome_confidence": 0.4,
        "outcome_provenance": "machine",
        "failure_mode": None,
        "failure_mode_confidence": None,
        "failure_mode_provenance": None,
        "task_category": "coding",
        "task_category_confidence": 0.9,
        "task_category_provenance": "machine",
    }
    return {**base, **overrides}


def test_differing_answer_is_human() -> None:
    updates = label_updates({"outcome": "failure"}, row())
    assert updates["outcome"] == "failure"
    assert updates["outcome_confidence"] == 1.0
    assert updates["outcome_provenance"] == "human"


def test_matching_machine_answer_is_confirmed() -> None:
    updates = label_updates({"outcome": "success"}, row())
    assert updates["outcome_provenance"] == "human_confirmed"
    assert updates["outcome_confidence"] == 1.0


def test_matching_human_answer_stays_human() -> None:
    # Confirmation compares against machine values only: re-answering a
    # previously human-set value is a fresh human assertion.
    updates = label_updates({"outcome": "success"}, row(outcome_provenance="human"))
    assert updates["outcome_provenance"] == "human"


def test_partial_answer_touches_only_answered_fields() -> None:
    updates = label_updates({"task_category": "coding"}, row())
    assert set(updates) == {"task_category", "task_category_confidence", "task_category_provenance"}
    assert updates["task_category_provenance"] == "human_confirmed"


def test_non_failure_outcome_nulls_machine_failure_mode() -> None:
    current = row(
        outcome="failure",
        failure_mode="system_failure",
        failure_mode_confidence=0.8,
        failure_mode_provenance="machine",
    )
    updates = label_updates({"outcome": "success"}, current)
    assert updates["failure_mode"] is None
    assert updates["failure_mode_confidence"] is None
    assert updates["failure_mode_provenance"] is None


def test_non_failure_outcome_keeps_human_failure_mode() -> None:
    current = row(outcome="failure", failure_mode="system_failure", failure_mode_provenance="human")
    updates = label_updates({"outcome": "indeterminate"}, current)
    assert "failure_mode" not in updates  # the human's label is their business


def test_failure_outcome_keeps_machine_failure_mode() -> None:
    current = row(
        outcome="failure", failure_mode="system_failure", failure_mode_provenance="machine"
    )
    updates = label_updates({"outcome": "failure"}, current)
    assert "failure_mode" not in updates


def test_answered_failure_mode_beats_the_nulling_rule() -> None:
    # Unreachable through the API since the request validator rejects this
    # shape; documents the pure function's standalone precedence.
    current = row(failure_mode="system_failure", failure_mode_provenance="machine")
    updates = label_updates({"outcome": "indeterminate", "failure_mode": "inconclusive"}, current)
    assert updates["failure_mode"] == "inconclusive"
    assert updates["failure_mode_provenance"] == "human"


# --- verdict_snapshot (owner-relabel context) ---


def test_snapshot_takes_machine_fields_only() -> None:
    current = row(outcome_provenance="human", outcome="failure", outcome_confidence=1.0)
    snapshot = verdict_snapshot(current)
    assert snapshot["outcome"] is None  # human-resolved: not the machine's take
    assert snapshot["outcome_confidence"] is None
    assert snapshot["task_category"] == "coding"
    assert snapshot["task_category_confidence"] == 0.9
    assert snapshot["failure_mode"] is None
