"""A4 filter vocabulary: TraceFilterQuery parsing (strict vs format-checked
values, the metric grammar), the SQL clause builders, the subscription
query's strict shape, and labels.jsonl line assembly."""

import json

import pytest
from pydantic import ValidationError

from app.queries.traces import analysis_clauses, filter_clauses, make_param, stage1_clauses
from app.routers.bulk import _label_line
from app.schemas.subscription import SubscriptionQuery
from app.schemas.trace import TraceFilterQuery, parse_metric


class TestParsing:
    def test_csv_strict_sets(self) -> None:
        q = TraceFilterQuery(outcome="failure,indeterminate", outcome_provenance="human")
        assert q.outcome == "failure,indeterminate"
        with pytest.raises(ValidationError, match="unknown outcome"):
            TraceFilterQuery(outcome="failure,bogus")
        with pytest.raises(ValidationError, match="unknown provenance"):
            TraceFilterQuery(failure_mode_provenance="machine,llm")
        with pytest.raises(ValidationError, match="unknown loop_kind"):
            TraceFilterQuery(loop_kind="spiral")

    def test_taxonomies_format_checked_only(self) -> None:
        # Evolving vocabularies (A4 decision 2): unknown-but-well-formed
        # values parse — soft-retired values must stay matchable.
        q = TraceFilterQuery(failure_mode="some_future_mode", task_category="coding,other")
        assert q.failure_mode == "some_future_mode"
        for bad in ("Bad-Value", "1leading", "spaced value"):
            with pytest.raises(ValidationError):
                TraceFilterQuery(failure_mode=bad)

    def test_metric_grammar(self) -> None:
        assert parse_metric("faithfulness:0.8") == ("faithfulness", 0.8)
        assert parse_metric("noise_sensitivity:true") == ("noise_sensitivity", True)
        for bad in ("faithfulness", "faithfulness:", ":0.8", "Faith:0.8", "f:maybe"):
            with pytest.raises(ValueError):
                parse_metric(bad)
        with pytest.raises(ValidationError):
            TraceFilterQuery(metric=["faithfulness:high"])
        assert TraceFilterQuery(metric=["a:0.5", "b:true"]).parsed_metrics == [
            ("a", 0.5),
            ("b", True),
        ]

    def test_bounds(self) -> None:
        with pytest.raises(ValidationError):
            TraceFilterQuery(outcome_confidence_gte=1.5)
        with pytest.raises(ValidationError):
            TraceFilterQuery(duration_ms_gte=-1)
        assert TraceFilterQuery(outcome_confidence_gte=0.8).outcome_confidence_gte == 0.8

    def test_from_to_aliases(self) -> None:
        q = TraceFilterQuery.model_validate({"from": "2026-01-01T00:00:00Z"})
        assert q.date_from is not None

    def test_has_analysis_predicate(self) -> None:
        # Stage-1 fields and the trace-column gtes don't trip the
        # excluded-unanalyzed note; analysis-backed predicates do.
        stage1_only = TraceFilterQuery(q="x", duration_ms_gte=5, total_tokens_gte=1)
        assert not stage1_only.has_analysis_predicate
        assert TraceFilterQuery(outcome="failure").has_analysis_predicate
        assert TraceFilterQuery(has_retry_loop=False).has_analysis_predicate
        assert TraceFilterQuery(metric=["f:0.1"]).has_analysis_predicate
        assert TraceFilterQuery(llm_call_count_gte=0).has_analysis_predicate


