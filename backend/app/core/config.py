from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Typed application configuration. Values come from environment or backend/.env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    careeros_env: Literal["development", "test", "production"] = "development"
    app_name: str = "CareerOS"
    secret_key: str = Field(min_length=16)
    log_level: str = "INFO"

    database_url: str
    test_database_url: str | None = None

    access_token_ttl_minutes: int = Field(default=15, ge=1, le=240)
    refresh_token_ttl_days: int = Field(default=14, ge=1, le=90)
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_domain: str | None = None

    login_max_attempts: int = Field(default=5, ge=3, le=20)
    login_lockout_seconds: int = Field(default=300, ge=30, le=3600)

    cors_origins: str = "http://localhost:5173"
    storage_dir: str = "./storage"
    max_upload_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=25 * 1024 * 1024)

    ai_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    ai_timeout_seconds: int = Field(default=90, ge=10, le=300)
    prompt_version: str = "analysis-v1"

    @field_validator("secret_key")
    @classmethod
    def _secret_must_be_real(cls, value: str) -> str:
        if value.strip().lower().startswith("change-me"):
            raise ValueError("SECRET_KEY still holds the example placeholder")
        return value

    @property
    def is_test(self) -> bool:
        return self.careeros_env == "test"

    @property
    def is_production(self) -> bool:
        return self.careeros_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        return path if path.is_absolute() else (BASE_DIR / path).resolve()

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def active_database_url(self) -> str:
        return (
            self.test_database_url if self.is_test and self.test_database_url else self.database_url
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
