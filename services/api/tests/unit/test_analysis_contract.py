"""Contract sanity: jsonb-safe dumps and input-model construction from
both sources."""

import json

from app.analysis import SignalsResult, TraceInput
from tests.unit.analysis_factories import load_fixture_trace


def test_signals_dump_jsonb_safe() -> None:
    dumped = SignalsResult(has_retry_loop=True, loop_kind="cycle").model_dump(mode="json")
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
