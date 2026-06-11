"""Unit coverage for the similar-behavior embedding pieces
(docs/proposals/similar-behavior.md): input truncation, the pgvector text
literal, and the subscription anchor validation rules.
"""

import json

import pytest
from pydantic import ValidationError

from app.analysis import AnalysisSettings
from app.analysis.embedding import embedding_input
from app.queries.embeddings import vector_literal
from app.schemas.subscription import SubscriptionCreateRequest, SubscriptionQuery
from tests.unit.analysis_factories import make_span, make_trace


def settings(**overrides) -> AnalysisSettings:
    return AnalysisSettings(_env_file=None, **overrides)


def _llm_attrs(user_text: str, assistant_text: str) -> dict:
    return {
        "gen_ai.input.messages": json.dumps(
            [{"role": "user", "parts": [{"type": "text", "content": user_text}]}]
        ),
        "gen_ai.output.messages": json.dumps(
            [{"role": "assistant", "parts": [{"type": "text", "content": assistant_text}]}]
        ),
    }


def test_embedding_input_fits_budget_untouched() -> None:
    trace = make_trace([make_span(0, kind="llm", attributes=_llm_attrs("hello", "world"))])
    text = embedding_input(trace, settings())
    assert "hello" in text and "world" in text
    assert "[…elided for embedding…]" not in text


def test_embedding_input_truncates_middle_out() -> None:
    spans = [
        make_span(
            i,
            kind="llm",
            attributes=_llm_attrs(f"question {i} " + "x" * 400, f"answer {i} " + "y" * 400),
        )
        for i in range(50)
    ]
    trace = make_trace(spans)
    small = settings(embedding_budget_tokens=500)
    text = embedding_input(trace, small)
    assert len(text) <= small.embedding_budget_tokens * 4
    assert "[…elided for embedding…]" in text
    # Middle-out: the opening and the ending both survive.
    assert "question 0" in text
    assert "answer 49" in text


def test_vector_literal_pgvector_shape() -> None:
    lit = vector_literal([0.25, -1.0, 3.5])
    assert lit == "[0.25,-1.0,3.5]"


def test_subscription_anchor_pair_enforced() -> None:
    base = {"name": "s", "query": {"outcome": "failure"}}
    with pytest.raises(ValidationError, match="set together"):
        SubscriptionCreateRequest(
            **base, similar_to_trace_id="11111111-1111-1111-1111-111111111111"
        )
    with pytest.raises(ValidationError, match="set together"):
        SubscriptionCreateRequest(**base, similarity_threshold=0.7)
    for bad in (0.0, 1.0, -0.1):
        with pytest.raises(ValidationError):
            SubscriptionCreateRequest(
                **base,
                similar_to_trace_id="11111111-1111-1111-1111-111111111111",
                similarity_threshold=bad,
            )


def test_subscription_anchor_counts_as_predicate() -> None:
    # Empty query + anchor: valid — the anchor is the predicate.
    req = SubscriptionCreateRequest(
        name="s",
        query=SubscriptionQuery(),
        similar_to_trace_id="11111111-1111-1111-1111-111111111111",
        similarity_threshold=0.7,
    )
    assert req.query.stored() == {}
    # Empty query, no anchor: still rejected.
    with pytest.raises(ValidationError, match="at least one filter predicate"):
        SubscriptionCreateRequest(name="s", query=SubscriptionQuery())
