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
    # PAR-B: environment flag ("dev" / "prod" / "test"). Gates the prod-only
    # pooler-hostname assertion and stricter logging in main.py.
    env: str = Field(alias="XTRUSIO_ENV")

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
    # PAR-B H7: how long the verifier may serve a stale JWKS doc when the
    # upstream fetch fails. Bounded blast radius for a key-rotation outage.
    jwks_stale_grace_sec: float = Field(alias="JWKS_STALE_GRACE_SEC")
    supabase_timeout_sec: float = Field(alias="SUPABASE_TIMEOUT_SEC")

    # PAR-B C3: server-side statement / idle-in-transaction timeouts pushed
    # into the asyncpg connection via ``connect_args``. Read from .env so an
    # operator can tune per-environment without code changes.
    db_statement_timeout_ms: int = Field(alias="DB_STATEMENT_TIMEOUT_MS")
    db_idle_in_tx_timeout_ms: int = Field(alias="DB_IDLE_IN_TX_TIMEOUT_MS")
    db_pool_size: int = Field(alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(alias="DB_MAX_OVERFLOW")
    db_pool_recycle_sec: int = Field(alias="DB_POOL_RECYCLE_SEC")
    db_pool_timeout_sec: int = Field(alias="DB_POOL_TIMEOUT_SEC")

    # PAR-B L16: hard cap on request body size before Pydantic.
    max_request_body_bytes: int = Field(alias="MAX_REQUEST_BODY_BYTES")

    # PAR-D M5: secret key used to HMAC-sign pagination cursors so a client
    # cannot forge / tamper with an opaque cursor. No default — fail fast.
    cursor_hmac_key: str = Field(alias="CURSOR_HMAC_KEY")

    # PAR-D M16: TTL (seconds) for the Valkey-backed effective-permission cache
    # consumed by GET /me. Short by design — the authz gate (require_permission)
    # is never cached, so this only bounds /me display staleness.
    perm_cache_ttl_sec: int = Field(alias="PERM_CACHE_TTL_SEC")

    # PAR-D H5: poll interval (seconds) for the in-process invite-email outbox
    # worker that sends invite emails out of band of the request transaction.
    outbox_poll_sec: float = Field(alias="OUTBOX_POLL_SEC")

    log_level: str = Field(alias="LOG_LEVEL")

    startup_reconcile_tolerant: bool = Field(alias="STARTUP_RECONCILE_TOLERANT")

    cors_allow_origins_raw: str = Field(alias="CORS_ALLOW_ORIGINS")

    @property
    def cors_allow_origins(self) -> list[str]:
        """Comma-separated browser origins allowed to call the API."""
        return [o.strip() for o in self.cors_allow_origins_raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
