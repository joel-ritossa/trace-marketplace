"""Importer edge cases the fixtures don't cover."""

import base64

import pytest

from app.importers import otlp
from app.importers.errors import PermanentIngestError
from app.importers.otlp.decode import decode_any_value, decode_attributes

TRACE_ID = "11111111111111111111111111111111"


def make_span(span_id: str = "a000000000000001", **overrides) -> dict:
    span = {
        "traceId": TRACE_ID,
        "spanId": span_id,
        "name": "span",
        "startTimeUnixNano": "1768471200000000000",
        "endTimeUnixNano": "1768471201000000000",
        "attributes": [],
    }
    span.update(overrides)
    return span


def payload_of(*spans: dict) -> dict:
    return {
        "resourceSpans": [{"resource": {"attributes": []}, "scopeSpans": [{"spans": list(spans)}]}]
    }


class TestAnyValue:
    def test_scalar_variants(self) -> None:
        assert decode_any_value({"stringValue": "x"}) == "x"
        assert decode_any_value({"intValue": "42"}) == 42  # int64 arrives as a string
        assert decode_any_value({"intValue": 42}) == 42
        assert decode_any_value({"doubleValue": 1.5}) == 1.5
        assert decode_any_value({"boolValue": True}) is True
        assert decode_any_value({"bytesValue": "aGk="}) == "aGk="

    def test_nested_variants(self) -> None:
        assert decode_any_value(
            {"arrayValue": {"values": [{"stringValue": "a"}, {"intValue": "1"}]}}
        ) == ["a", 1]
        assert decode_any_value(
            {"kvlistValue": {"values": [{"key": "k", "value": {"stringValue": "v"}}]}}
        ) == {"k": "v"}

    def test_garbage_decodes_to_none(self) -> None:
        assert decode_any_value({"intValue": "not-a-number"}) is None
        assert decode_any_value("bare string") is None
        assert decode_any_value({}) is None

    def test_attributes_list_to_dict(self) -> None:
        duplicate_keys = [
            {"key": "a", "value": {"stringValue": "1"}},
            {"key": "a", "value": {"stringValue": "2"}},
        ]
        assert decode_attributes(duplicate_keys) == {"a": "2"}  # last write wins
        assert decode_attributes("not-a-list") == {}


class TestIds:
    def test_base64_ids_normalize_to_hex(self) -> None:
        trace_hex = "0af7651916cd43dd8448eb211c80319c"
        span_hex = "b7ad6b7169203331"
        span = make_span(
            traceId=base64.b64encode(bytes.fromhex(trace_hex)).decode(),
            spanId=base64.b64encode(bytes.fromhex(span_hex)).decode(),
        )
        result = otlp.import_payload(payload_of(span))
        assert result.traces[0].source_trace_id == trace_hex
        assert result.traces[0].spans[0].source_span_id == span_hex

    def test_uppercase_hex_normalizes(self) -> None:
        span = make_span(traceId=TRACE_ID.upper())
        result = otlp.import_payload(payload_of(span))
        assert result.traces[0].source_trace_id == TRACE_ID

    def test_missing_parent_is_none(self) -> None:
        result = otlp.import_payload(payload_of(make_span()))
        assert result.traces[0].spans[0].source_parent_span_id is None


class TestValidation:
    def test_no_valid_spans_is_permanent(self) -> None:
        with pytest.raises(PermanentIngestError):
            otlp.import_payload(payload_of(make_span(spanId=None)))

    def test_out_of_range_timestamp_skips_span(self) -> None:
        """Absurd nanos overflow datetime; the span must skip, not crash."""
        bad = make_span("b000000000000001", startTimeUnixNano="9" * 30)
        result = otlp.import_payload(payload_of(make_span(), bad))
        assert len(result.traces[0].spans) == 1
        assert result.parse_warnings["skipped_spans"] == 1
        assert "timestamps" in result.parse_warnings["samples"][0]

    def test_skip_samples_truncate_payload_content(self) -> None:
        """Skip reasons reach error messages and logs; a giant value crammed
        into spanId must not ride along unbounded."""
        result = otlp.import_payload(payload_of(make_span(), make_span(spanId="x" * 10_000)))
        assert len(result.parse_warnings["samples"][0]) < 200

    def test_empty_resource_spans_is_permanent(self) -> None:
        with pytest.raises(PermanentIngestError):
            otlp.import_payload({"resourceSpans": []})

    def test_status_enum_names_accepted(self) -> None:
        span = make_span(status={"code": "STATUS_CODE_ERROR", "message": "boom"})
        result = otlp.import_payload(payload_of(span))
        assert result.traces[0].spans[0].status == "error"
        assert result.traces[0].status == "error"


class TestGrouping:
    def test_multiple_traces_in_one_payload(self) -> None:
        other_trace = "22222222222222222222222222222222"
        spans = [
            make_span(),
            make_span(
                "b000000000000001",
                traceId=other_trace,
                startTimeUnixNano="1768471300000000000",
                endTimeUnixNano="1768471301000000000",
            ),
        ]
        result = otlp.import_payload(payload_of(*spans))
        assert [t.source_trace_id for t in result.traces] == [TRACE_ID, other_trace]
        assert all(t.span_count == 1 for t in result.traces)

    def test_trace_name_prefers_root_span(self) -> None:
        spans = [
            make_span(
                "a000000000000002",
                name="child",
                parentSpanId="a000000000000001",
                startTimeUnixNano="1768471200000000000",
                endTimeUnixNano="1768471200500000000",
            ),
            make_span(
                "a000000000000001",
                name="root",
                startTimeUnixNano="1768471200100000000",
                endTimeUnixNano="1768471201000000000",
            ),
        ]
        result = otlp.import_payload(payload_of(*spans))
        assert result.traces[0].name == "root"

    def test_orphan_parent_still_imports(self) -> None:
        span = make_span(parentSpanId="feedfeedfeedfeed")
        result = otlp.import_payload(payload_of(span))
        assert result.traces[0].spans[0].source_parent_span_id == "feedfeedfeedfeed"


class TestKindPrecedence:
    def test_genai_operation_wins_over_openinference(self) -> None:
        span = make_span(
            attributes=[
                {"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}},
                {"key": "openinference.span.kind", "value": {"stringValue": "LLM"}},
            ]
        )
        result = otlp.import_payload(payload_of(span))
        assert result.traces[0].spans[0].kind == "tool"

    def test_unknown_operation_falls_through(self) -> None:
        span = make_span(
            attributes=[
                {"key": "gen_ai.operation.name", "value": {"stringValue": "mystery_op"}},
                {"key": "traceloop.span.kind", "value": {"stringValue": "workflow"}},
            ]
        )
        result = otlp.import_payload(payload_of(span))
        assert result.traces[0].spans[0].kind == "chain"

    def test_legacy_token_aliases(self) -> None:
        span = make_span(
            attributes=[
                {"key": "gen_ai.usage.prompt_tokens", "value": {"intValue": "10"}},
                {"key": "gen_ai.usage.completion_tokens", "value": {"intValue": "5"}},
            ]
        )
        result = otlp.import_payload(payload_of(span))
        s = result.traces[0].spans[0]
        assert (s.input_tokens, s.output_tokens, s.total_tokens) == (10, 5, 15)
