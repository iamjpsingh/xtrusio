# Plan 2B — Platform & tenant invites Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Email-based invitations for both platform users (super_admin invites admin/editor) and tenant users (owner/admin invites admin/editor/read_only). One generic acceptance endpoint handles both kinds.

**Architecture:** All invite emails are sent by Supabase via `auth.admin.invite_user_by_email`; we mirror each invite into `platform_invites` or `tenant_invites` for listing and revocation. The Supabase invite link is the bearer secret — we never generate or store our own tokens. On the user's first authenticated request after clicking the link, the frontend posts to `/api/invites/accept`, which reads `user_metadata` from the JWT, validates the matching invite row, and inserts the matching `platform_users` or `tenant_memberships` row.

**Spec:** `docs/superpowers/specs/2026-05-14-platform-settings-signup-and-invites-design.md`
**Depends on:** Plan 2A complete (`tenant_memberships`, `tenant_role`, `platform_settings`, AuthGuard, `/me` shape).

**Tech Stack:** Same as 2A.

---

## Files Created / Modified

### Backend (`apps/api/`)
- **Create:**
  - `migrations/versions/0003_platform_and_tenant_invites.py`
  - `src/xtrusio_api/models/platform_invite.py`
  - `src/xtrusio_api/models/tenant_invite.py`
  - `src/xtrusio_api/schemas/invite.py`
  - `src/xtrusio_api/services/invite_acceptance.py`
  - `src/xtrusio_api/services/platform_invites.py`
  - `src/xtrusio_api/services/tenant_invites.py`
  - `src/xtrusio_api/services/invite_rules.py`
  - `src/xtrusio_api/routes/platform_invites.py`
  - `src/xtrusio_api/routes/tenant_invites.py`
  - `src/xtrusio_api/routes/invite_acceptance.py`
  - `tests/services/test_invite_rules.py`
  - `tests/routes/test_platform_invites.py`
  - `tests/routes/test_tenant_invites.py`
  - `tests/routes/test_invite_acceptance.py`
  - `tests/rls/test_platform_invites_rls.py`
  - `tests/rls/test_tenant_invites_rls.py`
  - `tests/integration/test_invite_full_flow.py`
- **Modify:**
  - `src/xtrusio_api/models/__init__.py` (export new invite models)
  - `src/xtrusio_api/main.py` (register routers)
  - `src/xtrusio_api/routes/me.py` (read pending_invite from JWT claims)
  - `migrations/env.py` (import new models)

### Frontend (`apps/web/`)
- **Create:**
  - `src/routes/accept-invite.tsx`
  - `src/routes/accept-invite.test.tsx`
  - `src/routes/clients.$slug.users.tsx`
  - `src/routes/clients.$slug.users.test.tsx`
- **Modify:**
  - `src/routes/users.tsx` (expand with platform user list + invite dialog)
  - `src/routes/users.test.tsx` (new tests — file may not exist yet)
  - `src/lib/api.ts` (invite wrappers)
  - `src/lib/route-resolver.ts` (allow tenant owner/admin onto `/clients/$slug/users`)
  - `src/lib/route-resolver.test.ts` (cover new paths)

---

## Task 1: Migration 0003 — invite tables + RLS

**Files:**
- Create: `apps/api/migrations/versions/0003_platform_and_tenant_invites.py`

- [ ] **Step 1: Create the migration**

```python
"""platform_invites + tenant_invites tables with RLS

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-14

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # platform_invites — super_admin can only invite admin / editor (never super_admin).
    op.execute(
        """
        CREATE TABLE platform_invites (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email       citext NOT NULL,
            role        platform_role NOT NULL CHECK (role IN ('admin', 'editor')),
            invited_by  uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
            expires_at  timestamptz NOT NULL,
            accepted_at timestamptz,
            revoked_at  timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX platform_invites_email_pending_uq
            ON platform_invites(email)
            WHERE accepted_at IS NULL AND revoked_at IS NULL
        """
    )

    # tenant_invites — owner/admin invites; cannot invite owner.
    op.execute(
        """
        CREATE TABLE tenant_invites (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            email       citext NOT NULL,
            role        tenant_role NOT NULL CHECK (role IN ('admin','editor','read_only')),
            invited_by  uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
            expires_at  timestamptz NOT NULL,
            accepted_at timestamptz,
            revoked_at  timestamptz,
            created_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX tenant_invites_tenant_id_idx ON tenant_invites(tenant_id)")
    op.execute(
        """
        CREATE UNIQUE INDEX tenant_invites_email_pending_uq
            ON tenant_invites(tenant_id, email)
            WHERE accepted_at IS NULL AND revoked_at IS NULL
        """
    )

    # RLS — platform_invites
    op.execute("ALTER TABLE platform_invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY platform_invites_super_admin_all ON platform_invites
            FOR ALL TO authenticated
            USING (EXISTS (SELECT 1 FROM platform_users pu
                           WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
            WITH CHECK (EXISTS (SELECT 1 FROM platform_users pu
                                WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
        """
    )

    # RLS — tenant_invites
    op.execute("ALTER TABLE tenant_invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_invites_super_admin_all ON tenant_invites
            FOR ALL TO authenticated
            USING (EXISTS (SELECT 1 FROM platform_users pu
                           WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
            WITH CHECK (EXISTS (SELECT 1 FROM platform_users pu
                                WHERE pu.id = auth.uid() AND pu.role='super_admin' AND pu.is_active))
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_invites_owner_admin_all ON tenant_invites
            FOR ALL TO authenticated
            USING (EXISTS (SELECT 1 FROM tenant_memberships m
                           WHERE m.tenant_id = tenant_invites.tenant_id
                             AND m.user_id = auth.uid()
                             AND m.role IN ('owner','admin')))
            WITH CHECK (EXISTS (SELECT 1 FROM tenant_memberships m
                                WHERE m.tenant_id = tenant_invites.tenant_id
                                  AND m.user_id = auth.uid()
                                  AND m.role IN ('owner','admin')))
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_invites")
    op.execute("DROP TABLE IF EXISTS platform_invites")
```

- [ ] **Step 2: Apply + downgrade + reapply**

```bash
make migrate
make migrate-down
make migrate
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/migrations/versions/0003_platform_and_tenant_invites.py
git commit -m "feat(db): platform_invites + tenant_invites tables + RLS"
```

---

## Task 2: SQLAlchemy models for invite tables

**Files:**
- Create: `apps/api/src/xtrusio_api/models/platform_invite.py`
- Create: `apps/api/src/xtrusio_api/models/tenant_invite.py`
- Modify: `apps/api/src/xtrusio_api/models/__init__.py`
- Modify: `apps/api/migrations/env.py`

- [ ] **Step 1: PlatformInvite model**

`apps/api/src/xtrusio_api/models/platform_invite.py`:

```python
"""Platform invite (super_admin invites admin/editor)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import DateTime, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .platform_user import PlatformRole


class PlatformInvite(Base):
    __tablename__ = "platform_invites"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[PlatformRole] = mapped_column(
        SAEnum(
            PlatformRole,
            name="platform_role",
            create_constraint=False,
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    invited_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlatformInviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: PlatformRole
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
```

- [ ] **Step 2: TenantInvite model**

`apps/api/src/xtrusio_api/models/tenant_invite.py`:

```python
"""Tenant invite (owner/admin invites admin/editor/read_only)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import DateTime, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base
from .tenant_membership import TenantRole


class TenantInvite(Base):
    __tablename__ = "tenant_invites"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    role: Mapped[TenantRole] = mapped_column(
        SAEnum(
            TenantRole,
            name="tenant_role",
            create_constraint=False,
            native_enum=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    invited_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TenantInviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: TenantRole
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
```

- [ ] **Step 3: Export from models package**

Modify `apps/api/src/xtrusio_api/models/__init__.py` — add:

```python
from .platform_invite import PlatformInvite, PlatformInviteOut
from .tenant_invite import TenantInvite, TenantInviteOut
```

And add them to `__all__`.

- [ ] **Step 4: Update alembic env**

Modify `apps/api/migrations/env.py` line 13:

```python
from xtrusio_api.models import (  # noqa: F401  (register tables on Base)
    PlatformInvite,
    PlatformSettings,
    PlatformUser,
    Tenant,
    TenantInvite,
    TenantMembership,
)
```

- [ ] **Step 5: Smoke-test imports**

```bash
uv run --directory apps/api python -c "from xtrusio_api.models import PlatformInvite, TenantInvite; print('ok')"
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/models/ apps/api/migrations/env.py
git commit -m "feat(models): PlatformInvite + TenantInvite"
```

---

