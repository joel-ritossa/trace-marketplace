"""Review-item queries (2_data-model.md): the HIL queue plumbing. Items are
created server-side only — the analysis rewrite (routed) or the owner-relabel
endpoint; resolution is the one client-driven mutation.
"""

from collections.abc import Mapping
from typing import Any

import asyncpg

from app.queries import analysis as analysis_q


def label_updates(answer: Mapping[str, str], current: Mapping[str, Any]) -> dict[str, Any]:
    """The resolve write-set over `trace_analysis` (A3 decision 6): answered
    fields get confidence 1.0 and provenance `human` — or `human_confirmed`
    when the answer matches the field's current machine-provenance value.
    Coherence rule: a human non-failure outcome nulls a machine-provenance
    failure_mode (the judge only diagnoses declared failures); a
    human-provenance failure_mode is the human's business and stays."""
    updates: dict[str, Any] = {}
    for field, value in answer.items():
        confirmed = current[field] == value and current[f"{field}_provenance"] == "machine"
        updates[field] = value
        updates[f"{field}_confidence"] = 1.0
        updates[f"{field}_provenance"] = "human_confirmed" if confirmed else "human"
    if (
        updates.get("outcome") in ("success", "indeterminate")
        and "failure_mode" not in answer
        and current["failure_mode_provenance"] == "machine"
    ):
        updates["failure_mode"] = None
        updates["failure_mode_confidence"] = None
        updates["failure_mode_provenance"] = None
    return updates


def verdict_snapshot(current: Mapping[str, Any]) -> dict[str, Any]:
    """The machine's take from a `trace_analysis` row, for an owner-relabel
    item's context: machine-provenance triplets only — human-resolved fields
    are not the machine verdict."""
    snapshot: dict[str, Any] = {}
    for field in analysis_q.LABEL_FIELDS:
        machine = current[f"{field}_provenance"] == "machine"
        snapshot[field] = current[field] if machine else None
        snapshot[f"{field}_confidence"] = current[f"{field}_confidence"] if machine else None
    return snapshot


async def supersede_and_create(
    conn: asyncpg.Connection, *, trace_id: str, context: dict[str, Any]
) -> str:
    """The supersede rule (1_analysis.md): a re-run that routes again marks
    the open item superseded and creates a fresh one — never duplicates.
    Runs inside the analysis rewrite's transaction."""
    await conn.execute(
        "update review_items set status = 'superseded' where trace_id = $1 and status = 'open'",
        trace_id,
    )
    return await conn.fetchval(
        "insert into review_items (trace_id, context) values ($1, $2) returning id",
        trace_id,
        context,
    )


async def get_or_create_open(
    pool: asyncpg.Pool, *, trace_id: str, context: dict[str, Any]
) -> tuple[asyncpg.Record, bool]:
    """Owner-initiated relabel (3_api.md): returns the existing open item or
    creates one. The partial unique index arbitrates races; the bounded loop
    covers the open item resolving between the conflict and the re-select."""
    for _ in range(2):
        row = await pool.fetchrow(
            """
            insert into review_items (trace_id, context) values ($1, $2)
            on conflict (trace_id) where status = 'open' do nothing
            returning *
            """,
            trace_id,
            context,
        )
        if row is not None:
            return row, True
        row = await pool.fetchrow(
            "select * from review_items where trace_id = $1 and status = 'open'", trace_id
        )
        if row is not None:
            return row, False
    raise RuntimeError(f"review item churn on trace {trace_id}; retry")


