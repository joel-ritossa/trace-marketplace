"""Renderer golden tests: fixture in → exact RenderedTrace out.

The goldens pin the renderer's determinism contract at a fixed config.
Regenerate after an intentional renderer change with:
    uv run python -m tests.unit.golden.regenerate
then review the diff — a golden change without a RENDERER_VERSION bump is
a contract violation.
"""

import json
from pathlib import Path

import pytest

from app.analysis import RendererConfig, render_trace
from tests.unit.analysis_factories import load_fixture_trace

GOLDEN_DIR = Path(__file__).parent / "golden"

RENDER_FIXTURES = ["agent-session", "failure-trace", "minimal"]

# Explicit config (not env-derived settings) so goldens are stable anywhere.
GOLDEN_CONFIG = RendererConfig(
    budget_chars=60_000,
    final_steps=8,
    tool_field_cap_chars=2_000,
    conversation_cap_chars=8_000,
)


@pytest.mark.parametrize("name", RENDER_FIXTURES)
def test_fixture_rendering_matches_golden(name: str) -> None:
    rendered = render_trace(load_fixture_trace(name), GOLDEN_CONFIG)
    expected = json.loads((GOLDEN_DIR / f"{name}.render.expected.json").read_text())
    assert rendered.model_dump(mode="json") == expected


@pytest.mark.parametrize("name", RENDER_FIXTURES)
def test_rendering_is_deterministic(name: str) -> None:
    first = render_trace(load_fixture_trace(name), GOLDEN_CONFIG)
    second = render_trace(load_fixture_trace(name), GOLDEN_CONFIG)
    assert first.model_dump_json() == second.model_dump_json()
