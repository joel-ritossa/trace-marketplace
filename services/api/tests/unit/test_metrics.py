"""Family-3 metrics: applicability predicates, critic folds, the RAGAS
adapter driving the pinned collections metrics — all scripted fakes, no
network (the ragas prompt classes run for real against the fake LLM)."""

import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.analysis import llm
from app.analysis.config import AnalysisSettings
from app.analysis.metrics import (
    METRIC_RUNNERS,
    _CriticVote,
    run_faithfulness,
    run_goal_accuracy,
)
from app.analysis.models import METRICS, MetricResult
from app.analysis.registry import ANALYZERS, enabled_metric_specs, run_analyzer, run_metric_set
from tests.unit.analysis_factories import make_span, make_trace
from tests.unit.test_judge import META, FakeLLM

SETTINGS = AnalysisSettings()
CRITIC_NAMES = ("hallucination", "helpfulness", "harmfulness", "coherence", "relevancy")


@pytest.fixture
def patch_llm(monkeypatch):
    def _install(responses: dict[type[BaseModel], list[Any]]) -> FakeLLM:
        fake = FakeLLM(responses)
        monkeypatch.setattr(llm, "complete", fake.complete)
        monkeypatch.setattr(llm, "llm_configured", lambda model: True)
        return fake

    return _install


def _llm_response_span(i: int, text: str = "18C, cloudy"):
    return make_span(
        i,
        kind="llm",
        attributes={
            "gen_ai.output.messages": json.dumps(
                [{"role": "assistant", "parts": [{"type": "text", "content": text}]}]
            )
        },
    )


def _user_message_span(i: int, text: str = "weather in paris?"):
    return make_span(
        i,
        kind="llm",
        attributes={
            "gen_ai.input.messages": json.dumps(
                [{"role": "user", "parts": [{"type": "text", "content": text}]}]
            )
        },
    )


def _retriever_span(i: int, doc: str = "paris docs"):
    return make_span(
        i, kind="retriever", attributes={"retrieval.documents.0.document.content": doc}
    )


def _tool_span(i: int):
    return make_span(
        i,
        kind="tool",
        tool_name="get_weather",
        attributes={
            "gen_ai.tool.call.arguments": '{"location": "Paris"}',
            "gen_ai.tool.call.result": '{"temp": 18}',
        },
    )


def full_trace():
    """User goal + retrieval + tool action + LLM response: every metric
    applicable."""
    return make_trace(
        [_user_message_span(0), _retriever_span(1), _tool_span(2), _llm_response_span(3)]
    )


def cv(flag: bool, reason: str = "because") -> _CriticVote:
    return _CriticVote(flag=flag, reason=reason)


# --- applicability predicates ---


async def test_no_llm_response_makes_every_critic_inapplicable(patch_llm) -> None:
    patch_llm({})
    trace = make_trace([make_span(0), _tool_span(1)])
    for name in CRITIC_NAMES:
        assert await METRIC_RUNNERS[name](trace, SETTINGS) is None


async def test_no_retrieval_makes_faithfulness_inapplicable_while_critics_run(patch_llm) -> None:
    patch_llm({_CriticVote: [cv(True)]})
    trace = make_trace([_user_message_span(0), _llm_response_span(1)])
    assert await run_faithfulness(trace, SETTINGS) is None
    result = await METRIC_RUNNERS["hallucination"](trace, SETTINGS)
    assert result is not None and result.value is True


async def test_no_user_goal_makes_goal_accuracy_inapplicable(patch_llm) -> None:
    patch_llm({})
    trace = make_trace([_llm_response_span(0)])
    assert await run_goal_accuracy(trace, SETTINGS) is None


async def test_goal_without_workflow_is_inapplicable(patch_llm) -> None:
    patch_llm({})
    trace = make_trace([_user_message_span(0)])
    assert await run_goal_accuracy(trace, SETTINGS) is None


async def test_inapplicable_metric_produces_no_envelope(patch_llm) -> None:
    patch_llm({})
    trace = make_trace([make_span(0)])
    run = await run_analyzer(ANALYZERS["metric:faithfulness"], trace, SETTINGS)
    assert run is None  # no row, never a garbage score


# --- critics ---