async def list_for_owner(
    pool: asyncpg.Pool,
    owner_id: str,
    *,
    status: str,
    upload_id: str | None,
    limit: int,
    offset: int,
) -> tuple[list[asyncpg.Record], int]:
    """The caller's items on own traces, newest first (3_api.md), with the
    trace summary and upload_id for per-upload grouping. `status = 'all'`
    includes resolved/superseded history."""
    args: list = [owner_id]
    where = ["t.owner_id = $1"]

    def param(value) -> str:
        args.append(value)
        return f"${len(args)}"

    if status != "all":
        where.append(f"ri.status = {param(status)}")
    if upload_id:
        where.append(f"t.upload_id = {param(upload_id)}")

    base = f"""
        from review_items ri
        join traces t on t.id = ri.trace_id
        join uploads u on u.id = t.upload_id
        where {" and ".join(where)}
    """
    filter_args = list(args)
    rows = await pool.fetch(
        f"""
        select ri.*, t.upload_id, u.filename as upload_filename,
               t.name as trace_name, t.status as trace_status,
               t.duration_ms as trace_duration_ms, t.started_at as trace_started_at,
               count(*) over () as total
        {base}
        order by ri.created_at desc, ri.id desc
        limit {param(limit)} offset {param(offset)}
        """,
        *args,
    )
    if rows:
        return rows, rows[0]["total"]
    total = await pool.fetchval(f"select count(*) {base}", *filter_args)
    return rows, total


async def get_for_owner(pool: asyncpg.Pool, item_id: str, owner_id: str) -> asyncpg.Record | None:
    """Owner of the referenced trace only; invisible items are absent ones
    (404-not-403). A deleted trace cascades the item away — same 404."""
    return await pool.fetchrow(
        """
        select ri.*, t.upload_id, u.filename as upload_filename,
               t.name as trace_name, t.status as trace_status,
               t.duration_ms as trace_duration_ms, t.started_at as trace_started_at
        from review_items ri
        join traces t on t.id = ri.trace_id
        join uploads u on u.id = t.upload_id
        where ri.id = $1 and t.owner_id = $2
        """,
        item_id,
        owner_id,
    )


async def resolve(
    pool: asyncpg.Pool, item_id: str, owner_id: str, answer: dict[str, str]
) -> tuple[str, asyncpg.Record | None, dict[str, Any] | None]:
    """Resolve with provenance (3_api.md): write the answered triplets to
    `trace_analysis` and mark the item resolved, one transaction. Locks are
    taken in `rewrite`'s order — `trace_analysis` first, then the item — so
    a resolve racing a machine rewrite serializes instead of deadlocking;
    whichever side commits second sees the other's write (rewrite's
    carryover preserves human provenance; resolve re-checks the item's
    status under the lock).

    Returns (status, item_row, written_updates): `resolved` on success,
    else `not_found` / `already_resolved` / `superseded` /
    `analysis_pending`.
    """
    async with pool.acquire() as conn, conn.transaction():
        # Unlocked probe: ownership check + trace_id. resolved/superseded
        # are terminal states, so those early returns can't be stale.
        item = await conn.fetchrow(
            """
            select ri.* from review_items ri
            join traces t on t.id = ri.trace_id
            where ri.id = $1 and t.owner_id = $2
            """,
            item_id,
            owner_id,
        )
        if item is None:
            return "not_found", None, None
        if item["status"] == "resolved":
            return "already_resolved", item, None
        if item["status"] == "superseded":
            return "superseded", item, None
        current = await conn.fetchrow(
            "select * from trace_analysis where trace_id = $1 for update", item["trace_id"]
        )
        if current is None:  # analysis vanished under the item (re-run in flight)
            return "analysis_pending", None, None
        # Re-check under the lock: a rewrite holding the trace_analysis lock
        # may have superseded the item while we waited.
        item = await conn.fetchrow("select * from review_items where id = $1 for update", item_id)
        if item is None:  # trace deleted mid-flight; the item cascaded away
            return "not_found", None, None
        if item["status"] == "resolved":
            return "already_resolved", item, None
        if item["status"] == "superseded":
            return "superseded", item, None
        updates = label_updates(answer, current)
        sets = ", ".join(f"{col} = ${i + 2}" for i, col in enumerate(updates))
        await conn.execute(
            f"update trace_analysis set {sets} where trace_id = $1",
            item["trace_id"],
            *updates.values(),
        )
        row = await conn.fetchrow(
            """
            update review_items
            set status = 'resolved', answer = $3, resolved_at = now(), resolved_by = $2
            where id = $1
            returning *
            """,
            item_id,
            owner_id,
            dict(answer),
        )
        return "resolved", row, updates
