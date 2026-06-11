import asyncpg

from app.importers.otlp import NormalizedTrace

# Whitelist for the API's sort param; never interpolate user input directly.
# Qualified: list_owned joins profiles, which also has a created_at.
SORT_COLUMNS = {
    "created_at": "t.created_at desc",
    "duration_ms": "t.duration_ms desc",
    "span_count": "t.span_count desc",
}


async def delete_for_upload(conn: asyncpg.Connection, upload_id: str) -> None:
    """Drop an upload's traces (spans cascade) ahead of a rewrite.

    Part of the delete-and-rewrite idempotency contract (6_architecture.md):
    always called in the same transaction as the re-insert.
    """
    await conn.execute("delete from traces where upload_id = $1", upload_id)


async def insert(
    conn: asyncpg.Connection,
    *,
    upload_id: str,
    owner_id: str,
    trace: NormalizedTrace,
    source_format: str,
    importer_version: str,
) -> str:
    return await conn.fetchval(
        """
        insert into traces (
          upload_id, owner_id, source_trace_id, name, status, started_at, ended_at,
          duration_ms, span_count, error_count, provider, model, service_name,
          tool_names, error_types, source_format, importer_version
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
        returning id
        """,
        upload_id,
        owner_id,
        trace.source_trace_id,
        trace.name,
        trace.status,
        trace.started_at,
        trace.ended_at,
        trace.duration_ms,
        trace.span_count,
        trace.error_count,
        trace.provider,
        trace.model,
        trace.service_name,
        trace.tool_names,
        trace.error_types,
        source_format,
        importer_version,
    )


async def list_owned(
    pool: asyncpg.Pool, owner_id: str, *, sort: str, limit: int, offset: int
) -> tuple[list[asyncpg.Record], int]:
    order_by = SORT_COLUMNS[sort]
    rows = await pool.fetch(
        f"""
        select t.id, t.name, t.status, t.started_at, t.duration_ms, t.span_count,
               t.error_count, t.provider, t.model, t.created_at,
               p.display_name as owner_display_name, count(*) over () as total
        from traces t join profiles p on p.id = t.owner_id
        where t.owner_id = $1
        order by {order_by}, t.id
        limit $2 offset $3
        """,
        owner_id,
        limit,
        offset,
    )
    total = rows[0]["total"] if rows else 0
    return rows, total


async def get_owned(pool: asyncpg.Pool, trace_id: str, owner_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "select * from traces where id = $1 and owner_id = $2", trace_id, owner_id
    )


async def get_owned_with_upload(
    pool: asyncpg.Pool, trace_id: str, owner_id: str
) -> asyncpg.Record | None:
    """Trace plus the upload fields needed to serve the raw download."""
    return await pool.fetchrow(
        """
        select t.id, u.storage_path, u.filename
        from traces t join uploads u on u.id = t.upload_id
        where t.id = $1 and t.owner_id = $2
        """,
        trace_id,
        owner_id,
    )


async def ids_for_upload(pool: asyncpg.Pool, upload_id: str) -> list[str]:
    rows = await pool.fetch(
        "select id from traces where upload_id = $1 order by started_at, id", upload_id
    )
    return [str(r["id"]) for r in rows]
