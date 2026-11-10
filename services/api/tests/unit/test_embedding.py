"""Unit coverage for the similar-behavior embedding pieces
(docs/proposals/similar-behavior.md): the roll-up input, the pgvector text
literal, and the subscription anchor validation rules.
"""

import pytest
from pydantic import ValidationError

from app.analysis import AnalysisSettings
from app.analysis.embedding import embedding_input
from app.queries.embeddings import vector_literal
from app.schemas.subscription import SubscriptionCreateRequest, SubscriptionQuery


def settings(**overrides) -> AnalysisSettings:
    return AnalysisSettings(_env_file=None, **overrides)


def test_embedding_input_is_the_roll_up_text() -> None:
    text = embedding_input("fix the bug", "Fixed it.", [(0, "success", "Patched x")], settings())
    assert text == "Goal: fix the bug\nSummary: Fixed it.\nTurn 0 (success): Patched x"


def test_embedding_input_fits_budget() -> None:
    turns = [(i, "success", "y" * 400) for i in range(50)]
    small = settings(embedding_budget_tokens=500)
    assert len(embedding_input("g", "s", turns, small)) == 500 * 4


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
