"""Filter vocabulary: TraceFilterQuery parsing (strict vs format-checked
values), the SQL clause builders (session-array overlap), and the
subscription query's strict shape."""

import pytest
from pydantic import ValidationError

from app.queries.traces import analysis_clauses, filter_clauses, make_param, stage1_clauses
from app.schemas.subscription import SubscriptionQuery
from app.schemas.trace import TraceFilterQuery


class TestParsing:
    def test_csv_strict_sets(self) -> None:
        q = TraceFilterQuery(outcome="failure,partial,indeterminate")
        assert q.outcome == "failure,partial,indeterminate"
        with pytest.raises(ValidationError, match="unknown outcome"):
            TraceFilterQuery(outcome="failure,bogus")
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

    def test_bounds(self) -> None:
        with pytest.raises(ValidationError):
            TraceFilterQuery(duration_ms_gte=-1)

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
        assert TraceFilterQuery(failure_mode="system_failure").has_analysis_predicate
        assert TraceFilterQuery(llm_call_count_gte=0).has_analysis_predicate


class TestSubscriptionQuery:
    def test_unknown_and_shape_params_forbidden(self) -> None:
        # Request shape is not query: scope/sort/pagination are 422.
        removed = (
            {"metric": ["f:0.5"]},
            {"outcome_confidence_gte": 0.8},
            {"outcome_provenance": "human"},
        )
        for extra in (
            {"scope": "marketplace"},
            {"sort": "created_at"},
            {"limit": 5},
            {"nope": 1},
            *removed,
        ):
            with pytest.raises(ValidationError):
                SubscriptionQuery.model_validate({"outcome": "failure", **extra})

    def test_stored_round_trip(self) -> None:
        q = SubscriptionQuery.model_validate(
            {"outcome": "failure", "failure_mode": "system_failure"}
        )
        stored = q.stored()
        # Defaults dropped: the stored map is exactly the active predicates.
        assert stored == {"outcome": "failure", "failure_mode": "system_failure"}
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

        for empty in ({}, {"has_errors": False}):
            assert SubscriptionQuery.model_validate(empty).stored() == {}
            with pytest.raises(ValidationError, match="at least one filter"):
                SubscriptionCreateRequest(name="s", query=empty)


class TestClauseBuilders:
    def test_stage1_vs_analysis_split(self) -> None:
        q = TraceFilterQuery(provider="openai", duration_ms_gte=100, outcome="failure,partial")
        args: list = []
        param = make_param(args)
        stage1 = stage1_clauses(q, param)
        analysis = analysis_clauses(q, param)
        assert ["t.provider = $1", "t.duration_ms >= $2"] == stage1
        assert analysis == ["ta.outcome = any($3::text[])"]
        assert args[2] == ["failure", "partial"]

    def test_taxonomies_match_by_array_overlap(self) -> None:
        # CSV-OR: the session set contains any requested value.
        args: list = []
        q = TraceFilterQuery(task_category="coding, debugging", failure_mode="system_failure")
        clauses = analysis_clauses(q, make_param(args))
        assert clauses == [
            "ta.task_categories && $1::text[]",
            "ta.failure_modes && $2::text[]",
        ]
        assert args == [["coding", "debugging"], ["system_failure"]]

    def test_boolean_false_is_a_filter(self) -> None:
        args: list = []
        clauses = analysis_clauses(TraceFilterQuery(has_retry_loop=False), make_param(args))
        assert clauses == ["ta.has_retry_loop = $1"]
        assert args == [False]

    def test_empty_filters_no_clauses(self) -> None:
        assert filter_clauses(TraceFilterQuery(), make_param([])) == []
