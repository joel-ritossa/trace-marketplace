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
    source: str,
    redaction_salt: str,
) -> str:
    return await pool.fetchval(
        """
        insert into uploads
          (owner_id, filename, size_bytes, sha256, storage_path, source_format, source,
           redaction_salt)
        values ($1, $2, $3, $4, $5, $6, $7, $8)
        returning id
        """,
        owner_id,
        filename,
        size_bytes,
        sha256,
        storage_path,
        source_format,
        source,
        redaction_salt,
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
        select u.id, u.filename, u.size_bytes, u.status, u.error_message, u.source,
               u.created_at, u.processed_at, u.redaction_counts,
               coalesce(
                 array_agg(t.id order by t.started_at) filter (where t.id is not null),
                 '{}'
               ) as trace_ids,
               count(*) over () as total
        from uploads u
        left join traces t on t.upload_id = u.id
        where u.owner_id = $1
        group by u.id
        order by u.created_at desc
        limit $2 offset $3
        """,
        owner_id,
        limit,
        offset,
    )
    if rows:
        return rows, rows[0]["total"]
    # Past-the-end offset returns no rows, so the window total is lost;
    # count separately so the client can tell "empty" from "out of range".
    total = await pool.fetchval("select count(*) from uploads where owner_id = $1", owner_id)
    return rows, total


async def get(pool: asyncpg.Pool, upload_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow("select * from uploads where id = $1", upload_id)


async def lock(conn: asyncpg.Connection, upload_id: str) -> None:
    """Row-lock the upload for the duration of the current transaction.

    Serializes concurrent ingest runs of the same upload (sweep re-enqueue
    during a slow run, duplicate delivery): without it, two delete-and-rewrite
    transactions can interleave under READ COMMITTED — neither delete sees the
    other's uncommitted inserts — and both commit, duplicating traces.
    """
    await conn.execute("select 1 from uploads where id = $1 for update", upload_id)


async def mark_processing(pool: asyncpg.Pool, upload_id: str) -> int | None:
    """Claim the job: flip to processing, count the attempt, stamp the claim.

    Returns None when the upload is already complete. `complete` is terminal
    for ingestion — the guard lives in SQL so a stale duplicate delivery can't
    regress the status between a read and an update.
    """
    return await pool.fetchval(
        """
        update uploads
        set status = 'processing', attempts = attempts + 1, last_attempt_at = now()
        where id = $1 and status <> 'complete'
        returning attempts
        """,
        upload_id,
    )


async def mark_complete(
    executor: asyncpg.Pool | asyncpg.Connection,
    upload_id: str,
    *,
    parse_warnings: dict | None = None,
    redaction_version: str | None = None,
    redaction_counts: dict | None = None,
) -> None:
    """Takes a pool or an open connection so the status flip can share the
    ingest rewrite's transaction."""
    await executor.execute(
        "update uploads set status = 'complete', error_message = null, "
        "parse_warnings = $2, redaction_version = $3, redaction_counts = $4, "
        "processed_at = now() where id = $1",
        upload_id,
        parse_warnings,
        redaction_version,
        redaction_counts,
    )


async def mark_failed(pool: asyncpg.Pool, upload_id: str, error_message: str) -> None:
    """No-op when already complete: a stale retry chain exhausting after a
    concurrent run succeeded must not overwrite the terminal `complete`."""
    await pool.execute(
        "update uploads set status = 'failed', error_message = $2, processed_at = now() "
        "where id = $1 and status <> 'complete'",
        upload_id,
        error_message,
    )


async def attempt_count(pool: asyncpg.Pool, upload_id: str) -> int | None:
    """Durable attempt counter (state of record for the retry budget)."""
    return await pool.fetchval("select attempts from uploads where id = $1", upload_id)


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
    """Reset a terminal upload for a fresh ingest run; refuses in-flight
    states. `complete` became requeue-able at A2: stable trace identity
    makes a re-ingest preserve trace ids (and everything hung off them), so
    operator re-ingest — A5's redaction backfill mechanism — is safe."""
    status = await pool.fetchval(
        """
        update uploads
        set status = 'received', error_message = null, attempts = 0,
            processed_at = null, last_attempt_at = null
        where id = $1 and status in ('failed', 'complete')
        returning status
        """,
        upload_id,
    )
    return status is not None
