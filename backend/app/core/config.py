from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-do-not-use-in-production"


class Settings(BaseSettings):
    # env_ignore_empty: `RAG_MIN_SCORE=` in a .env file means "use the default", not "".
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

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
    # Business timezone: "resolved today" and daily charts follow the customer's calendar.
    timezone: str = "America/Sao_Paulo"

    # --- SLA (resolution targets per priority, in hours) ---
    sla_hours_low: float = 24
    sla_hours_medium: float = 8
    sla_hours_high: float = 4
    sla_hours_critical: float = 1
    # A ticket is "at risk" when less than this share of its SLA window is left.
    sla_at_risk_ratio: float = Field(0.25, gt=0, lt=1)

    # --- Dashboard estimates ---
    # Minutes a person would spend on work the automation did. Shown as an estimate.
    minutes_saved_per_applied_triage: float = 3
    minutes_saved_per_answered_suggestion: float = 5

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

    # --- Knowledge base / RAG ---
    # "local" hashes words into vectors (free, offline, lexical). "voyage" calls Voyage AI
    # (semantic; the first 200M tokens of voyage-4-lite are free per account).
    embedding_provider: Literal["local", "voyage"] = "local"
    voyage_api_key: str | None = None
    embedding_model: str = "voyage-4-lite"
    embedding_timeout_seconds: float = 30.0
    # Articles passed to the answer generator.
    rag_top_k: int = Field(3, ge=1, le=10)
    # Minimum cosine similarity for a chunk to count as relevant. Scores are not comparable
    # across providers, so each provider has its own default (see `effective_rag_min_score`).
    rag_min_score: float | None = Field(None, ge=0, le=1)
    ai_suggest_on_create: bool = True

    @property
    def effective_rag_min_score(self) -> float:
        if self.rag_min_score is not None:
            return self.rag_min_score
        # local: measured on the seed articles, relevant matches scored 0.24-0.36 and unrelated
        # ones at most 0.13. voyage: starting estimate, tune with real tickets.
        return 0.35 if self.embedding_provider == "voyage" else 0.15

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.environment == "production" and self.jwt_secret_key == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be set in production.")
        if self.ai_provider == "claude" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY must be set when AI_PROVIDER=claude.")
        if self.embedding_provider == "voyage" and not self.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY must be set when EMBEDDING_PROVIDER=voyage.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
