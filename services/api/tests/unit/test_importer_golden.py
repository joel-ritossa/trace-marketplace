"""Golden tests: fixture payload in → exact normalized output.

Regenerate goldens after an intentional importer change with:
    uv run python -m tests.unit.golden.regenerate
then review the diff — the golden files are the importer's contract.
"""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from app.importers import otlp

FIXTURES_DIR = Path(__file__).parents[4] / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"

FIXTURES = ["agent-session", "failure-trace", "minimal", "malformed-spans"]


def result_to_dict(result: otlp.ImportResult) -> dict[str, Any]:
    """JSON-safe form of an ImportResult (datetimes → ISO strings)."""

    def default(value: Any) -> str:
        return value.isoformat()

    return json.loads(json.dumps(dataclasses.asdict(result), default=default))


@pytest.mark.parametrize("name", FIXTURES)
def test_fixture_matches_golden(name: str) -> None:
    payload = json.loads((FIXTURES_DIR / f"{name}.json").read_text())
    expected = json.loads((GOLDEN_DIR / f"{name}.expected.json").read_text())
    assert result_to_dict(otlp.import_payload(payload)) == expected


def test_import_is_deterministic() -> None:
    payload = json.loads((FIXTURES_DIR / "agent-session.json").read_text())
    assert result_to_dict(otlp.import_payload(payload)) == result_to_dict(
        otlp.import_payload(payload)
    )
