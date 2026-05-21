"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .core.db import SessionLocal
from .rbac.reconcile import reconcile_rbac, reconcile_user_roles_from_enums
from .routes import invite_acceptance as invite_acceptance_routes
from .routes import me as me_routes
from .routes import onboarding as onboarding_routes
from .routes import platform_audit_log as platform_audit_log_routes
from .routes import platform_invites as platform_invites_routes
from .routes import platform_role_grants as platform_role_grants_routes
from .routes import platform_roles as platform_roles_routes
from .routes import platform_settings as platform_settings_routes
from .routes import signup as signup_routes
from .routes import tenant_invites as tenant_invites_routes
from .routes import tenants as tenants_routes
from .routes import workspace_role_grants as workspace_role_grants_routes
from .routes import workspace_roles as workspace_roles_routes


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        async with SessionLocal() as _s:
            await reconcile_rbac(_s)
        async with SessionLocal() as _s:
            await reconcile_user_roles_from_enums(_s)
    except Exception:
        import logging

        log = logging.getLogger(__name__)
        if settings.startup_reconcile_tolerant:
            log.exception("rbac reconcile on startup failed (tolerant mode, continuing)")
        else:
            log.exception("rbac reconcile on startup failed — failing fast")
            raise
    yield


app = FastAPI(title="Xtrusio API", version="0.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(me_routes.router)
app.include_router(tenants_routes.router)
app.include_router(platform_settings_routes.router)
app.include_router(platform_invites_routes.router)
app.include_router(platform_roles_routes.router)
app.include_router(platform_role_grants_routes.router)
app.include_router(platform_audit_log_routes.router)
app.include_router(tenant_invites_routes.router)
app.include_router(signup_routes.router)
app.include_router(onboarding_routes.router)
app.include_router(invite_acceptance_routes.router)
app.include_router(workspace_roles_routes.router)
app.include_router(workspace_role_grants_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
