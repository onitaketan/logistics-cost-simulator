from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    api_secret_key: str = "change-me"
    access_token_expire_minutes: int = 60
    require_2fa: bool = False

    # Comma-separated allowed origins for the browser frontend (split deployment).
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    database_url: str = "postgresql+psycopg://rams:rams@localhost:5432/rams"
    redis_url: str = "redis://localhost:6379/0"

    storage_provider: str = "local"
    storage_bucket: str = "rams-private"
    storage_endpoint_url: str | None = None
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    signed_url_ttl_seconds: int = 120

    ai_engine: str = "mock"
    ai_engine_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
