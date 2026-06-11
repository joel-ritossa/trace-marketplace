from collections.abc import Callable

import asyncpg

from app.importers.otlp import NormalizedTrace
from app.queries import uploads as uploads_q
from app.schemas.trace import TraceFilterQuery, csv_values

# Whitelist for the API's sort param; never interpolate user input directly.
# Qualified: list_visible joins profiles, which also has a created_at.
SORT_COLUMNS = {
    "created_at": "t.created_at desc",
    "duration_ms": "t.duration_ms desc",
    "span_count": "t.span_count desc",
}

# (filter field, ta column) pairs for the CSV equality predicates.
_CSV_COLUMNS = (
    ("outcome", "ta.outcome"),
    ("failure_mode", "ta.failure_mode"),
    ("task_category", "ta.task_category"),
    ("loop_kind", "ta.loop_kind"),
    ("outcome_provenance", "ta.outcome_provenance"),
    ("failure_mode_provenance", "ta.failure_mode_provenance"),
    ("task_category_provenance", "ta.task_category_provenance"),
)

_BOOL_COLUMNS = (
    ("has_retry_loop", "ta.has_retry_loop"),
    ("recovered_from_error", "ta.recovered_from_error"),
    ("truncation_suspected", "ta.truncation_suspected"),
)

_GTE_ANALYSIS_COLUMNS = (
    ("outcome_confidence_gte", "ta.outcome_confidence"),
    ("task_category_confidence_gte", "ta.task_category_confidence"),
    ("llm_call_count_gte", "ta.llm_call_count"),
    ("tool_call_count_gte", "ta.tool_call_count"),
)

Param = Callable[[object], str]


def stage1_clauses(filters: TraceFilterQuery, param: Param) -> list[str]:
    """WHERE fragments over `traces t` only — the pre-A4 vocabulary."""
    where: list[str] = []
    if filters.q:
        where.append(f"t.search_tsv @@ websearch_to_tsquery('english', {param(filters.q)})")
    if filters.provider:
        where.append(f"t.provider = {param(filters.provider)}")
    if filters.model:
        where.append(f"t.model = {param(filters.model)}")
    if filters.tool:
        where.append(f"{param(filters.tool)} = any(t.tool_names)")
    if filters.has_errors:
        where.append("t.error_count > 0")
    if filters.date_from:
        where.append(f"t.started_at >= {param(filters.date_from)}")
    if filters.date_to:
        where.append(f"t.started_at <= {param(filters.date_to)}")
    if filters.duration_ms_gte is not None:
        where.append(f"t.duration_ms >= {param(filters.duration_ms_gte)}")
    if filters.total_tokens_gte is not None:
        where.append(f"t.total_tokens >= {param(filters.total_tokens_gte)}")
    return where


def analysis_clauses(filters: TraceFilterQuery, param: Param) -> list[str]:
    """WHERE fragments over `trace_analysis ta` (A4 filter extension).
    Null never matches: every predicate is a plain comparison, so
    not-yet-analyzed traces (no row → all-null left join) drop out."""
    where: list[str] = []
    for field, column in _CSV_COLUMNS:
        raw = getattr(filters, field)
        if raw:
            where.append(f"{column} = any({param(csv_values(raw))}::text[])")
    for field, column in _BOOL_COLUMNS:
        value = getattr(filters, field)
        if value is not None:
            where.append(f"{column} = {param(value)}")
    for field, column in _GTE_ANALYSIS_COLUMNS:
        value = getattr(filters, field)
        if value is not None:
            where.append(f"{column} >= {param(value)}")
    for name, bound in filters.parsed_metrics:
        key = param(name)
        if bound is True:
            where.append(f"ta.metric_scores -> {key} = 'true'::jsonb")
        else:
            # The typeof guard makes a flag metric queried as a number (or a
            # number queried as a flag) match nothing instead of erroring.
            where.append(
                f"(jsonb_typeof(ta.metric_scores -> {key}) = 'number'"
                f" and (ta.metric_scores ->> {key})::numeric >= {param(bound)})"
            )
    return where


def filter_clauses(filters: TraceFilterQuery, param: Param) -> list[str]:
    """The full vocabulary — shared by GET /v1/traces, subscription match
    evaluation, and the feed (A4 decision 1). References only the `t` and
    `ta` aliases."""
    return stage1_clauses(filters, param) + analysis_clauses(filters, param)


