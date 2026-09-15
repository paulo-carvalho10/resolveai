from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ResolveAI"
    environment: str = "development"
    log_level: str = "INFO"

    # 127.0.0.1 instead of localhost: on Windows, localhost resolves to ::1 first, where the
    # WSL port relay can accept the connection without forwarding it and hang forever.
    database_url: str = (
        "postgresql+psycopg://resolveai:resolveai@127.0.0.1:5432/resolveai?connect_timeout=10"
    )

    jwt_secret_key: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cors_origins: list[str] = ["http://localhost:5173"]

    # --- AI triage ---
    # "keyword" runs a local, free classifier (tests, demos). "claude" calls the Anthropic API.
    ai_provider: Literal["keyword", "claude"] = "keyword"
    anthropic_api_key: str | None = None
    # Classification is a short, well-specified task: the fastest, cheapest model handles it.
    # Switch to claude-sonnet-5 or claude-opus-5 here if accuracy needs to go up.
    ai_model: str = "claude-haiku-4-5"
    # Only sent to models that support it (not Haiku 4.5). Low keeps latency and cost down.
    ai_effort: Literal["low", "medium", "high", "xhigh", "max"] = "low"
    ai_timeout_seconds: float = 30.0
    ai_max_retries: int = 2
    # Below this confidence the AI result is stored as a suggestion but not applied.
    ai_auto_apply_min_confidence: float = Field(0.7, ge=0, le=1)
    ai_analyze_on_create: bool = True

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.environment == "production" and self.jwt_secret_key == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be set in production.")
        if self.ai_provider == "claude" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set when AI_PROVIDER=claude.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
