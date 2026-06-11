from datetime import datetime

import asyncpg

from app.importers.otlp import NormalizedTrace
from app.queries import uploads as uploads_q

# Whitelist for the API's sort param; never interpolate user input directly.
# Qualified: list_visible joins profiles, which also has a created_at.
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


async def list_visible(
    pool: asyncpg.Pool,
    caller_id: str,
    *,
    scope: str,
    q: str | None,
    provider: str | None,
    model: str | None,
    tool: str | None,
    has_errors: bool,
    date_from: datetime | None,
    date_to: datetime | None,
    sort: str,
    limit: int,
    offset: int,
) -> tuple[list[asyncpg.Record], int]:
    """One parameterized builder for every list scope + search + filters.

    The acquisitions left join serves double duty: the caller's `acquired`
    flag on every card, and the membership test for scope=acquired.
    """
    order_by = SORT_COLUMNS[sort]
    args: list = [caller_id]
    where: list[str] = []

    if scope == "mine":
        where.append("t.owner_id = $1")
    elif scope == "marketplace":
        where.append("t.visibility = 'listed'")
    else:  # acquired: the library shows currently-listed acquisitions only
        where.append("a.id is not null and t.visibility = 'listed'")

    def param(value) -> str:
        args.append(value)
        return f"${len(args)}"

    if q:
        where.append(f"t.search_tsv @@ websearch_to_tsquery('english', {param(q)})")
    if provider:
        where.append(f"t.provider = {param(provider)}")
    if model:
        where.append(f"t.model = {param(model)}")
    if tool:
        where.append(f"{param(tool)} = any(t.tool_names)")
    if has_errors:
        where.append("t.error_count > 0")
    if date_from:
        where.append(f"t.started_at >= {param(date_from)}")
    if date_to:
        where.append(f"t.started_at <= {param(date_to)}")

    rows = await pool.fetch(
        f"""
        select t.id, t.name, t.status, t.started_at, t.duration_ms, t.span_count,
               t.error_count, t.provider, t.model, t.created_at, t.visibility,
               t.tags, t.description, t.listed_at,
               p.display_name as owner_display_name,
               (t.owner_id = $1) as is_owner,
               (a.id is not null) as acquired, a.acquired_at,
               count(*) over () as total
        from traces t
        join profiles p on p.id = t.owner_id
        left join acquisitions a on a.trace_id = t.id and a.consumer_id = $1
        where {" and ".join(where)}
        order by {order_by}, t.id
        limit {param(limit)} offset {param(offset)}
        """,
        *args,
    )
    total = rows[0]["total"] if rows else 0
    return rows, total


async def get_visible(pool: asyncpg.Pool, trace_id: str, caller_id: str) -> asyncpg.Record | None:
    """The one read-path access check: owner sees everything, others see
    listed only. Invisible traces are indistinguishable from absent ones."""
    return await pool.fetchrow(
        """
        select t.*, (t.owner_id = $2) as is_owner, (a.id is not null) as acquired,
               p.display_name as owner_display_name
        from traces t
        join profiles p on p.id = t.owner_id
        left join acquisitions a on a.trace_id = t.id and a.consumer_id = $2
        where t.id = $1 and (t.owner_id = $2 or t.visibility = 'listed')
        """,
        trace_id,
        caller_id,
    )


async def get_visible_with_upload(
    pool: asyncpg.Pool, trace_id: str, caller_id: str
) -> asyncpg.Record | None:
    """Trace plus the upload fields needed to serve the raw download."""
    return await pool.fetchrow(
        """
        select t.id, u.storage_path, u.filename,
               (t.owner_id = $2) as is_owner, (a.id is not null) as acquired
        from traces t
        join uploads u on u.id = t.upload_id
        left join acquisitions a on a.trace_id = t.id and a.consumer_id = $2
        where t.id = $1 and (t.owner_id = $2 or t.visibility = 'listed')
        """,
        trace_id,
        caller_id,
    )


# Sentinel: description is nullable, so None must mean "clear it" when the
# field was sent and "leave untouched" only when it wasn't.
_UNSET: object = object()


async def update_owned(
    pool: asyncpg.Pool,
    trace_id: str,
    owner_id: str,
    *,
    visibility: str | None = None,
    tags: list[str] | None = None,
    description: str | None | object = _UNSET,
) -> asyncpg.Record | None:
    """Patch the contributor-editable fields; omitted means leave untouched.

    `listed_at` records the first listing only (coalesce), so relisting keeps
    the original date.
    """
    sets: list[str] = []
    args: list = [trace_id, owner_id]

    def param(value) -> str:
        args.append(value)
        return f"${len(args)}"

    if visibility is not None:
        sets.append(f"visibility = {param(visibility)}")
        if visibility == "listed":
            sets.append("listed_at = coalesce(listed_at, now())")
    if tags is not None:
        sets.append(f"tags = {param(tags)}")
    if description is not _UNSET:
        sets.append(f"description = {param(description)}")

    return await pool.fetchrow(
        f"""
        update traces set {", ".join(sets)}
        where id = $1 and owner_id = $2
        returning *
        """,
        *args,
    )


async def delete_owned(pool: asyncpg.Pool, trace_id: str, owner_id: str) -> tuple[bool, str | None]:
    """Delete a trace (spans and acquisitions cascade). When it was the last
    trace referencing its upload, delete the upload row too and return the
    storage path so the caller can remove the object after commit.

    Returns (deleted, storage_path_to_delete).
    """
    async with pool.acquire() as conn, conn.transaction():
        upload_id = await conn.fetchval(
            "select upload_id from traces where id = $1 and owner_id = $2",
            trace_id,
            owner_id,
        )
        if upload_id is None:
            return False, None
        # Same lock the ingest rewrite takes: serializes sibling deletes so the
        # last one out reliably sees remaining == 0 and cleans up the upload
        # (under READ COMMITTED, two concurrent deletes each count the other's
        # uncommitted delete as a survivor and both skip cleanup), and keeps a
        # redelivered rewrite from resurrecting the deleted trace.
        await uploads_q.lock(conn, upload_id)
        deleted = await conn.fetchval("delete from traces where id = $1 returning id", trace_id)
        if deleted is None:  # lost the race to a concurrent delete of this trace
            return False, None
        remaining = await conn.fetchval(
            "select count(*) from traces where upload_id = $1", upload_id
        )
        if remaining > 0:
            return True, None
        storage_path = await conn.fetchval(
            "delete from uploads where id = $1 returning storage_path", upload_id
        )
        return True, storage_path


async def ids_for_upload(pool: asyncpg.Pool, upload_id: str) -> list[str]:
    rows = await pool.fetch(
        "select id from traces where upload_id = $1 order by started_at, id", upload_id
    )
    return [str(r["id"]) for r in rows]
