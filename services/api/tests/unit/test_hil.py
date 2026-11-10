"""Session-analysis pure logic (9_session-analysis.md): which turns get
(re)judged, the derived status, the review-item context rule, stored turns
back as verdicts, the relabel request, session signal aggregation, and the
canned-verdict fault grammar. The transactional plumbing (union recompute,
human-turn guard, review sync) is integration-tested."""

import pytest
from pydantic import ValidationError

from app.analysis import SignalsResult, combine
from app.analysis.agent.models import FailureLabel, TurnVerdict
from app.dev import faults
from app.queries.analysis import (
    derive_status,
    needs_judging,
    roll_up_state,
    stored_verdict,
    verdict_labels,
)
from app.queries.review_items import review_action, review_context
from app.routers.traces import turn_analysis
from app.schemas.analysis import TurnLabelsRequest


def turn(**overrides) -> dict:
    return {"provenance": "machine", "fingerprint": "f1", "outcome": "success", **overrides}


# --- needs_judging: which turns a run judges ---


def test_missing_turn_is_judged() -> None:
    assert needs_judging(None, "f1", llm=True)
    assert needs_judging(None, "f1", llm=False)  # signals-only row still written


def test_current_turn_is_not_rejudged() -> None:
    assert not needs_judging(turn(), "f1", llm=True)


def test_changed_fingerprint_is_rejudged() -> None:
    assert needs_judging(turn(), "f2", llm=True)


def test_human_turn_is_never_rejudged() -> None:
    assert not needs_judging(turn(provenance="human"), "f2", llm=True)


def test_unjudged_turn_waits_for_a_judge() -> None:
    keyless = turn(outcome=None)
    assert needs_judging(keyless, "f1", llm=True)
    assert not needs_judging(keyless, "f1", llm=False)


# --- derive_status ---


def test_status() -> None:
    assert derive_status(None, None, 0) == "pending"
    assert derive_status("skipped", None, 1) == "skipped"
    assert derive_status("complete", None, 1) == "in_progress"
    assert derive_status("complete", "2026-01-01", 1) == "final"
    # Re-ingested since the last claim: not final until re-seen.
    assert derive_status("complete", "2026-01-01", 0) == "in_progress"


# --- review_context: one open item listing the uncertain turns ---


def test_no_uncertain_turn_no_item() -> None:
    assert review_context([]) is None


def test_review_action_updates_in_place() -> None:
    a = {"turns": [{"turn_index": 1, "reason": "r", "summary": None}]}
    b = {"turns": [{"turn_index": 2, "reason": "r", "summary": None}]}
    assert review_action(None, None) == "keep"
    assert review_action(None, a) == "create"
    assert review_action(a, a) == "keep"
    assert review_action(a, b) == "update"  # never supersede-and-recreate
    assert review_action(a, None) == "close"


def test_item_lists_uncertain_turns() -> None:
    rows = [{"turn_index": 2, "uncertain": "step limit", "summary": "Ran tests"}]
    assert review_context(rows) == {
        "turns": [{"turn_index": 2, "reason": "step limit", "summary": "Ran tests"}]
    }


# --- stored_verdict: stored rows back into the roll-up ---


def test_stored_verdict_splits_labels() -> None:
    row = {
        "turn_index": 1,
        "outcome": "partial",
        "summary": None,
        "uncertain": None,
        "labels": [
            {"field": "task_category", "value": "coding", "span_ids": [], "reason": None},
            {"field": "failure_mode", "value": "system_failure", "span_ids": [], "reason": None},
        ],
    }
    verdict = stored_verdict(row)
    assert verdict.task_categories == ["coding"]
    assert verdict.failure_modes[0].value == "system_failure"
    assert verdict.failure_modes[0].span_ids == []  # human labels may cite no span
    assert verdict.summary == ""


# --- TurnLabelsRequest ---


