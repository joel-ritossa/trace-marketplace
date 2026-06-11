"""Env-file discovery shared by the platform and analysis settings classes.

Lives apart from `app.config` so modules with no platform dependencies (the
offline analysis runner) can load their settings without importing — and
therefore instantiating — the platform `Settings`, which requires DB/Redis env.
"""

from pathlib import Path


def env_files() -> tuple[str, ...]:
    """Locate .env/.env.local upward from cwd (repo root when run from a subdir).

    Real environment variables always take precedence over file values, and
    `.env.local` over `.env`. In containers/cloud no files exist and only the
    injected environment applies.
    """
    for directory in (Path.cwd(), *Path.cwd().parents):
        if (directory / ".env").exists() or (directory / ".env.local").exists():
            return (str(directory / ".env"), str(directory / ".env.local"))
    return (".env", ".env.local")