## Task 3: Invite rules helper (pure)

**Files:**
- Create: `apps/api/src/xtrusio_api/services/invite_rules.py`
- Create: `apps/api/tests/services/test_invite_rules.py`

- [ ] **Step 1: Failing tests**

`apps/api/tests/services/test_invite_rules.py`:

```python
"""Unit tests for can_invite — owner/admin permission rules."""

from __future__ import annotations

import pytest

from xtrusio_api.models.tenant_membership import TenantRole
from xtrusio_api.services.invite_rules import can_invite


@pytest.mark.parametrize(
    "inviter,target,allowed",
    [
        (TenantRole.OWNER, TenantRole.ADMIN, True),
        (TenantRole.OWNER, TenantRole.EDITOR, True),
        (TenantRole.OWNER, TenantRole.READ_ONLY, True),
        (TenantRole.OWNER, TenantRole.OWNER, False),
        (TenantRole.ADMIN, TenantRole.ADMIN, False),
        (TenantRole.ADMIN, TenantRole.EDITOR, True),
        (TenantRole.ADMIN, TenantRole.READ_ONLY, True),
        (TenantRole.ADMIN, TenantRole.OWNER, False),
        (TenantRole.EDITOR, TenantRole.READ_ONLY, False),
        (TenantRole.READ_ONLY, TenantRole.READ_ONLY, False),
    ],
)
def test_can_invite(inviter: TenantRole, target: TenantRole, allowed: bool) -> None:
    assert can_invite(inviter=inviter, target=target) is allowed
```

- [ ] **Step 2: Implement**

`apps/api/src/xtrusio_api/services/invite_rules.py`:

```python
"""Authorization rules for tenant invites.

Owner can invite: admin, editor, read_only.
Admin can invite: editor, read_only (not other admins).
Editor / read_only can't invite anyone.
Nobody can invite owner — that role is born only via self-serve signup.
"""

from __future__ import annotations

from ..models.tenant_membership import TenantRole

_OWNER_TARGETS = {TenantRole.ADMIN, TenantRole.EDITOR, TenantRole.READ_ONLY}
_ADMIN_TARGETS = {TenantRole.EDITOR, TenantRole.READ_ONLY}


def can_invite(*, inviter: TenantRole, target: TenantRole) -> bool:
    if target is TenantRole.OWNER:
        return False
    if inviter is TenantRole.OWNER:
        return target in _OWNER_TARGETS
    if inviter is TenantRole.ADMIN:
        return target in _ADMIN_TARGETS
    return False
```

- [ ] **Step 3: Run, expect pass**

```bash
uv run --directory apps/api pytest tests/services/test_invite_rules.py -v
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/services/invite_rules.py apps/api/tests/services/test_invite_rules.py
git commit -m "feat(api): can_invite() rule + tests"
```

---

## Task 4: Invite schemas

**Files:**
- Create: `apps/api/src/xtrusio_api/schemas/invite.py`

- [ ] **Step 1: Write the schemas**

`apps/api/src/xtrusio_api/schemas/invite.py`:

```python
"""Pydantic schemas for invite endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

from ..models.platform_user import PlatformRole
from ..models.tenant_membership import TenantRole


# Platform invites -----------------------------------------------------------

class CreatePlatformInviteRequest(BaseModel):
    email: EmailStr
    role: PlatformRole  # CHECK constraint in DB rejects 'super_admin'


class PlatformInviteResponse(BaseModel):
    id: UUID
    email: EmailStr
    role: PlatformRole
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class PlatformInvitesPage(BaseModel):
    items: list[PlatformInviteResponse]
    next_cursor: str | None = None


# Tenant invites -------------------------------------------------------------

class CreateTenantInviteRequest(BaseModel):
    email: EmailStr
    role: TenantRole  # CHECK rejects 'owner'


class TenantInviteResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: EmailStr
    role: TenantRole
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class TenantInvitesPage(BaseModel):
    items: list[TenantInviteResponse]
    next_cursor: str | None = None


# Acceptance ----------------------------------------------------------------

class AcceptInviteResult(BaseModel):
    kind: Literal["platform", "tenant"]
    role: str
    tenant_id: UUID | None = None
```

- [ ] **Step 2: Commit**

```bash
git add apps/api/src/xtrusio_api/schemas/invite.py
git commit -m "feat(api): pydantic schemas for invite endpoints"
```

---

## Task 5: Platform invites service + route

**Files:**
- Create: `apps/api/src/xtrusio_api/services/platform_invites.py`
- Create: `apps/api/src/xtrusio_api/routes/platform_invites.py`
- Create: `apps/api/tests/routes/test_platform_invites.py`
- Modify: `apps/api/src/xtrusio_api/main.py`

- [ ] **Step 1: Failing tests**

`apps/api/tests/routes/test_platform_invites.py`:

```python
"""Tests for POST/GET/DELETE /api/platform/users/invites."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_create_invite_unauth_returns_401(http_client: AsyncClient) -> None:
    r = await http_client.post(
        "/api/platform/users/invites", json={"email": "a@a.com", "role": "admin"}
    )
    assert r.status_code == 401


async def test_create_invite_non_super_admin_returns_403(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    from xtrusio_api.models.platform_user import PlatformRole as PR, PlatformUser as PU
    user_id = uuid4()
    email = f"editor-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    db_session.add(PU(id=user_id, email=email, role=PR.EDITOR, is_active=True))
    await db_session.commit()
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            "/api/platform/users/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "admin"},
        )
        assert r.status_code == 403
    finally:
        await db_session.execute(
            text("DELETE FROM platform_users WHERE id = :id; DELETE FROM auth.users WHERE id = :id"),
            {"id": str(user_id)},
        )
        await db_session.commit()


async def test_create_invite_happy_path(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newadmin@example.com", "role": "admin"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "newadmin@example.com"
    assert body["role"] == "admin"
    mock_supabase_admin.auth.admin.invite_user_by_email.assert_called_once()
    args, kwargs = mock_supabase_admin.auth.admin.invite_user_by_email.call_args
    assert args[0] == "newadmin@example.com"
    assert kwargs["data"]["platform_invite_id"] == body["id"]
    assert kwargs["data"]["platform_role"] == "admin"
    # cleanup
    await db_session.execute(
        text("DELETE FROM platform_invites WHERE email = :e"), {"e": "newadmin@example.com"}
    )
    await db_session.commit()


async def test_create_invite_duplicate_pending_returns_409(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    body = {"email": "dup@example.com", "role": "admin"}
    r1 = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert r1.status_code == 201
    r2 = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "invite_pending"
    await db_session.execute(
        text("DELETE FROM platform_invites WHERE email = :e"), {"e": "dup@example.com"}
    )
    await db_session.commit()


async def test_revoke_invite(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock(
        user=MagicMock(id=str(uuid4()))
    )
    r = await http_client.post(
        "/api/platform/users/invites",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "rev@example.com", "role": "editor"},
    )
    invite_id = r.json()["id"]
    r = await http_client.delete(
        f"/api/platform/users/invites/{invite_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204
    row = (
        await db_session.execute(
            text("SELECT revoked_at FROM platform_invites WHERE id = :id"), {"id": invite_id}
        )
    ).scalar_one()
    assert row is not None
    await db_session.execute(text("DELETE FROM platform_invites WHERE id = :id"), {"id": invite_id})
    await db_session.commit()
```

- [ ] **Step 2: Implement service**

`apps/api/src/xtrusio_api/services/platform_invites.py`:

