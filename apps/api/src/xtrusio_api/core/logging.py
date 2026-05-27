"""Structured logging via structlog (PAR-B M13).

JSON renderer for production (machine-parseable); a console renderer for dev
so a developer's terminal stays readable. The renderer choice is bound to
``settings.env`` — "prod" → JSON, anything else → console.

``configure_logging()`` MUST run before any logger is bound. The FastAPI
lifespan calls it as the very first step of startup.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from .config import get_settings


def configure_logging() -> None:
    """One-shot structlog configuration. Idempotent — calling twice is safe."""
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Wire stdlib logging through structlog so libraries (uvicorn, sqlalchemy,
    # httpx) emit through the same renderer the app uses.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.stdlib.add_logger_name,
    ]

    renderer: Any
    if settings.env == "prod":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger. Always returns a logger; ``name`` becomes
    the ``logger`` field in the rendered output."""
    return structlog.get_logger(name) if name else structlog.get_logger()
