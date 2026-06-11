"""Trace loading for analysis: normalized rows → `TraceInput`.

The one DB read path into the analysis contract — shared by the offline
runner's DB mode and (at A2) the `analyze_trace` worker job. `select *` is
deliberate: `TraceInput` mirrors the full normalized column set and ignores
platform-only columns (owner_id, upload_id, …).
"""

import asyncpg

from app.analysis import TraceInput


async def fetch_trace_input(pool: asyncpg.Pool, trace_id: str) -> TraceInput | None:
    trace_row = await pool.fetchrow("select * from traces where id = $1", trace_id)
    if trace_row is None:
        return None
    span_rows = await pool.fetch(
        "select * from spans where trace_id = $1 order by started_at, source_span_id",
        trace_id,
    )
    return TraceInput.from_db_rows(trace_row, list(span_rows))