class TestSubscriptionQuery:
    def test_unknown_and_shape_params_forbidden(self) -> None:
        # Request shape is not query: scope/sort/pagination are 422.
        for extra in ({"scope": "marketplace"}, {"sort": "created_at"}, {"limit": 5}, {"nope": 1}):
            with pytest.raises(ValidationError):
                SubscriptionQuery.model_validate({"outcome": "failure", **extra})

    def test_stored_round_trip(self) -> None:
        q = SubscriptionQuery.model_validate(
            {"outcome": "failure", "outcome_confidence_gte": 0.8, "metric": ["faithfulness:0.8"]}
        )
        stored = q.stored()
        # Defaults dropped: the stored map is exactly the active predicates.
        assert stored == {
            "outcome": "failure",
            "outcome_confidence_gte": 0.8,
            "metric": ["faithfulness:0.8"],
        }
        assert SubscriptionQuery.model_validate(stored).stored() == stored

    def test_stored_uses_param_names(self) -> None:
        q = SubscriptionQuery.model_validate({"from": "2026-01-01T00:00:00Z"})
        assert list(q.stored()) == ["from"]

    def test_empty_query_rejected_without_anchor(self) -> None:
        # A subscribe-to-everything subscription is a footgun: no active
        # predicate (defaults and no-op values included) is a 422. The
        # floor lives on the request, where the behavior anchor counts as
        # a predicate (docs/proposals/similar-behavior.md).
        from app.schemas.subscription import SubscriptionCreateRequest

        for empty in ({}, {"has_errors": False}, {"metric": []}):
            assert SubscriptionQuery.model_validate(empty).stored() == {}
            with pytest.raises(ValidationError, match="at least one filter"):
                SubscriptionCreateRequest(name="s", query=empty)


class TestClauseBuilders:
    def test_stage1_vs_analysis_split(self) -> None:
        q = TraceFilterQuery(
            provider="openai", duration_ms_gte=100, outcome="failure", metric=["f:0.5"]
        )
        args: list = []
        param = make_param(args)
        stage1 = stage1_clauses(q, param)
        analysis = analysis_clauses(q, param)
        assert ["t.provider = $1", "t.duration_ms >= $2"] == stage1
        assert analysis[0] == "ta.outcome = any($3::text[])"
        assert args[2] == ["failure"]
        # The metric min-bound guards on type so flags never error a query.
        assert "jsonb_typeof(ta.metric_scores -> $4) = 'number'" in analysis[1]
        assert args[3:] == ["f", 0.5]

    def test_metric_flag_clause(self) -> None:
        args: list = []
        clauses = analysis_clauses(TraceFilterQuery(metric=["recovered:true"]), make_param(args))
        assert clauses == ["ta.metric_scores -> $1 = 'true'::jsonb"]
        assert args == ["recovered"]

    def test_boolean_false_is_a_filter(self) -> None:
        args: list = []
        clauses = analysis_clauses(TraceFilterQuery(has_retry_loop=False), make_param(args))
        assert clauses == ["ta.has_retry_loop = $1"]
        assert args == [False]

    def test_empty_filters_no_clauses(self) -> None:
        assert filter_clauses(TraceFilterQuery(), make_param([])) == []


class TestLabelLine:
    def test_analyzed_row(self) -> None:
        row = {
            "llm_status": "complete",
            "outcome": "failure",
            "outcome_confidence": 0.9,
            "outcome_provenance": "machine",
            "failure_mode": None,
            "failure_mode_confidence": None,
            "failure_mode_provenance": None,
            "task_category": "coding",
            "task_category_confidence": 0.7,
            "task_category_provenance": "human",
            "metric_scores": {"faithfulness": 0.81},
            "has_retry_loop": True,
            "loop_kind": "cycle",
            "recovered_from_error": False,
            "truncation_suspected": None,
            "llm_call_count": 3,
            "tool_call_count": 2,
            "analyzer_versions": {"signals": "1", "judge": "1"},
        }
        line = json.loads(_label_line("t-1", row))  # type: ignore[arg-type]
        assert line["trace_id"] == "t-1"
        assert line["outcome"] == {"value": "failure", "confidence": 0.9, "provenance": "machine"}
        assert line["failure_mode"] is None  # fail-open field stays honest
        assert line["task_category"]["provenance"] == "human"
        assert line["metric_scores"] == {"faithfulness": 0.81}
        assert line["signals"]["loop_kind"] == "cycle"
        assert line["analyzer_versions"] == {"signals": "1", "judge": "1"}

    def test_unanalyzed_row_is_all_null(self) -> None:
        line = json.loads(_label_line("t-2", None))
        assert line == {
            "trace_id": "t-2",
            "outcome": None,
            "failure_mode": None,
            "task_category": None,
            "metric_scores": None,
            "signals": None,
            "analyzer_versions": None,
        }
