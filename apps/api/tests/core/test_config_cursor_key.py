"""Boot-time rejection of a weak CURSOR_HMAC_KEY in prod (CWE-798/321).

The placeholder key shipped in ``.env.example`` was copied into a live ``.env``;
a known signing key lets a client forge pagination cursors. The Settings model
must FAIL FAST in prod on the placeholder prefix or an obviously-too-short key,
while staying frictionless in dev/test.

Pure-unit: we reconstruct ``Settings`` from the live settings' field dump and
override only ``env`` + ``cursor_hmac_key`` — no .env mutation, no DB.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError
from xtrusio_api.core.config import (
    _MIN_CURSOR_KEY_LEN,
    _WEAK_CURSOR_KEY_PREFIX,
    Settings,
    get_settings,
)

# A strong, well-formed key (64 hex chars — secrets.token_hex(32) shape).
_STRONG_KEY = "a" * _MIN_CURSOR_KEY_LEN + "b" * _MIN_CURSOR_KEY_LEN
_WEAK_PLACEHOLDER = f"{_WEAK_CURSOR_KEY_PREFIX}-0123456789abcdef0123456789abcdef"


def _build_settings(*, env: str, cursor_hmac_key: str) -> Settings:
    """Construct a Settings overriding only env + cursor key.

    We dump the live settings BY ALIAS (env-var names) and pass them as init
    kwargs with ``_env_file=None``: init kwargs are pydantic-settings' highest-
    priority source, so they win over both the .env file and OS env vars. This
    lets us flip ``XTRUSIO_ENV`` / ``CURSOR_HMAC_KEY`` deterministically without
    mutating the real environment.
    """
    base: dict[str, Any] = get_settings().model_dump(by_alias=True)
    base["XTRUSIO_ENV"] = env
    base["CURSOR_HMAC_KEY"] = cursor_hmac_key
    return Settings(_env_file=None, **base)  # type: ignore[call-arg]


def test_prod_rejects_known_weak_placeholder() -> None:
    with pytest.raises(ValidationError) as exc:
        _build_settings(env="prod", cursor_hmac_key=_WEAK_PLACEHOLDER)
    assert "CURSOR_HMAC_KEY" in str(exc.value)


def test_prod_rejects_too_short_key() -> None:
    short = "x" * (_MIN_CURSOR_KEY_LEN - 1)
    with pytest.raises(ValidationError) as exc:
        _build_settings(env="prod", cursor_hmac_key=short)
    assert "CURSOR_HMAC_KEY" in str(exc.value)


def test_prod_accepts_strong_key() -> None:
    s = _build_settings(env="prod", cursor_hmac_key=_STRONG_KEY)
    assert s.cursor_hmac_key == _STRONG_KEY
    assert s.env == "prod"


@pytest.mark.parametrize("env", ["dev", "test"])
def test_non_prod_tolerates_weak_placeholder(env: str) -> None:
    # Dev/test must keep working on the placeholder so local pagination cursors
    # don't break and onboarding stays frictionless.
    s = _build_settings(env=env, cursor_hmac_key=_WEAK_PLACEHOLDER)
    assert s.cursor_hmac_key == _WEAK_PLACEHOLDER


@pytest.mark.parametrize("env", ["dev", "test"])
def test_non_prod_tolerates_short_key(env: str) -> None:
    s = _build_settings(env=env, cursor_hmac_key="short")
    assert s.cursor_hmac_key == "short"
