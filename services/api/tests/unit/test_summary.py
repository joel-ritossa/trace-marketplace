"""Behavior-summary generator: display bounds, fail-open paths, the registry
envelope — all scripted fakes, no network."""

import pytest
from pydantic import BaseModel

from app.analysis import llm
from app.analysis.config import AnalysisSettings
from app.analysis.models import SummaryResult
from app.analysis.prompts import summary as summary_prompt
from app.analysis.registry import ANALYZERS, run_analyzer
from app.analysis.summary import _SummaryDraft, normalize_steps, run_summary
from tests.unit.analysis_factories import make_span, make_trace
from tests.unit.test_judge import META, FakeLLM

SETTINGS = AnalysisSettings()


@pytest.fixture
def patch_llm(monkeypatch):
    def _install(responses: dict[type[BaseModel], list]) -> FakeLLM:
        fake = FakeLLM(responses)
        monkeypatch.setattr(llm, "complete", fake.complete)
        monkeypatch.setattr(llm, "llm_configured", lambda model: True)
        return fake

    return _install


def trace():
    return make_trace([make_span(0, kind="llm"), make_span(1, kind="tool", tool_name="search")])


def draft(gist: str = "A weather lookup run that ended with an answer.", steps=None):
    return _SummaryDraft(
        gist=gist, steps=steps if steps is not None else ["Called search", "Replied to the user"]
    )


# --- step normalization ---


def test_normalize_steps_trims_and_drops_empties() -> None:
    assert normalize_steps(["  Called search  ", "", "   "]) == ["Called search"]


def test_normalize_steps_clamps_length_and_count() -> None:
    steps = normalize_steps(["x" * 400] + [f"step {i}" for i in range(12)])
    assert len(steps) == 10
    assert steps[0] == "x" * 300


# --- run_summary ---


async def test_happy_path_carries_call_meta(patch_llm) -> None:
    fake = patch_llm({_SummaryDraft: [draft(gist="  Tidy run.  ")]})
    result = await run_summary(trace(), SETTINGS)
    assert result == SummaryResult(
        gist="Tidy run.",
        steps=["Called search", "Replied to the user"],
        calls=[META.model_dump()],
    )
    # One call, against the summary prompt, on the judge's model.
    assert len(fake.calls) == 1
    assert fake.calls[0]["messages"][0] == {"role": "system", "content": summary_prompt.V1}
    assert fake.calls[0]["model"] == SETTINGS.judge_model


async def test_gist_clamped_to_display_bound(patch_llm) -> None:
    patch_llm({_SummaryDraft: [draft(gist="g" * 1000)]})
    result = await run_summary(trace(), SETTINGS)
    assert result is not None and len(result.gist or "") == 500


async def test_partial_output_still_produces_result(patch_llm) -> None:
    patch_llm({_SummaryDraft: [draft(gist="   ", steps=["keeper"])]})
    result = await run_summary(trace(), SETTINGS)
    assert result is not None and result.gist is None and result.steps == ["keeper"]


async def test_empty_output_fails_open(patch_llm) -> None:
    patch_llm({_SummaryDraft: [draft(gist=" ", steps=["", "  "])]})
    assert await run_summary(trace(), SETTINGS) is None


async def test_malformed_response_fails_open(patch_llm) -> None:
    patch_llm({_SummaryDraft: [llm.MalformedResponse(META)]})
    assert await run_summary(trace(), SETTINGS) is None


async def test_keyless_is_inapplicable(monkeypatch) -> None:
    monkeypatch.setattr(llm, "llm_configured", lambda model: False)
    assert await run_summary(trace(), SETTINGS) is None


async def test_registry_envelope(patch_llm) -> None:
    patch_llm({_SummaryDraft: [draft()]})
    run = await run_analyzer(ANALYZERS["summary"], trace(), SETTINGS)
    assert run is not None
    assert run.analyzer == "summary"
    assert run.model_id == SETTINGS.judge_model
    assert run.confidence is None  # prose has no vote share
    SummaryResult.model_validate(run.output)
