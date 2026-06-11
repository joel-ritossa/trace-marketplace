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


async def insert_many(conn: asyncpg.Connection, trace_id: str, spans: list[NormalizedSpan]) -> None:
    rows = [
        (
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
        for s in spans
    ]
    for start in range(0, len(rows), INSERT_BATCH_SIZE):
        await conn.executemany(
            """
            insert into spans (
              trace_id, source_span_id, source_parent_span_id, name, kind, started_at,
              ended_at, duration_ms, status, status_message, error_type, provider,
              model, tool_name, input_tokens, output_tokens, total_tokens,
              attributes, events
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                    $16, $17, $18, $19)
            """,
            rows[start : start + INSERT_BATCH_SIZE],
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


async def get(pool: asyncpg.Pool, trace_id: str, span_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "select * from spans where trace_id = $1 and id = $2", trace_id, span_id
    )
