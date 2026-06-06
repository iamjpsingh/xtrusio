"""Direct-create a platform user (Supabase auth + platform_users + grant).

Backs ``POST /api/platform/users``. Mirrors ``scripts/bootstrap.py``: create
the Supabase user via the SERVICE-ROLE Admin API with ``email_confirm: True``
(no confirmation round-trip — an operator is provisioning a known account),
then insert the ``platform_users`` row and grant the platform ``admin`` system
role in the SAME transaction.

Caller-owns-transaction: this flushes (not commits) so a uniqueness conflict
surfaces here as :class:`PlatformUserExistsError`; the route commits on success
and rolls back on any raised error. The role is pinned to ``admin`` by the
schema (``super_admin`` stays CLI/seed-only per the single-super_admin
invariant), so this never touches the super_admin grant.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from gotrue.errors import AuthApiError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from supabase import create_client

from ..core.audit import write_audit_event
from ..core.config import get_settings
from ..core.permissions import set_actor
from ..models.platform_user import PlatformRole, PlatformUser
from ..rbac.grants import grant_role
from ..schemas.platform_user_create import PlatformUserCreated

# Stable gotrue error codes meaning "this email is already registered".
_EMAIL_TAKEN_CODES = frozenset({"email_exists", "user_already_exists"})


class PlatformUserExistsError(Exception):
    """The email is already a Supabase auth user or an existing platform_users
    row. Mapped to 409 by the route (idempotency / non-clobber)."""


class EmailProviderUnavailableError(Exception):
    """The Supabase Admin call failed (timeout / transport). Route → 502."""


async def create_platform_user(
    db: AsyncSession,
    *,
    actor_id: UUID,
    email: str,
    password: str,
) -> PlatformUserCreated:
    """Provision a platform ``admin`` user directly. Caller owns the commit."""
    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> object:
        return sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except TimeoutError as e:
        raise EmailProviderUnavailableError() from e
    except AuthApiError as e:
        if (e.code or "") in _EMAIL_TAKEN_CODES:
            raise PlatformUserExistsError() from e
        raise

    user = getattr(result, "user", None)
    if user is None:
        raise EmailProviderUnavailableError()
    user_id = UUID(str(user.id))

    # Tag the transaction with the acting user so the 0013 priv-escalation
    # trigger can verify the actor holds the perms carried by the granted role.
    await set_actor(db, actor_id)
    db.add(PlatformUser(id=user_id, email=email, role=PlatformRole.ADMIN, is_active=True))
    await grant_role(
        db,
        auth_user_id=user_id,
        scope="platform",
        key="admin",
        granted_by=actor_id,
    )
    try:
        await db.flush()
    except IntegrityError as e:
        constraint = getattr(e.orig, "constraint_name", None) or str(e.orig)
        if "platform_users_pkey" in constraint or "platform_users_email_key" in constraint:
            raise PlatformUserExistsError() from e
        raise

    # Audit coverage (same tx — route owns the commit). target is the new
    # platform_users row; actor is the provisioning operator.
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_user.create",
        target_type="platform_user",
        target_id=user_id,
        scope="platform",
        after={"email": email, "role": PlatformRole.ADMIN.value},
    )

    return PlatformUserCreated(id=user_id, email=email, role="admin", is_active=True)
