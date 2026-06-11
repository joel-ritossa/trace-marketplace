"""Listing-copy generator: normalization bounds, fail-open paths, the
registry envelope — all scripted fakes, no network."""

import pytest
from pydantic import BaseModel

from app.analysis import llm
from app.analysis.config import AnalysisSettings
from app.analysis.listing import _ListingDraft, normalize_tags, run_listing
from app.analysis.models import ListingResult
from app.analysis.prompts import listing as listing_prompt
from app.analysis.registry import ANALYZERS, run_analyzer
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


def draft(description: str = "A weather lookup run. Shows clean tool use.", tags=None):
    return _ListingDraft(description=description, tags=tags or ["tool-use", "weather"])


# --- tag normalization ---


def test_normalize_tags_kebab_cases_and_dedupes() -> None:
    assert normalize_tags(["Tool Use", "tool_use", " tool-use ", "Web  Research"]) == [
        "tool-use",
        "web-research",
    ]


def test_normalize_tags_drops_empty_and_oversize() -> None:
    assert normalize_tags(["", "   ", "-", "x" * 81, "ok"]) == ["ok"]


def test_normalize_tags_caps_count() -> None:
    assert normalize_tags([f"tag-{i}" for i in range(10)]) == [f"tag-{i}" for i in range(6)]


# --- run_listing ---


async def test_happy_path_normalizes_and_carries_call_meta(patch_llm) -> None:
    fake = patch_llm({_ListingDraft: [draft(description="  Solid trace.  ", tags=["Tool Use"])]})
    result = await run_listing(trace(), SETTINGS)
    assert result == ListingResult(
        description="Solid trace.",
        tags=["tool-use"],
        calls=[META.model_dump()],
    )
    # One call, against the listing prompt, on the judge's model.
    assert len(fake.calls) == 1
    assert fake.calls[0]["messages"][0] == {"role": "system", "content": listing_prompt.V1}
    assert fake.calls[0]["model"] == SETTINGS.judge_model


async def test_description_clamped_to_owner_input_bound(patch_llm) -> None:
    patch_llm({_ListingDraft: [draft(description="d" * 3000)]})
    result = await run_listing(trace(), SETTINGS)
    assert result is not None and len(result.description or "") == 2000


async def test_partial_output_still_produces_result(patch_llm) -> None:
    patch_llm({_ListingDraft: [draft(description="   ", tags=["keeper"])]})
    result = await run_listing(trace(), SETTINGS)
    assert result is not None and result.description is None and result.tags == ["keeper"]


async def test_empty_output_fails_open(patch_llm) -> None:
    patch_llm({_ListingDraft: [draft(description=" ", tags=["", "-"])]})
    assert await run_listing(trace(), SETTINGS) is None


async def test_malformed_response_fails_open(patch_llm) -> None:
    patch_llm({_ListingDraft: [llm.MalformedResponse(META)]})
    assert await run_listing(trace(), SETTINGS) is None


async def test_keyless_is_inapplicable(monkeypatch) -> None:
    monkeypatch.setattr(llm, "llm_configured", lambda model: False)
    assert await run_listing(trace(), SETTINGS) is None


async def test_registry_envelope(patch_llm) -> None:
    patch_llm({_ListingDraft: [draft()]})
    run = await run_analyzer(ANALYZERS["listing"], trace(), SETTINGS)
    assert run is not None
    assert run.analyzer == "listing"
    assert run.model_id == SETTINGS.judge_model
    assert run.confidence is None  # prose has no vote share
    ListingResult.model_validate(run.output)
