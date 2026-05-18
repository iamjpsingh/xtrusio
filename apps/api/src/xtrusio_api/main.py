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
from .routes import platform_invites as platform_invites_routes
from .routes import platform_settings as platform_settings_routes
from .routes import signup as signup_routes
from .routes import tenant_invites as tenant_invites_routes
from .routes import tenants as tenants_routes


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        async with SessionLocal() as _s:
            await reconcile_rbac(_s)
        async with SessionLocal() as _s:
            await reconcile_user_roles_from_enums(_s)
    except Exception:  # pragma: no cover - boot must not fail on reconcile
        import logging

        logging.getLogger(__name__).exception("rbac reconcile on startup failed")
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
app.include_router(tenant_invites_routes.router)
app.include_router(signup_routes.router)
app.include_router(onboarding_routes.router)
app.include_router(invite_acceptance_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
