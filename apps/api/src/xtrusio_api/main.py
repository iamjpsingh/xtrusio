"""FastAPI application entrypoint.

PAR-B operational hardening (M13, M14, L1, L2, L16):
  - structlog configured first thing in the lifespan
  - request-id middleware so every log line + error body carries the id
  - body-size cap before Pydantic
  - explicit CORS allow lists + max_age
  - global exception handler so 500s share a stable response shape
  - JWKS httpx client closed on shutdown
  - prod-only warning when ``DATABASE_URL`` doesn't point at the pooler
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.extension import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.auth import close_jwks_client
from .core.config import get_settings
from .core.db import SessionLocal
from .core.email_throttle import close_email_throttle
from .core.logging import configure_logging, get_logger
from .core.middleware import (
    BodySizeLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from .core.outbox_worker import run_outbox_worker
from .core.perm_cache import close_perm_cache
from .core.rate_limit import limiter
from .core.reconciler_db import get_reconciler_sessionmaker
from .rbac.reconcile import reconcile_rbac, reconcile_user_roles_from_enums
from .routes import audit_catalog as audit_catalog_routes
from .routes import health as health_routes
from .routes import internal_auth_events as internal_auth_events_routes
from .routes import invite_acceptance as invite_acceptance_routes
from .routes import me as me_routes
from .routes import onboarding as onboarding_routes
from .routes import permissions as permissions_routes
from .routes import platform_audit_log as platform_audit_log_routes
from .routes import platform_clients as platform_clients_routes
from .routes import platform_invites as platform_invites_routes
from .routes import platform_job_runs as platform_job_runs_routes
from .routes import platform_role_grants as platform_role_grants_routes
from .routes import platform_roles as platform_roles_routes
from .routes import platform_settings as platform_settings_routes
from .routes import platform_stats as platform_stats_routes
from .routes import platform_users as platform_users_routes
from .routes import signup as signup_routes
from .routes import tenant_invites as tenant_invites_routes
from .routes import tenants as tenants_routes
from .routes import workspace_audit_log as workspace_audit_log_routes
from .routes import workspace_members as workspace_members_routes
from .routes import workspace_role_grants as workspace_role_grants_routes
from .routes import workspace_roles as workspace_roles_routes
from .routes import workspace_settings as workspace_settings_routes
from .routes import workspace_stats as workspace_stats_routes

# PAR-D M9: advisory-lock key gating the boot reconcile to a single process.
# 0x52424143 = "RBAC". Reconcile is idempotent, so a missed lock only costs a
# redundant pass (never correctness) if the pooler doesn't pin the session.
_RECONCILE_LOCK_KEY = 0x52424143


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    log = get_logger(__name__)
    settings = get_settings()

    # PAR-B C3: production sanity check. The direct-DB hostname can be retired
    # by Supabase under-the-hood (paid projects are not exempt — observed
    # 2026-05-26 on this project); warning at boot makes a misconfig visible
    # in the very first log line rather than at first inbound request.
    if settings.env == "prod" and ".pooler.supabase.com" not in settings.database_url:
        log.warning(
            "database_url_not_pooler",
            hint="prod should point DATABASE_URL at *.pooler.supabase.com",
        )

    try:
        # PAR-D M9: gate the boot reconcile behind a session-level advisory lock
        # held on a dedicated connection so only one process runs it when N
        # workers boot together. The reconciles run on separate sessions (each
        # self-commits); the lock connection stays open around both and is
        # released in the finally.
        async with SessionLocal() as lock_s:
            got = bool(
                (
                    await lock_s.execute(
                        text("SELECT pg_try_advisory_lock(:k)"),
                        {"k": _RECONCILE_LOCK_KEY},
                    )
                ).scalar_one()
            )
            # End the lock session's transaction immediately. ``pg_try_advisory_lock``
            # is SESSION-scoped — the lock is held on the CONNECTION until we unlock
            # or the session closes, NOT tied to this transaction. Committing now means
            # the lock connection sits plain-idle (not idle-IN-TRANSACTION) while the
            # reconcile runs. Otherwise, on slow managed Postgres the reconcile can
            # exceed ``idle_in_transaction_session_timeout`` and the server terminates
            # this idle lock connection, so the later pg_advisory_unlock hits a closed
            # connection (regression introduced with the M9 lock in PAR-D slice 2a).
            await lock_s.commit()
            if not got:
                log.info("rbac_reconcile_skipped_lock_held")
            else:
                # PAR-C M15: run the reconcile (which sets the bypass GUC) on
                # the dedicated xtrusio_reconciler role when provisioned, so the
                # request path can never effect the bypass. Falls back to the
                # request engine in dev (RECONCILE_DATABASE_URL unset) with a
                # warning — the bypass then rides postgres until the operator
                # provisions the role.
                reconcile_maker = get_reconciler_sessionmaker()
                if reconcile_maker is None:
                    reconcile_maker = SessionLocal
                    log.warning(
                        "rbac_reconcile_on_request_engine",
                        reason="RECONCILE_DATABASE_URL unset",
                    )
                try:
                    async with reconcile_maker() as _s:
                        await reconcile_rbac(_s)
                    async with reconcile_maker() as _s:
                        await reconcile_user_roles_from_enums(_s)
                finally:
                    await lock_s.execute(
                        text("SELECT pg_advisory_unlock(:k)"),
                        {"k": _RECONCILE_LOCK_KEY},
                    )
                    await lock_s.commit()
    except Exception:
        if settings.startup_reconcile_tolerant:
            log.exception("rbac_reconcile_failed_tolerant")
        else:
            log.exception("rbac_reconcile_failed_fail_fast")
            raise

    # PAR-D H5: launch the in-process invite-email outbox worker. It polls the
    # outbox and performs Supabase invite sends out of band of the request tx.
    outbox_stop = asyncio.Event()
    outbox_task = asyncio.create_task(run_outbox_worker(outbox_stop))

    try:
        yield
    finally:
        # Stop the outbox worker cooperatively, then force-cancel if it overruns.
        outbox_stop.set()
        try:
            await asyncio.wait_for(outbox_task, timeout=10.0)
        except (TimeoutError, asyncio.CancelledError):
            outbox_task.cancel()
        # PAR-B H7: close the JWKS httpx client cleanly on shutdown so asyncio
        # doesn't warn about an unclosed transport in unit tests / hot reload.
        await close_jwks_client()
        # PAR-D M16: close the Valkey perm-cache client likewise.
        await close_perm_cache()
        # RL-2: close the Valkey per-email signup-throttle client likewise.
        await close_email_throttle()


app = FastAPI(title="Xtrusio API", version="0.0.0", lifespan=lifespan)

# PAR-A H8: rate limiting (SlowAPI + Valkey). Order matters — the limiter must
# be registered before route includes so decorated routes see ``app.state``.
app.state.limiter = limiter
# slowapi's _rate_limit_exceeded_handler signature is narrower than starlette's
# expected ``(Request, Exception) -> Response``; cast is safe because Starlette
# dispatches the registered class (``RateLimitExceeded``) to the matching
# handler before the type signature is enforced.
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# RL-1: install SlowAPIMiddleware so the user-keyed authenticated catch-all
# (limiter.default_limits, read from AUTHED_CATCHALL_RATE) is evaluated on every
# request. Without the middleware, default_limits only apply to routes that
# carry an explicit @limiter.limit decorator — i.e. the catch-all would stay
# dead. The middleware skips routes that already have an explicit per-route
# limit and routes registered as exempt, so it never double-limits or clobbers
# SIGNUP_RATE / INVITE_ACCEPT_RATE / ONBOARDING_RATE. (It also short-circuits
# entirely when ``limiter.enabled`` is False, which the test suite relies on.)
app.add_middleware(SlowAPIMiddleware)

# RL-1: exempt the K8s liveness/readiness probes from the catch-all so an
# orchestrator polling them frequently never trips a 429. ``limiter.exempt``
# registers the endpoint's ``module.func`` name in the limiter's exempt set as
# a side effect (the SlowAPIMiddleware checks that set before applying any
# default limit); we discard the returned wrapper because the routes are
# already bound to the original functions.
for _probe in (health_routes.live, health_routes.ready, health_routes.health):
    limiter.exempt(_probe)  # type: ignore[no-untyped-call]


# PAR-B M13: global exception handlers — every error response carries the
# request_id so a user-reported error can be traced in logs without
# guesswork. The handlers run AFTER the request-id middleware has populated
# ``request.state.request_id``.
@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    rid: str | None = getattr(request.state, "request_id", None)
    detail: Any = exc.detail
    return JSONResponse(
        {"detail": detail, "request_id": rid},
        status_code=exc.status_code,
        headers={"X-Request-ID": rid} if rid else None,
    )


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    rid: str | None = getattr(request.state, "request_id", None)
    # PAR-B M13: ``exc.errors()`` can carry non-JSON-serialisable values
    # (e.g. ``ValueError`` instances Pydantic threads through ``ctx``).
    # ``jsonable_encoder`` turns them into a portable shape — same path
    # FastAPI's stock validation handler uses.
    return JSONResponse(
        {"detail": jsonable_encoder(exc.errors()), "request_id": rid},
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        headers={"X-Request-ID": rid} if rid else None,
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    rid: str | None = getattr(request.state, "request_id", None)
    log = get_logger(__name__)
    log.exception("unhandled_exception", exc_type=type(exc).__name__, request_id=rid)
    return JSONResponse(
        {"detail": "internal_server_error", "request_id": rid},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        headers={"X-Request-ID": rid} if rid else None,
    )


# Middleware order matters in Starlette (outermost added LAST executes
# FIRST). We want request-id first so every other layer sees state.request_id;
# then the body-size cap so 413s are also tagged. CORS runs near last-out so it
# can observe and tag every response. SecurityHeadersMiddleware is added LAST so
# it is the OUTERMOST layer — it stamps the hardening headers on EVERY response,
# including CORS preflight (204) responses CORSMiddleware short-circuits and the
# global exception handler's 4xx/5xx bodies.
app.add_middleware(
    CORSMiddleware,
    # PAR-B M14: explicit allow lists, no wildcards; preflight cache 10 min;
    # expose X-Request-ID so the SPA can pick it up for sentry breadcrumbs.
    allow_origins=get_settings().cors_allow_origins,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.add_middleware(BodySizeLimitMiddleware, max_bytes=get_settings().max_request_body_bytes)
app.add_middleware(RequestIdMiddleware)
# HSTS is env-gated; resolve env once at registration so the request path holds
# no env literal (no hardcoded config — driven from settings.env).
app.add_middleware(SecurityHeadersMiddleware, is_prod=get_settings().env == "prod")

# Health probes register before any router that may itself be rate-limited so
# the orchestrator's probes never trip a limit.
app.include_router(health_routes.router)

app.include_router(me_routes.router)
app.include_router(tenants_routes.router)
app.include_router(platform_settings_routes.router)
app.include_router(platform_invites_routes.router)
app.include_router(platform_roles_routes.router)
app.include_router(platform_role_grants_routes.router)
# Note: platform_users_routes registers GET /api/platform/users (empty path
# under the same prefix as platform_role_grants_routes). Static sub-paths
# (e.g. /invites) and parameterised ones (/{user_id}/roles) belong to other
# routers — they coexist because the paths are distinct.
app.include_router(platform_users_routes.router)
# Static sub-path GET /api/platform/stats — distinct from the /users sub-paths.
app.include_router(platform_stats_routes.router)
app.include_router(platform_audit_log_routes.router)
app.include_router(platform_job_runs_routes.router)
app.include_router(internal_auth_events_routes.router)
# GET /api/platform/clients/{slug} — its own prefix so the {slug} param can't
# shadow the static /api/platform/{settings,users,roles,stats,...} sub-paths.
app.include_router(platform_clients_routes.router)
app.include_router(permissions_routes.router)
# GET /api/audit/catalog — authed-only non-secret event catalog (label +
# category per action), mirrors the permissions catalog.
app.include_router(audit_catalog_routes.router)
app.include_router(tenant_invites_routes.router)
app.include_router(signup_routes.router)
app.include_router(onboarding_routes.router)
app.include_router(invite_acceptance_routes.router)
app.include_router(workspace_roles_routes.router)
# Note: workspace_members_routes is registered BEFORE workspace_role_grants_routes
# so the include order stays predictable (both share the prefix
# /api/workspaces/{workspace_id}/members and declare distinct sub-paths).
app.include_router(workspace_members_routes.router)
app.include_router(workspace_role_grants_routes.router)
app.include_router(workspace_settings_routes.router)
app.include_router(workspace_audit_log_routes.router)
# Static sub-path GET /api/workspaces/{workspace_id}/stats.
app.include_router(workspace_stats_routes.router)
