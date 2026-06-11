"""Family-2 judge: voting folds, call composition, clean room, the
disagreement cap, keyless skip — all scripted fakes, no network."""

import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.analysis import llm
from app.analysis.config import AnalysisSettings
from app.analysis.judge import (
    INVALID_VOTE,
    _CategoryVote,
    _FailureModeVote,
    _OutcomeVote,
    fold_category,
    fold_failure_mode,
    fold_outcome,
    run_judge,
)
from app.analysis.models import JudgeVerdict, JudgeVote, SignalsResult
from app.analysis.registry import ANALYZERS, run_analyzer
from tests.unit.analysis_factories import make_span, make_trace

SETTINGS = AnalysisSettings(judge_votes=3, judge_consensus=0.5)
META = llm.CallMeta(latency_ms=5, input_tokens=10, output_tokens=2, cost_usd=0.001)


# --- scripted fake for llm.complete ---


class FakeLLM:
    """Pops scripted responses per vote schema; records every call."""

    def __init__(self, responses: dict[type[BaseModel], list[Any]]):
        self.responses = {schema: list(items) for schema, items in responses.items()}
        self.calls: list[dict[str, Any]] = []

    async def complete(self, model, messages, schema, temperature):
        self.calls.append(
            {"model": model, "messages": messages, "schema": schema, "temperature": temperature}
        )
        item = self.responses[schema].pop(0)
        if isinstance(item, Exception):
            raise item
        return item, META

    def messages_for(self, schema: type[BaseModel]) -> list[list[dict[str, str]]]:
        return [c["messages"] for c in self.calls if c["schema"] is schema]


@pytest.fixture
def patch_llm(monkeypatch):
    def _install(responses: dict[type[BaseModel], list[Any]]) -> FakeLLM:
        fake = FakeLLM(responses)
        monkeypatch.setattr(llm, "complete", fake.complete)
        monkeypatch.setattr(llm, "llm_configured", lambda model: True)
        return fake

    return _install


def ov(value: str, conf: float = 0.9, reasoning: str | None = None) -> _OutcomeVote:
    return _OutcomeVote(outcome=value, confidence=conf, reasoning=reasoning or f"{value} reasoning")


def fv(value: str, conf: float = 0.8) -> _FailureModeVote:
    return _FailureModeVote(failure_mode=value, confidence=conf, reasoning="fm reasoning")


def cv(value: str, conf: float = 0.8) -> _CategoryVote:
    return _CategoryVote(task_category=value, confidence=conf, reasoning="cat reasoning")


def jv(call: str, value: str, conf: float | None = None, reasoning: str | None = None) -> JudgeVote:
    return JudgeVote(call=call, value=value, confidence=conf, reasoning=reasoning)


def judge_trace(error_end: bool = False):
    spans = [
        make_span(
            0,
            kind="llm",
            attributes={
                "gen_ai.input.messages": json.dumps(
                    [{"role": "user", "parts": [{"type": "text", "content": "do the thing"}]}]
                )
            },
        ),
        make_span(1, kind="tool", tool_name="search"),
    ]
    if error_end:
        spans.append(make_span(2, kind="tool", tool_name="search", status="error"))
    return make_trace(spans)


# --- voting folds ---


def test_fold_outcome_majority_with_reasoning() -> None:
    votes = [
        jv("outcome", "success", reasoning="first"),
        jv("outcome", "success", reasoning="second"),
        jv("outcome", "failure", reasoning="dissent"),
    ]
    label, confidence, reasoning = fold_outcome(votes, consensus=0.5)
    assert (label, reasoning) == ("success", "first")
    assert confidence == pytest.approx(2 / 3)


def test_fold_outcome_split_is_indeterminate() -> None:
    votes = [jv("outcome", "success"), jv("outcome", "failure"), jv("outcome", "indeterminate")]
    label, confidence, _ = fold_outcome(votes, consensus=0.5)
    assert label == "indeterminate"
    assert confidence == pytest.approx(1 / 3)


def test_fold_outcome_abstention_majority() -> None:
    votes = [jv("outcome", "indeterminate")] * 2 + [jv("outcome", "success")]
    label, confidence, _ = fold_outcome(votes, consensus=0.5)
    assert label == "indeterminate"
    assert confidence == pytest.approx(2 / 3)


