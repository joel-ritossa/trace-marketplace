import uuid
from collections.abc import Mapping
from typing import Any

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


# The trace's span tree without payloads: id/parent/kind/status/time/token
# columns for every span, plus the few attributes the detail needs, read only
# from the spans that carry them. Each subquery's predicate matches a partial
# index (migration 19) so no other span's attributes are detoasted.
SKELETON = """
    select s.source_span_id as span_id, s.source_parent_span_id as parent_id,
           s.kind, s.status, s.started_at, s.ended_at, s.input_tokens, s.output_tokens,
           t.turn_index, k.skill_name, k.skill_source,
           a.subagent_id, a.description, a.type, a.model, a.background
    from spans s
    left join (
      select id, (attributes ->> 'turn.index')::int as turn_index
      from spans
      where trace_id = $1 and attributes ? 'turn.index'
        and jsonb_typeof(attributes -> 'turn.index') = 'number'
        and attributes ->> 'turn.index' ~ '^-?[0-9]+$'
    ) t on t.id = s.id
    left join (
      select id, attributes ->> 'skill.name' as skill_name,
             attributes ->> 'skill.source' as skill_source
      from spans where trace_id = $1 and attributes ? 'skill.name'
    ) k on k.id = s.id
    left join (
      select id, attributes ->> 'subagent.id' as subagent_id,
             attributes ->> 'subagent.description' as description,
             attributes ->> 'subagent.type' as type, attributes ->> 'subagent.model' as model,
             attributes ->> 'subagent.background' as background
      from spans
      where trace_id = $1
        and attributes ?| array['subagent.id', 'subagent.description', 'subagent.type']
    ) a on a.id = s.id
    where s.trace_id = $1
    order by s.started_at, s.source_span_id
"""


async def skeleton(pool: asyncpg.Pool, trace_id: str) -> list[asyncpg.Record]:
    return await pool.fetch(SKELETON, trace_id)


def _walk(spans: list[Mapping[str, Any]]):
    """Depth-first over the span tree in start order, yielding (span, turn
    index it belongs to, chain of spawn ancestors' span ids). Spans whose
    parent is unknown are roots; a span only reachable through a parent
    cycle is walked from itself, and each span is yielded once."""
    ids = {s["span_id"] for s in spans}
    children: dict[str, list[Mapping[str, Any]]] = {}
    roots = []
    for span in spans:
        if span["parent_id"] in ids:
            children.setdefault(span["parent_id"], []).append(span)
        else:
            roots.append(span)
    has_turns = any(s["turn_index"] is not None for s in spans)
    seen: set[str] = set()
    # Roots first; then anything only reachable through a parent cycle.
    for start in [*roots, *spans]:
        stack = [(start, None, ())]
        while stack:
            span, turn, chain = stack.pop()
            if span["span_id"] in seen:
                continue
            seen.add(span["span_id"])
            if span["turn_index"] is not None:
                turn = span["turn_index"]
            yield span, (turn if has_turns else 0), chain
            if is_spawn(span):
                chain = (*chain, span["span_id"])
            stack.extend((c, turn, chain) for c in reversed(children.get(span["span_id"], [])))


def is_spawn(span: Mapping[str, Any]) -> bool:
    return any(span[k] is not None for k in ("subagent_id", "description", "type"))


def overview(spans: list[Mapping[str, Any]]) -> tuple[list[dict], list[dict]]:
    """One pass over the skeleton (start order) for the detail's two views.

    Skill uses: one per span with `skill.name`, placed in its turn — its own
    `turn.index` (a slash command on a turn span), else its nearest
    ancestor's; turn 0 when the trace has no turn spans; null outside any.

    Subagents: one per spawn span, in start order. Totals cover everything
    under the spawn (nested subagents included); `own_span_count` only its
    direct stream (a nested spawn span counts, its subtree does not).
    """
    skills: list[dict] = []
    agents: dict[str, dict[str, Any]] = {}
    for span, turn, chain in _walk(spans):
        if span["skill_name"] is not None:
            skills.append(
                {
                    "name": span["skill_name"],
                    "source": span["skill_source"],
                    "turn_index": turn,
                    "span_id": span["span_id"],
                }
            )
        for ancestor in chain:
            agent = agents[ancestor]
            agent["span_count"] += 1
            agent["llm_calls"] += span["kind"] == "llm"
            agent["tool_calls"] += span["kind"] == "tool"
            agent["error_count"] += span["status"] == "error"
            agent["input_tokens"] += span["input_tokens"] or 0
            agent["output_tokens"] += span["output_tokens"] or 0
            agent["ended_at"] = max(agent["ended_at"], span["ended_at"])
        if chain:
            agents[chain[-1]]["own_span_count"] += 1
        if is_spawn(span):
            agents[span["span_id"]] = {
                "span_id": span["span_id"],
                "parent_span_id": chain[-1] if chain else None,
                "turn_index": turn,
                "depth": len(chain),
                "description": span["description"],
                "type": span["type"],
                "model": span["model"],
                "background": {"true": True, "false": False}.get(span["background"]),
                "subagent_id": span["subagent_id"],
                "status": "error" if span["status"] == "error" else "ok",
                "started_at": span["started_at"],
                "ended_at": span["ended_at"],
                "span_count": 0,
                "own_span_count": 0,
                "llm_calls": 0,
                "tool_calls": 0,
                "error_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
    order = {s["span_id"]: i for i, s in enumerate(spans)}
    skills.sort(key=lambda u: order[u["span_id"]])
    result = sorted(agents.values(), key=lambda a: order[a["span_id"]])
    for agent in result:
        agent["linked"] = agent.pop("subagent_id") is not None and agent["span_count"] > 0
    return skills, result


def subagent_summary(agents: list[Mapping[str, Any]]) -> dict[str, int]:
    return {
        "count": len(agents),
        "turns": len({a["turn_index"] for a in agents if a["turn_index"] is not None}),
        "max_depth": max((a["depth"] for a in agents), default=0),
    }
