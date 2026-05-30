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

    # NOTE: do NOT add ``structlog.stdlib.add_logger_name`` here. It reads
    # ``logger.name``, which only exists on stdlib-backed loggers. We use
    # ``PrintLoggerFactory`` (below), whose ``PrintLogger`` has no ``.name`` —
    # so ``add_logger_name`` raises ``AttributeError`` on EVERY emission in both
    # dev and prod. The ``logger`` field is instead injected by ``get_logger``,
    # which binds ``logger=<name>`` into the context.
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    renderer: Any
    render_chain: list[Any] = [structlog.processors.StackInfoRenderer()]
    if settings.env == "prod":
        # JSONRenderer can't serialize a raw exc_info tuple — format_exc_info
        # turns it into an ``exception`` string field first.
        render_chain.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer()
    else:
        # ConsoleRenderer formats exceptions itself (pretty tracebacks); adding
        # format_exc_info ahead of it double-handles exc_info and trips a
        # structlog warning, so it's omitted on the dev path.
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
    render_chain.append(renderer)

    structlog.configure(
        processors=[
            *shared_processors,
            *render_chain,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structlog logger. Always returns a logger; ``name`` becomes
    the ``logger`` field in the rendered output.

    The name is bound into the context (rather than relying on
    ``structlog.stdlib.add_logger_name``, which is incompatible with the
    ``PrintLoggerFactory`` we use — see ``configure_logging``)."""
    if name:
        return structlog.get_logger().bind(logger=name)
    return structlog.get_logger()
