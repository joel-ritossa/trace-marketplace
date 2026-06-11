import asyncpg


async def find_by_hash(pool: asyncpg.Pool, owner_id: str, sha256: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "select id, status from uploads where owner_id = $1 and sha256 = $2", owner_id, sha256
    )


async def create(
    pool: asyncpg.Pool,
    *,
    owner_id: str,
    filename: str,
    size_bytes: int,
    sha256: str,
    storage_path: str,
    source_format: str,
) -> str:
    return await pool.fetchval(
        """
        insert into uploads (owner_id, filename, size_bytes, sha256, storage_path, source_format)
        values ($1, $2, $3, $4, $5, $6)
        returning id
        """,
        owner_id,
        filename,
        size_bytes,
        sha256,
        storage_path,
        source_format,
    )


async def get_owned(pool: asyncpg.Pool, upload_id: str, owner_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "select * from uploads where id = $1 and owner_id = $2", upload_id, owner_id
    )


async def list_owned(
    pool: asyncpg.Pool, owner_id: str, *, limit: int, offset: int
) -> tuple[list[asyncpg.Record], int]:
    rows = await pool.fetch(
        """
        select id, filename, size_bytes, status, error_message, created_at, processed_at,
               count(*) over () as total
        from uploads
        where owner_id = $1
        order by created_at desc
        limit $2 offset $3
        """,
        owner_id,
        limit,
        offset,
    )
    total = rows[0]["total"] if rows else 0
    return rows, total


async def get(pool: asyncpg.Pool, upload_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow("select * from uploads where id = $1", upload_id)


async def mark_processing(pool: asyncpg.Pool, upload_id: str) -> int:
    """Claim the job: flip to processing, count the attempt, stamp the claim."""
    return await pool.fetchval(
        """
        update uploads
        set status = 'processing', attempts = attempts + 1, last_attempt_at = now()
        where id = $1
        returning attempts
        """,
        upload_id,
    )


async def mark_complete(pool: asyncpg.Pool, upload_id: str) -> None:
    await pool.execute(
        "update uploads set status = 'complete', error_message = null, processed_at = now() "
        "where id = $1",
        upload_id,
    )


async def mark_failed(pool: asyncpg.Pool, upload_id: str, error_message: str) -> None:
    await pool.execute(
        "update uploads set status = 'failed', error_message = $2, processed_at = now() "
        "where id = $1",
        upload_id,
        error_message,
    )


async def stuck_ids(pool: asyncpg.Pool, *, older_than_minutes: int) -> list[str]:
    """Uploads whose job was likely lost (6_architecture.md lost-job recovery).

    Keyed off the last claim, not created_at, so an upload re-enqueues at most
    once per timeout window rather than on every sweep tick.
    """
    rows = await pool.fetch(
        """
        select id from uploads
        where status in ('received', 'processing')
          and coalesce(last_attempt_at, created_at) < now() - make_interval(mins => $1)
        """,
        older_than_minutes,
    )
    return [str(r["id"]) for r in rows]


async def reset_for_requeue(pool: asyncpg.Pool, upload_id: str) -> bool:
    """Reset a failed upload for a fresh ingest run; refuses other states."""
    status = await pool.fetchval(
        """
        update uploads
        set status = 'received', error_message = null, attempts = 0,
            processed_at = null, last_attempt_at = null
        where id = $1 and status = 'failed'
        returning status
        """,
        upload_id,
    )
    return status is not None
