"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import me as me_routes
from .routes import tenants as tenants_routes

app = FastAPI(title="Xtrusio API", version="0.0.0")
app.include_router(me_routes.router)
app.include_router(tenants_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
