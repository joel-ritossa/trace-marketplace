from pydantic_settings import BaseSettings, SettingsConfigDict

from app.env import env_files


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=env_files(), extra="ignore")

    # Required: no localhost fallbacks, so a misconfigured deployment fails
    # loudly instead of silently pointing at a local stack.
    database_url: str
    redis_url: str
    supabase_url: str
    supabase_service_role_key: str
    web_origin: str = "http://localhost:3000"
    # Mounts /v1/dev/* (worker ping etc.) and honors the X-Fault injection
    # header on uploads. Off by default so a deployment that forgets to set it
    # gets the safe outcome; local .env opts in.
    dev_routes: bool = False

    upload_max_bytes: int = 25 * 1024 * 1024

    # Rate limits (6_architecture.md). Token buckets in Redis; tuned for a
    # local demo, env-overridable for anything else.
    rate_limit_global_rate: float = 50  # req/s
    rate_limit_global_burst: int = 100
    rate_limit_user_rate: float = 10  # req/s
    rate_limit_user_burst: int = 20
    rate_limit_upload_per_minute: int = 10

    # Ingestion reliability (6_architecture.md).
    ingest_max_attempts: int = 5
    ingest_retry_base_seconds: float = 2.0
    ingest_retry_cap_seconds: float = 60.0
    sweep_stuck_after_minutes: int = 10

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json"

    @property
    def supabase_storage_url(self) -> str:
        return f"{self.supabase_url}/storage/v1"

    @property
    def web_origins(self) -> list[str]:
        # Browsers treat localhost and 127.0.0.1 as distinct origins; accept
        # both spellings so CORS doesn't depend on which one the user typed.
        origins = {self.web_origin}
        for a, b in (("//localhost", "//127.0.0.1"), ("//127.0.0.1", "//localhost")):
            origins.add(self.web_origin.replace(a, b))
        return sorted(origins)


settings = Settings()
