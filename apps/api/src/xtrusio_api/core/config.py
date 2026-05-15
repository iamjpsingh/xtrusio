"""Application settings loaded from .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env_file() -> Path | None:
    """Walk up from this file to find the repo-root `.env`.

    `apps/api/...` runs from various CWDs (apps/api during alembic, repo root during
    `make api`). Anchor to the file location instead of CWD so it always works.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


_ENV_FILE = _find_env_file()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE else ".env",
        extra="ignore",
        case_sensitive=False,
    )

    process_role: str = Field(alias="XTRUSIO_PROCESS_ROLE")

    database_url: str = Field(alias="DATABASE_URL")
    valkey_url: str = Field(alias="VALKEY_URL")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwks_url: str = Field(alias="SUPABASE_JWKS_URL")

    # Browser-facing URL of the SPA (used in CLI output, e.g. bootstrap).
    web_app_url: str = Field(alias="WEB_APP_URL")

    # Network / tuning — every environment-varying value comes from .env.
    jwks_ttl_sec: float = Field(alias="JWKS_TTL_SEC")
    jwks_fetch_timeout_sec: float = Field(alias="JWKS_FETCH_TIMEOUT_SEC")
    supabase_timeout_sec: float = Field(alias="SUPABASE_TIMEOUT_SEC")

    log_level: str = Field(alias="LOG_LEVEL")

    cors_allow_origins_raw: str = Field(alias="CORS_ALLOW_ORIGINS")

    @property
    def cors_allow_origins(self) -> list[str]:
        """Comma-separated browser origins allowed to call the API."""
        return [o.strip() for o in self.cors_allow_origins_raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
