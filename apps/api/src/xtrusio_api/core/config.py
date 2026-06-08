"""Application settings loaded from .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Prefix of the placeholder CURSOR_HMAC_KEY shipped in .env.example. A known key
# = forgeable pagination cursors (CWE-798/321), so prod must reject it. Matched
# by prefix (not equality) so any "dev-only-change-me…" variant is also caught.
_WEAK_CURSOR_KEY_PREFIX = "dev-only-change-me"
# Minimum cursor-signing key length enforced in prod. 32 chars is the floor for a
# secrets.token_hex(32) (= 64 hex chars) style key; anything shorter is rejected
# in prod as low-entropy.
_MIN_CURSOR_KEY_LEN = 32


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
    # PAR-C M15: DSN for the least-privileged ``xtrusio_reconciler`` role that
    # runs the reconcile. OPTIONAL by design: when unset (local dev before the
    # operator provisions the role) the reconciler falls back to the request
    # engine and logs a warning. Production should set it so the reconcile runs
    # off the request role; the 0013 trigger gates the priv-escalation bypass on
    # ``current_user = 'xtrusio_reconciler'``. ``None`` here means "absent", not
    # a hardcoded config value.
    reconcile_database_url: str | None = Field(default=None, alias="RECONCILE_DATABASE_URL")
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

    # Shared secret the Supabase Database Webhook (on auth.audit_log_entries)
    # presents in the X-Webhook-Secret header when POSTing GoTrue auth events to
    # POST /api/internal/auth-events. The endpoint is unauthenticated (called by
    # Supabase, not a user); this secret is its only gate. REQUIRED — no default
    # (an empty/known secret would let anyone forge auth-event rows). Prod refuses
    # to boot on the dev placeholder or a secret < 32 chars.
    auth_webhook_secret: str = Field(alias="AUTH_WEBHOOK_SECRET")

    # PAR-D M16: TTL (seconds) for the Valkey-backed effective-permission cache
    # consumed by GET /me. Short by design — the authz gate (require_permission)
    # is never cached, so this only bounds /me display staleness.
    perm_cache_ttl_sec: int = Field(alias="PERM_CACHE_TTL_SEC")

    # PAR-D H5: poll interval (seconds) for the in-process invite-email outbox
    # worker that sends invite emails out of band of the request transaction.
    outbox_poll_sec: float = Field(alias="OUTBOX_POLL_SEC")

    # === Rate-limit hardening (RL-1/RL-2/RL-3) ===
    # Per-EMAIL throttle on /api/signup + /api/signup/resend. Defends the
    # secure-signup design (which ALWAYS sends mail) against email-bombing a
    # known victim by rotating source IPs to dodge the per-IP slowapi limit.
    # Counts REQUESTS PER NORMALIZED EMAIL — never branches on whether the
    # account exists — so it can never become an enumeration oracle.
    # OPTIONAL with a sane default (no .env change needed for dev); an operator
    # can tighten/loosen per-environment without a code change.
    signup_email_max_per_window: int = Field(default=5, alias="SIGNUP_EMAIL_MAX_PER_WINDOW")
    signup_email_window_sec: int = Field(default=3600, alias="SIGNUP_EMAIL_WINDOW_SEC")

    # Authenticated catch-all ceiling (RL-1: wires the previously-dead
    # AUTHED_CATCHALL_RATE). A slowapi limit string (e.g. "120/minute") applied
    # USER-keyed as a default limit to every authenticated route that has no
    # explicit per-route limit; health probes are exempt. Default is generous
    # so a normal multi-query dashboard load (and the test suite) never trips
    # it — it only catches a single user/token hammering the API.
    authed_catchall_rate: str = Field(default="120/minute", alias="AUTHED_CATCHALL_RATE")

    # RL-3: trusted reverse-proxy hop count for client-IP derivation from
    # X-Forwarded-For. 0 (default) = trust ONLY the socket peer, ignore XFF
    # entirely (correct for dev and any deployment where the app is directly
    # exposed). Behind N trusted proxies/CDN hops, set this to N: the limiter
    # then takes the (N+1)-th entry from the RIGHT of XFF (the address the
    # outermost trusted proxy observed), never a blindly-trusted leftmost
    # client-supplied value. PROD OPERATOR NOTE: also pin uvicorn
    # ``--forwarded-allow-ips`` to the real proxy egress IP(s) so a direct
    # attacker cannot inject a forged XFF that the app would honour.
    rate_limit_trusted_proxy_hops: int = Field(default=0, alias="RATE_LIMIT_TRUSTED_PROXY_HOPS")

    log_level: str = Field(alias="LOG_LEVEL")

    startup_reconcile_tolerant: bool = Field(alias="STARTUP_RECONCILE_TOLERANT")

    cors_allow_origins_raw: str = Field(alias="CORS_ALLOW_ORIGINS")

    @property
    def cors_allow_origins(self) -> list[str]:
        """Comma-separated browser origins allowed to call the API."""
        return [o.strip() for o in self.cors_allow_origins_raw.split(",") if o.strip()]

    @model_validator(mode="after")
    def _reject_weak_cursor_key_in_prod(self) -> Self:
        """Fail fast in prod on a known-weak / too-short CURSOR_HMAC_KEY.

        The placeholder shipped in ``.env.example`` was copied verbatim into a
        live ``.env`` (CWE-798/321) — a known signing key lets a client forge
        pagination cursors. We reject the placeholder prefix and obviously
        low-entropy keys ONLY when ``env == "prod"`` so dev/test stay frictionless
        (the dev placeholder keeps working locally; rotating it only invalidates
        ephemeral dev cursors).
        """
        if self.env != "prod":
            return self
        key = self.cursor_hmac_key
        if key.startswith(_WEAK_CURSOR_KEY_PREFIX):
            raise ValueError(
                "CURSOR_HMAC_KEY is set to the shipped dev placeholder in prod. "
                'Generate a fresh key: python -c "import secrets; '
                'print(secrets.token_hex(32))"'
            )
        if len(key) < _MIN_CURSOR_KEY_LEN:
            raise ValueError(
                f"CURSOR_HMAC_KEY is too short for prod ({len(key)} < "
                f"{_MIN_CURSOR_KEY_LEN} chars). Generate a strong key: "
                'python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self

    @model_validator(mode="after")
    def _reject_weak_webhook_secret_in_prod(self) -> Self:
        """Fail fast in prod on a known-weak / too-short AUTH_WEBHOOK_SECRET.

        This secret is the ONLY gate on the unauthenticated auth-event ingest
        endpoint, so a shipped placeholder / low-entropy value would let anyone
        forge auth-event audit rows. Dev/test stay frictionless (the placeholder
        keeps working locally)."""
        if self.env != "prod":
            return self
        secret = self.auth_webhook_secret
        if secret.startswith(_WEAK_CURSOR_KEY_PREFIX) or len(secret) < _MIN_CURSOR_KEY_LEN:
            raise ValueError(
                "AUTH_WEBHOOK_SECRET is the dev placeholder or too short "
                f"(< {_MIN_CURSOR_KEY_LEN} chars) in prod. Generate a strong "
                'secret: python -c "import secrets; print(secrets.token_hex(32))"'
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
