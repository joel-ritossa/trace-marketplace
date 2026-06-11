import asyncpg


async def insert(
    pool: asyncpg.Pool,
    *,
    upload_id: str,
    task_name: str,
    attempts: int,
    last_error: str,
    error_context: dict,
) -> str:
    return await pool.fetchval(
        """
        insert into dead_letters (upload_id, task_name, attempts, last_error, error_context)
        values ($1, $2, $3, $4, $5)
        returning id
        """,
        upload_id,
        task_name,
        attempts,
        last_error,
        error_context,
    )


async def mark_requeued(pool: asyncpg.Pool, upload_id: str) -> None:
    await pool.execute(
        "update dead_letters set requeued_at = now() where upload_id = $1 and requeued_at is null",
        upload_id,
    )
