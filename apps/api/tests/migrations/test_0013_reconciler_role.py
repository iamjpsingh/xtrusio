"""DB-level guards added in migration 0013 (PAR-C slice 2).

Exercised directly via raw SQL against the shared managed DB. Test data uses the
``@example.com`` convention and is swept by the session purge; each test also
tears down its own tenant under the bypass GUC.

Covers:
  - C4 (role-gate): ``enforce_priv_escalation`` is recreated ``SECURITY
    INVOKER`` (so ``current_user`` reflects the session role, not the owner) and
    its body gates the bypass GUC on ``current_user = 'xtrusio_reconciler'``.
    Behaviourally: a bypass GUC set on the REQUEST role (``postgres``) is INERT
    — a privilege-escalating INSERT still raises. (Spec's
    ``test_bypass_guc_role_gated``.)
  - C4 (INSERT OR UPDATE): the trigger now fires on UPDATE as well as INSERT.
  - M15: the least-privileged ``xtrusio_reconciler`` role exists (NOLOGIN,
    NOSUPERUSER) with table DML but no superuser.

The reconciler login DSN is NOT required to run these — the negative path uses
the ordinary test role, and the positive path assumes the role via ``SET ROLE``
(skipped if the test role can't assume it).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio(loop_scope="session")

_RECONCILER_ROLE = "xtrusio_reconciler"


async def _insert_auth_user(s: AsyncSession, *, email: str) -> UUID:
    uid = uuid4()
    await s.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, "
            "encrypted_password, email_confirmed_at, created_at, updated_at) "
            "VALUES (:id, '00000000-0000-0000-0000-000000000000', 'authenticated', "
            "'authenticated', :email, '', now(), now(), now())"
        ),
        {"id": str(uid), "email": email},
    )
    return uid


async def _seed_escalation_probe() -> tuple[UUID, UUID, UUID, UUID, UUID]:
    """Create a tenant + a CUSTOM (is_system=false) workspace role carrying one
    real workspace permission, plus an actor that holds NO perms and a target
    user. Returns (tenant_id, role_id, target_user, actor, creator). A grant of role_id
    by ``actor`` is a privilege escalation (actor lacks the role's perm), so the
    trigger must reject it unless legitimately bypassed.

    is_system=false → ``reject_system_role_perm_change`` (0009) does not block
    wiring the perm, so no bypass GUC is needed for setup.
    """
    tenant_id = uuid4()
    role_id = uuid4()
    async with SessionLocal() as s:
        creator = await _insert_auth_user(s, email=f"rg-creator-{tenant_id.hex[:8]}@example.com")
        await s.execute(
            text("INSERT INTO tenants (id, slug, name, created_by) VALUES (:t,:sl,:n,:c)"),
            {
                "t": str(tenant_id),
                "sl": f"rg-{tenant_id.hex[:8]}",
                "n": "Role-gate probe",
                "c": str(creator),
            },
        )
        await s.execute(
            text(
                "INSERT INTO roles (id, scope, workspace_id, key, name, description, is_system) "
                "VALUES (:rid, 'workspace', :t, 'rg_custom', 'RG Custom', '', false)"
            ),
            {"rid": str(role_id), "t": str(tenant_id)},
        )
        perm_id = (
            await s.execute(
                text(
                    "SELECT id FROM permissions "
                    "WHERE scope='workspace' AND NOT is_deprecated LIMIT 1"
                )
            )
        ).scalar_one()
        await s.execute(
            text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:r, :p)"),
            {"r": str(role_id), "p": str(perm_id)},
        )
        target = await _insert_auth_user(s, email=f"rg-target-{tenant_id.hex[:8]}@example.com")
        actor = await _insert_auth_user(s, email=f"rg-actor-{tenant_id.hex[:8]}@example.com")
        await s.commit()
    return tenant_id, role_id, target, actor, creator


async def _teardown(tenant_id: UUID, *user_ids: UUID) -> None:
    async with SessionLocal() as s:
        await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
        await s.execute(text("DELETE FROM tenants WHERE id = :t"), {"t": str(tenant_id)})
        for uid in user_ids:
            await s.execute(text("DELETE FROM auth.users WHERE id = :u"), {"u": str(uid)})
        await s.commit()


# --- C4: SECURITY INVOKER + role-gate (introspection) -----------------------


async def test_enforce_priv_escalation_is_security_invoker() -> None:
    """The role-gate ``current_user = 'xtrusio_reconciler'`` only works under
    SECURITY INVOKER — under DEFINER ``current_user`` is the function owner."""
    async with SessionLocal() as s:
        prosecdef = (
            await s.execute(
                text("SELECT prosecdef FROM pg_proc WHERE proname = 'enforce_priv_escalation'")
            )
        ).scalar_one()
        assert prosecdef is False, "enforce_priv_escalation must be SECURITY INVOKER"


async def test_enforce_priv_escalation_source_gates_bypass_on_role() -> None:
    async with SessionLocal() as s:
        src = (
            await s.execute(
                text(
                    "SELECT pg_get_functiondef(oid) FROM pg_proc "
                    "WHERE proname = 'enforce_priv_escalation'"
                )
            )
        ).scalar_one()
        assert f"current_user = '{_RECONCILER_ROLE}'" in src


async def test_priv_escalation_trigger_fires_on_insert_and_update() -> None:
    """tgtype bits: INSERT = 1<<2 (4), UPDATE = 1<<4 (16)."""
    async with SessionLocal() as s:
        tgtype = (
            await s.execute(
                text(
                    "SELECT tgtype FROM pg_trigger "
                    "WHERE tgname = 'trg_user_roles_priv_escalation'"
                )
            )
        ).scalar_one()
        assert tgtype & 4, "trigger must fire on INSERT"
        assert tgtype & 16, "trigger must fire on UPDATE"


# --- M15: reconciler role exists, least-privileged --------------------------


async def test_reconciler_role_exists_and_is_least_privileged() -> None:
    async with SessionLocal() as s:
        row = (
            await s.execute(
                text("SELECT rolsuper, rolcanlogin FROM pg_roles WHERE rolname = :r"),
                {"r": _RECONCILER_ROLE},
            )
        ).first()
        assert row is not None, "xtrusio_reconciler role missing"
        assert row.rolsuper is False, "reconciler must not be superuser"
        # Created NOLOGIN in the migration; the operator flips LOGIN out of band.
        # We don't assert rolcanlogin (an operator may have enabled it already),
        # only that it is never a superuser.
        has_insert = (
            await s.execute(
                text("SELECT has_table_privilege(:r, 'user_roles', 'INSERT')"),
                {"r": _RECONCILER_ROLE},
            )
        ).scalar_one()
        assert has_insert is True, "reconciler needs INSERT on user_roles"


# --- C4 behavioural: bypass GUC inert on the request role -------------------


async def test_bypass_guc_inert_on_request_role() -> None:
    """A bypass GUC set on the REQUEST role (postgres) must NOT bypass — the
    escalating grant still raises insufficient_privilege."""
    tenant_id, role_id, target, actor, creator = await _seed_escalation_probe()
    try:
        async with SessionLocal() as s:
            # Request-path role sets the GUC — must be ignored by the trigger.
            await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
            await s.execute(text("SELECT set_config('app.actor_id', :a, true)"), {"a": str(actor)})
            with pytest.raises(DBAPIError) as exc:
                await s.execute(
                    text(
                        "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
                        "VALUES (:u, :r, :t, :g)"
                    ),
                    {"u": str(target), "r": str(role_id), "t": str(tenant_id), "g": str(actor)},
                )
            assert "privilege escalation denied" in str(exc.value)
            await s.rollback()
    finally:
        await _teardown(tenant_id, target, actor, creator)


async def test_reconciler_role_can_bypass() -> None:
    """Positive path: under the reconciler role the bypass GUC IS honoured AND
    the 0013 permissive RLS policy lets the non-owner role write user_roles.

    Assumes the role via ``SET LOCAL ROLE`` (no login needed). Skipped when the
    test role can't be granted membership in / assume the reconciler role.
    """
    tenant_id, role_id, target, actor, creator = await _seed_escalation_probe()
    try:
        async with SessionLocal() as s:
            try:
                await s.execute(text(f"GRANT {_RECONCILER_ROLE} TO current_user"))
                await s.execute(text(f"SET LOCAL ROLE {_RECONCILER_ROLE}"))
            except (DBAPIError, ProgrammingError):
                await s.rollback()
                pytest.skip("test role cannot assume xtrusio_reconciler")
            await s.execute(text("SELECT set_config('app.bypass_priv_escalation', 'on', true)"))
            await s.execute(text("SELECT set_config('app.actor_id', :a, true)"), {"a": str(actor)})
            # Same escalating grant as the negative test — under the reconciler
            # role + GUC it must SUCCEED.
            await s.execute(
                text(
                    "INSERT INTO user_roles (auth_user_id, role_id, workspace_id, granted_by) "
                    "VALUES (:u, :r, :t, :g)"
                ),
                {"u": str(target), "r": str(role_id), "t": str(tenant_id), "g": str(actor)},
            )
            await s.rollback()
    finally:
        await _teardown(tenant_id, target, actor, creator)
