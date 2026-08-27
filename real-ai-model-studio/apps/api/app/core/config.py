from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env candidates absolutely so the values load no matter the CWD. The
# README runs uvicorn from apps/api while `.env` lives at the repo root; a bare
# relative "env_file=.env" silently misses it and falls back to defaults. Check
# repo-root, apps/api, and CWD (later entries take precedence for duplicates).
_CORE = Path(__file__).resolve()
_REPO_ROOT = _CORE.parents[4]   # …/real-ai-model-studio
_API_DIR = _CORE.parents[2]     # …/real-ai-model-studio/apps/api


class Settings(BaseSettings):
    # pydantic-settings gives LATER files higher precedence, so the repo-root
    # .env (the canonical one) is listed LAST and wins over a stray CWD/apps-api
    # .env — avoiding a silent override of e.g. api_secret_key.
    model_config = SettingsConfigDict(
        env_file=(".env", str(_API_DIR / ".env"), str(_REPO_ROOT / ".env")),
        extra="ignore",
    )

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

    # OFFLINE MODE — default ON (fail-closed): prompts and generated likeness
    # data must not leave this machine. While true, external AI engines
    # (openai/replicate) and cloud storage (s3/r2) are refused both at startup
    # (below) and at the engine registry. Real image generation stays possible
    # fully offline via ai_engine=self_hosted (a local Stable Diffusion server).
    # Set OFFLINE_MODE=false explicitly to opt in to external transmission.
    offline_mode: bool = True

    def enforce_offline_consistency(self) -> None:
        """Refuse to start with a configuration that would send data online
        while offline_mode is on. Startup-time twin of the registry guard."""
        if not self.offline_mode:
            return
        if self.ai_engine in ("openai", "replicate"):
            raise RuntimeError(
                f"OFFLINE_MODE 有効のため AI_ENGINE='{self.ai_engine}'（外部送信）では起動できません。"
                "self_hosted / mock を使うか、OFFLINE_MODE=false を明示してください。"
            )
        if self.storage_provider in ("s3", "r2"):
            raise RuntimeError(
                f"OFFLINE_MODE 有効のため STORAGE_PROVIDER='{self.storage_provider}'"
                "（クラウド保存）では起動できません。local を使うか、OFFLINE_MODE=false を明示してください。"
            )

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
    settings.enforce_offline_consistency()
    return settings