def anchor_clauses(param: Param, anchor_trace_id: str, threshold: float) -> list[str]:
    """The behavior-anchor predicate (docs/proposals/similar-behavior.md),
    over the `t` alias like every other clause: within `threshold` cosine
    similarity of the anchor's embedding, and never the anchor itself. No
    embedding on either side ⇒ no match — an anchored subscription is inert
    until both vectors exist."""
    return [
        f"""exists (
        select 1
        from trace_embeddings qe
        join trace_embeddings te on te.trace_id = t.id
        where qe.trace_id = {param(anchor_trace_id)}
          and 1 - (qe.embedding <=> te.embedding) >= {param(threshold)}
      )""",
        f"t.id <> {param(anchor_trace_id)}",
    ]


def make_param(args: list) -> Param:
    """The $N placeholder closure used with the clause builders."""

    def param(value: object) -> str:
        args.append(value)
        return f"${len(args)}"

    return param


async def upsert(
    conn: asyncpg.Connection,
    *,
    upload_id: str,
    owner_id: str,
    trace: NormalizedTrace,
    source_format: str,
    importer_version: str,
) -> str:
    """Rewrite one trace's normalized columns under stable identity.

    Keyed on (owner_id, source_trace_id) so traces.id survives both a
    re-ingest and a re-upload (6_architecture.md, A2 amendment + A6) — rows
    hung off it (acquisitions, trace_analysis, review items) are never
    cascade-destroyed by a rewrite. The newest upload adopts the row
    (upload_id moves), which is what makes re-syncing a grown session log
    idempotent: existing turns update in place, new turns append
    (8_session-ingestion.md). Owner state (visibility, tags, description,
    listed_at) is untouched; the analysis retry budget resets because
    rewritten content gets a fresh analysis run.
    """
    return await conn.fetchval(
        """
        insert into traces (
          upload_id, owner_id, source_trace_id, name, status, started_at, ended_at,
          duration_ms, span_count, error_count, provider, model, service_name,
          tool_names, error_types, total_tokens, source_format, importer_version
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
        on conflict (owner_id, source_trace_id) do update set
          upload_id = excluded.upload_id,
          name = excluded.name,
          status = excluded.status,
          started_at = excluded.started_at,
          ended_at = excluded.ended_at,
          duration_ms = excluded.duration_ms,
          span_count = excluded.span_count,
          error_count = excluded.error_count,
          provider = excluded.provider,
          model = excluded.model,
          service_name = excluded.service_name,
          tool_names = excluded.tool_names,
          error_types = excluded.error_types,
          total_tokens = excluded.total_tokens,
          source_format = excluded.source_format,
          importer_version = excluded.importer_version,
          analysis_attempts = 0,
          analysis_attempted_at = null
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
        trace.total_tokens,
        source_format,
        importer_version,
    )


async def delete_absent(conn: asyncpg.Connection, upload_id: str, keep_ids: list[str]) -> None:
    """Drop traces whose source_trace_id vanished from the re-imported
    payload — the delete half of the stable-identity rewrite."""
    await conn.execute(
        "delete from traces where upload_id = $1 and not (id = any($2::uuid[]))",
        upload_id,
        keep_ids,
    )


def _scope_clause(scope: str) -> str:
    if scope == "mine":
        return "t.owner_id = $1"
    if scope == "marketplace":
        return "t.visibility = 'listed'"
    # acquired: the library shows currently-listed acquisitions only
    return "a.id is not null and t.visibility = 'listed'"


async def list_visible(
    pool: asyncpg.Pool,
    caller_id: str,
    *,
    scope: str,
    filters: TraceFilterQuery,
    sort: str,
    limit: int,
    offset: int,
    anchor: tuple[str, float] | None = None,
) -> tuple[list[asyncpg.Record], int, int | None]:
    """One parameterized builder for every list scope + search + filters.

    The acquisitions left join serves double duty: the caller's `acquired`
    flag on every card, and the membership test for scope=acquired.

    `anchor` is the behavior-anchor predicate — only the subscription feed
    passes it (an anchored subscription's results must honor the anchor the
    same way match evaluation does).

    Returns (rows, total, excluded_unanalyzed) — the third is the count of
    traces matching the non-analysis filters with no trace_analysis row,
    populated only when an analysis predicate is active (A4 decision 4).
    """
    order_by = SORT_COLUMNS[sort]
    args: list = [caller_id]
    param = make_param(args)
    pre_analysis = [_scope_clause(scope), *stage1_clauses(filters, param)]
    if anchor is not None:
        pre_analysis.extend(anchor_clauses(param, *anchor))
    pre_analysis_args = list(args)
    where = pre_analysis + analysis_clauses(filters, param)

    base = f"""
        from traces t
        join profiles p on p.id = t.owner_id
        left join acquisitions a on a.trace_id = t.id and a.consumer_id = $1
        left join trace_analysis ta on ta.trace_id = t.id
        where {" and ".join(where)}
    """
    filter_args = list(args)  # before limit/offset, for the count fallback
    rows = await pool.fetch(
        f"""
        select t.id, t.name, t.status, t.started_at, t.duration_ms, t.span_count,
               t.error_count, t.provider, t.model, t.created_at, t.visibility,
               t.tags, t.description, t.listed_at,
               p.display_name as owner_display_name,
               (t.owner_id = $1) as is_owner,
               (a.id is not null) as acquired, a.acquired_at,
               ta.outcome, ta.outcome_confidence, ta.outcome_provenance, ta.llm_status,
               exists (
                 select 1 from dead_letters dl
                 where dl.trace_id = t.id and dl.requeued_at is null
               ) as analysis_failed,
               (
                 select ri.id from review_items ri
                 where ri.trace_id = t.id and ri.status = 'open' and t.owner_id = $1
                 limit 1
               ) as open_review_item_id,
               count(*) over () as total
        {base}
        order by {order_by}, t.id
        limit {param(limit)} offset {param(offset)}
        """,
        *args,
    )
    if rows:
        total = rows[0]["total"]
    else:
        # Past-the-end offset returns no rows, so the window total is lost;
        # count separately so the client can tell "empty" from "out of range".
        total = await pool.fetchval(f"select count(*) {base}", *filter_args)

    excluded = None
    if filters.has_analysis_predicate:
        # Skipped traces have rows (their nulls honestly never match) and are
        # deliberately not in this count — they *were* analyzed.
        excluded = await pool.fetchval(
            f"""
            select count(*)
            from traces t
            left join acquisitions a on a.trace_id = t.id and a.consumer_id = $1
            left join trace_analysis ta on ta.trace_id = t.id
            where {" and ".join(pre_analysis)} and ta.trace_id is null
            """,
            *pre_analysis_args,
        )
    return rows, total, excluded


async def metric_keys(pool: asyncpg.Pool, caller_id: str) -> list[str]:
    """Observed metric_scores keys over traces visible to the caller (own +
    listed) — the filter UI enumerates these (A4 decision 5)."""
    rows = await pool.fetch(
        """
        select distinct jsonb_object_keys(ta.metric_scores) as key
        from trace_analysis ta
        join traces t on t.id = ta.trace_id
        where ta.metric_scores is not null
          and (t.owner_id = $1 or t.visibility = 'listed')
        order by key
        """,
        caller_id,
    )
    return [r["key"] for r in rows]


async def get_visible(pool: asyncpg.Pool, trace_id: str, caller_id: str) -> asyncpg.Record | None:
    """The one read-path access check: owner sees everything, others see
    listed only. Invisible traces are indistinguishable from absent ones."""
    return await pool.fetchrow(
        """
        select t.*, (t.owner_id = $2) as is_owner, (a.id is not null) as acquired,
               p.display_name as owner_display_name,
               ta.outcome, ta.outcome_confidence, ta.outcome_provenance, ta.llm_status,
               exists (
                 select 1 from dead_letters dl
                 where dl.trace_id = t.id and dl.requeued_at is null
               ) as analysis_failed,
               (
                 -- Owner-only (A3 decision 8): review items are the owner's
                 -- backlog, never shown on a consumer's card.
                 select ri.id from review_items ri
                 where ri.trace_id = t.id and ri.status = 'open' and t.owner_id = $2
                 limit 1
               ) as open_review_item_id
        from traces t
        join profiles p on p.id = t.owner_id
        left join acquisitions a on a.trace_id = t.id and a.consumer_id = $2
        left join trace_analysis ta on ta.trace_id = t.id
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


async def fill_listing_meta(
    pool: asyncpg.Pool,
    trace_id: str,
    *,
    tags: list[str],
    description: str | None,
) -> None:
    """Write machine-generated listing copy fill-if-empty: owner values are
    never overwritten, checked atomically in SQL so a concurrent owner edit
    wins (1_analysis.md listing-copy rules)."""
    await pool.execute(
        """
        update traces
        set tags = case when cardinality(tags) = 0 then $2::text[] else tags end,
            description = coalesce(description, $3)
        where id = $1
        """,
        trace_id,
        tags,
        description,
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
