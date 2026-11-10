"""Review-item queries (2_data-model.md, 9_session-analysis.md Review): a
trace with any uncertain machine turn has exactly one open item listing
those turns. Items are written server-side only, inside the analysis
rewrite or an owner relabel (`sync`).
"""

from collections.abc import Mapping
from typing import Any

import asyncpg

from app.queries import notifications as notifications_q


def review_context(uncertain: list[Mapping[str, Any]]) -> dict[str, Any] | None:
    """The open item's context for the trace's uncertain machine turns, or
    None when there are none (no item)."""
    if not uncertain:
        return None
    return {
        "turns": [
            {"turn_index": t["turn_index"], "reason": t["uncertain"], "summary": t["summary"]}
            for t in uncertain
        ]
    }


async def sync(
    conn: asyncpg.Connection,
    trace_id: str,
    *,
    owner_id: str | None = None,
    upload_id: str | None = None,
    resolved_by: str | None = None,
) -> None:
    """Make the trace's open item match its uncertain machine turns.

    Analysis rewrite (`owner_id`/`upload_id` given): an unchanged question
    keeps its item; a different one supersedes it with a fresh item and
    bumps the owner's per-upload digest; none left supersedes it.
    Owner relabel (`resolved_by` given): none left resolves the item,
    otherwise its context narrows in place — the owner is working it.
    """
    uncertain = await conn.fetch(
        """
        select turn_index, uncertain, summary from turn_analysis
        where trace_id = $1 and provenance = 'machine' and uncertain is not null
        order by turn_index
        """,
        trace_id,
    )
    context = review_context(uncertain)
    item = await conn.fetchrow(
        "select id, context from review_items where trace_id = $1 and status = 'open' for update",
        trace_id,
    )
    if item is not None and item["context"] == context:
        return
    if resolved_by is not None:
        if item is None:
            return
        if context is None:
            await conn.execute(
                """
                update review_items
                set status = 'resolved', resolved_at = now(), resolved_by = $2
                where id = $1
                """,
                item["id"],
                resolved_by,
            )
        else:
            await conn.execute(
                "update review_items set context = $2 where id = $1", item["id"], context
            )
        return
    if item is not None:
        await conn.execute(
            "update review_items set status = 'superseded' where id = $1", item["id"]
        )
    if context is not None:
        await conn.execute(
            "insert into review_items (trace_id, context) values ($1, $2)", trace_id, context
        )
        await notifications_q.review_digest_upsert(conn, user_id=owner_id, upload_id=upload_id)


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
