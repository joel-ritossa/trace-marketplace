import asyncpg


async def get_profile(pool: asyncpg.Pool, user_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        "select display_name, created_at from profiles where id = $1", user_id
    )