def test_fold_outcome_share_at_consensus_fails_strict_majority() -> None:
    votes = [jv("outcome", "success")] * 2 + [jv("outcome", "failure"), jv("outcome", "failure")]
    label, _, _ = fold_outcome(votes, consensus=0.5)
    assert label == "indeterminate"  # 2/4 == 0.5 is not > 0.5


def test_fold_outcome_n1_uses_self_report() -> None:
    label, confidence, _ = fold_outcome([jv("outcome", "success", conf=0.4)], consensus=0.5)
    assert (label, confidence) == ("success", 0.4)


def test_fold_outcome_n1_malformed_reports_zero() -> None:
    label, confidence, reasoning = fold_outcome([jv("outcome", "indeterminate")], consensus=0.5)
    assert (label, confidence, reasoning) == ("indeterminate", 0.0, None)


def test_fold_failure_mode_plurality() -> None:
    votes = [
        jv("failure_mode", "system_failure"),
        jv("failure_mode", "system_failure"),
        jv("failure_mode", "invalid_invocation"),
    ]
    assert fold_failure_mode(votes) == ("system_failure", pytest.approx(2 / 3))


def test_fold_failure_mode_tie_is_inconclusive() -> None:
    votes = [
        jv("failure_mode", "system_failure"),
        jv("failure_mode", "invalid_invocation"),
        jv("failure_mode", INVALID_VOTE),
    ]
    assert fold_failure_mode(votes) == ("inconclusive", 0.0)


def test_fold_failure_mode_no_valid_votes() -> None:
    assert fold_failure_mode([jv("failure_mode", INVALID_VOTE)] * 3) == ("inconclusive", 0.0)


def test_fold_category_tie_breaks_lexicographically() -> None:
    votes = [
        jv("category", "web_research"),
        jv("category", "coding"),
        jv("category", INVALID_VOTE),
    ]
    label, confidence = fold_category(votes)
    assert (label, confidence) == ("coding", pytest.approx(1 / 3))


def test_fold_category_no_valid_votes_is_null() -> None:
    assert fold_category([jv("category", INVALID_VOTE)] * 3) == (None, None)


def test_fold_category_n1_uses_self_report() -> None:
    assert fold_category([jv("category", "coding", conf=0.6)]) == ("coding", 0.6)


# --- composition ---


async def test_success_skips_failure_mode_call(patch_llm) -> None:
    fake = patch_llm({_OutcomeVote: [ov("success")] * 3, _CategoryVote: [cv("coding")] * 3})
    verdict = await run_judge(judge_trace(), SETTINGS)
    assert verdict.outcome == "success"
    assert verdict.failure_mode is None and verdict.failure_mode_confidence is None
    assert not fake.messages_for(_FailureModeVote)
    assert len(verdict.votes) == 6


async def test_failure_triggers_failure_mode_call(patch_llm) -> None:
    patch_llm(
        {
            _OutcomeVote: [ov("failure")] * 3,
            _FailureModeVote: [fv("invalid_invocation")] * 3,
            _CategoryVote: [cv("coding")] * 3,
        }
    )
    verdict = await run_judge(judge_trace(error_end=True), SETTINGS)
    assert verdict.outcome == "failure"
    assert verdict.failure_mode == "invalid_invocation"
    assert verdict.failure_mode_confidence == pytest.approx(1.0)
    assert len(verdict.votes) == 9


async def test_outcome_prompt_is_clean_room(patch_llm) -> None:
    fake = patch_llm(
        {
            _OutcomeVote: [ov("failure")] * 3,
            _FailureModeVote: [fv("system_failure")] * 3,
            _CategoryVote: [cv("coding")] * 3,
        }
    )
    await run_judge(judge_trace(error_end=True), SETTINGS)
    for messages in fake.messages_for(_OutcomeVote):
        for message in messages:
            assert "Deterministic evidence" not in message["content"]
            assert "failure_suspected" not in message["content"]
    # The evidence lives in the failure-mode prompt only.
    fm_user = fake.messages_for(_FailureModeVote)[0][1]["content"]
    assert "Deterministic evidence:" in fm_user
    assert "error span:" in fm_user


async def test_category_skipped_without_goal_inputs(patch_llm) -> None:
    fake = patch_llm({_OutcomeVote: [ov("success")] * 3})
    trace = make_trace([make_span(0, kind="llm"), make_span(1, kind="llm")])
    verdict = await run_judge(trace, SETTINGS)
    assert verdict.task_category is None and verdict.task_category_confidence is None
    assert not fake.messages_for(_CategoryVote)


