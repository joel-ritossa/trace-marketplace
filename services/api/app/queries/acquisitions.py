import asyncpg


async def create(pool: asyncpg.Pool, consumer_id: str, trace_id: str) -> asyncpg.Record | None:
    """Acquire a listed trace, idempotently, in one statement.

    The listed check lives inside the insert's select so an unlist can't race
    between a separate check and the write. Returns the acquisition row with a
    `created` flag (false = it already existed), or None when the trace isn't
    listed (and no prior acquisition exists) — the router maps that to 409.
    """
    return await pool.fetchrow(
        """
        with ins as (
          insert into acquisitions (consumer_id, trace_id)
          select $1, $2
          from traces t
          where t.id = $2 and t.visibility = 'listed' and t.owner_id <> $1
          on conflict (consumer_id, trace_id) do nothing
          returning id, trace_id, price_usd, acquired_at
        )
        select id, trace_id, price_usd, acquired_at, true as created from ins
        union all
        select id, trace_id, price_usd, acquired_at, false as created
        from acquisitions
        where consumer_id = $1 and trace_id = $2
          and not exists (select 1 from ins)
        """,
        consumer_id,
        trace_id,
    )
