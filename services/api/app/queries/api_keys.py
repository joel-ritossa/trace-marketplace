import asyncpg

# Update last_used_at at most this often per key: it's list-rendering
# bookkeeping, not an audit log, so one write per minute is plenty.
LAST_USED_THROTTLE_SECONDS = 60


async def create(
    pool: asyncpg.Pool,
    *,
    owner_id: str,
    name: str,
    key_hash: str,
    key_display: str,
) -> asyncpg.Record:
    return await pool.fetchrow(
        """
        insert into api_keys (owner_id, name, key_hash, key_display)
        values ($1, $2, $3, $4)
        returning id, name, key_display, scope, created_at
        """,
        owner_id,
        name,
        key_hash,
        key_display,
    )


async def list_owned(pool: asyncpg.Pool, owner_id: str) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        select id, name, key_display, scope, created_at, last_used_at, revoked_at
        from api_keys
        where owner_id = $1
        order by created_at desc
        """,
        owner_id,
    )


async def revoke(pool: asyncpg.Pool, key_id: str, owner_id: str) -> bool:
    """Soft revoke; idempotent. Returns False only when the row isn't the
    caller's (404 material — already-revoked is a success)."""
    return (
        await pool.fetchval(
            """
            update api_keys
            set revoked_at = coalesce(revoked_at, now())
            where id = $1 and owner_id = $2
            returning id
            """,
            key_id,
            owner_id,
        )
        is not None
    )


async def find_active_by_hash(pool: asyncpg.Pool, key_hash: str) -> asyncpg.Record | None:
    """Only upload-scoped keys authenticate: today every key is `upload`, but
    the predicate fails closed if a wider scope ever lands — granting the
    upload pair to it must be a deliberate change here."""
    return await pool.fetchrow(
        """
        select id, owner_id from api_keys
        where key_hash = $1 and revoked_at is null and scope = 'upload'
        """,
        key_hash,
    )


async def touch_last_used(pool: asyncpg.Pool, key_id: str) -> None:
    await pool.execute(
        """
        update api_keys
        set last_used_at = now()
        where id = $1
          and (last_used_at is null
               or last_used_at < now() - make_interval(secs => $2))
        """,
        key_id,
        float(LAST_USED_THROTTLE_SECONDS),
    )