```python
"""Platform invites: create / list / revoke."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import create_client

from ..core.config import get_settings
from ..models.platform_invite import PlatformInvite
from ..models.platform_user import PlatformRole, PlatformUser

_SUPABASE_TIMEOUT = 10.0
_TTL_DAYS = 7


class UserExistsError(Exception):
    pass


class InvitePendingError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def create_platform_invite(
    db: AsyncSession,
    *,
    email: str,
    role: PlatformRole,
    invited_by: UUID,
) -> PlatformInvite:
    # Reject if user already exists (auth.users + platform_users).
    existing_pu = (
        await db.execute(select(PlatformUser).where(PlatformUser.email == email))
    ).scalar_one_or_none()
    if existing_pu is not None:
        raise UserExistsError()

    # Reject duplicate pending invite.
    pending = (
        await db.execute(
            select(PlatformInvite).where(
                and_(
                    PlatformInvite.email == email,
                    PlatformInvite.accepted_at.is_(None),
                    PlatformInvite.revoked_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise InvitePendingError()

    invite = PlatformInvite(
        email=email,
        role=role,
        invited_by=invited_by,
        expires_at=datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS),
    )
    db.add(invite)
    await db.flush()
    invite_id = invite.id

    # Send the email via Supabase.
    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> Any:
        return sb.auth.admin.invite_user_by_email(
            email,
            data={"platform_invite_id": str(invite_id), "platform_role": role.value},
        )

    try:
        await asyncio.wait_for(asyncio.to_thread(_call), timeout=_SUPABASE_TIMEOUT)
    except asyncio.TimeoutError as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e

    await db.commit()
    await db.refresh(invite)
    return invite


async def revoke_platform_invite(db: AsyncSession, *, invite_id: UUID) -> None:
    invite = (
        await db.execute(select(PlatformInvite).where(PlatformInvite.id == invite_id))
    ).scalar_one_or_none()
    if invite is None:
        return
    if invite.accepted_at is not None:
        # Accepted invites cannot be revoked.
        raise InvitePendingError()  # caller maps to 409
    invite.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    # Delete Supabase user — best-effort, not transactional.
    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)
    try:
        # We don't have the supabase user id stored; look it up by email.
        # supabase-py 2.x exposes list_users(); fall through silently on failure.
        await asyncio.wait_for(
            asyncio.to_thread(
                lambda: [
                    sb.auth.admin.delete_user(u.id)
                    for u in sb.auth.admin.list_users().get("users", [])
                    if u.email == invite.email and u.email_confirmed_at is None
                ]
            ),
            timeout=_SUPABASE_TIMEOUT,
        )
    except Exception:
        pass


async def list_platform_invites(db: AsyncSession, *, limit: int = 50) -> list[PlatformInvite]:
    rows = (
        await db.execute(
            select(PlatformInvite).order_by(PlatformInvite.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return list(rows)
```

- [ ] **Step 3: Implement route**

`apps/api/src/xtrusio_api/routes/platform_invites.py`:

```python
"""POST/GET/DELETE /api/platform/users/invites — super_admin only."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, require_super_admin
from ..core.db import get_db
from ..schemas.invite import (
    CreatePlatformInviteRequest,
    PlatformInviteResponse,
    PlatformInvitesPage,
)
from ..services.platform_invites import (
    EmailProviderUnavailableError,
    InvitePendingError,
    UserExistsError,
    create_platform_invite,
    list_platform_invites,
    revoke_platform_invite,
)

router = APIRouter(prefix="/api/platform/users/invites", tags=["platform-invites"])


@router.post("", response_model=PlatformInviteResponse, status_code=status.HTTP_201_CREATED)
async def create(
    body: CreatePlatformInviteRequest,
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformInviteResponse:
    try:
        invite = await create_platform_invite(
            db, email=body.email, role=body.role, invited_by=user.user_id
        )
    except UserExistsError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "user_exists") from e
    except InvitePendingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_pending") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return PlatformInviteResponse.model_validate(invite)


@router.get("", response_model=PlatformInvitesPage)
async def list_invites(
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformInvitesPage:
    rows = await list_platform_invites(db)
    return PlatformInvitesPage(
        items=[PlatformInviteResponse.model_validate(r) for r in rows], next_cursor=None
    )


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(
    invite_id: UUID,
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await revoke_platform_invite(db, invite_id=invite_id)
    except InvitePendingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
```

- [ ] **Step 4: Register router**

Modify `apps/api/src/xtrusio_api/main.py`:

```python
from .routes import platform_invites as platform_invites_routes
# ...
app.include_router(platform_invites_routes.router)
```

- [ ] **Step 5: Run tests**

```bash
uv run --directory apps/api pytest tests/routes/test_platform_invites.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/services/platform_invites.py \
        apps/api/src/xtrusio_api/routes/platform_invites.py \
        apps/api/src/xtrusio_api/main.py \
        apps/api/tests/routes/test_platform_invites.py
git commit -m "feat(api): platform invites (create/list/revoke)"
```

---

## Task 6: Tenant invites service + route

**Files:**
- Create: `apps/api/src/xtrusio_api/services/tenant_invites.py`
- Create: `apps/api/src/xtrusio_api/routes/tenant_invites.py`
- Create: `apps/api/tests/routes/test_tenant_invites.py`
- Modify: `apps/api/src/xtrusio_api/main.py`

- [ ] **Step 1: Failing tests** (subset shown — full table in test_tenant_invites.py)

`apps/api/tests/routes/test_tenant_invites.py`:

```python
"""Tests for POST/GET/DELETE /api/tenants/{tid}/invites."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _seed_owner(db: AsyncSession) -> tuple:
    """Insert auth.users row, tenant, and tenant_memberships(owner) row."""
    user_id = uuid4()
    email = f"o-{user_id.hex[:8]}@example.com"
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    slug = f"t-{user_id.hex[:8]}"
    await db.execute(
        text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
        {"slug": slug, "name": "T", "uid": str(user_id)},
    )
    tid = (
        await db.execute(text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": slug})
    ).scalar_one()
    await db.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "VALUES (:tid, :uid, 'owner')"
        ),
        {"tid": str(tid), "uid": str(user_id)},
    )
    await db.commit()
    return user_id, tid


async def _cleanup(db: AsyncSession, user_id) -> None:
    await db.execute(
        text(
            "DELETE FROM tenant_invites WHERE invited_by = :id; "
            "DELETE FROM tenant_memberships WHERE user_id = :id; "
            "DELETE FROM tenants WHERE created_by = :id; "
            "DELETE FROM auth.users WHERE id = :id"
        ),
        {"id": str(user_id)},
    )
    await db.commit()


async def test_owner_invites_admin(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt,
    mock_supabase_admin: MagicMock,
) -> None:
    user_id, tid = await _seed_owner(db_session)
    try:
        mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "alice@example.com", "role": "admin"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["role"] == "admin"
        assert mock_supabase_admin.auth.admin.invite_user_by_email.called
    finally:
        await _cleanup(db_session, user_id)


async def test_admin_cannot_invite_admin(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    owner_id, tid = await _seed_owner(db_session)
    admin_id = uuid4()
    email = f"adm-{admin_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(admin_id), "email": email},
    )
    await db_session.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "VALUES (:tid, :uid, 'admin')"
        ),
        {"tid": str(tid), "uid": str(admin_id)},
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=admin_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "admin"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "forbidden_role"
    finally:
        await db_session.execute(
            text(
                "DELETE FROM tenant_memberships WHERE user_id = :id; "
                "DELETE FROM auth.users WHERE id = :id"
            ),
            {"id": str(admin_id)},
        )
        await db_session.commit()
        await _cleanup(db_session, owner_id)


async def test_non_member_cannot_invite(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    owner_id, tid = await _seed_owner(db_session)
    outsider_id = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(outsider_id), "email": f"out-{outsider_id.hex[:8]}@example.com"},
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=outsider_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "editor"},
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "not_a_member"
    finally:
        await db_session.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(outsider_id)})
        await db_session.commit()
        await _cleanup(db_session, owner_id)


async def test_check_constraint_prevents_owner_role(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    user_id, tid = await _seed_owner(db_session)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            f"/api/tenants/{tid}/invites",
            headers={"Authorization": f"Bearer {token}"},
            json={"email": "x@x.com", "role": "owner"},
        )
        # Pydantic enum rejects this before it reaches the DB.
        assert r.status_code == 422
    finally:
        await _cleanup(db_session, user_id)
```

- [ ] **Step 2: Implement service**

`apps/api/src/xtrusio_api/services/tenant_invites.py`:

