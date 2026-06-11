import asyncpg


async def is_allowed(pool: asyncpg.Pool, email: str) -> bool:
    """Allowlist entries are full emails or whole domains ('@example.com');
    mirrors the signup trigger in migration 6."""
    return await pool.fetchval(
        """
        select exists(
          select 1 from allowed_emails
          where entry = $1 or entry = '@' || split_part($1, '@', 2)
        )
        """,
        email.lower(),
    )
