"""Hygiene-safe coverage for ``xtrusio_api.scripts.bootstrap`` (F.4 / H14).

The bootstrap CLI creates the platform owner = a super_admin (a ``platform_users``
row + a ``user_roles`` super_admin grant). Test-data hygiene FORBIDS persisting a
super_admin to the shared managed DB, so this test must never commit one.

Mechanism (no super_admin ever reaches the DB):
  * The real Supabase admin client is mocked — no auth.users row is created
    remotely and the returned id is a deterministic @example.com fixture id.
  * ``bootstrap.SessionLocal`` is monkeypatched to a sessionmaker bound to a
    single outer connection whose transaction the test OWNS. Sessions join that
    transaction in ``create_savepoint`` mode, so each ``await db.commit()`` the
    bootstrap performs only releases a SAVEPOINT (visible to later assertions on
    the SAME connection) — it never reaches a real Postgres COMMIT.
  * The test rolls the outer transaction back in a ``finally``, discarding
    everything. A post-condition then opens a FRESH ``SessionLocal()`` and
    asserts zero @example.com super_admin rows persisted.

The bootstrap row id MUST be in the auth.users FK target. Because we never let
the outer transaction commit and we insert a matching auth.users stub row inside
it, the FK from platform_users -> auth.users is satisfied for the in-transaction
assertions and then rolled away with everything else.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker
from xtrusio_api.core.db import engine
from xtrusio_api.scripts import bootstrap

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Deterministic @example.com fixture identity (NOT the real owner).
_OWNER_ID = UUID("00000000-0000-0000-0000-0000000be571")
_OWNER_EMAIL = "bootstrap-owner@example.com"
_SUPER_ADMIN_ROLE_ID = "00000000-0000-0000-0000-0000000000a1"


@pytest_asyncio.fixture
async def rollback_conn() -> AsyncIterator[AsyncConnection]:
    """An outer connection + transaction the test rolls back unconditionally."""
    conn = await engine.connect()
    trans = await conn.begin()
    try:
        yield conn
    finally:
        # Discard EVERYTHING the bootstrap did — nothing is ever committed.
        if trans.is_active:
            await trans.rollback()
        await conn.close()


@pytest.fixture
def patched_bootstrap(rollback_conn: AsyncConnection, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Point bootstrap at a savepoint-joined sessionmaker + a fake Supabase
    client; return the fake client so tests can assert on it."""
    maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=rollback_conn,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    monkeypatch.setattr(bootstrap, "SessionLocal", maker)

    fake_user = MagicMock()
    fake_user.id = str(_OWNER_ID)
    fake_client = MagicMock()
    fake_client.auth.admin.create_user.return_value = MagicMock(user=fake_user)

    def _factory(*_a: object, **_k: object) -> MagicMock:
        return fake_client

    monkeypatch.setattr(bootstrap, "create_client", _factory)
    return fake_client


async def _prepare_clean_state(conn: AsyncConnection) -> None:
    """Inside the rolled-back transaction ONLY, simulate a not-yet-bootstrapped
    DB so the non-force create path is exercised.

    The shared managed DB already has the real operator super_admin
    (admin@xtrusio.com), which the bootstrap's first-run SELECT would otherwise
    see and (correctly) refuse on. We delete the super_admin user_roles grant +
    platform_users rows HERE, but only on this connection's open transaction —
    the ``rollback_conn`` fixture rolls it all back, so the real owner is never
    actually touched. A post-condition test reconfirms the real owner survived.

    We then insert the matching auth.users stub row so the platform_users ->
    auth.users FK holds for the in-transaction assertions.
    """
    await conn.execute(
        text("DELETE FROM user_roles WHERE role_id = :r"),
        {"r": _SUPER_ADMIN_ROLE_ID},
    )
    await conn.execute(text("DELETE FROM platform_users WHERE role = 'super_admin'"))
    await conn.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(_OWNER_ID), "email": _OWNER_EMAIL},
    )


async def _count(conn: AsyncConnection, sql: str, params: dict[str, Any]) -> int:
    return int((await conn.execute(text(sql), params)).scalar_one())


async def test_bootstrap_creates_owner_row_and_grant(
    rollback_conn: AsyncConnection,
    patched_bootstrap: MagicMock,
) -> None:
    """A first run writes the platform_users super_admin row + user_roles grant.

    Asserted against the in-transaction (uncommitted) state; rolled back after.
    """
    await _prepare_clean_state(rollback_conn)

    await bootstrap._run(email=_OWNER_EMAIL, password="Bootstrap1!", force=False)

    pu = await _count(
        rollback_conn,
        "SELECT count(*) FROM platform_users "
        "WHERE id = :id AND email = :email AND role = 'super_admin' AND is_active",
        {"id": str(_OWNER_ID), "email": _OWNER_EMAIL},
    )
    assert pu == 1, "bootstrap must create exactly one super_admin platform_users row"

    ur = await _count(
        rollback_conn,
        "SELECT count(*) FROM user_roles WHERE auth_user_id = :u AND role_id = :r",
        {"u": str(_OWNER_ID), "r": _SUPER_ADMIN_ROLE_ID},
    )
    assert ur == 1, "bootstrap must create the user_roles super_admin grant"

    # The Supabase admin client was asked to create exactly the owner.
    patched_bootstrap.auth.admin.create_user.assert_called_once()
    (call_args,) = patched_bootstrap.auth.admin.create_user.call_args.args
    assert call_args["email"] == _OWNER_EMAIL
    assert call_args["email_confirm"] is True


async def test_bootstrap_second_run_without_force_is_rejected(
    rollback_conn: AsyncConnection,
    patched_bootstrap: MagicMock,
) -> None:
    """Idempotency / safety: once a super_admin exists, a non-force run exits
    non-zero and does NOT create a second one."""
    await _prepare_clean_state(rollback_conn)

    # First run establishes the owner (in-transaction).
    await bootstrap._run(email=_OWNER_EMAIL, password="Bootstrap1!", force=False)

    # Second run without --force must refuse (typer.Exit(code=1)).
    import typer

    with pytest.raises(typer.Exit) as exc:
        await bootstrap._run(email=_OWNER_EMAIL, password="Bootstrap1!", force=False)
    assert exc.value.exit_code == 1

    # Still exactly one super_admin platform_users row — no duplicate written.
    pu = await _count(
        rollback_conn,
        "SELECT count(*) FROM platform_users WHERE role = 'super_admin' AND email = :email",
        {"email": _OWNER_EMAIL},
    )
    assert pu == 1


async def test_bootstrap_persists_nothing() -> None:
    """Post-condition guard: after the rolled-back runs above, a FRESH session
    (real engine, autonomous transaction) sees ZERO @example.com super_admins
    AND the real operator owner is untouched (its in-tx delete rolled back)."""
    from xtrusio_api.core.db import SessionLocal

    async with SessionLocal() as s:
        stray = (
            await s.execute(
                text(
                    "SELECT count(*) FROM platform_users "
                    "WHERE role = 'super_admin' AND email LIKE '%@example.com'"
                )
            )
        ).scalar_one()
        # The real operator super_admin(s) the rolled-back transaction deleted
        # in-tx must still be present — proving the rollback protected real data.
        real_owners = (
            await s.execute(
                text(
                    "SELECT count(*) FROM platform_users "
                    "WHERE role = 'super_admin' AND email NOT LIKE '%@example.com'"
                )
            )
        ).scalar_one()
    assert stray == 0, "bootstrap test leaked a super_admin into the shared DB"
    assert real_owners >= 1, "rollback failed to restore the real operator owner"
