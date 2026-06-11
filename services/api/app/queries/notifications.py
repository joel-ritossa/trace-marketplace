"""Notification queries (2_data-model.md). Creation is server-side only —
worker jobs and API logic; clients read and mark read, nothing else.
"""

import asyncpg

Executor = asyncpg.Pool | asyncpg.Connection


async def review_digest_upsert(
    executor: Executor, *, user_id: str, upload_id: str, new_items: int = 1
) -> None:
    """The per-upload review_request digest (A3 decision 4): one unread
    notification per (user, upload) — the partial unique index is the
    upsert target — its item_count incremented and re-dated as routed
    items land. Once read, the slot frees and the next item starts a
    fresh unread digest. Takes a connection so item + digest can share
    the analysis rewrite's transaction."""
    await executor.execute(
        """
        insert into notifications (user_id, type, payload)
        values (
          $1, 'review_request',
          jsonb_build_object(
            'upload_id', $2::text,
            'filename', (select filename from uploads where id = $2::uuid),
            'item_count', $3::int
          )
        )
        on conflict (user_id, ((payload ->> 'upload_id')))
          where type = 'review_request' and read_at is null
        do update set
          payload = jsonb_set(
            notifications.payload,
            '{item_count}',
            to_jsonb(((notifications.payload ->> 'item_count')::int + $3::int))
          ),
          created_at = now()
        """,
        user_id,
        upload_id,
        new_items,
    )


async def subscription_match_upsert(
    executor: Executor, *, user_id: str, subscription_id: str, name: str, trace_id: str
) -> None:
    """The per-subscription subscription_match digest (A4 decision 9),
    mirroring the review digest: one unread notification per
    (user, subscription), match_count incremented as matches land. trace_id
    survives only while match_count = 1 — a single match links to the
    trace, a digest links to the feed. Once read, the slot frees. The name
    is refreshed on every match so a renamed subscription's open digest
    never shows the stale one."""
    await executor.execute(
        """
        insert into notifications (user_id, type, payload)
        values (
          $1, 'subscription_match',
          jsonb_build_object(
            'subscription_id', $2::text,
            'name', $3::text,
            'match_count', 1,
            'trace_id', $4::text
          )
        )
        on conflict (user_id, ((payload ->> 'subscription_id')))
          where type = 'subscription_match' and read_at is null
        do update set
          payload = jsonb_set(
            jsonb_set(notifications.payload - 'trace_id', '{name}', to_jsonb($3::text)),
            '{match_count}',
            to_jsonb(((notifications.payload ->> 'match_count')::int + 1))
          ),
          created_at = now()
        """,
        user_id,
        subscription_id,
        name,
        trace_id,
    )


async def upload_failed(pool: asyncpg.Pool, upload_id: str) -> None:
    """Emit upload_failed for CLI-source uploads only (2_data-model.md: web
    failures fail in front of the user). Called at both failure sites —
    the permanent-error path and DLQ exhaustion (A3 decision 5); each
    failure event notifies, no dedupe."""
    await pool.execute(
        """
        insert into notifications (user_id, type, payload)
        select u.owner_id, 'upload_failed',
               jsonb_build_object('upload_id', u.id::text, 'filename', u.filename)
        from uploads u
        where u.id = $1 and u.source = 'cli'
        """,
        upload_id,
    )


async def list_for_user(
    pool: asyncpg.Pool, user_id: str, *, limit: int, offset: int
) -> tuple[list[asyncpg.Record], int, int]:
    """Newest first. Returns (rows, total, unread_count)."""
    rows = await pool.fetch(
        """
        select *, count(*) over () as total
        from notifications
        where user_id = $1
        order by created_at desc, id
        limit $2 offset $3
        """,
        user_id,
        limit,
        offset,
    )
    total = (
        rows[0]["total"]
        if rows
        else await pool.fetchval("select count(*) from notifications where user_id = $1", user_id)
    )
    unread = await pool.fetchval(
        "select count(*) from notifications where user_id = $1 and read_at is null", user_id
    )
    return rows, total, unread


async def mark_read(
    pool: asyncpg.Pool, user_id: str, *, ids: list[str] | None, mark_all: bool
) -> None:
    """Recipient-scoped, idempotent: already-read rows keep their original
    read_at; foreign ids silently no-op (they're not the caller's)."""
    if mark_all:
        await pool.execute(
            "update notifications set read_at = now() where user_id = $1 and read_at is null",
            user_id,
        )
        return
    await pool.execute(
        """
        update notifications set read_at = now()
        where user_id = $1 and id = any($2::uuid[]) and read_at is null
        """,
        user_id,
        ids or [],
    )
