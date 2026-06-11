"""Golden harness corpus: real-shaped session logs in → exact normalized output.

`fixtures/golden/` holds one synthetic session per supported harness whose
*structure* mirrors real logs (verified against live ~/.claude, ~/.codex,
~/.cursor captures): Claude Code responses split across same-`message.id`
records with cache-heavy usage, sidechain/meta records, thinking blocks;
Codex reasoning summaries, `token_count` events, `tool_search_*` calls, an
unpaired call; Cursor id-less multi-block tool_use records with no clocks.

Each converts through the real pipeline (sniff → convert → normalize) and
must match its golden snapshot exactly. Regenerate after an intentional
importer change with:
    uv run python -m tests.unit.golden.regenerate
then review the diff — the golden files are the converter's contract.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import importers
from app.importers import otlp, sessions
from app.redaction import OFFLINE_SALT
from tests.unit.test_importer_golden import GOLDEN_DIR, result_to_dict

CORPUS_DIR = Path(__file__).parents[4] / "fixtures" / "golden"
ANCHOR = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

SESSIONS = {
    "claude-code": "anthropic_jsonl",
    "codex": "codex_jsonl",
    "cursor": "anthropic_jsonl",
}


def convert_session(name: str) -> otlp.ImportResult:
    data = (CORPUS_DIR / f"{name}.jsonl").read_bytes()
    assert importers.sniff_format(data) == SESSIONS[name]
    records = sessions.parse_records(data)
    payload = sessions.convert(SESSIONS[name], records, session_id=name, anchor=ANCHOR)
    return otlp.import_payload(payload, redaction_salt=OFFLINE_SALT)


@pytest.mark.parametrize("name", sorted(SESSIONS))
def test_session_matches_golden(name: str) -> None:
    expected = json.loads((GOLDEN_DIR / f"{name}.expected.json").read_text())
    assert result_to_dict(convert_session(name)) == expected
