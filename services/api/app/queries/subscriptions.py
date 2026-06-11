"""Subscription queries (2_data-model.md): owner-scoped CRUD, the live
feed/count execution of stored queries, and event-driven match evaluation
(3_api.md). All execution paths build SQL through the shared filter-clause
builder in queries/traces.py — one vocabulary, one builder (A4 decision 1).
"""

import asyncpg

from app.queries.traces import anchor_clauses, filter_clauses, make_param
from app.schemas.trace import TraceFilterQuery

# Sentinel mirroring traces.update_owned: None must mean "leave untouched"
# for optional patch fields.
_UNSET: object = object()

# (anchor trace id, similarity threshold) — the behavior-anchor predicate
# threaded through match evaluation and live counts.
Anchor = tuple[str, float]


def anchor_of(row: asyncpg.Record) -> Anchor | None:
    """The row's behavior anchor, if intact. A deleted anchor trace nulls
    the reference (on delete set null) while the threshold stays — that
    half-pair matches nothing, by design, until the owner edits it."""
    if row["similar_to_trace_id"] is None or row["similarity_threshold"] is None:
        return None
    return (str(row["similar_to_trace_id"]), row["similarity_threshold"])


async def create(
    pool: asyncpg.Pool,
    owner_id: str,
    *,
    name: str,
    query: dict,
    similar_to_trace_id: str | None = None,
    similarity_threshold: float | None = None,
) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        insert into subscriptions
          (owner_id, name, query, similar_to_trace_id, similarity_threshold)
        values ($1, $2, $3, $4, $5)
        returning *
        """,
        owner_id,
        name,
        query,
        similar_to_trace_id,
        similarity_threshold,
    )


async def list_for_owner(pool: asyncpg.Pool, owner_id: str) -> list[asyncpg.Record]:
    """The caller's subscriptions with last-match time from the ledger.
    Live match counts are computed per row by the router (small N — a
    user's subscription list, not a list surface)."""
    return await pool.fetch(
        """
        select s.*, anchor.name as similar_to_name,
               (
                 select max(m.matched_at) from subscription_matches m
                 where m.subscription_id = s.id
               ) as last_match_at
        from subscriptions s
        left join traces anchor on anchor.id = s.similar_to_trace_id
        where s.owner_id = $1
        order by s.created_at desc, s.id
        """,
        owner_id,
    )


async def get_owned(
    pool: asyncpg.Pool, subscription_id: str, owner_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        select s.*, anchor.name as similar_to_name,
               (
                 select max(m.matched_at) from subscription_matches m
                 where m.subscription_id = s.id
               ) as last_match_at
        from subscriptions s
        left join traces anchor on anchor.id = s.similar_to_trace_id
        where s.id = $1 and s.owner_id = $2
        """,
        subscription_id,
        owner_id,
    )


async def update_owned(
    pool: asyncpg.Pool,
    subscription_id: str,
    owner_id: str,
    *,
    name: str | None = None,
    query: dict | object = _UNSET,
    anchor: Anchor | None | object = _UNSET,
) -> asyncpg.Record | None:
    sets: list[str] = []
    args: list = [subscription_id, owner_id]
    param = make_param(args)
    if name is not None:
        sets.append(f"name = {param(name)}")
    if query is not _UNSET:
        sets.append(f"query = {param(query)}")
    if anchor is not _UNSET:
        trace_id, threshold = anchor if anchor is not None else (None, None)
        sets.append(f"similar_to_trace_id = {param(trace_id)}")
        sets.append(f"similarity_threshold = {param(threshold)}")
    return await pool.fetchrow(
        f"""
        update subscriptions set {", ".join(sets)}
        where id = $1 and owner_id = $2
        returning *
        """,
        *args,
    )


async def delete_owned(pool: asyncpg.Pool, subscription_id: str, owner_id: str) -> bool:
    deleted = await pool.fetchval(
        "delete from subscriptions where id = $1 and owner_id = $2 returning id",
        subscription_id,
        owner_id,
    )
    return deleted is not None


async def mark_seen(
    pool: asyncpg.Pool, subscription_id: str, owner_id: str
) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        update subscriptions set last_seen_at = now()
        where id = $1 and owner_id = $2
        returning last_seen_at
        """,
        subscription_id,
        owner_id,
    )


async def live_match_count(
    pool: asyncpg.Pool, filters: TraceFilterQuery, anchor: Anchor | None = None
) -> int:
    """The stored query as a count over listed traces — the list page's
    match stat (3_api.md: live, not the ledger). The behavior anchor, when
    present, ANDs in like any other predicate; the anchor trace itself is
    excluded (it trivially matches itself)."""
    args: list = []
    param = make_param(args)
    where = ["t.visibility = 'listed'", *filter_clauses(filters, param)]
    if anchor is not None:
        where.extend(anchor_clauses(param, *anchor))
    return await pool.fetchval(
        f"""
        select count(*)
        from traces t
        left join trace_analysis ta on ta.trace_id = t.id
        where {" and ".join(where)}
        """,
        *args,
    )


async def matches_trace(
    executor: asyncpg.Pool | asyncpg.Connection,
    filters: TraceFilterQuery,
    trace_id: str,
    anchor: Anchor | None = None,
) -> bool:
    """Event-driven match evaluation (A4 decision 6): the stored query
    pinned to one trace, listed-only. Subscriptions never match private
    traces; an anchored subscription never matches its own anchor."""
    args: list = []
    param = make_param(args)
    where = [
        f"t.id = {param(trace_id)}",
        "t.visibility = 'listed'",
        *filter_clauses(filters, param),
    ]
    if anchor is not None:
        where.extend(anchor_clauses(param, *anchor))
    return await executor.fetchval(
        f"""
        select exists (
          select 1
          from traces t
          left join trace_analysis ta on ta.trace_id = t.id
          where {" and ".join(where)}
        )
        """,
        *args,
    )


async def record_match(
    executor: asyncpg.Pool | asyncpg.Connection, subscription_id: str, trace_id: str
) -> bool:
    """First-match ledger insert; the unique pair is the notification
    dedupe — a trace notifies a subscription at most once, ever. Returns
    whether this event was the first match. Takes a connection so the
    ledger row and its digest can share one transaction."""
    inserted = await executor.fetchval(
        """
        insert into subscription_matches (subscription_id, trace_id)
        values ($1, $2)
        on conflict (subscription_id, trace_id) do nothing
        returning id
        """,
        subscription_id,
        trace_id,
    )
    return inserted is not None


async def fetch_all(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Every subscription, for the match loop. Demo-scale by design
    (A4 decision 6); batching is an optimization with no current evidence."""
    return await pool.fetch(
        """
        select id, owner_id, name, query, similar_to_trace_id, similarity_threshold
        from subscriptions
        """
    )


async def new_match_ids(pool: asyncpg.Pool, subscription_id: str, trace_ids: list[str]) -> set[str]:
    """Which of these feed rows matched after last_seen_at (A4 decision 10).
    Backfill rows have no match record and are never 'new'."""
    rows = await pool.fetch(
        """
        select m.trace_id
        from subscription_matches m
        join subscriptions s on s.id = m.subscription_id
        where m.subscription_id = $1
          and m.trace_id = any($2::uuid[])
          and m.matched_at > s.last_seen_at
        """,
        subscription_id,
        trace_ids,
    )
    return {str(r["trace_id"]) for r in rows}
