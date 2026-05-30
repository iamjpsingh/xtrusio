"""Regression guards for two latent boot-time crashes.

1. structlog ``add_logger_name`` read ``logger.name`` on a ``PrintLogger`` that
   has none, so EVERY ``log.*`` emission raised ``AttributeError`` in both dev
   and prod (it only stayed hidden because the happy reconcile path never logs).
2. ``_reset_session_gucs`` (the SQLAlchemy ``checkin`` listener) called
   ``.cursor()`` on the dbapi connection before guarding it — but ``checkin``
   fires with ``dbapi_conn=None`` when a connection is INVALIDATED after a
   fault, masking the original error with ``'NoneType' has no attribute
   'cursor'``.

These are pure unit tests — no DB connection is opened.
"""

from __future__ import annotations

from xtrusio_api.core.db import _reset_session_gucs
from xtrusio_api.core.logging import configure_logging, get_logger


def test_logging_emits_without_attribute_error() -> None:
    """Every emission level must render without touching a non-existent
    ``logger.name`` (the removed ``add_logger_name`` processor)."""
    configure_logging()
    log = get_logger("regression.logging")
    log.info("info_event", k="v")
    log.warning("warning_event")
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("exception_event")  # exc_info path — must not raise


def test_reset_session_gucs_tolerates_none_connection() -> None:
    """checkin fires with ``dbapi_conn=None`` on an invalidated connection; the
    GUC-reset listener must no-op instead of raising ``AttributeError``."""
    _reset_session_gucs(None, None)  # must not raise
