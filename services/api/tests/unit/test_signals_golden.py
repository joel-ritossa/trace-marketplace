"""Signals golden tests: fixture in → exact SignalsResult out.

Regenerate after an intentional signals change with:
    uv run python -m tests.unit.golden.regenerate
then review the diff — a golden change without a SIGNALS_VERSION bump is
a contract violation.
"""

import json
from pathlib import Path

import pytest

from app.analysis.config import AnalysisSettings
from app.analysis.signals import run_signals
from tests.unit.analysis_factories import load_fixture_trace

GOLDEN_DIR = Path(__file__).parent / "golden"

SIGNALS_FIXTURES = ["agent-session", "failure-trace", "malformed-spans", "minimal"]

# Explicit threshold (not env-derived) so goldens are stable anywhere.
SIGNALS_SETTINGS = AnalysisSettings(loop_n=3)


@pytest.mark.parametrize("name", SIGNALS_FIXTURES)
async def test_fixture_signals_match_golden(name: str) -> None:
    result = await run_signals(load_fixture_trace(name), SIGNALS_SETTINGS)
    expected = json.loads((GOLDEN_DIR / f"{name}.signals.expected.json").read_text())
    assert result.model_dump(mode="json") == expected