def test_relabel_request_validates_vocabularies() -> None:
    TurnLabelsRequest(
        outcome="partial",
        task_categories=["coding"],
        failure_modes=[{"value": "invalid_invocation", "span_ids": ["a"]}],
    )
    mode = {"value": "invalid_invocation"}
    for bad in (
        {"outcome": "partial", "task_categories": ["coding", "coding"]},
        {"outcome": "failure", "task_categories": ["coding"], "failure_modes": [mode, mode]},
        {
            "outcome": "failure",
            "task_categories": ["coding"],
            "failure_modes": [{"value": "invalid_invocation", "span_ids": ["a", "a"]}],
        },
        {
            "outcome": "failure",
            "task_categories": ["coding"],
            "failure_modes": [{"value": "invalid_invocation", "reason": "x" * 2001}],
        },
        {"outcome": "partial", "task_categories": []},
        {"outcome": "partial", "task_categories": ["nope"]},
        {"outcome": "maybe", "task_categories": ["coding"]},
        {"outcome": "failure", "task_categories": ["coding"], "failure_modes": [{"value": "x"}]},
        # An empty set already says "none identified".
        {
            "outcome": "failure",
            "task_categories": ["coding"],
            "failure_modes": [{"value": "inconclusive"}],
        },
    ):
        with pytest.raises(ValidationError):
            TurnLabelsRequest.model_validate(bad)


# --- combine: session signals from turns ---


def test_combine_any_and_sums() -> None:
    combined = combine(
        [
            SignalsResult(has_retry_loop=False, recovered_from_error=None, llm_call_count=2),
            SignalsResult(has_retry_loop=True, loop_kind="cycle", llm_call_count=3),
            SignalsResult(),
        ]
    )
    assert combined.has_retry_loop is True
    assert combined.loop_kind == "cycle"
    assert combined.recovered_from_error is None
    assert combined.llm_call_count == 5
    assert combined.tool_call_count is None


# --- canned-verdict fault grammar ---


@pytest.mark.parametrize(
    "spec",
    [
        "analyze:verdict:success",
        "analyze:verdict:partial:uncertain",
        "analyze:permanent",  # the A2 grammar still validates
        "transient:2",
    ],
)
def test_fault_grammar_accepts(spec: str) -> None:
    assert faults.is_valid(spec)


@pytest.mark.parametrize(
    "spec",
    ["verdict:success", "analyze:verdict:maybe", "analyze:verdict:success:0.4"],
)
def test_fault_grammar_rejects(spec: str) -> None:
    assert not faults.is_valid(spec)


async def test_canned_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def armed(upload_id: str) -> str:
        return "analyze:verdict:failure:uncertain"

    monkeypatch.setattr(faults, "_armed_spec", armed)
    assert await faults.canned_verdict("u1") == ("failure", True)


async def test_non_verdict_spec_is_not_canned(monkeypatch: pytest.MonkeyPatch) -> None:
    async def armed(upload_id: str) -> str:
        return "analyze:permanent"

    monkeypatch.setattr(faults, "_armed_spec", armed)
    assert await faults.canned_verdict("u1") is None


async def test_verdict_spec_never_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    async def armed(upload_id: str) -> str:
        return "analyze:verdict:success"

    monkeypatch.setattr(faults, "_armed_spec", armed)
    await faults.trip_analysis("u1", attempt=1)  # must not raise


# --- rewrite guards (pure parts) ---


def test_roll_up_state() -> None:
    assert roll_up_state(True, written=2, applied=2, changed=True) == "stamp"
    assert roll_up_state(True, written=0, applied=0, changed=False) == "stamp"  # re-roll only
    # A finalize whose write was refused (rows moved) does not stamp.
    assert roll_up_state(True, written=2, applied=1, changed=True) == "stale"
    assert roll_up_state(False, written=1, applied=1, changed=True) == "stale"
    # Nothing the roll-up saw changed: an older snapshot must not unstamp.
    assert roll_up_state(False, written=1, applied=0, changed=False) == "keep"


def test_verdict_labels_merge_repeated_failure_modes() -> None:
    verdict = TurnVerdict(
        turn_index=0,
        outcome="failure",
        summary="s",
        task_categories=["coding"],
        failure_modes=[
            FailureLabel(value="invalid_invocation", span_ids=["a"], reason="first"),
            FailureLabel(value="invalid_invocation", span_ids=["b", "a"], reason="second"),
        ],
        uncertain=None,
    )
    assert verdict_labels(verdict) == [
        ("task_category", "coding", [], None),
        ("failure_mode", "invalid_invocation", ["a", "b"], "first"),
    ]


def test_uncertain_is_owner_only() -> None:
    row = {
        "turn_index": 0,
        "outcome": "indeterminate",
        "summary": "s",
        "uncertain": "step limit",
        "provenance": "machine",
        "signals": {},
        "labels": [],
    }
    assert turn_analysis(row, "automated", is_owner=True).uncertain == "step limit"
    assert turn_analysis(row, "human", is_owner=False).uncertain is None
    assert turn_analysis(row, "automated", is_owner=False).origin == "automated"
