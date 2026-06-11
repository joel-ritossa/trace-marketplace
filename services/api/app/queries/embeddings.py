"""Trace-embedding queries (docs/proposals/similar-behavior.md): the vector
row's lifecycle (rewritten per analyze run, deleted when the LLM gate
closes), the visibility-scoped kNN behind GET /v1/traces/{id}/similar, and
the anchor clause shared by subscription matching and live counts.
"""

import asyncpg

from app.queries.traces import anchor_clauses, make_param


def vector_literal(values: list[float]) -> str:
    """pgvector's text input format — avoids a client-side codec dep for the
    one round-trip direction we need (vectors are only ever read SQL-side)."""
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


async def upsert(
    pool: asyncpg.Pool,
    trace_id: str,
    *,
    embedding: list[float],
    model: str,
    renderer_version: str,
) -> None:
    await pool.execute(
        """
        insert into trace_embeddings (trace_id, embedding, model, renderer_version)
        values ($1, $2::vector, $3, $4)
        on conflict (trace_id) do update set
          embedding = excluded.embedding,
          model = excluded.model,
          renderer_version = excluded.renderer_version,
          created_at = now()
        """,
        trace_id,
        vector_literal(embedding),
        model,
        renderer_version,
    )


async def delete(pool: asyncpg.Pool, trace_id: str) -> None:
    await pool.execute("delete from trace_embeddings where trace_id = $1", trace_id)


async def exists(pool: asyncpg.Pool, trace_id: str) -> bool:
    return await pool.fetchval(
        "select exists (select 1 from trace_embeddings where trace_id = $1)", trace_id
    )


async def similar_traces(
    pool: asyncpg.Pool,
    caller_id: str,
    trace_id: str,
    *,
    limit: int,
    min_similarity: float | None = None,
) -> tuple[list[asyncpg.Record], int | None]:
    """Cosine nearest neighbors among traces visible to the caller (own +
    listed), as list-card rows + similarity. When `min_similarity` is given,
    also returns the count of visible traces at or above it — the
    subscription slider's live preview."""
    rows = await pool.fetch(
        """
        select t.id, t.name, t.status, t.started_at, t.duration_ms, t.span_count,
               t.error_count, t.provider, t.model, t.created_at, t.visibility,
               t.tags, t.description, t.listed_at,
               p.display_name as owner_display_name,
               (t.owner_id = $2) as is_owner,
               (a.id is not null) as acquired, a.acquired_at,
               ta.outcome, ta.outcome_confidence, ta.outcome_provenance, ta.llm_status,
               exists (
                 select 1 from dead_letters dl
                 where dl.trace_id = t.id and dl.requeued_at is null
               ) as analysis_failed,
               (
                 select ri.id from review_items ri
                 where ri.trace_id = t.id and ri.status = 'open' and t.owner_id = $2
                 limit 1
               ) as open_review_item_id,
               1 - (te.embedding <=> qe.embedding) as similarity
        from trace_embeddings qe
        join trace_embeddings te on te.trace_id <> qe.trace_id
        join traces t on t.id = te.trace_id
        join profiles p on p.id = t.owner_id
        left join acquisitions a on a.trace_id = t.id and a.consumer_id = $2
        left join trace_analysis ta on ta.trace_id = t.id
        where qe.trace_id = $1 and (t.owner_id = $2 or t.visibility = 'listed')
        order by te.embedding <=> qe.embedding, t.id
        limit $3
        """,
        trace_id,
        caller_id,
        limit,
    )
    total_above = None
    if min_similarity is not None:
        args: list = [caller_id]
        param = make_param(args)
        clauses = anchor_clauses(param, trace_id, min_similarity)
        total_above = await pool.fetchval(
            f"""
            select count(*) from traces t
            where (t.owner_id = $1 or t.visibility = 'listed')
              and {" and ".join(clauses)}
            """,
            *args,
        )
    return rows, total_above
