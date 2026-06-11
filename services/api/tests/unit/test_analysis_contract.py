"""Contract sanity: envelope round-trip through JSON, jsonb-safe dumps,
input-model construction from both sources."""

import json

import pytest

from app.analysis import (
    AnalyzerRun,
    JudgeVerdict,
    JudgeVote,
    MetricResult,
    SignalsResult,
    TraceInput,
    run_analyzer,
)
from app.analysis.config import AnalysisSettings
from app.analysis.registry import ANALYZERS, StubResult
from tests.unit.analysis_factories import load_fixture_trace


async def test_stub_round_trips_through_envelope_json() -> None:
    trace = load_fixture_trace("failure-trace")
    spec = ANALYZERS["stub"]

    run = await run_analyzer(spec, trace, AnalysisSettings())
    assert run is not None

    # Dump → parse → re-validate output via the registry's result model:
    # exactly what the offline runner emits and A2's worker will persist.
    parsed = AnalyzerRun.model_validate_json(run.model_dump_json())
    assert parsed == run
    output = spec.result_model.model_validate(parsed.output)
    assert output == StubResult(
        span_count=3, llm_span_count=1, tool_span_count=1, error_span_count=2
    )
    assert parsed.analyzer == "stub"
    assert parsed.model_id is None
    assert parsed.confidence is None


async def test_stub_is_deterministic() -> None:
    trace = load_fixture_trace("agent-session")
    spec = ANALYZERS["stub"]
    first = await run_analyzer(spec, trace, AnalysisSettings())
    second = await run_analyzer(spec, trace, AnalysisSettings())
    assert first == second


@pytest.mark.parametrize(
    "model",
    [
        SignalsResult(has_retry_loop=True, loop_kind="cycle", failure_suspected=True),
        JudgeVerdict(
            outcome="failure",
            outcome_confidence=0.67,
            failure_mode="system_failure",
            votes=[JudgeVote(call="outcome", value="failure", reasoning="errors end the run")],
        ),
        MetricResult(metric="faithfulness", value=0.8, reason="grounded"),
        MetricResult(metric="hallucination", value=False),
    ],
)
def test_result_models_dump_jsonb_safe(model) -> None:
    dumped = model.model_dump(mode="json")
    assert json.loads(json.dumps(dumped)) == dumped


def test_trace_input_from_db_rows_matches_import_path() -> None:
    fixture = load_fixture_trace("minimal")
    trace_row = {
        **fixture.model_dump(exclude={"spans", "trace_id"}),
        "id": "00000000-0000-0000-0000-000000000001",
        "owner_id": "ignored",
        "upload_id": "ignored",
    }
    span_rows = [s.model_dump() for s in fixture.spans]
    from_db = TraceInput.from_db_rows(trace_row, span_rows)
    assert from_db.trace_id == "00000000-0000-0000-0000-000000000001"
    assert from_db.model_dump(exclude={"trace_id"}) == fixture.model_dump(exclude={"trace_id"})
