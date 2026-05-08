"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Xtrusio API", version="0.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
