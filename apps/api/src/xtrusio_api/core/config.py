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

    process_role: str = Field(default="api", alias="XTRUSIO_PROCESS_ROLE")

    database_url: str = Field(alias="DATABASE_URL")
    valkey_url: str = Field(default="redis://localhost:63792/0", alias="VALKEY_URL")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwks_url: str = Field(alias="SUPABASE_JWKS_URL")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
