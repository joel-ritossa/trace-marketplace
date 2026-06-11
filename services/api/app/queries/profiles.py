import asyncpg


async def get_profile(pool: asyncpg.Pool, user_id: str) -> asyncpg.Record | None:
    return await pool.fetchrow(
        """
        select display_name, allow_private_llm_analysis, task_categories, created_at
        from profiles where id = $1
        """,
        user_id,
    )


async def update_profile(
    pool: asyncpg.Pool,
    user_id: str,
    *,
    display_name: str | None,
    allow_private_llm_analysis: bool | None,
    task_categories: list[str] | None,
) -> asyncpg.Record | None:
    """Partial update: None leaves the column untouched."""
    return await pool.fetchrow(
        """
        update profiles
        set display_name = coalesce($2, display_name),
            allow_private_llm_analysis = coalesce($3, allow_private_llm_analysis),
            task_categories = coalesce($4, task_categories)
        where id = $1
        returning display_name, allow_private_llm_analysis, task_categories, created_at
        """,
        user_id,
        display_name,
        allow_private_llm_analysis,
        task_categories,
    )