```python
"""Tenant invites: create / list / revoke."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import create_client

from ..core.config import get_settings
from ..models.tenant_invite import TenantInvite
from ..models.tenant_membership import TenantMembership, TenantRole
from .invite_rules import can_invite

_SUPABASE_TIMEOUT = 10.0
_TTL_DAYS = 7


class NotAMemberError(Exception):
    pass


class NotOwnerOrAdminError(Exception):
    pass


class ForbiddenRoleError(Exception):
    pass


class UserAlreadyMemberError(Exception):
    pass


class InvitePendingError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def create_tenant_invite(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    inviter_id: UUID,
    email: str,
    role: TenantRole,
) -> TenantInvite:
    # 1. Confirm inviter is a member of this tenant.
    membership = (
        await db.execute(
            select(TenantMembership).where(
                and_(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.user_id == inviter_id,
                )
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise NotAMemberError()
    if membership.role not in (TenantRole.OWNER, TenantRole.ADMIN):
        raise NotOwnerOrAdminError()

    # 2. Role rule.
    if not can_invite(inviter=membership.role, target=role):
        raise ForbiddenRoleError()

    # 3. Reject if the target email already has a membership in this tenant.
    from sqlalchemy import text
    member_row = (
        await db.execute(
            text(
                """
                SELECT 1
                FROM tenant_memberships m
                JOIN auth.users u ON u.id = m.user_id
                WHERE m.tenant_id = :tid AND u.email = :email
                LIMIT 1
                """
            ),
            {"tid": str(tenant_id), "email": email},
        )
    ).first()
    if member_row is not None:
        raise UserAlreadyMemberError()

    # 4. Reject duplicate pending invite for this (tenant, email).
    pending = (
        await db.execute(
            select(TenantInvite).where(
                and_(
                    TenantInvite.tenant_id == tenant_id,
                    TenantInvite.email == email,
                    TenantInvite.accepted_at.is_(None),
                    TenantInvite.revoked_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if pending is not None:
        raise InvitePendingError()

    invite = TenantInvite(
        tenant_id=tenant_id,
        email=email,
        role=role,
        invited_by=inviter_id,
        expires_at=datetime.now(timezone.utc) + timedelta(days=_TTL_DAYS),
    )
    db.add(invite)
    await db.flush()
    invite_id = invite.id

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> Any:
        return sb.auth.admin.invite_user_by_email(
            email,
            data={
                "tenant_invite_id": str(invite_id),
                "tenant_id": str(tenant_id),
                "tenant_role": role.value,
            },
        )

    try:
        await asyncio.wait_for(asyncio.to_thread(_call), timeout=_SUPABASE_TIMEOUT)
    except asyncio.TimeoutError as e:
        await db.rollback()
        raise EmailProviderUnavailableError() from e

    await db.commit()
    await db.refresh(invite)
    return invite


async def list_tenant_invites(db: AsyncSession, *, tenant_id: UUID) -> list[TenantInvite]:
    rows = (
        await db.execute(
            select(TenantInvite)
            .where(TenantInvite.tenant_id == tenant_id)
            .order_by(TenantInvite.created_at.desc())
        )
    ).scalars().all()
    return list(rows)


async def revoke_tenant_invite(db: AsyncSession, *, invite_id: UUID) -> None:
    invite = (
        await db.execute(select(TenantInvite).where(TenantInvite.id == invite_id))
    ).scalar_one_or_none()
    if invite is None:
        return
    if invite.accepted_at is not None:
        raise InvitePendingError()
    invite.revoked_at = datetime.now(timezone.utc)
    await db.commit()
```

- [ ] **Step 3: Implement route**

`apps/api/src/xtrusio_api/routes/tenant_invites.py`:

```python
"""POST/GET/DELETE /api/tenants/{tid}/invites — tenant owner/admin."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..schemas.invite import (
    CreateTenantInviteRequest,
    TenantInviteResponse,
    TenantInvitesPage,
)
from ..services.tenant_invites import (
    EmailProviderUnavailableError,
    ForbiddenRoleError,
    InvitePendingError,
    NotAMemberError,
    NotOwnerOrAdminError,
    UserAlreadyMemberError,
    create_tenant_invite,
    list_tenant_invites,
    revoke_tenant_invite,
)

router = APIRouter(prefix="/api/tenants/{tenant_id}/invites", tags=["tenant-invites"])


@router.post("", response_model=TenantInviteResponse, status_code=status.HTTP_201_CREATED)
async def create(
    tenant_id: UUID,
    body: CreateTenantInviteRequest,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantInviteResponse:
    try:
        invite = await create_tenant_invite(
            db,
            tenant_id=tenant_id,
            inviter_id=identity.user_id,
            email=body.email,
            role=body.role,
        )
    except NotAMemberError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_member") from e
    except NotOwnerOrAdminError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_owner_or_admin") from e
    except ForbiddenRoleError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden_role") from e
    except UserAlreadyMemberError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "user_already_member") from e
    except InvitePendingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_pending") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return TenantInviteResponse.model_validate(invite)


@router.get("", response_model=TenantInvitesPage)
async def list_invites(
    tenant_id: UUID,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantInvitesPage:
    # RLS gates this — owner/admin/super_admin see; others get an empty list.
    rows = await list_tenant_invites(db, tenant_id=tenant_id)
    return TenantInvitesPage(
        items=[TenantInviteResponse.model_validate(r) for r in rows], next_cursor=None
    )


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke(
    tenant_id: UUID,
    invite_id: UUID,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    # Authorization piggybacks on RLS: if the caller isn't owner/admin of the tenant,
    # the UPDATE that sets revoked_at finds 0 rows and the row stays untouched.
    try:
        await revoke_tenant_invite(db, invite_id=invite_id)
    except InvitePendingError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
```

- [ ] **Step 4: Register router**

```python
from .routes import tenant_invites as tenant_invites_routes
# ...
app.include_router(tenant_invites_routes.router)
```

- [ ] **Step 5: Run tests**

```bash
uv run --directory apps/api pytest tests/routes/test_tenant_invites.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/services/tenant_invites.py \
        apps/api/src/xtrusio_api/routes/tenant_invites.py \
        apps/api/src/xtrusio_api/main.py \
        apps/api/tests/routes/test_tenant_invites.py
git commit -m "feat(api): tenant invites with role-of-inviter rules"
```

---

## Task 7: Invite acceptance endpoint

**Files:**
- Create: `apps/api/src/xtrusio_api/services/invite_acceptance.py`
- Create: `apps/api/src/xtrusio_api/routes/invite_acceptance.py`
- Create: `apps/api/tests/routes/test_invite_acceptance.py`
- Modify: `apps/api/src/xtrusio_api/main.py`
- Modify: `apps/api/src/xtrusio_api/core/auth.py` (extract user_metadata from JWT)

- [ ] **Step 1: Extend auth.py to surface user_metadata**

Modify `apps/api/src/xtrusio_api/core/auth.py` — add to `AuthIdentity`:

```python
@dataclass
class AuthIdentity:
    user_id: UUID
    email: str
    user_metadata: dict[str, Any]
```

Update `require_authenticated` to populate `user_metadata` from the JWT `user_metadata` claim (Supabase emits this when admin APIs set the `data` field):

```python
async def require_authenticated(...) -> AuthIdentity:
    # ... existing decode logic ...
    user_metadata = payload.get("user_metadata") or {}
    # ... look up email ...
    return AuthIdentity(user_id=user_id, email=row[0], user_metadata=user_metadata)
```

Update the existing `make_jwt` fixture in `tests/conftest.py` to accept user_metadata:

```python
def _factory(*, sub: UUID, expired: bool = False, user_metadata: dict | None = None) -> str:
    now = int(time.time())
    payload = {
        "sub": str(sub),
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now - 60 if expired else now + 3600,
        "user_metadata": user_metadata or {},
    }
    ...
```

- [ ] **Step 2: Failing tests**

`apps/api/tests/routes/test_invite_acceptance.py`:

```python
"""Tests for POST /api/invites/accept."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_no_invite_in_metadata_returns_403(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    user_id = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": f"x-{user_id.hex[:8]}@example.com"},
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=user_id, user_metadata={})
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "no_invite"
    finally:
        await db_session.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
        await db_session.commit()


async def test_accept_platform_invite_happy_path(
    http_client: AsyncClient, super_admin_user, make_jwt, db_session: AsyncSession
) -> None:
    invite_id = uuid4()
    user_id = uuid4()
    email = f"new-platform-{user_id.hex[:8]}@example.com"
    # Seed invite.
    await db_session.execute(
        text(
            """
            INSERT INTO platform_invites
                (id, email, role, invited_by, expires_at, accepted_at, revoked_at)
            VALUES (:id, :email, 'admin', :inv, :exp, NULL, NULL)
            """
        ),
        {
            "id": str(invite_id),
            "email": email,
            "inv": str(super_admin_user.id),
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db_session.commit()
    try:
        token = make_jwt(
            sub=user_id,
            user_metadata={"platform_invite_id": str(invite_id), "platform_role": "admin"},
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "platform"
        assert body["role"] == "admin"
        # Verify platform_users row inserted.
        row = (
            await db_session.execute(
                text("SELECT role FROM platform_users WHERE id = :id"), {"id": str(user_id)}
            )
        ).scalar_one()
        assert row == "admin"
    finally:
        await db_session.execute(
            text(
                "DELETE FROM platform_users WHERE id = :id; "
                "DELETE FROM platform_invites WHERE id = :iid; "
                "DELETE FROM auth.users WHERE id = :id"
            ),
            {"id": str(user_id), "iid": str(invite_id)},
        )
        await db_session.commit()


async def test_expired_invite_returns_403(
    http_client: AsyncClient, super_admin_user, make_jwt, db_session: AsyncSession
) -> None:
    invite_id = uuid4()
    user_id = uuid4()
    email = f"exp-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO platform_invites (id, email, role, invited_by, expires_at) "
            "VALUES (:id, :email, 'editor', :inv, :exp)"
        ),
        {
            "id": str(invite_id),
            "email": email,
            "inv": str(super_admin_user.id),
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db_session.commit()
    try:
        token = make_jwt(
            sub=user_id,
            user_metadata={"platform_invite_id": str(invite_id), "platform_role": "editor"},
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "invite_expired"
    finally:
        await db_session.execute(
            text(
                "DELETE FROM platform_invites WHERE id = :iid; "
                "DELETE FROM auth.users WHERE id = :id"
            ),
            {"id": str(user_id), "iid": str(invite_id)},
        )
        await db_session.commit()
```

