from functools import lru_cache

from pydantic import model_validator
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

    @model_validator(mode="after")
    def _require_real_secret_in_production(self) -> "Settings":
        if self.environment == "production" and self.jwt_secret_key == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET_KEY must be set in production.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
