"""Similar behavior (docs/proposals/similar-behavior.md): the
similar-traces endpoint and behavior-anchored subscriptions.

Geometry is seeded into `trace_embeddings` directly — how vectors get
computed is the analysis stream's concern; these tests own retrieval,
visibility, and matching semantics. The worker's embedding stage also acts
on these traces (keyless stacks delete, keyed stacks upsert real vectors),
so every seed happens only after the relevant analyze run has settled —
`wait_embedding_stage` is the settle probe.
"""

import asyncio
import math
import random
import uuid

import asyncpg
import httpx
import pytest

from tests.integration.conftest import API_URL, signup_token
from tests.integration.test_analysis import upload_and_ingest, wait_analysis, wait_until
from tests.integration.test_discovery import list_trace
from tests.integration.test_discovery_scale import (
    subscription_match_notifications,
    unique_payload,
    wait_for_digest,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def consumer():
    token = await signup_token()
    async with httpx.AsyncClient(
        base_url=API_URL,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    ) as client:
        yield client


DIM = 1536


def _unit(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def random_plane() -> tuple[list[float], list[float]]:
    """A fresh random orthonormal 2D plane in embedding space, per test.
    The local stack's data persists across runs, so absolute axes would
    collide with earlier seeds; anything seeded in a different random plane
    (and any real embedding a keyed stack produces) is near-orthogonal
    (|cos| ≈ 1/√1536) and can never clear the thresholds used here."""
    rng = random.Random()
    u = _unit([rng.gauss(0, 1) for _ in range(DIM)])
    raw = [rng.gauss(0, 1) for _ in range(DIM)]
    dot = sum(a * b for a, b in zip(raw, u, strict=True))
    v = _unit([b - dot * a for a, b in zip(u, raw, strict=True)])
    return u, v


def vec(plane: tuple[list[float], list[float]], x: float, y: float) -> str:
    """x·u + y·v as a pgvector literal — cosine similarity between two
    vectors in the same plane is exactly x_a*x_b + y_a*y_b."""
    u, v = plane
    return "[" + ",".join(repr(x * a + y * b) for a, b in zip(u, v, strict=True)) + "]"


async def seed_embedding(db: asyncpg.Connection, trace_id: str, literal: str) -> None:
    await db.execute(
        """
        insert into trace_embeddings (trace_id, embedding, model, renderer_version)
        values ($1, $2::vector, 'seeded', '1')
        on conflict (trace_id) do update set
          embedding = excluded.embedding, model = excluded.model
        """,
        uuid.UUID(trace_id),
        literal,
    )


async def wait_embedding_stage(db: asyncpg.Connection, trace_id: str) -> None:
    """Wait until the worker's embedding stage for the trace's latest
    analyze run has acted, so a subsequent seed cannot be overwritten:
    keyed stacks upsert a real (non-'seeded') row; gated/keyless stacks
    delete — which has no durable marker, hence the settling beat."""

    async def probe():
        row = await db.fetchrow(
            """
            select ta.llm_status,
                   (select model from trace_embeddings te where te.trace_id = ta.trace_id)
                   as embedding_model
            from trace_analysis ta where ta.trace_id = $1
            """,
            uuid.UUID(trace_id),
        )
        if row is None:
            return None
        if row["llm_status"] == "complete":
            return row["embedding_model"] not in (None, "seeded") or None
        return True

    await wait_until(probe, 60.0, f"embedding stage never settled for {trace_id}")
    await asyncio.sleep(2)


async def settled_trace(api: httpx.AsyncClient, db: asyncpg.Connection) -> str:
    """Ingested + analysis and embedding stage settled — safe to seed."""
    trace_id = await upload_and_ingest(api, unique_payload())
    await wait_analysis(api, trace_id, timeout=240.0)
    await wait_embedding_stage(db, trace_id)
    return trace_id


async def relist(api: httpx.AsyncClient, db: asyncpg.Connection, trace_id: str) -> None:
    """Listing a trace whose analysis was skipped for owner_opt_out re-runs
    analysis (the consent hook), which rewrites/deletes embeddings — wait it
    out so a caller's later seeds stick. Any other listing fires match_trace
    directly (no analysis, seeds survive); just give the match a beat."""
    reanalyzes = await db.fetchval(
        "select llm_skip_reason = 'owner_opt_out' from trace_analysis where trace_id = $1",
        uuid.UUID(trace_id),
    )
    assert (await list_trace(api, trace_id)).status_code == 200
    if not reanalyzes:
        await asyncio.sleep(2)
        return
    await wait_until(
        lambda: db.fetchval(
            """
            select case when llm_skip_reason is distinct from 'owner_opt_out' then true end
            from trace_analysis where trace_id = $1
            """,
            uuid.UUID(trace_id),
        ),
        240.0,
        f"post-listing re-analysis never settled for {trace_id}",
    )
    await wait_embedding_stage(db, trace_id)


async def test_similar_endpoint_visibility_and_ordering(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    plane = random_plane()
    anchor = await settled_trace(api, db)
    near = await settled_trace(api, db)
    listed = await settled_trace(consumer, db)
    await relist(consumer, db, listed)
    invisible = await settled_trace(consumer, db)  # consumer-private: hidden from api user

    # Unembedded anchor: explicit anchor_embedded=false, not a 404. (On a
    # keyed stack a real vector may exist — equally fine; skip the probe.)
    if not await db.fetchval(
        "select exists (select 1 from trace_embeddings where trace_id = $1)",
        uuid.UUID(anchor),
    ):
        res = await api.get(f"/v1/traces/{anchor}/similar")
        assert res.status_code == 200
        assert res.json() == {"anchor_embedded": False, "items": [], "total_above": None}

    await seed_embedding(db, anchor, vec(plane, 1.0, 0.0))
    await seed_embedding(db, near, vec(plane, 0.9, math.sqrt(1 - 0.81)))
    await seed_embedding(db, listed, vec(plane, 0.8, 0.6))
    await seed_embedding(db, invisible, vec(plane, 0.99, math.sqrt(1 - 0.9801)))

    res = await api.get(f"/v1/traces/{anchor}/similar", params={"min_similarity": 0.85})
    body = res.json()
    assert body["anchor_embedded"] is True
    got = [(item["trace_id"], round(item["similarity"], 3)) for item in body["items"]]
    # Own private trace and the listed one, by similarity; the other user's
    # private trace is invisible no matter how close it sits.
    assert [g for g in got if g[0] in {near, listed, invisible}] == [
        (near, 0.9),
        (listed, 0.8),
    ]
    above = {g[0] for g in got if g[1] >= 0.85}
    assert near in above and listed not in above
    assert body["total_above"] == len([i for i in body["items"] if i["similarity"] >= 0.85])

    # The anchor itself must be visible to the caller: 404-not-403.
    assert (await consumer.get(f"/v1/traces/{anchor}/similar")).status_code == 404


async def test_anchored_subscription_matching(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    # The consumer anchors on its own listed trace; the owner's trace `near`
    # sits at cosine ≈ 0.98 to it.
    plane = random_plane()
    anchor = await settled_trace(consumer, db)
    await relist(consumer, db, anchor)
    near = await settled_trace(api, db)
    await seed_embedding(db, anchor, vec(plane, 0.8, 0.6))
    await seed_embedding(db, near, vec(plane, 0.9, math.sqrt(1 - 0.81)))  # cos ≈ 0.9815

    # Anchor-only subscription (empty query is valid with an anchor); a
    # stricter sibling that `near` cannot clear.
    loose = (
        await consumer.post(
            "/v1/subscriptions",
            json={
                "name": "behaves like anchor",
                "query": {},
                "similar_to_trace_id": anchor,
                "similarity_threshold": 0.9,
            },
        )
    ).json()
    strict = (
        await consumer.post(
            "/v1/subscriptions",
            json={
                "name": "near-identical only",
                "query": {},
                "similar_to_trace_id": anchor,
                "similarity_threshold": 0.99,
            },
        )
    ).json()
    assert loose["similar_to_trace_id"] == anchor
    assert loose["similar_to_name"]
    assert loose["match_count"] == 0  # `near` is still private

    # If the first listing re-analyzes (opt-out stacks), it rewrites the
    # embeddings — re-seed both sides after it settles, then unlist+relist so
    # match_trace fires against the seeds. On consenting stacks the first
    # listing already matched against the seeds; the second pass is idempotent.
    await relist(api, db, near)
    await seed_embedding(db, near, vec(plane, 0.9, math.sqrt(1 - 0.81)))
    await seed_embedding(db, anchor, vec(plane, 0.8, 0.6))
    await api.patch(f"/v1/traces/{near}", json={"visibility": "private"})
    assert (await list_trace(api, near)).status_code == 200

    digest = await wait_for_digest(consumer, loose["subscription_id"], 1)
    assert digest["payload"]["trace_id"] == near

    # The strict sibling saw the same trigger and matched nothing.
    strict_matches = [
        n
        for n in await subscription_match_notifications(consumer)
        if n["payload"]["subscription_id"] == strict["subscription_id"]
    ]
    assert strict_matches == []

    # Live count and the feed honor the anchor like match evaluation does.
    refreshed = (await consumer.get("/v1/subscriptions")).json()["subscriptions"]
    by_id = {s["subscription_id"]: s for s in refreshed}
    assert by_id[loose["subscription_id"]]["match_count"] == 1
    assert by_id[strict["subscription_id"]]["match_count"] == 0
    feed = (await consumer.get(f"/v1/subscriptions/{loose['subscription_id']}/results")).json()
    assert [t["trace_id"] for t in feed["traces"]] == [near]

    # Threshold edits flow through PATCH; clearing the anchor on an
    # anchor-only subscription would leave it empty — rejected.
    res = await consumer.patch(
        f"/v1/subscriptions/{loose['subscription_id']}",
        json={"similar_to_trace_id": anchor, "similarity_threshold": 0.99},
    )
    assert res.status_code == 200
    assert res.json()["similarity_threshold"] == pytest.approx(0.99)
    res = await consumer.patch(
        f"/v1/subscriptions/{loose['subscription_id']}",
        json={"similar_to_trace_id": None, "similarity_threshold": None},
    )
    assert res.status_code == 422


async def test_anchor_validation(
    api: httpx.AsyncClient, consumer: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    private = await settled_trace(api, db)
    # Anchor invisible to the subscriber: 422 (the subscription is malformed).
    res = await consumer.post(
        "/v1/subscriptions",
        json={
            "name": "s",
            "query": {},
            "similar_to_trace_id": private,
            "similarity_threshold": 0.8,
        },
    )
    assert res.status_code == 422
    # Threshold without anchor, anchor without threshold, empty everything.
    for body in (
        {"name": "s", "query": {}, "similarity_threshold": 0.8},
        {"name": "s", "query": {}, "similar_to_trace_id": private},
        {"name": "s", "query": {}},
    ):
        assert (await api.post("/v1/subscriptions", json=body)).status_code == 422