async def test_critic_result_carries_flag_reason_and_cost(patch_llm) -> None:
    fake = patch_llm({_CriticVote: [cv(False, "all claims grounded")]})
    result = await METRIC_RUNNERS["hallucination"](full_trace(), SETTINGS)
    assert result == MetricResult(
        metric="hallucination",
        value=False,
        reason="all claims grounded",
        calls=[{"latency_ms": 5, "input_tokens": 10, "output_tokens": 2, "cost_usd": 0.001}],
    )
    # One structured call: the critic prompt as system, the rendering as user.
    (messages,) = fake.messages_for(_CriticVote)
    assert "hallucinat" in messages[0]["content"]
    assert messages[1]["content"].startswith("system: ")
    assert "18C, cloudy" in messages[1]["content"]


async def test_critic_envelope_round_trips(patch_llm) -> None:
    patch_llm({_CriticVote: [cv(True)]})
    run = await run_analyzer(ANALYZERS["metric:harmfulness"], full_trace(), SETTINGS)
    assert run is not None
    assert run.analyzer == "metric:harmfulness"
    assert run.model_id == SETTINGS.judge_model
    assert run.confidence is None  # metric scores are not labels
    output = MetricResult.model_validate(json.loads(run.model_dump_json())["output"])
    assert output.value is True


async def test_critic_majority_fold_at_three_votes(patch_llm) -> None:
    settings = AnalysisSettings(critic_votes=3)
    patch_llm({_CriticVote: [cv(True, "first"), cv(False, "dissent"), cv(True, "third")]})
    result = await METRIC_RUNNERS["coherence"](full_trace(), settings)
    assert result is not None
    assert result.value is True
    assert result.reason == "first"  # first vote matching the majority flag
    assert len(result.calls) == 3


async def test_critic_tie_fails_open(patch_llm) -> None:
    settings = AnalysisSettings(critic_votes=2)
    patch_llm({_CriticVote: [cv(True), cv(False)]})
    assert await METRIC_RUNNERS["relevancy"](full_trace(), settings) is None


async def test_malformed_vote_is_dropped_not_fatal(patch_llm) -> None:
    settings = AnalysisSettings(critic_votes=3)
    patch_llm({_CriticVote: [cv(True), llm.MalformedResponse(META), cv(True)]})
    result = await METRIC_RUNNERS["helpfulness"](full_trace(), settings)
    assert result is not None
    assert result.value is True
    assert len(result.calls) == 3  # the malformed call's cost still rides


async def test_all_votes_malformed_fails_open(patch_llm) -> None:
    patch_llm({_CriticVote: [llm.MalformedResponse(META)]})
    assert await METRIC_RUNNERS["hallucination"](full_trace(), SETTINGS) is None


async def test_transient_error_propagates(patch_llm) -> None:
    patch_llm({_CriticVote: [RuntimeError("provider hiccup")]})
    with pytest.raises(RuntimeError):
        await METRIC_RUNNERS["hallucination"](full_trace(), SETTINGS)


# --- keyless ---


async def test_keyless_skips_every_metric(monkeypatch) -> None:
    monkeypatch.setattr(llm, "llm_configured", lambda model: False)
    for name in METRICS:
        assert await METRIC_RUNNERS[name](full_trace(), SETTINGS) is None


# --- the default-set knob ---


def test_default_settings_enable_the_full_locked_catalog() -> None:
    assert [s.name for s in enabled_metric_specs(SETTINGS)] == [f"metric:{n}" for n in METRICS]


def test_metric_subset_is_honored() -> None:
    settings = AnalysisSettings(metrics="harmfulness,faithfulness")
    assert [s.name for s in enabled_metric_specs(settings)] == [
        "metric:harmfulness",
        "metric:faithfulness",
    ]


def test_unknown_metric_name_fails_at_settings_load() -> None:
    with pytest.raises(ValidationError, match="unknown metrics"):
        AnalysisSettings(metrics="hallucination,bogus")


def test_duplicate_metric_names_dedupe_order_preserving() -> None:
    settings = AnalysisSettings(metrics="faithfulness,hallucination,faithfulness")
    assert settings.metric_names == ["faithfulness", "hallucination"]


# --- the concurrent metric-set runner ---


async def test_run_metric_set_returns_applicable_envelopes_in_spec_order(patch_llm) -> None:
    settings = AnalysisSettings(metrics="harmfulness,hallucination,faithfulness")
    patch_llm({_CriticVote: [cv(True), cv(False)]})
    # No retrieval span: faithfulness is inapplicable and drops out.
    trace = make_trace([_user_message_span(0), _llm_response_span(1)])
    runs = await run_metric_set(trace, settings)
    assert [run.analyzer for run in runs] == ["metric:harmfulness", "metric:hallucination"]