async def test_out_of_vocabulary_vote_is_malformed(patch_llm) -> None:
    patch_llm(
        {
            _OutcomeVote: [ov("success")] * 3,
            _CategoryVote: [cv("nonsense_category"), cv("coding"), cv("coding")],
        }
    )
    verdict = await run_judge(judge_trace(), SETTINGS)
    assert verdict.task_category == "coding"
    assert verdict.task_category_confidence == pytest.approx(2 / 3)
    category_votes = [v for v in verdict.votes if v.call == "category"]
    assert [v.value for v in category_votes].count(INVALID_VOTE) == 1


async def test_malformed_outcome_vote_abstains(patch_llm) -> None:
    patch_llm(
        {
            _OutcomeVote: [llm.MalformedResponse(META), ov("success"), ov("success")],
            _CategoryVote: [cv("coding")] * 3,
        }
    )
    verdict = await run_judge(judge_trace(), SETTINGS)
    assert verdict.outcome == "success"
    assert verdict.outcome_confidence == pytest.approx(2 / 3)
    outcome_votes = [v for v in verdict.votes if v.call == "outcome"]
    abstained = [v for v in outcome_votes if v.reasoning is None]
    assert len(abstained) == 1 and abstained[0].value == "indeterminate"
    assert abstained[0].cost_usd == META.cost_usd  # malformed votes keep their cost


async def test_disagreement_cap_applied_to_verdict(patch_llm) -> None:
    # Trace ends in an unrecovered error -> failure_suspected; judge says
    # success -> confidence hard-capped at 0.5 before the verdict returns.
    patch_llm({_OutcomeVote: [ov("success")] * 3, _CategoryVote: [cv("coding")] * 3})
    verdict = await run_judge(judge_trace(error_end=True), SETTINGS)
    assert verdict.outcome == "success"
    assert verdict.outcome_confidence == 0.5


async def test_caller_supplied_signals_drive_cap(patch_llm) -> None:
    # Trace itself looks clean; the caller's signals suspect failure — the
    # passed-in result, not an internal re-run, must drive the cap.
    patch_llm({_OutcomeVote: [ov("success")] * 3, _CategoryVote: [cv("coding")] * 3})
    signals = SignalsResult(failure_suspected=True)
    verdict = await run_judge(judge_trace(), SETTINGS, signals)
    assert verdict.outcome_confidence == 0.5


async def test_transient_vote_error_settles_siblings_then_propagates(patch_llm) -> None:
    fake = patch_llm({_OutcomeVote: [ov("success"), RuntimeError("rate limited"), ov("success")]})
    with pytest.raises(RuntimeError, match="rate limited"):
        await run_judge(judge_trace(), SETTINGS)
    # All three votes ran to completion — no orphaned sibling tasks.
    assert len(fake.messages_for(_OutcomeVote)) == 3


def test_settings_reject_invalid_voting_config() -> None:
    with pytest.raises(ValidationError):
        AnalysisSettings(judge_votes=0)
    with pytest.raises(ValidationError):
        AnalysisSettings(judge_consensus=0.3)


async def test_keyless_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(llm, "llm_configured", lambda model: False)
    assert await run_judge(judge_trace(), SETTINGS) is None


async def test_vote_metadata_recorded(patch_llm) -> None:
    patch_llm({_OutcomeVote: [ov("success")] * 3, _CategoryVote: [cv("coding")] * 3})
    verdict = await run_judge(judge_trace(), SETTINGS)
    for vote in verdict.votes:
        assert vote.latency_ms == META.latency_ms
        assert vote.input_tokens == META.input_tokens
        assert vote.output_tokens == META.output_tokens
        assert vote.cost_usd == META.cost_usd


async def test_envelope_round_trip(patch_llm) -> None:
    patch_llm({_OutcomeVote: [ov("success")] * 3, _CategoryVote: [cv("coding")] * 3})
    run = await run_analyzer(ANALYZERS["judge"], judge_trace(), SETTINGS)
    assert run.analyzer == "judge"
    assert run.model_id == SETTINGS.judge_model
    parsed = JudgeVerdict.model_validate(json.loads(run.model_dump_json())["output"])
    assert run.confidence == parsed.outcome_confidence
    assert len(parsed.votes) == 6
