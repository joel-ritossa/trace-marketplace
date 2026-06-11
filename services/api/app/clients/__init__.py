"""Process-lifetime clients for external systems (Postgres, Redis, Storage).

Each module follows the same pattern: open_*/close_* called from the FastAPI
lifespan or worker startup/shutdown events, and a module-level accessor that
raises if used before startup.
"""