- [ ] **Step 3: Implement the service**

`apps/api/src/xtrusio_api/services/invite_acceptance.py`:

```python
"""Accept a platform or tenant invite based on JWT user_metadata claims."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.platform_invite import PlatformInvite
from ..models.platform_user import PlatformRole, PlatformUser
from ..models.tenant_invite import TenantInvite
from ..models.tenant_membership import TenantMembership, TenantRole


class NoInviteError(Exception):
    pass


class InviteRevokedError(Exception):
    pass


class InviteExpiredError(Exception):
    pass


class InviteAlreadyAcceptedError(Exception):
    pass


class EmailMismatchError(Exception):
    pass


async def _accept_platform(
    db: AsyncSession, *, user_id: UUID, email: str, invite_id: UUID
) -> dict[str, Any]:
    invite = (
        await db.execute(select(PlatformInvite).where(PlatformInvite.id == invite_id))
    ).scalar_one_or_none()
    if invite is None:
        raise NoInviteError()
    if invite.revoked_at is not None:
        raise InviteRevokedError()
    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError()
    if invite.expires_at < datetime.now(timezone.utc):
        raise InviteExpiredError()
    if invite.email.lower() != email.lower():
        raise EmailMismatchError()

    db.add(
        PlatformUser(
            id=user_id, email=email, role=invite.role, is_active=True
        )
    )
    invite.accepted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"kind": "platform", "role": invite.role.value, "tenant_id": None}


async def _accept_tenant(
    db: AsyncSession, *, user_id: UUID, email: str, invite_id: UUID
) -> dict[str, Any]:
    invite = (
        await db.execute(select(TenantInvite).where(TenantInvite.id == invite_id))
    ).scalar_one_or_none()
    if invite is None:
        raise NoInviteError()
    if invite.revoked_at is not None:
        raise InviteRevokedError()
    if invite.accepted_at is not None:
        raise InviteAlreadyAcceptedError()
    if invite.expires_at < datetime.now(timezone.utc):
        raise InviteExpiredError()
    if invite.email.lower() != email.lower():
        raise EmailMismatchError()

    db.add(
        TenantMembership(
            tenant_id=invite.tenant_id, user_id=user_id, role=invite.role
        )
    )
    invite.accepted_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "kind": "tenant",
        "role": invite.role.value,
        "tenant_id": str(invite.tenant_id),
    }


async def accept_invite(
    db: AsyncSession, *, user_id: UUID, email: str, user_metadata: dict[str, Any]
) -> dict[str, Any]:
    platform_invite_id = user_metadata.get("platform_invite_id")
    tenant_invite_id = user_metadata.get("tenant_invite_id")
    if platform_invite_id:
        return await _accept_platform(
            db, user_id=user_id, email=email, invite_id=UUID(platform_invite_id)
        )
    if tenant_invite_id:
        return await _accept_tenant(
            db, user_id=user_id, email=email, invite_id=UUID(tenant_invite_id)
        )
    raise NoInviteError()
```

- [ ] **Step 4: Implement the route**

`apps/api/src/xtrusio_api/routes/invite_acceptance.py`:

```python
"""POST /api/invites/accept — generic acceptance for both kinds."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..schemas.invite import AcceptInviteResult
from ..services.invite_acceptance import (
    EmailMismatchError,
    InviteAlreadyAcceptedError,
    InviteExpiredError,
    InviteRevokedError,
    NoInviteError,
    accept_invite,
)

router = APIRouter(prefix="/api/invites", tags=["invite-acceptance"])


@router.post("/accept", response_model=AcceptInviteResult)
async def accept(
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcceptInviteResult:
    try:
        result = await accept_invite(
            db,
            user_id=identity.user_id,
            email=identity.email,
            user_metadata=identity.user_metadata,
        )
    except NoInviteError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no_invite") from e
    except InviteRevokedError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invite_revoked") from e
    except InviteExpiredError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invite_expired") from e
    except InviteAlreadyAcceptedError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "invite_already_accepted") from e
    except EmailMismatchError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "email_mismatch") from e
    return AcceptInviteResult.model_validate(result)
```

- [ ] **Step 5: Register router**

```python
from .routes import invite_acceptance as invite_acceptance_routes
# ...
app.include_router(invite_acceptance_routes.router)
```

- [ ] **Step 6: Run tests**

```bash
uv run --directory apps/api pytest tests/routes/test_invite_acceptance.py -v
```

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/xtrusio_api/services/invite_acceptance.py \
        apps/api/src/xtrusio_api/routes/invite_acceptance.py \
        apps/api/src/xtrusio_api/main.py \
        apps/api/src/xtrusio_api/core/auth.py \
        apps/api/tests/routes/test_invite_acceptance.py \
        apps/api/tests/conftest.py
git commit -m "feat(api): /invites/accept handles platform + tenant invites"
```

---

## Task 8: Update `/me` to expose pending_invite

**Files:**
- Modify: `apps/api/src/xtrusio_api/routes/me.py`
- Modify: `apps/api/tests/routes/test_me.py` (add pending_invite cases)

- [ ] **Step 1: Add test for pending_invite path**

Append to `apps/api/tests/routes/test_me.py`:

```python
from datetime import datetime, timedelta, timezone
from uuid import uuid4