async def test_run_metric_set_settles_all_before_raising(patch_llm, monkeypatch) -> None:
    """One failing metric must not abandon the others mid-flight, and its
    typed error must propagate for the worker's retry classification."""
    settings = AnalysisSettings(metrics="hallucination,helpfulness")
    patch_llm({_CriticVote: [llm.PermanentAnalysisError("bad request"), cv(True)]})
    with pytest.raises(llm.PermanentAnalysisError):
        await run_metric_set(full_trace(), settings)


async def test_run_metric_set_runs_concurrently(monkeypatch) -> None:
    """Two stalled metrics overlap: total wall time is one stall, not two."""
    import asyncio

    in_flight = 0
    peak = 0

    async def stalled_complete(model, messages, schema, temperature):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.05)
        in_flight -= 1
        return cv(False), META

    monkeypatch.setattr(llm, "complete", stalled_complete)
    monkeypatch.setattr(llm, "llm_configured", lambda model: True)
    settings = AnalysisSettings(metrics="hallucination,helpfulness,coherence")
    runs = await run_metric_set(full_trace(), settings)
    assert len(runs) == 3
    assert peak == 3


# --- RAGAS-backed metrics (real pinned prompt classes, fake LLM) ---


def _faithfulness_schemas():
    from ragas.metrics.collections.faithfulness.metric import (
        NLIStatementOutput,
        StatementGeneratorOutput,
    )
    from ragas.metrics.collections.faithfulness.util import StatementFaithfulnessAnswer

    return StatementGeneratorOutput, NLIStatementOutput, StatementFaithfulnessAnswer


def _goal_schemas():
    from ragas.metrics.collections.agent_goal_accuracy.metric import (
        CompareOutcomeOutput,
        WorkflowOutput,
    )

    return WorkflowOutput, CompareOutcomeOutput


async def test_faithfulness_scores_through_the_adapter(patch_llm) -> None:
    StatementGeneratorOutput, NLIStatementOutput, Answer = _faithfulness_schemas()
    patch_llm(
        {
            StatementGeneratorOutput: [
                StatementGeneratorOutput(statements=["it is 18C", "it is sunny"])
            ],
            NLIStatementOutput: [
                NLIStatementOutput(
                    statements=[
                        Answer(statement="it is 18C", reason="in context", verdict=1),
                        Answer(statement="it is sunny", reason="contradicted", verdict=0),
                    ]
                )
            ],
        }
    )
    result = await run_faithfulness(full_trace(), SETTINGS)
    assert result is not None
    assert result.metric == "faithfulness"
    assert result.value == 0.5  # 1 of 2 statements grounded
    assert len(result.calls) == 2  # statement generation + NLI verdicts


async def test_faithfulness_with_no_statements_fails_open(patch_llm) -> None:
    StatementGeneratorOutput, _, _ = _faithfulness_schemas()
    patch_llm({StatementGeneratorOutput: [StatementGeneratorOutput(statements=[])]})
    # RAGAS's no-statements path yields NaN — not a score, no row.
    assert await run_faithfulness(full_trace(), SETTINGS) is None


async def test_goal_accuracy_scores_through_the_adapter(patch_llm) -> None:
    WorkflowOutput, CompareOutcomeOutput = _goal_schemas()
    fake = patch_llm(
        {
            WorkflowOutput: [
                WorkflowOutput(user_goal="learn the weather", end_state="weather reported")
            ],
            CompareOutcomeOutput: [CompareOutcomeOutput(reason="goal met", verdict="1")],
        }
    )
    result = await run_goal_accuracy(full_trace(), SETTINGS)
    assert result is not None
    assert result.metric == "goal_accuracy"
    assert result.value == 1.0
    assert len(result.calls) == 2  # goal inference + outcome comparison
    # Our trace shape reached the conversation: goal, tool action, response.
    (workflow_messages,) = fake.messages_for(WorkflowOutput)
    conversation = workflow_messages[0]["content"]
    assert "weather in paris?" in conversation
    assert "get_weather" in conversation
    assert "18C, cloudy" in conversation


async def test_ragas_malformed_response_fails_open(patch_llm) -> None:
    StatementGeneratorOutput, _, _ = _faithfulness_schemas()
    patch_llm({StatementGeneratorOutput: [llm.MalformedResponse(META)]})
    assert await run_faithfulness(full_trace(), SETTINGS) is None
