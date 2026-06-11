import asyncpg


async def insert(
    pool: asyncpg.Pool,
    *,
    upload_id: str,
    task_name: str,
    attempts: int,
    last_error: str,
    error_context: dict,
    trace_id: str | None = None,
) -> str:
    """`trace_id` marks trace-scoped (analysis) rows; ingestion rows leave
    it null (2_data-model.md stage-1 deltas)."""
    return await pool.fetchval(
        """
        insert into dead_letters
          (upload_id, trace_id, task_name, attempts, last_error, error_context)
        values ($1, $2, $3, $4, $5, $6)
        returning id
        """,
        upload_id,
        trace_id,
        task_name,
        attempts,
        last_error,
        error_context,
    )


async def mark_requeued(pool: asyncpg.Pool, upload_id: str) -> None:
    """Close an upload's ingestion dead letters ahead of a requeue. Scoped
    to ingestion rows: a trace-scoped analysis dead letter is closed by the
    trace requeue path, not an upload requeue."""
    await pool.execute(
        """
        update dead_letters set requeued_at = now()
        where upload_id = $1 and trace_id is null and requeued_at is null
        """,
        upload_id,
    )


async def mark_requeued_for_trace(
    executor: asyncpg.Pool | asyncpg.Connection, trace_id: str
) -> None:
    """Close a trace's open analysis dead letters. Takes a pool or an open
    connection so the close can share the analysis rewrite's transaction."""
    await executor.execute(
        "update dead_letters set requeued_at = now() where trace_id = $1 and requeued_at is null",
        trace_id,
    )