async def test_me_with_pending_platform_invite(
    http_client: AsyncClient, super_admin_user, make_jwt, db_session: AsyncSession
) -> None:
    invite_id = uuid4()
    user_id = uuid4()
    email = f"pi-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO platform_invites (id, email, role, invited_by, expires_at) "
            "VALUES (:id, :email, 'admin', :inv, :exp)"
        ),
        {
            "id": str(invite_id),
            "email": email,
            "inv": str(super_admin_user.id),
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db_session.commit()
    try:
        token = make_jwt(
            sub=user_id,
            user_metadata={"platform_invite_id": str(invite_id), "platform_role": "admin"},
        )
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        body = r.json()
        assert body["pending_invite"] is not None
        assert body["pending_invite"]["kind"] == "platform"
        assert body["pending_invite"]["role"] == "admin"
    finally:
        await db_session.execute(
            text(
                "DELETE FROM platform_invites WHERE id = :iid; "
                "DELETE FROM auth.users WHERE id = :id"
            ),
            {"id": str(user_id), "iid": str(invite_id)},
        )
        await db_session.commit()
```

- [ ] **Step 2: Update the route to populate pending_invite**

Edit `apps/api/src/xtrusio_api/routes/me.py` — extend the function to look up the invite:

```python
from datetime import datetime, timezone
from uuid import UUID

from ..models.platform_invite import PlatformInvite
from ..models.tenant_invite import TenantInvite
from ..schemas.me import PendingInvite

# ... in the handler, after computing platform + tenants, add:

pending_invite = None
md = identity.user_metadata
now = datetime.now(timezone.utc)
if pid := md.get("platform_invite_id"):
    inv = (
        await db.execute(select(PlatformInvite).where(PlatformInvite.id == UUID(pid)))
    ).scalar_one_or_none()
    if (
        inv is not None
        and inv.accepted_at is None
        and inv.revoked_at is None
        and inv.expires_at > now
        and inv.email.lower() == identity.email.lower()
    ):
        pending_invite = PendingInvite(
            kind="platform", id=inv.id, tenant_id=None, role=inv.role.value
        )
elif tid := md.get("tenant_invite_id"):
    inv = (
        await db.execute(select(TenantInvite).where(TenantInvite.id == UUID(tid)))
    ).scalar_one_or_none()
    if (
        inv is not None
        and inv.accepted_at is None
        and inv.revoked_at is None
        and inv.expires_at > now
        and inv.email.lower() == identity.email.lower()
    ):
        pending_invite = PendingInvite(
            kind="tenant", id=inv.id, tenant_id=inv.tenant_id, role=inv.role.value
        )

return MeResponse(
    user_id=identity.user_id,
    email=identity.email,
    platform=platform,
    tenants=tenants,
    pending_invite=pending_invite,
)
```

- [ ] **Step 3: Run tests**

```bash
uv run --directory apps/api pytest tests/routes/test_me.py -v
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/me.py apps/api/tests/routes/test_me.py
git commit -m "feat(api): /me populates pending_invite from JWT metadata + DB row"
```

---

## Task 9: RLS tests for invites

**Files:**
- Create: `apps/api/tests/rls/test_platform_invites_rls.py`
- Create: `apps/api/tests/rls/test_tenant_invites_rls.py`

- [ ] **Step 1: platform_invites RLS**

`apps/api/tests/rls/test_platform_invites_rls.py`:

```python
"""platform_invites RLS — only super_admin sees."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_non_super_admin_cannot_see(rls_as, super_admin_user: PlatformUser) -> None:
    # Seed an invite.
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO platform_invites (email, role, invited_by, expires_at) "
                "VALUES (:e, 'admin', :inv, :exp)"
            ),
            {
                "e": "rlscheck@example.com",
                "inv": str(super_admin_user.id),
                "exp": datetime.now(timezone.utc) + timedelta(days=7),
            },
        )
        await priv.commit()
    # Make a non-super_admin user.
    user_id = uuid4()
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": f"nope-{user_id.hex[:8]}@example.com"},
        )
        await priv.commit()
    try:
        async with rls_as(user_id) as s:
            rows = (await s.execute(text("SELECT email FROM platform_invites"))).all()
            assert rows == []
        async with rls_as(super_admin_user.id) as s:
            rows = (await s.execute(text("SELECT email FROM platform_invites"))).all()
            assert ("rlscheck@example.com",) in [tuple(r) for r in rows]
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "DELETE FROM platform_invites WHERE email = :e; "
                    "DELETE FROM auth.users WHERE id = :id"
                ),
                {"e": "rlscheck@example.com", "id": str(user_id)},
            )
            await priv.commit()
```

- [ ] **Step 2: tenant_invites RLS**

`apps/api/tests/rls/test_tenant_invites_rls.py`:

```python
"""tenant_invites RLS — owner/admin see their tenant's invites; others cannot."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from xtrusio_api.core.db import SessionLocal

pytestmark = pytest.mark.asyncio


async def test_editor_cannot_see_invites(rls_as) -> None:
    owner_id = uuid4()
    editor_id = uuid4()
    async with SessionLocal() as priv:
        for uid in (owner_id, editor_id):
            await priv.execute(
                text(
                    "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                    "email_confirmed_at, created_at, updated_at) VALUES "
                    "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                    ":email, '', now(), now(), now())"
                ),
                {"id": str(uid), "email": f"u-{uid.hex[:8]}@example.com"},
            )
        await priv.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:s, :n, :u)"),
            {"s": f"t-{owner_id.hex[:8]}", "n": "T", "u": str(owner_id)},
        )
        tid = (
            await priv.execute(
                text("SELECT id FROM tenants WHERE slug = :s"),
                {"s": f"t-{owner_id.hex[:8]}"},
            )
        ).scalar_one()
        await priv.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) VALUES "
                "(:tid, :owner, 'owner'), (:tid, :editor, 'editor')"
            ),
            {"tid": str(tid), "owner": str(owner_id), "editor": str(editor_id)},
        )
        await priv.execute(
            text(
                "INSERT INTO tenant_invites (tenant_id, email, role, invited_by, expires_at) "
                "VALUES (:tid, :e, 'editor', :inv, :exp)"
            ),
            {
                "tid": str(tid),
                "e": "newhire@example.com",
                "inv": str(owner_id),
                "exp": datetime.now(timezone.utc) + timedelta(days=7),
            },
        )
        await priv.commit()
    try:
        async with rls_as(editor_id) as s:
            rows = (await s.execute(text("SELECT email FROM tenant_invites"))).all()
            assert rows == []
        async with rls_as(owner_id) as s:
            rows = (await s.execute(text("SELECT email FROM tenant_invites"))).all()
            assert len(rows) == 1
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "DELETE FROM tenant_invites WHERE tenant_id = :tid; "
                    "DELETE FROM tenant_memberships WHERE tenant_id = :tid; "
                    "DELETE FROM tenants WHERE id = :tid; "
                    "DELETE FROM auth.users WHERE id IN (:o, :e)"
                ),
                {"tid": str(tid), "o": str(owner_id), "e": str(editor_id)},
            )
            await priv.commit()
```

- [ ] **Step 3: Run RLS tests**

```bash
uv run --directory apps/api pytest tests/rls/test_platform_invites_rls.py tests/rls/test_tenant_invites_rls.py -v
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/rls/test_platform_invites_rls.py \
        apps/api/tests/rls/test_tenant_invites_rls.py
