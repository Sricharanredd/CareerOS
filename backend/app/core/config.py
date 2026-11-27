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

    ai_provider: str = "cloudflare"
    ai_provider_order: str = "cloudflare"
    ai_approved_providers: str = "cloudflare"
    ai_allow_training_providers: bool = False
    ai_free_only: bool = True
    ai_timeout_seconds: int = Field(default=90, ge=10, le=300)
    # Provider attempts per run (adapter invocations, not HTTP requests). 2 keeps B2's
    # effective "one retry" now that adapters no longer retry internally.
    ai_max_attempts: int = Field(default=2, ge=1, le=5)
    ai_retry_base_delay_seconds: float = Field(default=1.0, ge=0, le=60)
    ai_retry_max_delay_seconds: float = Field(default=10.0, ge=0, le=300)
    # Circuit breaker (M2-B). Disabled reproduces the M2-A observational behaviour.
    ai_breaker_enabled: bool = True
    ai_breaker_failures: int = Field(default=3, ge=1, le=20)
    ai_breaker_cooldown_seconds: float = Field(default=120.0, ge=0, le=3600)
    ai_breaker_cooldown_max_seconds: float = Field(default=900.0, ge=0, le=86400)
    ai_breaker_backoff_multiplier: float = Field(default=2.0, ge=1, le=10)
    # Quota manager (M3). Disabled skips quota admission but keeps evidence recording.
    ai_quota_enabled: bool = True
    # Router (M4). Disabled reproduces the M3 single-provider path exactly.
    ai_routing_enabled: bool = True
    # Reserved for a later milestone. M4 never enables cross-provider fallback.
    ai_allow_cross_provider_fallback: bool = False
    prompt_version: str = "analysis-v1"

    cloudflare_api_token: str | None = None
    cloudflare_account_id: str | None = None
    cloudflare_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"

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
    def ai_approved_provider_set(self) -> set[str]:
        return {
            name.strip().lower() for name in self.ai_approved_providers.split(",") if name.strip()
        }

    @property
    def ai_provider_chain(self) -> list[str]:
        chain: list[str] = []
        for name in self.ai_provider_order.split(","):
            clean = name.strip().lower()
            if clean and clean not in chain:
                chain.append(clean)
        return chain or [self.ai_provider.strip().lower()]

    @property
    def ai_configured(self) -> bool:
        """Credential presence only. The privacy gate in ``ai/router.py`` is authoritative."""
        return bool(
            "cloudflare" in self.ai_approved_provider_set
            and self.cloudflare_api_token
            and self.cloudflare_account_id
        )

    def active_database_url(self) -> str:
        return (
            self.test_database_url if self.is_test and self.test_database_url else self.database_url
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
