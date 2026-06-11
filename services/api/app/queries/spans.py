import uuid

import asyncpg

from app.importers.otlp import NormalizedSpan

# Keep executemany batches bounded so a huge trace doesn't build one giant
# argument list in memory.
INSERT_BATCH_SIZE = 1000

# Tree-building fields only; attributes/events stay behind the per-span
# endpoint so list payloads scale with span count, not content size (3_api.md).
LIGHT_FIELDS = """
    id, source_span_id, source_parent_span_id, name, kind, started_at, ended_at,
    duration_ms, status, status_message, error_type, provider, model, tool_name,
    input_tokens, output_tokens, total_tokens
"""


async def delete_for_trace(conn: asyncpg.Connection, trace_id: str) -> None:
    """Drop one trace's spans (span_raw cascades) ahead of a rewrite — the
    per-trace half of the stable-identity ingest (6_architecture.md)."""
    await conn.execute("delete from spans where trace_id = $1", trace_id)


async def insert_many(conn: asyncpg.Connection, trace_id: str, spans: list[NormalizedSpan]) -> None:
    """Write the scrubbed span rows plus their owner-only span_raw siblings.

    Ids are minted here so both tables insert as parallel executemany batches
    in the caller's transaction without `returning id` plumbing.
    """
    ids = [str(uuid.uuid4()) for _ in spans]
    rows = [
        (
            span_id,
            trace_id,
            s.source_span_id,
            s.source_parent_span_id,
            s.name,
            s.kind,
            s.started_at,
            s.ended_at,
            s.duration_ms,
            s.status,
            s.status_message,
            s.error_type,
            s.provider,
            s.model,
            s.tool_name,
            s.input_tokens,
            s.output_tokens,
            s.total_tokens,
            s.attributes,
            s.events,
        )
        for span_id, s in zip(ids, spans, strict=True)
    ]
    raw_rows = [
        (span_id, s.raw_attributes, s.raw_events, s.raw_status_message)
        for span_id, s in zip(ids, spans, strict=True)
    ]
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        await conn.executemany(
            """
            insert into spans (
              id, trace_id, source_span_id, source_parent_span_id, name, kind, started_at,
              ended_at, duration_ms, status, status_message, error_type, provider,
              model, tool_name, input_tokens, output_tokens, total_tokens,
              attributes, events
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19, $20)
            """,
            rows[start : start + INSERT_BATCH_SIZE],
        )
        await conn.executemany(
            """
            insert into span_raw (span_id, attributes, events, status_message)
            values ($1, $2, $3, $4)
            """,
            raw_rows[start : start + INSERT_BATCH_SIZE],
        )


async def list_for_trace(
    pool: asyncpg.Pool, trace_id: str, *, limit: int, offset: int
) -> tuple[list[asyncpg.Record], int]:
    rows = await pool.fetch(
        f"""
        select {LIGHT_FIELDS}, count(*) over () as total
        from spans
        where trace_id = $1
        order by started_at, source_span_id
        limit $2 offset $3
        """,
        trace_id,
        limit,
        offset,
    )
    total = rows[0]["total"] if rows else 0
    return rows, total


async def get(
    pool: asyncpg.Pool, trace_id: str, span_id: str, *, include_raw: bool
) -> asyncpg.Record | None:
    """Span detail row; with include_raw (owners only — 7_redaction.md) the
    raw_* columns carry the unscrubbed content from span_raw."""
    if not include_raw:
        return await pool.fetchrow(
            "select * from spans where trace_id = $1 and id = $2", trace_id, span_id
        )
    return await pool.fetchrow(
        """
        select s.*, r.attributes as raw_attributes, r.events as raw_events,
               r.status_message as raw_status_message
        from spans s
        left join span_raw r on r.span_id = s.id
        where s.trace_id = $1 and s.id = $2
        """,
        trace_id,
        span_id,
    )