git commit -m "test(rls): platform_invites + tenant_invites policies"
```

---

## Task 10: Integration test — invite full flow

**Files:**
- Create: `apps/api/tests/integration/test_invite_full_flow.py`

- [ ] **Step 1: Write the test**

`apps/api/tests/integration/test_invite_full_flow.py`:

```python
"""Owner creates a tenant invite → invitee 'clicks the email' (we simulate Supabase
adding the user with the right metadata) → /invites/accept → /me reflects new role."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_owner_invites_admin_full_flow(
    http_client: AsyncClient,
    db_session: AsyncSession,
    make_jwt,
    mock_supabase_admin: MagicMock,
) -> None:
    # 1. Seed an owner with a tenant.
    owner_id = uuid4()
    email_owner = f"owner-{owner_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(owner_id), "email": email_owner},
    )
    await db_session.execute(
        text("INSERT INTO tenants (slug, name, created_by) VALUES (:s, 'T', :u)"),
        {"s": f"t-{owner_id.hex[:8]}", "u": str(owner_id)},
    )
    tid = (
        await db_session.execute(
            text("SELECT id FROM tenants WHERE slug = :s"),
            {"s": f"t-{owner_id.hex[:8]}"},
        )
    ).scalar_one()
    await db_session.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "VALUES (:tid, :uid, 'owner')"
        ),
        {"tid": str(tid), "uid": str(owner_id)},
    )
    await db_session.commit()

    # 2. Owner creates an invite.
    owner_token = make_jwt(sub=owner_id)
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock()
    invitee_email = f"new-{uuid4().hex[:8]}@example.com"
    r = await http_client.post(
        f"/api/tenants/{tid}/invites",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"email": invitee_email, "role": "admin"},
    )
    assert r.status_code == 201
    invite_id = r.json()["id"]

    # 3. Simulate Supabase creating the user + delivering them to /accept-invite.
    invitee_id = uuid4()
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(invitee_id), "email": invitee_email},
    )
    await db_session.commit()
    try:
        # 4. Invitee accepts.
        token = make_jwt(
            sub=invitee_id,
            user_metadata={
                "tenant_invite_id": invite_id,
                "tenant_id": str(tid),
                "tenant_role": "admin",
            },
        )
        r = await http_client.post(
            "/api/invites/accept", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "tenant"
        assert body["role"] == "admin"

        # 5. /me reflects admin role.
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        body = r.json()
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["role"] == "admin"
    finally:
        await db_session.execute(
            text(
                "DELETE FROM tenant_invites WHERE id = :iid; "
                "DELETE FROM tenant_memberships WHERE tenant_id = :tid; "
                "DELETE FROM tenants WHERE id = :tid; "
                "DELETE FROM auth.users WHERE id IN (:o, :i)"
            ),
            {
                "iid": invite_id,
                "tid": str(tid),
                "o": str(owner_id),
                "i": str(invitee_id),
            },
        )
        await db_session.commit()
```

- [ ] **Step 2: Run**

```bash
uv run --directory apps/api pytest tests/integration/test_invite_full_flow.py -v
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/integration/test_invite_full_flow.py
git commit -m "test(integration): tenant invite full flow"
```

---

## Task 11: Frontend api.ts — invite wrappers

**Files:**
- Modify: `apps/web/src/lib/api.ts`

- [ ] **Step 1: Append wrappers**

```typescript
export type PlatformInvite = {
  id: string;
  email: string;
  role: "admin" | "editor";
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type TenantInvite = {
  id: string;
  tenant_id: string;
  email: string;
  role: "admin" | "editor" | "read_only";
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export async function postPlatformInvite(
  email: string,
  role: "admin" | "editor",
): Promise<PlatformInvite> {
  return apiFetch("/api/platform/users/invites", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function fetchPlatformInvites(): Promise<{ items: PlatformInvite[] }> {
  return apiFetch("/api/platform/users/invites");
}

export async function deletePlatformInvite(id: string): Promise<void> {
  await apiFetch(`/api/platform/users/invites/${id}`, { method: "DELETE" });
}

export async function postTenantInvite(
  tenantId: string,
  email: string,
  role: "admin" | "editor" | "read_only",
): Promise<TenantInvite> {
  return apiFetch(`/api/tenants/${tenantId}/invites`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function fetchTenantInvites(tenantId: string): Promise<{ items: TenantInvite[] }> {
  return apiFetch(`/api/tenants/${tenantId}/invites`);
}

export async function deleteTenantInvite(tenantId: string, id: string): Promise<void> {
  await apiFetch(`/api/tenants/${tenantId}/invites/${id}`, { method: "DELETE" });
}

export async function postAcceptInvite(): Promise<{
  kind: "platform" | "tenant";
  role: string;
  tenant_id: string | null;
}> {
  return apiFetch("/api/invites/accept", { method: "POST" });
}
```

- [ ] **Step 2: Typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): api wrappers for platform + tenant invites + accept"
```

---

## Task 12: `/accept-invite` page

**Files:**
- Create: `apps/web/src/routes/accept-invite.tsx`
- Create: `apps/web/src/routes/accept-invite.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AcceptInvitePage } from "./accept-invite";

vi.mock("../lib/api", () => ({ postAcceptInvite: vi.fn() }));
const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => () => ({}),
  useNavigate: () => navigateMock,
}));

import { postAcceptInvite } from "../lib/api";

describe("AcceptInvitePage", () => {
  beforeEach(() => {
    vi.mocked(postAcceptInvite).mockReset();
    navigateMock.mockReset();
  });

  it("auto-posts on mount and redirects to /", async () => {
    vi.mocked(postAcceptInvite).mockResolvedValue({
      kind: "platform",
      role: "admin",
      tenant_id: null,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AcceptInvitePage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/" }));
    expect(postAcceptInvite).toHaveBeenCalled();
  });

  it("renders explanation on error", async () => {
    vi.mocked(postAcceptInvite).mockRejectedValue(new Error("invite_expired"));
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AcceptInvitePage />
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText(/expired/i)).toBeTruthy());
  });
});
```

- [ ] **Step 2: Implement**

`apps/web/src/routes/accept-invite.tsx`:

```tsx
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postAcceptInvite } from "../lib/api";
import { errorMessage } from "../lib/error-messages";
import { Button } from "../components/ui/button";
import { supabase } from "../lib/supabase";

function AcceptInvitePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: postAcceptInvite,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate({ to: "/" });
    },
  });
  useEffect(() => {
    m.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  if (m.error) {
    return (
      <main className="grid min-h-screen place-items-center px-6">
        <div className="max-w-md space-y-4 text-center">
          <h1 className="text-2xl font-semibold">Couldn't accept invitation</h1>
          <p className="text-muted-foreground">{errorMessage((m.error as Error).message)}</p>
          <Button onClick={() => supabase.auth.signOut().then(() => navigate({ to: "/sign-in" }))}>
            Sign out
          </Button>
        </div>
      </main>
    );
  }
  return (
    <main className="grid min-h-screen place-items-center text-muted-foreground">
      Completing your invitation…
    </main>
  );
}

export const Route = createFileRoute("/accept-invite")({ component: AcceptInvitePage });
export { AcceptInvitePage };
```

- [ ] **Step 3: Test + commit**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test src/routes/accept-invite.test.tsx
git add apps/web/src/routes/accept-invite.tsx apps/web/src/routes/accept-invite.test.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /accept-invite auto-posts and routes"
```

---

## Task 13: `/users` expanded with invite UI

**Files:**
- Modify: `apps/web/src/routes/users.tsx`
- Create: `apps/web/src/routes/users.test.tsx`

- [ ] **Step 1: Failing test (member tab + invite dialog)**

`apps/web/src/routes/users.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { UsersPage } from "./users";

vi.mock("../lib/api", () => ({
  fetchPlatformInvites: vi.fn(),
  postPlatformInvite: vi.fn(),
  deletePlatformInvite: vi.fn(),
}));

import {
  deletePlatformInvite,
  fetchPlatformInvites,
  postPlatformInvite,
} from "../lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <UsersPage />
    </QueryClientProvider>,
  );
}

describe("UsersPage", () => {
  beforeEach(() => {
    vi.mocked(fetchPlatformInvites).mockReset();
    vi.mocked(postPlatformInvite).mockReset();
    vi.mocked(deletePlatformInvite).mockReset();
  });

  it("renders pending invites and lets super_admin invite a new user", async () => {
    vi.mocked(fetchPlatformInvites).mockResolvedValue({ items: [] });
    vi.mocked(postPlatformInvite).mockResolvedValue({
      id: "1",
      email: "alice@example.com",
      role: "admin",
      expires_at: new Date().toISOString(),
      accepted_at: null,
      revoked_at: null,
      created_at: new Date().toISOString(),
    });
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole("button", { name: /invite user/i }));
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    // role select stays at default "admin"
    await user.click(screen.getByRole("button", { name: /send invite/i }));
    await waitFor(() =>
      expect(postPlatformInvite).toHaveBeenCalledWith("alice@example.com", "admin"),
    );
  });
});
```

- [ ] **Step 2: Implement**

Read existing `apps/web/src/routes/users.tsx`. Replace its body with a tabbed layout:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  deletePlatformInvite,
  fetchPlatformInvites,
  postPlatformInvite,
  type PlatformInvite,
} from "../lib/api";
import { errorMessage } from "../lib/error-messages";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { PageHeader } from "../components/page-header";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";

function InviteDialog() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "editor">("admin");
  const [open, setOpen] = useState(false);
  const m = useMutation({
    mutationFn: () => postPlatformInvite(email, role),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["platform-invites"] });
      setOpen(false);
      setEmail("");
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Invite user</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a platform user</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate();
          }}
          className="space-y-4"
        >
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div>
            <Label htmlFor="role">Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as "admin" | "editor")}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="editor">Editor</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {m.error ? (
            <p className="text-sm text-destructive">
              {errorMessage((m.error as Error).message)}
            </p>
          ) : null}
          <Button type="submit" disabled={m.isPending} className="w-full">
            {m.isPending ? "Sending…" : "Send invite"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function UsersPage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["platform-invites"],
    queryFn: fetchPlatformInvites,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => deletePlatformInvite(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-invites"] }),
  });
  const invites: PlatformInvite[] = data?.items ?? [];
  return (
    <div className="space-y-6">
      <PageHeader title="Platform users" actions={<InviteDialog />} />
      <section>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Pending invites</h2>
        {invites.length === 0 ? (
          <p className="text-sm text-muted-foreground">No pending invites.</p>
        ) : (
          <ul className="divide-y rounded-md border">
            {invites.map((i) => (
              <li key={i.id} className="flex items-center justify-between p-4">
                <div>
                  <p className="font-medium">{i.email}</p>
                  <p className="text-xs text-muted-foreground">{i.role}</p>
                </div>
                {i.accepted_at ? (
                  <span className="text-xs text-success">Accepted</span>
                ) : i.revoked_at ? (
                  <span className="text-xs text-muted-foreground">Revoked</span>
                ) : (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => revoke.mutate(i.id)}
                    disabled={revoke.isPending}
                  >
                    Revoke
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

export const Route = createFileRoute("/users")({ component: UsersPage });
export { UsersPage };
```

- [ ] **Step 3: Run tests + typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test src/routes/users.test.tsx
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/routes/users.tsx apps/web/src/routes/users.test.tsx
git commit -m "feat(web): /users page with platform invite UI"
```

---

## Task 14: `/clients/$slug/users` page (tenant invites)

**Files:**
- Create: `apps/web/src/routes/clients.$slug.users.tsx`
- Create: `apps/web/src/routes/clients.$slug.users.test.tsx`
- Modify: `apps/web/src/lib/route-resolver.ts` (allow tenant owner/admin on this path)
- Modify: `apps/web/src/lib/route-resolver.test.ts`

- [ ] **Step 1: Update resolveRoute to allow `/clients/$slug/users`**

The current logic redirects tenant_members away from `/settings` and `/users`, but tenant routes should pass through. Verify `/clients/...` is not in `PLATFORM_ONLY`. It isn't, so tenant members can already reach it. No change needed — but we should make this an explicit test.

Append to `apps/web/src/lib/route-resolver.test.ts`:

```typescript
it("tenant_member can navigate to /clients/$slug/users", () => {
  expect(resolveRoute({ session: "s", me: tenant }, "/clients/acme/users")).toEqual({
    kind: "render",
  });
});
```

- [ ] **Step 2: Failing test for the page**

`apps/web/src/routes/clients.$slug.users.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { TenantUsersPage } from "./clients.$slug.users";

vi.mock("../lib/api", () => ({
  fetchTenantInvites: vi.fn(),
  postTenantInvite: vi.fn(),
  deleteTenantInvite: vi.fn(),
  fetchMe: vi.fn(),
}));
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => () => ({}),
  useParams: () => ({ slug: "acme" }),
}));

import { fetchMe, fetchTenantInvites, postTenantInvite } from "../lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <TenantUsersPage />
    </QueryClientProvider>,
  );
}

describe("TenantUsersPage", () => {
  beforeEach(() => {
    vi.mocked(fetchTenantInvites).mockReset();
    vi.mocked(postTenantInvite).mockReset();
    vi.mocked(fetchMe).mockReset();
  });

  it("invites a tenant editor", async () => {
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: null,
      tenants: [{ id: "t-1", slug: "acme", name: "Acme", role: "owner" }],
      pending_invite: null,
    });
    vi.mocked(fetchTenantInvites).mockResolvedValue({ items: [] });
    vi.mocked(postTenantInvite).mockResolvedValue({
      id: "1",
      tenant_id: "t-1",
      email: "ed@example.com",
      role: "editor",
      expires_at: new Date().toISOString(),
      accepted_at: null,
      revoked_at: null,
      created_at: new Date().toISOString(),
    });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: /invite user/i }));
    await user.click(screen.getByRole("button", { name: /invite user/i }));
    await user.type(screen.getByLabelText(/email/i), "ed@example.com");
    // Pick role=editor
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /editor/i }));
    await user.click(screen.getByRole("button", { name: /send invite/i }));
    await waitFor(() =>
      expect(postTenantInvite).toHaveBeenCalledWith("t-1", "ed@example.com", "editor"),
    );
  });
});
```

- [ ] **Step 3: Implement**

`apps/web/src/routes/clients.$slug.users.tsx`:

```tsx
import { createFileRoute, useParams } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  deleteTenantInvite,
  fetchMe,
  fetchTenantInvites,
  postTenantInvite,
  type TenantInvite,
} from "../lib/api";
import { errorMessage } from "../lib/error-messages";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { PageHeader } from "../components/page-header";

type TenantRole = "admin" | "editor" | "read_only";

function InviteTenantDialog({ tenantId, inviterRole }: { tenantId: string; inviterRole: "owner" | "admin" }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<TenantRole>(inviterRole === "owner" ? "admin" : "editor");
  const [open, setOpen] = useState(false);
  const allowed: TenantRole[] =
    inviterRole === "owner" ? ["admin", "editor", "read_only"] : ["editor", "read_only"];
  const m = useMutation({
    mutationFn: () => postTenantInvite(tenantId, email, role),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["tenant-invites", tenantId] });
      setOpen(false);
      setEmail("");
    },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Invite user</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite a user to this workspace</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate();
          }}
          className="space-y-4"
        >
          <div>
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div>
            <Label htmlFor="role">Role</Label>
            <Select value={role} onValueChange={(v) => setRole(v as TenantRole)}>
              <SelectTrigger id="role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {allowed.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {m.error ? (
            <p className="text-sm text-destructive">
              {errorMessage((m.error as Error).message)}
            </p>
          ) : null}
          <Button type="submit" disabled={m.isPending} className="w-full">
            {m.isPending ? "Sending…" : "Send invite"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function TenantUsersPage() {
  const { slug } = useParams({ strict: false }) as { slug: string };
  const qc = useQueryClient();
  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const myTenant = me?.tenants.find((t) => t.slug === slug);
  const { data: invites } = useQuery({
    queryKey: ["tenant-invites", myTenant?.id],
    queryFn: () => fetchTenantInvites(myTenant!.id),
    enabled: !!myTenant,
  });
  const revoke = useMutation({
    mutationFn: (id: string) => deleteTenantInvite(myTenant!.id, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tenant-invites", myTenant?.id] }),
  });
  if (!myTenant) return null;
  const canInvite = myTenant.role === "owner" || myTenant.role === "admin";
  return (
    <div className="space-y-6">
      <PageHeader
        title={`${myTenant.name} — Users`}
        actions={
          canInvite ? (
            <InviteTenantDialog tenantId={myTenant.id} inviterRole={myTenant.role as "owner" | "admin"} />
          ) : null
        }
      />
      <section>
        <h2 className="mb-2 text-sm font-medium text-muted-foreground">Invitations</h2>
        {invites && invites.items.length > 0 ? (
          <ul className="divide-y rounded-md border">
            {invites.items.map((i: TenantInvite) => (
              <li key={i.id} className="flex items-center justify-between p-4">
                <div>
                  <p className="font-medium">{i.email}</p>
                  <p className="text-xs text-muted-foreground">{i.role}</p>
                </div>
                {!i.accepted_at && !i.revoked_at ? (
                  <Button variant="ghost" size="sm" onClick={() => revoke.mutate(i.id)}>
                    Revoke
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">No invitations yet.</p>
        )}
      </section>
    </div>
  );
}

export const Route = createFileRoute("/clients/$slug/users")({ component: TenantUsersPage });
export { TenantUsersPage };
```

- [ ] **Step 4: Run tests + typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test src/routes/clients.$slug.users.test.tsx src/lib/route-resolver.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/clients.\$slug.users.tsx \
        apps/web/src/routes/clients.\$slug.users.test.tsx \
        apps/web/src/lib/route-resolver.test.ts \
        apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /clients/\$slug/users — tenant invite UI"
```

---

## Task 15: Manual end-to-end smoke test (invites)

**No new files. Manual verification only.**

- [ ] **Step 1: All migrations applied**

```bash
make migrate
```

- [ ] **Step 2: Start the app**

```bash
make dev
```

- [ ] **Step 3: Sign in as super_admin → /users → invite an editor**

Open `/users` as the super_admin. Click "Invite user" → fill in an email you can receive on → role: editor → send. Confirm the invite appears in the list.

- [ ] **Step 4: Open the email + complete acceptance**

Click the link → set password on Supabase's page → returns to `/accept-invite` → auto-accept fires → land on `/`. The sidebar should now reflect a platform editor identity.

- [ ] **Step 5: Self-serve signup → onboarding (from Plan 2A) → tenant invite**

In an incognito, sign up + confirm + onboard a workspace. Then in `/clients/<your-slug>/users`, invite an admin. Repeat the email-click → /accept-invite flow as the admin.

- [ ] **Step 6: Verify in DB**

```bash
psql "$DATABASE_URL" -c "SELECT email, role, accepted_at FROM platform_invites ORDER BY created_at DESC LIMIT 5;"
psql "$DATABASE_URL" -c "SELECT email, role, accepted_at FROM tenant_invites ORDER BY created_at DESC LIMIT 5;"
psql "$DATABASE_URL" -c "SELECT user_id, role FROM tenant_memberships ORDER BY created_at DESC LIMIT 5;"
```

- [ ] **Step 7: `make check` clean**

```bash
make check
```

---

## Self-review against the spec

- [ ] §3.4 `platform_invites` — Task 1, with CHECK preventing super_admin invites.
- [ ] §3.5 `tenant_invites` — Task 1, with CHECK preventing owner invites.
- [ ] §3.6 RLS on `platform_invites` + `tenant_invites` — Task 1, tested in Task 9.
- [ ] §4.3 `POST/GET/DELETE /platform/users/invites` — Task 5.
- [ ] §4.4 `POST/GET/DELETE /tenants/{id}/invites` — Task 6.
- [ ] §4.2 `POST /invites/accept` — Task 7.
- [ ] §4.2 `/me` includes `pending_invite` — Task 8.
- [ ] §5.1 routes `/accept-invite`, expanded `/users`, `/clients/$slug/users` — Tasks 12–14.
- [ ] §7 testing — Tasks 3, 5–10 (backend); 12–14 (frontend); 9 (RLS).
- [ ] §6 emails — verified by manual smoke test (Task 15); template config is dashboard-only.

If any spec section lacks a corresponding task, add it here before declaring this plan complete.

---

## Out of scope (still deferred)

- Custom email templates (Supabase defaults are fine for v1)
- Orphan cleanup nightly job (auth.users with no rows after 7d)
- `sent_at` flag + Dramatiq retry for Supabase email send failures
- Ownership transfer between tenant members
- Multi-tenant URL routing beyond `/clients/$slug/users`
- Audit log table
- Rate limiting
