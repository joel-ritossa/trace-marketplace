"""Session-analysis pure logic (9_session-analysis.md): which turns get
(re)judged, the derived status, the review-item context rule, stored turns
back as verdicts, the relabel request, session signal aggregation, and the
canned-verdict fault grammar. The transactional plumbing (union recompute,
human-turn guard, review sync) is integration-tested."""

import pytest
from pydantic import ValidationError

from app.analysis import SignalsResult, combine
from app.dev import faults
from app.queries.analysis import derive_status, needs_judging, stored_verdict
from app.queries.review_items import review_context
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
    ok = TurnLabelsRequest(
        outcome="partial",
        task_categories=["coding", "coding"],
        failure_modes=[{"value": "invalid_invocation", "span_ids": ["a"]}],
    )
    assert ok.task_categories == ["coding"]
    for bad in (
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
