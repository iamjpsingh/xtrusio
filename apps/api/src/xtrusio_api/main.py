"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .routes import me as me_routes
from .routes import onboarding as onboarding_routes
from .routes import platform_invites as platform_invites_routes
from .routes import platform_settings as platform_settings_routes
from .routes import signup as signup_routes
from .routes import tenant_invites as tenant_invites_routes
from .routes import tenants as tenants_routes

app = FastAPI(title="Xtrusio API", version="0.0.0")
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
