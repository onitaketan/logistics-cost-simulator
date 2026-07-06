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

    # Celery / queue worker (docs/06 §5). Broker & result backend default to
    # redis_url so a single Redis serves both. task_always_eager defaults to True
    # for local/dev and tests: `.delay()` then runs the task inline in-process,
    # so no Redis or separate worker is required to reach a terminal state.
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    celery_task_always_eager: bool = True

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url

    storage_provider: str = "local"
    storage_bucket: str = "rams-private"
    storage_endpoint_url: str | None = None
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    signed_url_ttl_seconds: int = 120

    ai_engine: str = "mock"
    ai_engine_api_key: str | None = None

    def enforce_production_secrets(self) -> None:
        """Refuse to run outside local with a default/blank signing secret.

        The JWT signing key protects every authenticated call; shipping the
        placeholder "change-me" to staging/production would let anyone mint a
        valid admin token. Fail-closed at startup rather than silently trusting
        forgeable tokens (docs/06 §1).
        """
        if self.app_env != "local" and self.api_secret_key in ("", "change-me"):
            raise RuntimeError(
                "api_secret_key must be set to a non-default value when "
                f"app_env='{self.app_env}'. Refusing to start with an insecure "
                "signing key."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.enforce_production_secrets()
    return settings
