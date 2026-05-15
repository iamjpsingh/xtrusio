# Plan 2A — Public signup chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the public chain from the design spec — a super_admin-controlled signup toggle, a `/sign-up` form, email confirmation via managed Supabase, and an `/onboarding` step that creates the new user's tenant and makes them its owner.

**Architecture:** Application-gated signup (Supabase project-level signup stays on; our `POST /signup` checks `platform_settings.signups_enabled`). New `tenant_role` enum, new `tenant_memberships` table (with a one-owner-per-tenant partial unique index), new singleton `platform_settings` row. RLS on every new table as defense in depth; FastAPI deps are the primary gate. Frontend gets a state-machine AuthGuard, a `/sign-up`, `/onboarding`, and an expanded `/settings` toggle UI.

**Spec:** `docs/superpowers/specs/2026-05-14-platform-settings-signup-and-invites-design.md`

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, python-jose, pydantic v2, supabase-py 2.10 (Admin API). Frontend — React 19, TanStack Router, TanStack Query, `@supabase/supabase-js`, Tailwind v4 + shadcn-ui, Vitest + RTL + MSW.

**Prereq:** Plan 1A, 1A5, 1B all done. `.env` filled in against a managed Supabase project. Migration `0001` already applied.

---

## Files Created / Modified

### Backend (`apps/api/`)
- **Create:**
  - `migrations/versions/0002_platform_settings_and_tenant_memberships.py`
  - `src/xtrusio_api/models/platform_settings.py`
  - `src/xtrusio_api/models/tenant_membership.py`
  - `src/xtrusio_api/schemas/__init__.py`
  - `src/xtrusio_api/schemas/me.py`
  - `src/xtrusio_api/schemas/signup.py`
  - `src/xtrusio_api/schemas/onboarding.py`
  - `src/xtrusio_api/schemas/platform_settings.py`
  - `src/xtrusio_api/services/__init__.py`
  - `src/xtrusio_api/services/slug.py`
  - `src/xtrusio_api/services/signup.py`
  - `src/xtrusio_api/services/onboarding.py`
  - `src/xtrusio_api/services/platform_settings.py`
  - `src/xtrusio_api/routes/signup.py`
  - `src/xtrusio_api/routes/onboarding.py`
  - `src/xtrusio_api/routes/platform_settings.py`
  - `tests/services/__init__.py`
  - `tests/services/test_slug.py`
  - `tests/routes/test_signup.py`
  - `tests/routes/test_platform_settings.py`
  - `tests/routes/test_onboarding.py`
  - `tests/rls/__init__.py`
  - `tests/rls/conftest.py`
  - `tests/rls/test_platform_settings_rls.py`
  - `tests/rls/test_tenant_memberships_rls.py`
  - `tests/rls/test_tenants_rls.py`
  - `tests/integration/__init__.py`
  - `tests/integration/test_signup_to_tenant_flow.py`
- **Modify:**
  - `src/xtrusio_api/models/__init__.py` (export new models)
  - `src/xtrusio_api/routes/me.py` (extended /me response)
  - `src/xtrusio_api/main.py` (register new routers)
  - `migrations/env.py` (import new models)
  - `tests/conftest.py` (add tenant_member_user fixture)
  - `tests/routes/test_me.py` (cover the new response shape)

### Frontend (`apps/web/`)
- **Create:**
  - `src/lib/error-messages.ts`
  - `src/lib/error-messages.test.ts`
  - `src/lib/route-resolver.ts`
  - `src/lib/route-resolver.test.ts`
  - `src/routes/sign-up.tsx`
  - `src/routes/sign-up.test.tsx`
  - `src/routes/onboarding.tsx`
  - `src/routes/onboarding.test.tsx`
  - `src/routes/settings.test.tsx`
  - `src/components/auth-guard.test.tsx`
- **Modify:**
  - `src/components/auth-guard.tsx` (full rewrite)
  - `src/routes/settings.tsx` (signup toggle UI)
  - `src/routes/__root.tsx` (provider wiring if needed)
  - `src/lib/api.ts` (new endpoint wrappers)

---

## Task 1: Alembic migration 0002 — schema + RLS

**Files:**
- Create: `apps/api/migrations/versions/0002_platform_settings_and_tenant_memberships.py`

- [ ] **Step 1: Create the migration file**

```python
"""platform_settings singleton + tenant_role enum + tenant_memberships

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-14

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE tenant_role AS ENUM ('owner', 'admin', 'editor', 'read_only')")

    # platform_settings — singleton row enforced via CHECK (id=1).
    op.execute(
        """
        CREATE TABLE platform_settings (
            id              smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            signups_enabled boolean NOT NULL DEFAULT false,
            updated_at      timestamptz NOT NULL DEFAULT now(),
            updated_by      uuid REFERENCES auth.users(id) ON DELETE SET NULL
        )
        """
    )
    op.execute("INSERT INTO platform_settings (id, signups_enabled) VALUES (1, false)")

    # tenant_memberships
    op.execute(
        """
        CREATE TABLE tenant_memberships (
            id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id    uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            role       tenant_role NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, user_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX tenant_memberships_user_id_idx ON tenant_memberships(user_id)"
    )
    op.execute(
        "CREATE INDEX tenant_memberships_tenant_id_idx ON tenant_memberships(tenant_id)"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX tenant_memberships_one_owner_per_tenant
            ON tenant_memberships(tenant_id)
            WHERE role = 'owner'
        """
    )

    op.execute(
        "CREATE TRIGGER tenant_memberships_set_updated_at "
        "BEFORE UPDATE ON tenant_memberships "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # RLS — platform_settings
    op.execute("ALTER TABLE platform_settings ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY platform_settings_authenticated_read ON platform_settings
            FOR SELECT TO authenticated USING (true)
        """
    )
    op.execute(
        """
        CREATE POLICY platform_settings_super_admin_write ON platform_settings
            FOR UPDATE TO authenticated
            USING (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
        """
    )

    # RLS — tenant_memberships
    op.execute("ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_memberships_self_read ON tenant_memberships
            FOR SELECT TO authenticated USING (user_id = auth.uid())
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_memberships_super_admin_all ON tenant_memberships
            FOR ALL TO authenticated
            USING (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM platform_users pu
                WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
            ))
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_memberships_owner_admin_manage ON tenant_memberships
            FOR ALL TO authenticated
            USING (EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenant_memberships.tenant_id
                  AND m.user_id = auth.uid()
                  AND m.role IN ('owner','admin')
            ))
            WITH CHECK (EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenant_memberships.tenant_id
                  AND m.user_id = auth.uid()
                  AND m.role IN ('owner','admin')
            ))
        """
    )

    # tenants — add tenant_member read policy (super_admin policy from 0001 keeps FOR ALL).
    op.execute(
        """
        CREATE POLICY tenants_member_read ON tenants
            FOR SELECT TO authenticated
            USING (EXISTS (
                SELECT 1 FROM tenant_memberships m
                WHERE m.tenant_id = tenants.id AND m.user_id = auth.uid()
            ))
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenants_member_read ON tenants")
    op.execute("DROP TABLE IF EXISTS tenant_memberships")
    op.execute("DROP TABLE IF EXISTS platform_settings")
    op.execute("DROP TYPE IF EXISTS tenant_role")
```

- [ ] **Step 2: Apply the migration**

```bash
make migrate
```
Expected: `INFO  [alembic.runtime.migration] Running upgrade 0001 -> 0002, ...` and no errors.

- [ ] **Step 3: Verify the downgrade also works**

```bash
make migrate-down
make migrate
```
Both must succeed cleanly.

- [ ] **Step 4: Commit**

```bash
git add apps/api/migrations/versions/0002_platform_settings_and_tenant_memberships.py
git commit -m "feat(db): add platform_settings, tenant_memberships, tenant_role enum + RLS"
```

---

## Task 2: SQLAlchemy models for new tables

**Files:**
- Create: `apps/api/src/xtrusio_api/models/platform_settings.py`
- Create: `apps/api/src/xtrusio_api/models/tenant_membership.py`
- Modify: `apps/api/src/xtrusio_api/models/__init__.py`
- Modify: `apps/api/migrations/env.py`

- [ ] **Step 1: PlatformSettings model**

`apps/api/src/xtrusio_api/models/platform_settings.py`:

```python
"""Platform-wide settings singleton (id always = 1)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Boolean, DateTime, SmallInteger, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    signups_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)


class PlatformSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signups_enabled: bool
    updated_at: datetime
    updated_by_email: str | None = None
```

- [ ] **Step 2: TenantMembership model**

`apps/api/src/xtrusio_api/models/tenant_membership.py`:

```python
"""Tenant membership: links a user to a tenant with a role."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class TenantRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    READ_ONLY = "read_only"


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"

    id: Mapped[UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TenantMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    role: TenantRole
```

- [ ] **Step 3: Export from models package**

Read `apps/api/src/xtrusio_api/models/__init__.py`. Append imports so they register on `Base.metadata`:

```python
from .platform_settings import PlatformSettings, PlatformSettingsOut
from .platform_user import PlatformRole, PlatformUser, PlatformUserOut
from .tenant import Tenant, TenantIn, TenantOut
from .tenant_membership import TenantMembership, TenantMembershipOut, TenantRole

__all__ = [
    "PlatformRole",
    "PlatformSettings",
    "PlatformSettingsOut",
    "PlatformUser",
    "PlatformUserOut",
    "Tenant",
    "TenantIn",
    "TenantOut",
    "TenantMembership",
    "TenantMembershipOut",
    "TenantRole",
]
```

- [ ] **Step 4: Register in Alembic env**

Modify `apps/api/migrations/env.py` line 13 — add the new imports so autogenerate works:

```python
from xtrusio_api.models import (  # noqa: F401  (register tables on Base)
    PlatformSettings,
    PlatformUser,
    Tenant,
    TenantMembership,
)
```

- [ ] **Step 5: Smoke-test the models**

```bash
uv run --directory apps/api python -c "from xtrusio_api.models import PlatformSettings, TenantMembership, TenantRole; print(TenantRole.OWNER.value)"
```
Expected output: `owner`

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/models/ apps/api/migrations/env.py
git commit -m "feat(models): add PlatformSettings, TenantMembership, TenantRole"
```

---

## Task 3: Slug service (pure helper)

**Files:**
- Create: `apps/api/src/xtrusio_api/services/__init__.py` (empty)
- Create: `apps/api/src/xtrusio_api/services/slug.py`
- Create: `apps/api/tests/services/__init__.py` (empty)
- Create: `apps/api/tests/services/test_slug.py`

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/services/test_slug.py`:

```python
"""Unit tests for slug helpers — pure functions, no DB."""

from __future__ import annotations

import pytest

from xtrusio_api.services.slug import slugify, unique_slug_from_taken


@pytest.mark.parametrize(
    "name,expected",
    [
        ("Acme Corp", "acme-corp"),
        ("  Acme  Corp  ", "acme-corp"),
        ("ACME!!! Corp™", "acme-corp"),
        ("Über Glühwein", "uber-gluhwein"),
        ("123 Numbers Then Letters", "n123-numbers-then-letters"),  # leading digit forbidden by schema regex
        ("------", "tenant"),  # all hyphens stripped → fallback
        ("a", "tenant-a"),  # below min length 3, padded by fallback
        ("x" * 200, "x" * 64),  # truncated to schema max
    ],
)
def test_slugify_known_cases(name: str, expected: str) -> None:
    assert slugify(name) == expected


def test_unique_slug_no_collision() -> None:
    assert unique_slug_from_taken("acme", taken=set()) == "acme"


def test_unique_slug_first_collision() -> None:
    assert unique_slug_from_taken("acme", taken={"acme"}) == "acme-2"


def test_unique_slug_multiple_collisions() -> None:
    assert unique_slug_from_taken("acme", taken={"acme", "acme-2", "acme-3"}) == "acme-4"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
make migrate  # ensure DB ready in case anything in conftest needs it (not used here)
uv run --directory apps/api pytest tests/services/test_slug.py -v
```
Expected: ImportError / module not found.

- [ ] **Step 3: Implement the slug service**

`apps/api/src/xtrusio_api/services/slug.py`:

```python
"""Slug helpers.

The tenants table CHECK requires:
    slug ~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$'

i.e. 3-64 chars, lowercase, starts with a letter, ends alnum, hyphens in middle.
slugify() normalizes user input toward that shape; unique_slug_from_taken()
appends -2/-3/... on collision.
"""

from __future__ import annotations

import re
import unicodedata

_MAX = 64
_MIN_BODY = 1  # body length excludes the required leading letter
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_LEADING_HYPHENS = re.compile(r"^-+")
_TRAILING_HYPHENS = re.compile(r"-+$")


def slugify(name: str) -> str:
    """Normalize a workspace name into a slug satisfying the tenants_slug_format CHECK."""
    # Unicode → ASCII (NFKD strips combining accents).
    ascii_lower = (
        unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii").lower()
    )
    # Collapse non-alnum to a single hyphen.
    collapsed = _NON_ALNUM.sub("-", ascii_lower)
    # Trim leading/trailing hyphens.
    trimmed = _TRAILING_HYPHENS.sub("", _LEADING_HYPHENS.sub("", collapsed))
    # Require a letter as the first char; if it's a digit or empty, prefix.
    if not trimmed or not trimmed[0].isalpha():
        if trimmed and trimmed[0].isdigit():
            trimmed = f"n{trimmed}"
        else:
            trimmed = f"tenant-{trimmed}" if trimmed else "tenant"
    # Schema regex requires 3-64 chars; pad short results.
    if len(trimmed) < 3:
        trimmed = f"tenant-{trimmed}"
    # Truncate to max length.
    return trimmed[:_MAX]


def unique_slug_from_taken(base: str, taken: set[str]) -> str:
    """Return `base` if not taken, else `base-2`, `base-3`, ... until a free one."""
    if base not in taken:
        return base
    i = 2
    while True:
        candidate = f"{base[: _MAX - len(str(i)) - 1]}-{i}"
        if candidate not in taken:
            return candidate
        i += 1
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run --directory apps/api pytest tests/services/test_slug.py -v
```
Expected: all parametrized cases + 3 unique-slug tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/services/ apps/api/tests/services/
git commit -m "feat(api): slug helpers + tests"
```

---

## Task 4: Pydantic schemas

**Files:**
- Create: `apps/api/src/xtrusio_api/schemas/__init__.py` (empty)
- Create: `apps/api/src/xtrusio_api/schemas/me.py`
- Create: `apps/api/src/xtrusio_api/schemas/signup.py`
- Create: `apps/api/src/xtrusio_api/schemas/onboarding.py`
- Create: `apps/api/src/xtrusio_api/schemas/platform_settings.py`

- [ ] **Step 1: `me.py`**

```python
"""Response schema for GET /api/me."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr

from ..models.platform_user import PlatformRole
from ..models.tenant_membership import TenantRole


class PlatformContext(BaseModel):
    role: PlatformRole
    is_active: bool


class TenantContext(BaseModel):
    id: UUID
    slug: str
    name: str
    role: TenantRole


class PendingInvite(BaseModel):
    kind: Literal["platform", "tenant"]
    id: UUID
    tenant_id: UUID | None
    role: str  # widened union of platform_role and tenant_role; validated server-side


class MeResponse(BaseModel):
    user_id: UUID
    email: EmailStr
    platform: PlatformContext | None
    tenants: list[TenantContext]
    pending_invite: PendingInvite | None
```

- [ ] **Step 2: `signup.py`**

```python
"""Request/response schemas for /api/signup and /api/platform/signup-status."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class SignupStatus(BaseModel):
    signups_enabled: bool


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class SignupResponse(BaseModel):
    state: Literal["confirm_email_sent"]
```

- [ ] **Step 3: `onboarding.py`**

```python
"""Request/response schemas for /api/onboarding/tenants."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from ..models.tenant_membership import TenantRole


class CreateTenantRequest(BaseModel):
    workspace_name: str = Field(min_length=2, max_length=200)


class CreatedTenant(BaseModel):
    id: UUID
    slug: str
    name: str
    role: TenantRole


class CreateTenantResponse(BaseModel):
    tenant: CreatedTenant
```

- [ ] **Step 4: `platform_settings.py`**

```python
"""Request/response schemas for /api/platform/settings."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PlatformSettingsResponse(BaseModel):
    signups_enabled: bool
    updated_at: datetime
    updated_by_email: str | None


class UpdatePlatformSettingsRequest(BaseModel):
    signups_enabled: bool
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/schemas/
git commit -m "feat(api): pydantic schemas for signup, onboarding, settings, me"
```

---

## Task 5: Platform settings service + route

**Files:**
- Create: `apps/api/src/xtrusio_api/services/platform_settings.py`
- Create: `apps/api/src/xtrusio_api/routes/platform_settings.py`
- Create: `apps/api/tests/routes/test_platform_settings.py`
- Modify: `apps/api/src/xtrusio_api/main.py`

- [ ] **Step 1: Write failing tests**

`apps/api/tests/routes/test_platform_settings.py`:

```python
"""Tests for GET/PUT /api/platform/settings."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_get_settings_unauthenticated(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/platform/settings")
    assert r.status_code == 401


async def test_get_settings_super_admin_returns_default(
    http_client: AsyncClient, super_admin_user: PlatformUser, make_jwt
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    r = await http_client.get(
        "/api/platform/settings", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["signups_enabled"] is False
    assert body["updated_by_email"] is None


async def test_put_settings_requires_super_admin(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
    # Create an admin (non-super) platform user.
    from uuid import uuid4

    from xtrusio_api.models.platform_user import PlatformRole, PlatformUser as PU

    user_id = uuid4()
    email = f"admin-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    db_session.add(PU(id=user_id, email=email, role=PlatformRole.ADMIN, is_active=True))
    await db_session.commit()

    try:
        token = make_jwt(sub=user_id)
        r = await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": True},
        )
        assert r.status_code == 403
    finally:
        await db_session.execute(text("DELETE FROM platform_users WHERE id = :id"), {"id": str(user_id)})
        await db_session.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
        await db_session.commit()


async def test_put_settings_happy_path(
    http_client: AsyncClient, super_admin_user: PlatformUser, make_jwt
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    r = await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["signups_enabled"] is True
    assert body["updated_by_email"] == super_admin_user.email
    # Restore to default for test isolation.
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": False},
    )
```

- [ ] **Step 2: Run tests, expect ImportError**

```bash
uv run --directory apps/api pytest tests/routes/test_platform_settings.py -v
```

- [ ] **Step 3: Implement the service**

`apps/api/src/xtrusio_api/services/platform_settings.py`:

```python
"""Read/write platform_settings."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.platform_settings import PlatformSettings
from ..models.platform_user import PlatformUser


async def get_settings(db: AsyncSession) -> tuple[PlatformSettings, str | None]:
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one()
    updated_by_email: str | None = None
    if row.updated_by is not None:
        updater = (
            await db.execute(select(PlatformUser).where(PlatformUser.id == row.updated_by))
        ).scalar_one_or_none()
        updated_by_email = updater.email if updater else None
    return row, updated_by_email


async def is_signups_enabled(db: AsyncSession) -> bool:
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one()
    return row.signups_enabled


async def update_settings(
    db: AsyncSession, *, signups_enabled: bool, updated_by: UUID
) -> tuple[PlatformSettings, str | None]:
    row = (await db.execute(select(PlatformSettings).where(PlatformSettings.id == 1))).scalar_one()
    row.signups_enabled = signups_enabled
    row.updated_by = updated_by
    await db.commit()
    await db.refresh(row)
    return await get_settings(db)
```

- [ ] **Step 4: Implement the route**

`apps/api/src/xtrusio_api/routes/platform_settings.py`:

```python
"""GET/PUT /api/platform/settings — super_admin only writes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user, require_super_admin
from ..core.db import get_db
from ..schemas.platform_settings import (
    PlatformSettingsResponse,
    UpdatePlatformSettingsRequest,
)
from ..services.platform_settings import get_settings, update_settings

router = APIRouter(prefix="/api/platform/settings", tags=["platform-settings"])


@router.get("", response_model=PlatformSettingsResponse)
async def read(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformSettingsResponse:
    row, email = await get_settings(db)
    return PlatformSettingsResponse(
        signups_enabled=row.signups_enabled,
        updated_at=row.updated_at,
        updated_by_email=email,
    )


@router.put("", response_model=PlatformSettingsResponse)
async def update(
    body: UpdatePlatformSettingsRequest,
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformSettingsResponse:
    row, email = await update_settings(
        db, signups_enabled=body.signups_enabled, updated_by=user.user_id
    )
    return PlatformSettingsResponse(
        signups_enabled=row.signups_enabled,
        updated_at=row.updated_at,
        updated_by_email=email,
    )
```

- [ ] **Step 5: Register router**

Modify `apps/api/src/xtrusio_api/main.py`:

```python
from .routes import me as me_routes
from .routes import platform_settings as platform_settings_routes
from .routes import tenants as tenants_routes

app = FastAPI(title="Xtrusio API", version="0.0.0")
app.include_router(me_routes.router)
app.include_router(tenants_routes.router)
app.include_router(platform_settings_routes.router)
```

- [ ] **Step 6: Run tests, expect PASS**

```bash
uv run --directory apps/api pytest tests/routes/test_platform_settings.py -v
```
All 4 tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/xtrusio_api/services/platform_settings.py \
        apps/api/src/xtrusio_api/routes/platform_settings.py \
        apps/api/src/xtrusio_api/main.py \
        apps/api/tests/routes/test_platform_settings.py
git commit -m "feat(api): GET/PUT /platform/settings (super_admin)"
```

---

## Task 6: Signup service + routes

**Files:**
- Create: `apps/api/src/xtrusio_api/services/signup.py`
- Create: `apps/api/src/xtrusio_api/routes/signup.py`
- Create: `apps/api/tests/routes/test_signup.py`
- Modify: `apps/api/src/xtrusio_api/main.py`
- Modify: `apps/api/tests/conftest.py` (add Supabase admin client fixture)

- [ ] **Step 1: Add a Supabase admin mock fixture**

Modify `apps/api/tests/conftest.py` — append to the file:

```python
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_supabase_admin(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Replace the supabase client factory so tests never hit the real API."""
    mock_client = MagicMock()
    mock_client.auth.admin = MagicMock()

    def _factory(*_args, **_kwargs) -> MagicMock:
        return mock_client

    monkeypatch.setattr("xtrusio_api.services.signup.create_client", _factory)
    yield mock_client
```

- [ ] **Step 2: Write failing tests**

`apps/api/tests/routes/test_signup.py`:

```python
"""Tests for /api/signup and /api/platform/signup-status."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_signup_status_default_false(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/platform/signup-status")
    assert r.status_code == 200
    assert r.json() == {"signups_enabled": False}


async def test_signup_disabled_returns_403(
    http_client: AsyncClient, mock_supabase_admin: MagicMock
) -> None:
    r = await http_client.post(
        "/api/signup", json={"email": "anon@example.com", "password": "Password1!"}
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "signups_disabled"
    mock_supabase_admin.auth.admin.create_user.assert_not_called()


async def test_signup_invalid_email_returns_422(
    http_client: AsyncClient, super_admin_user: PlatformUser, make_jwt
) -> None:
    # Toggle on first.
    token = make_jwt(sub=super_admin_user.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    try:
        r = await http_client.post(
            "/api/signup", json={"email": "not-an-email", "password": "Password1!"}
        )
        assert r.status_code == 422
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


async def test_signup_happy_path_calls_supabase(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    mock_supabase_admin.auth.admin.create_user.return_value = MagicMock(
        user=MagicMock(id="00000000-0000-0000-0000-000000000999")
    )
    try:
        r = await http_client.post(
            "/api/signup",
            json={"email": "newuser@example.com", "password": "Password1!"},
        )
        assert r.status_code == 202
        assert r.json() == {"state": "confirm_email_sent"}
        mock_supabase_admin.auth.admin.create_user.assert_called_once()
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )


async def test_signup_email_taken_returns_409(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    mock_supabase_admin: MagicMock,
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"signups_enabled": True},
    )
    mock_supabase_admin.auth.admin.create_user.side_effect = Exception("user already registered")
    try:
        r = await http_client.post(
            "/api/signup", json={"email": "taken@example.com", "password": "Password1!"}
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "email_taken"
    finally:
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {token}"},
            json={"signups_enabled": False},
        )
```

- [ ] **Step 3: Implement the service**

`apps/api/src/xtrusio_api/services/signup.py`:

```python
"""Signup orchestration: gate check + Supabase Admin user creation."""

from __future__ import annotations

import asyncio
from typing import Any

from supabase import create_client

from ..core.config import get_settings
from .platform_settings import is_signups_enabled

_SUPABASE_TIMEOUT = 10.0


class SignupsDisabledError(Exception):
    pass


class EmailTakenError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def create_signup_user(*, db: Any, email: str, password: str) -> str:
    """Create an unconfirmed Supabase auth user. Returns the user id."""
    if not await is_signups_enabled(db):
        raise SignupsDisabledError()

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> Any:
        return sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": False}
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call), timeout=_SUPABASE_TIMEOUT)
    except asyncio.TimeoutError as e:
        raise EmailProviderUnavailableError() from e
    except Exception as e:
        # supabase-py 2.x raises on duplicate email — string match is brittle but works for now.
        if "already" in str(e).lower():
            raise EmailTakenError() from e
        raise

    if result.user is None:
        raise EmailProviderUnavailableError()
    return str(result.user.id)
```

- [ ] **Step 4: Implement the route**

`apps/api/src/xtrusio_api/routes/signup.py`:

```python
"""POST /api/signup and GET /api/platform/signup-status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.db import get_db
from ..schemas.signup import SignupRequest, SignupResponse, SignupStatus
from ..services.platform_settings import is_signups_enabled
from ..services.signup import (
    EmailProviderUnavailableError,
    EmailTakenError,
    SignupsDisabledError,
    create_signup_user,
)

router = APIRouter(prefix="/api", tags=["signup"])


@router.get("/platform/signup-status", response_model=SignupStatus)
async def signup_status(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SignupStatus:
    return SignupStatus(signups_enabled=await is_signups_enabled(db))


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_202_ACCEPTED)
async def signup(
    body: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SignupResponse:
    try:
        await create_signup_user(db=db, email=body.email, password=body.password)
    except SignupsDisabledError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signups_disabled") from e
    except EmailTakenError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "email_taken") from e
    except EmailProviderUnavailableError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "email_provider_unavailable") from e
    return SignupResponse(state="confirm_email_sent")
```

- [ ] **Step 5: Register router**

Modify `apps/api/src/xtrusio_api/main.py`:

```python
from .routes import me as me_routes
from .routes import platform_settings as platform_settings_routes
from .routes import signup as signup_routes
from .routes import tenants as tenants_routes

app.include_router(signup_routes.router)
```

- [ ] **Step 6: Run tests**

```bash
uv run --directory apps/api pytest tests/routes/test_signup.py -v
```
All 5 tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/xtrusio_api/services/signup.py \
        apps/api/src/xtrusio_api/routes/signup.py \
        apps/api/src/xtrusio_api/main.py \
        apps/api/tests/conftest.py \
        apps/api/tests/routes/test_signup.py
git commit -m "feat(api): public signup with platform-settings gate"
```

---

## Task 7: Onboarding service + route

**Files:**
- Create: `apps/api/src/xtrusio_api/services/onboarding.py`
- Create: `apps/api/src/xtrusio_api/routes/onboarding.py`
- Create: `apps/api/tests/routes/test_onboarding.py`
- Modify: `apps/api/src/xtrusio_api/main.py`

- [ ] **Step 1: Write failing tests**

`apps/api/tests/routes/test_onboarding.py`:

```python
"""Tests for POST /api/onboarding/tenants."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _make_unprovisioned_user(db: AsyncSession) -> tuple:
    user_id = uuid4()
    email = f"new-{user_id.hex[:8]}@example.com"
    await db.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db.commit()
    return user_id, email


async def _cleanup_user(db: AsyncSession, user_id) -> None:
    await db.execute(
        text(
            "DELETE FROM tenant_memberships WHERE user_id = :id; "
            "DELETE FROM tenants WHERE created_by = :id; "
            "DELETE FROM auth.users WHERE id = :id"
        ),
        {"id": str(user_id)},
    )
    await db.commit()


async def test_onboarding_unauth_returns_401(http_client: AsyncClient) -> None:
    r = await http_client.post("/api/onboarding/tenants", json={"workspace_name": "Acme Corp"})
    assert r.status_code == 401


async def test_onboarding_happy_path(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    user_id, email = await _make_unprovisioned_user(db_session)
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "Acme Corp"},
        )
        # Note: get_current_user requires a platform_users row — for tenant onboarding
        # we need a different auth dep. See routes/onboarding.py for require_authenticated.
        assert r.status_code == 201
        body = r.json()
        assert body["tenant"]["slug"] == "acme-corp"
        assert body["tenant"]["name"] == "Acme Corp"
        assert body["tenant"]["role"] == "owner"
    finally:
        await _cleanup_user(db_session, user_id)


async def test_onboarding_slug_collision_appends_suffix(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    # Pre-create a tenant with the colliding slug.
    user_id_a, _ = await _make_unprovisioned_user(db_session)
    user_id_b, _ = await _make_unprovisioned_user(db_session)
    try:
        token_a = make_jwt(sub=user_id_a)
        await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token_a}"},
            json={"workspace_name": "Acme Corp"},
        )
        token_b = make_jwt(sub=user_id_b)
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"workspace_name": "Acme Corp"},
        )
        assert r.status_code == 201
        assert r.json()["tenant"]["slug"] == "acme-corp-2"
    finally:
        await _cleanup_user(db_session, user_id_a)
        await _cleanup_user(db_session, user_id_b)


async def test_onboarding_already_has_membership_returns_409(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    user_id, _ = await _make_unprovisioned_user(db_session)
    try:
        token = make_jwt(sub=user_id)
        await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "First Workspace"},
        )
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "Second Workspace"},
        )
        assert r.status_code == 409
        assert r.json()["detail"] == "already_has_membership"
    finally:
        await _cleanup_user(db_session, user_id)
```

- [ ] **Step 2: Add a require_authenticated dep that does NOT require platform_users row**

The existing `get_current_user` 401s when a user has no `platform_users` row. Onboarding is called by users who haven't been provisioned yet. We need a softer dep.

Modify `apps/api/src/xtrusio_api/core/auth.py` — add (after the existing functions):

```python
@dataclass
class AuthIdentity:
    user_id: UUID
    email: str


async def require_authenticated(
    db: Annotated[AsyncSession, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> AuthIdentity:
    """JWT-validated identity. Does NOT require a platform_users row."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(
            token,
            get_settings().supabase_jwt_secret,
            algorithms=[_ALGO],
            audience=_AUDIENCE,
        )
    except JWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token missing sub")
    try:
        user_id = UUID(sub)
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid sub") from e
    # Look up email from auth.users (no platform_users requirement).
    from sqlalchemy import text  # local import to avoid top-level churn

    row = (
        await db.execute(
            text("SELECT email FROM auth.users WHERE id = :id"), {"id": str(user_id)}
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not in auth.users")
    return AuthIdentity(user_id=user_id, email=row[0])
```

- [ ] **Step 3: Implement the onboarding service**

`apps/api/src/xtrusio_api/services/onboarding.py`:

```python
"""Onboarding: create a tenant + owner membership atomically."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.tenant import Tenant
from ..models.tenant_membership import TenantMembership, TenantRole
from .slug import slugify, unique_slug_from_taken


class AlreadyHasMembershipError(Exception):
    pass


async def create_tenant_with_owner(
    db: AsyncSession, *, user_id: UUID, workspace_name: str
) -> Tenant:
    existing = (
        await db.execute(select(TenantMembership).where(TenantMembership.user_id == user_id))
    ).scalar_one_or_none()
    if existing is not None:
        raise AlreadyHasMembershipError()

    base = slugify(workspace_name)
    taken = {
        row.slug
        for row in (await db.execute(select(Tenant.slug).where(Tenant.slug.like(f"{base}%"))))
        .scalars()
        .all()
    }
    slug = unique_slug_from_taken(base, taken)

    tenant = Tenant(slug=slug, name=workspace_name, created_by=user_id)
    db.add(tenant)
    try:
        await db.flush()  # gets server-generated id
    except IntegrityError:
        await db.rollback()
        raise

    db.add(TenantMembership(tenant_id=tenant.id, user_id=user_id, role=TenantRole.OWNER))
    await db.commit()
    await db.refresh(tenant)
    return tenant
```

- [ ] **Step 4: Implement the route**

`apps/api/src/xtrusio_api/routes/onboarding.py`:

```python
"""POST /api/onboarding/tenants — provisions a fresh signup into a new tenant."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..models.tenant_membership import TenantRole
from ..schemas.onboarding import CreatedTenant, CreateTenantRequest, CreateTenantResponse
from ..services.onboarding import AlreadyHasMembershipError, create_tenant_with_owner

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


@router.post(
    "/tenants", response_model=CreateTenantResponse, status_code=status.HTTP_201_CREATED
)
async def onboard(
    body: CreateTenantRequest,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreateTenantResponse:
    try:
        tenant = await create_tenant_with_owner(
            db, user_id=identity.user_id, workspace_name=body.workspace_name
        )
    except AlreadyHasMembershipError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_has_membership") from e
    return CreateTenantResponse(
        tenant=CreatedTenant(
            id=tenant.id, slug=tenant.slug, name=tenant.name, role=TenantRole.OWNER
        )
    )
```

- [ ] **Step 5: Register router**

Modify `apps/api/src/xtrusio_api/main.py`:

```python
from .routes import onboarding as onboarding_routes
# ...
app.include_router(onboarding_routes.router)
```

- [ ] **Step 6: Run tests**

```bash
uv run --directory apps/api pytest tests/routes/test_onboarding.py -v
```
All 4 tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/xtrusio_api/services/onboarding.py \
        apps/api/src/xtrusio_api/routes/onboarding.py \
        apps/api/src/xtrusio_api/core/auth.py \
        apps/api/src/xtrusio_api/main.py \
        apps/api/tests/routes/test_onboarding.py
git commit -m "feat(api): onboarding endpoint — creates tenant + owner membership"
```

---

## Task 8: Extended `/me` response

**Files:**
- Modify: `apps/api/src/xtrusio_api/routes/me.py`
- Modify: `apps/api/tests/routes/test_me.py` (existing file)

- [ ] **Step 1: Update tests to assert new response shape**

Read existing `apps/api/tests/routes/test_me.py` first. Then rewrite to cover:
- super_admin returns `{platform: {role:super_admin}, tenants:[], pending_invite: null}`
- tenant_member returns `{platform: null, tenants:[{slug, role:owner}], pending_invite: null}`
- unprovisioned user returns `{platform: null, tenants:[], pending_invite: null}`

`apps/api/tests/routes/test_me.py`:

```python
"""Tests for GET /api/me — composite identity response."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_me_unauth_returns_401(http_client: AsyncClient) -> None:
    r = await http_client.get("/api/me")
    assert r.status_code == 401


async def test_me_super_admin(
    http_client: AsyncClient, super_admin_user: PlatformUser, make_jwt
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == super_admin_user.email
    assert body["platform"]["role"] == "super_admin"
    assert body["tenants"] == []
    assert body["pending_invite"] is None


async def test_me_tenant_member(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    from uuid import uuid4

    user_id = uuid4()
    email = f"member-{user_id.hex[:8]}@example.com"
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    await db_session.execute(
        text(
            "INSERT INTO tenants (slug, name, created_by) VALUES "
            "(:slug, :name, :uid) RETURNING id"
        ),
        {"slug": f"t-{user_id.hex[:8]}", "name": "T", "uid": str(user_id)},
    )
    await db_session.execute(
        text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
            "SELECT id, :uid, 'owner' FROM tenants WHERE created_by = :uid"
        ),
        {"uid": str(user_id)},
    )
    await db_session.commit()
    try:
        token = make_jwt(sub=user_id)
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["platform"] is None
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["role"] == "owner"
        assert body["tenants"][0]["slug"] == f"t-{user_id.hex[:8]}"
        assert body["pending_invite"] is None
    finally:
        await db_session.execute(
            text(
                "DELETE FROM tenant_memberships WHERE user_id = :id; "
                "DELETE FROM tenants WHERE created_by = :id; "
                "DELETE FROM auth.users WHERE id = :id"
            ),
            {"id": str(user_id)},
        )
        await db_session.commit()


async def test_me_unprovisioned(
    http_client: AsyncClient, db_session: AsyncSession, make_jwt
) -> None:
    from uuid import uuid4

    user_id = uuid4()
    email = f"unprov-{user_id.hex[:8]}@example.com"
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
        token = make_jwt(sub=user_id)
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["platform"] is None
        assert body["tenants"] == []
        assert body["pending_invite"] is None
    finally:
        await db_session.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
        await db_session.commit()
```

- [ ] **Step 2: Rewrite the route**

`apps/api/src/xtrusio_api/routes/me.py`:

```python
"""GET /api/me — composite identity for the frontend AuthGuard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import AuthIdentity, require_authenticated
from ..core.db import get_db
from ..models.platform_user import PlatformUser
from ..models.tenant import Tenant
from ..models.tenant_membership import TenantMembership
from ..schemas.me import MeResponse, PlatformContext, TenantContext

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=MeResponse)
async def me(
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MeResponse:
    pu = (
        await db.execute(select(PlatformUser).where(PlatformUser.id == identity.user_id))
    ).scalar_one_or_none()
    platform = None
    if pu is not None and pu.is_active:
        platform = PlatformContext(role=pu.role, is_active=pu.is_active)

    rows = (
        await db.execute(
            select(TenantMembership, Tenant)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(TenantMembership.user_id == identity.user_id)
            .order_by(Tenant.created_at.desc())
        )
    ).all()
    tenants = [
        TenantContext(id=t.id, slug=t.slug, name=t.name, role=m.role) for m, t in rows
    ]

    # pending_invite — populated in Plan 2B when invite metadata is read from JWT claims.
    return MeResponse(
        user_id=identity.user_id,
        email=identity.email,
        platform=platform,
        tenants=tenants,
        pending_invite=None,
    )
```

- [ ] **Step 3: Run tests**

```bash
uv run --directory apps/api pytest tests/routes/test_me.py -v
```
All 4 tests pass.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/me.py apps/api/tests/routes/test_me.py
git commit -m "feat(api): /me returns composite identity (platform + tenants + pending_invite)"
```

---

## Task 9: RLS tests

**Files:**
- Create: `apps/api/tests/rls/__init__.py` (empty)
- Create: `apps/api/tests/rls/conftest.py`
- Create: `apps/api/tests/rls/test_platform_settings_rls.py`
- Create: `apps/api/tests/rls/test_tenant_memberships_rls.py`
- Create: `apps/api/tests/rls/test_tenants_rls.py`

- [ ] **Step 1: RLS conftest — helper to execute as authenticated role with a jwt claim**

`apps/api/tests/rls/conftest.py`:

```python
"""RLS test helpers — run queries as the `authenticated` role with a synthetic auth.uid()."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from xtrusio_api.core.db import SessionLocal


@asynccontextmanager
async def as_user(user_id: UUID) -> AsyncIterator[AsyncSession]:
    """Execute statements as `authenticated` with auth.uid() returning user_id."""
    async with SessionLocal() as s:
        await s.execute(
            text(
                "SELECT set_config('request.jwt.claims', "
                ":claims, true), set_config('role', 'authenticated', true)"
            ),
            {"claims": '{"sub": "' + str(user_id) + '", "role": "authenticated"}'},
        )
        await s.execute(text("SET LOCAL ROLE authenticated"))
        try:
            yield s
        finally:
            await s.rollback()


@pytest_asyncio.fixture
async def rls_as() -> Callable:  # type: ignore[type-arg]
    return as_user
```

- [ ] **Step 2: platform_settings RLS test**

`apps/api/tests/rls/test_platform_settings_rls.py`:

```python
"""platform_settings RLS — non-super_admin cannot UPDATE; everyone can SELECT."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_authenticated_can_read(rls_as, super_admin_user: PlatformUser) -> None:
    # Use the super admin's id as our authenticated principal, but any auth.users id works.
    async with rls_as(super_admin_user.id) as s:
        rows = (await s.execute(text("SELECT signups_enabled FROM platform_settings"))).all()
        assert len(rows) == 1


async def test_non_super_admin_update_silently_blocked(
    rls_as, super_admin_user: PlatformUser
) -> None:
    # Make a plain auth.users row with no platform_users entry (i.e. unprovisioned).
    from uuid import uuid4

    user_id = uuid4()
    async with rls_as(super_admin_user.id) as s:
        # First, escape RLS to seed: use service_role implicitly (we're still in the same session
        # but we haven't SET ROLE yet at the outer connection — quick hack: open a fresh session).
        pass
    from xtrusio_api.core.db import SessionLocal
    async with SessionLocal() as priv:
        await priv.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(user_id), "email": f"x-{user_id.hex[:8]}@example.com"},
        )
        await priv.commit()
    try:
        async with rls_as(user_id) as s:
            res = await s.execute(
                text("UPDATE platform_settings SET signups_enabled = true WHERE id = 1")
            )
            assert res.rowcount == 0  # RLS makes the row invisible to UPDATE.
    finally:
        async with SessionLocal() as priv:
            await priv.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": str(user_id)})
            await priv.commit()


async def test_super_admin_can_update(rls_as, super_admin_user: PlatformUser) -> None:
    async with rls_as(super_admin_user.id) as s:
        res = await s.execute(
            text("UPDATE platform_settings SET signups_enabled = true WHERE id = 1")
        )
        assert res.rowcount == 1
```

- [ ] **Step 3: tenant_memberships RLS test**

`apps/api/tests/rls/test_tenant_memberships_rls.py`:

```python
"""tenant_memberships RLS — self-read, super_admin all, owner/admin manage own tenant."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def _seed_tenant_with_owner(name_suffix: str) -> tuple:
    owner_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(owner_id), "email": f"o-{name_suffix}@example.com"},
        )
        await s.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
            {"slug": f"t-{name_suffix}", "name": f"Tenant {name_suffix}", "uid": str(owner_id)},
        )
        tid = (
            await s.execute(
                text("SELECT id FROM tenants WHERE slug = :slug"), {"slug": f"t-{name_suffix}"}
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:tid, :uid, 'owner')"
            ),
            {"tid": str(tid), "uid": str(owner_id)},
        )
        await s.commit()
    return owner_id, tid


async def _cleanup(user_id) -> None:
    async with SessionLocal() as s:
        await s.execute(
            text(
                "DELETE FROM tenant_memberships WHERE user_id = :id; "
                "DELETE FROM tenants WHERE created_by = :id; "
                "DELETE FROM auth.users WHERE id = :id"
            ),
            {"id": str(user_id)},
        )
        await s.commit()


async def test_user_sees_own_membership_not_others(rls_as) -> None:
    a_id, _ = await _seed_tenant_with_owner("a")
    b_id, _ = await _seed_tenant_with_owner("b")
    try:
        async with rls_as(a_id) as s:
            rows = (await s.execute(text("SELECT user_id FROM tenant_memberships"))).all()
        seen = {str(r[0]) for r in rows}
        assert str(a_id) in seen
        assert str(b_id) not in seen
    finally:
        await _cleanup(a_id)
        await _cleanup(b_id)


async def test_super_admin_sees_all(rls_as, super_admin_user: PlatformUser) -> None:
    a_id, _ = await _seed_tenant_with_owner("sa-a")
    try:
        async with rls_as(super_admin_user.id) as s:
            rows = (await s.execute(text("SELECT user_id FROM tenant_memberships"))).all()
        seen = {str(r[0]) for r in rows}
        assert str(a_id) in seen
    finally:
        await _cleanup(a_id)
```

- [ ] **Step 4: tenants RLS regression**

`apps/api/tests/rls/test_tenants_rls.py`:

```python
"""tenants RLS — member can SELECT own tenant; super_admin sees all (regression on 0001)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from xtrusio_api.core.db import SessionLocal
from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_member_sees_only_their_tenants(rls_as) -> None:
    from uuid import uuid4

    a_id = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(a_id), "email": f"m-{a_id.hex[:8]}@example.com"},
        )
        await s.execute(
            text("INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"),
            {"slug": f"own-{a_id.hex[:8]}", "name": "Own", "uid": str(a_id)},
        )
        tid = (
            await s.execute(
                text("SELECT id FROM tenants WHERE slug = :slug"),
                {"slug": f"own-{a_id.hex[:8]}"},
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO tenant_memberships (tenant_id, user_id, role) "
                "VALUES (:tid, :uid, 'owner')"
            ),
            {"tid": str(tid), "uid": str(a_id)},
        )
        # Decoy tenant the user has no membership in.
        await s.execute(
            text(
                "INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"
            ),
            {"slug": f"decoy-{a_id.hex[:8]}", "name": "Decoy", "uid": str(a_id)},
        )
        await s.commit()
    try:
        async with rls_as(a_id) as s:
            rows = (await s.execute(text("SELECT slug FROM tenants ORDER BY slug"))).all()
        slugs = {r[0] for r in rows}
        assert f"own-{a_id.hex[:8]}" in slugs
        assert f"decoy-{a_id.hex[:8]}" not in slugs
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "DELETE FROM tenant_memberships WHERE user_id = :id; "
                    "DELETE FROM tenants WHERE created_by = :id; "
                    "DELETE FROM auth.users WHERE id = :id"
                ),
                {"id": str(a_id)},
            )
            await priv.commit()


async def test_super_admin_sees_all_tenants(rls_as, super_admin_user: PlatformUser) -> None:
    from uuid import uuid4

    decoy_owner = uuid4()
    async with SessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
                "email_confirmed_at, created_at, updated_at) VALUES "
                "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
                ":email, '', now(), now(), now())"
            ),
            {"id": str(decoy_owner), "email": f"dec-{decoy_owner.hex[:8]}@example.com"},
        )
        await s.execute(
            text(
                "INSERT INTO tenants (slug, name, created_by) VALUES (:slug, :name, :uid)"
            ),
            {"slug": f"sa-decoy-{decoy_owner.hex[:8]}", "name": "Decoy", "uid": str(decoy_owner)},
        )
        await s.commit()
    try:
        async with rls_as(super_admin_user.id) as s:
            rows = (await s.execute(text("SELECT slug FROM tenants"))).all()
        slugs = {r[0] for r in rows}
        assert f"sa-decoy-{decoy_owner.hex[:8]}" in slugs
    finally:
        async with SessionLocal() as priv:
            await priv.execute(
                text(
                    "DELETE FROM tenants WHERE created_by = :id; "
                    "DELETE FROM auth.users WHERE id = :id"
                ),
                {"id": str(decoy_owner)},
            )
            await priv.commit()
```

- [ ] **Step 5: Run all RLS tests**

```bash
uv run --directory apps/api pytest tests/rls/ -v
```
All tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/tests/rls/
git commit -m "test(rls): platform_settings, tenant_memberships, tenants policies"
```

---

## Task 10: Integration test — signup → onboarding flow

**Files:**
- Create: `apps/api/tests/integration/__init__.py` (empty)
- Create: `apps/api/tests/integration/test_signup_to_tenant_flow.py`

- [ ] **Step 1: Write the integration test**

`apps/api/tests/integration/test_signup_to_tenant_flow.py`:

```python
"""End-to-end: super_admin enables signup → anon signs up → simulated email confirm
→ unprovisioned user calls /me → posts /onboarding/tenants → becomes owner."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xtrusio_api.models.platform_user import PlatformUser

pytestmark = pytest.mark.asyncio


async def test_signup_to_tenant_flow(
    http_client: AsyncClient,
    super_admin_user: PlatformUser,
    make_jwt,
    db_session: AsyncSession,
    mock_supabase_admin: MagicMock,
) -> None:
    # 1. super_admin enables signups.
    sa_token = make_jwt(sub=super_admin_user.id)
    r = await http_client.put(
        "/api/platform/settings",
        headers={"Authorization": f"Bearer {sa_token}"},
        json={"signups_enabled": True},
    )
    assert r.status_code == 200

    # 2. Anon signs up. We pre-allocate the user id so we can simulate the confirm.
    user_id = uuid4()
    mock_supabase_admin.auth.admin.create_user.return_value = MagicMock(
        user=MagicMock(id=str(user_id))
    )
    r = await http_client.post(
        "/api/signup",
        json={"email": f"e2e-{user_id.hex[:8]}@example.com", "password": "Password1!"},
    )
    assert r.status_code == 202

    # 3. Simulate email confirmation: insert into auth.users with a confirmed timestamp.
    email = f"e2e-{user_id.hex[:8]}@example.com"
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
        # 4. User authenticates, /me reports unprovisioned.
        token = make_jwt(sub=user_id)
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        me = r.json()
        assert me["platform"] is None
        assert me["tenants"] == []

        # 5. Onboarding.
        r = await http_client.post(
            "/api/onboarding/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json={"workspace_name": "End to End Co"},
        )
        assert r.status_code == 201
        assert r.json()["tenant"]["role"] == "owner"

        # 6. /me now shows them as tenant owner.
        r = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        body = r.json()
        assert len(body["tenants"]) == 1
        assert body["tenants"][0]["role"] == "owner"
    finally:
        await db_session.execute(
            text(
                "DELETE FROM tenant_memberships WHERE user_id = :id; "
                "DELETE FROM tenants WHERE created_by = :id; "
                "DELETE FROM auth.users WHERE id = :id"
            ),
            {"id": str(user_id)},
        )
        await http_client.put(
            "/api/platform/settings",
            headers={"Authorization": f"Bearer {sa_token}"},
            json={"signups_enabled": False},
        )
        await db_session.commit()
```

- [ ] **Step 2: Run the integration test**

```bash
uv run --directory apps/api pytest tests/integration/ -v
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/integration/
git commit -m "test(integration): signup → confirm → onboarding happy path"
```

---

## Task 11: Frontend error-messages map (pure)

**Files:**
- Create: `apps/web/src/lib/error-messages.ts`
- Create: `apps/web/src/lib/error-messages.test.ts`

- [ ] **Step 1: Write failing tests**

`apps/web/src/lib/error-messages.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { errorMessage } from "./error-messages";

describe("errorMessage", () => {
  it("returns the mapped string for known codes", () => {
    expect(errorMessage("signups_disabled")).toMatch(/disabled/i);
    expect(errorMessage("email_taken")).toMatch(/already/i);
    expect(errorMessage("already_has_membership")).toMatch(/workspace/i);
  });

  it("falls back to a generic string for unknown codes", () => {
    expect(errorMessage("not_a_real_code")).toMatch(/something/i);
  });
});
```

- [ ] **Step 2: Run, expect fail**

```bash
pnpm --filter @xtrusio/web test src/lib/error-messages.test.ts
```

- [ ] **Step 3: Implement**

`apps/web/src/lib/error-messages.ts`:

```typescript
const MESSAGES: Record<string, string> = {
  signups_disabled: "Signups are currently disabled.",
  email_taken: "An account with that email already exists.",
  invalid_email: "That email address doesn't look valid.",
  weak_password: "Password must be at least 8 characters.",
  already_has_membership: "You're already in a workspace.",
  workspace_name_invalid: "Workspace name must be 2-200 characters.",
  email_provider_unavailable:
    "Couldn't send the email. Please try again in a moment.",
  no_invite: "We couldn't find an invitation for your account.",
  invite_expired: "This invitation has expired.",
  invite_revoked: "This invitation was revoked.",
  invite_already_accepted: "This invitation has already been accepted.",
  email_mismatch: "This invitation was for a different email address.",
};

export function errorMessage(code: string): string {
  return MESSAGES[code] ?? "Something went wrong. Please try again.";
}
```

- [ ] **Step 4: Run, expect pass**

```bash
pnpm --filter @xtrusio/web test src/lib/error-messages.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/error-messages.ts apps/web/src/lib/error-messages.test.ts
git commit -m "feat(web): error-message lookup with fallback"
```

---

## Task 12: Frontend route-resolver (pure)

**Files:**
- Create: `apps/web/src/lib/route-resolver.ts`
- Create: `apps/web/src/lib/route-resolver.test.ts`

- [ ] **Step 1: Write failing tests**

`apps/web/src/lib/route-resolver.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { resolveRoute, type MeResponse } from "./route-resolver";

const unprov: MeResponse = {
  user_id: "u",
  email: "x@x.com",
  platform: null,
  tenants: [],
  pending_invite: null,
};
const sa: MeResponse = { ...unprov, platform: { role: "super_admin", is_active: true } };
const tenant: MeResponse = {
  ...unprov,
  tenants: [{ id: "t", slug: "acme", name: "Acme", role: "owner" }],
};
const pending: MeResponse = {
  ...unprov,
  pending_invite: { kind: "tenant", id: "i", tenant_id: "t", role: "admin" },
};

describe("resolveRoute", () => {
  it("redirects unauth to /sign-in", () => {
    expect(resolveRoute({ session: null, me: null }, "/")).toEqual({ kind: "redirect", to: "/sign-in" });
  });
  it("allows /sign-up when unauth", () => {
    expect(resolveRoute({ session: null, me: null }, "/sign-up")).toEqual({ kind: "render" });
  });
  it("pending invite forces /accept-invite", () => {
    expect(resolveRoute({ session: "s", me: pending }, "/")).toEqual({
      kind: "redirect",
      to: "/accept-invite",
    });
  });
  it("super_admin can navigate platform routes", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/settings")).toEqual({ kind: "render" });
  });
  it("tenant_member redirected away from /settings", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/settings")).toEqual({
      kind: "redirect",
      to: "/",
    });
  });
  it("unprovisioned forced to /onboarding", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/")).toEqual({
      kind: "redirect",
      to: "/onboarding",
    });
  });
  it("unprovisioned on /onboarding renders", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/onboarding")).toEqual({
      kind: "render",
    });
  });
});
```

- [ ] **Step 2: Run, expect fail**

```bash
pnpm --filter @xtrusio/web test src/lib/route-resolver.test.ts
```

- [ ] **Step 3: Implement**

`apps/web/src/lib/route-resolver.ts`:

```typescript
export type MeResponse = {
  user_id: string;
  email: string;
  platform: { role: "super_admin" | "admin" | "editor"; is_active: boolean } | null;
  tenants: { id: string; slug: string; name: string; role: "owner" | "admin" | "editor" | "read_only" }[];
  pending_invite:
    | { kind: "platform" | "tenant"; id: string; tenant_id: string | null; role: string }
    | null;
};

export type AuthState = { session: string | null; me: MeResponse | null };
export type RouteDecision = { kind: "render" } | { kind: "redirect"; to: string };

const PLATFORM_ONLY = new Set(["/settings", "/users"]);
const PUBLIC = new Set(["/sign-in", "/sign-up"]);

export function resolveRoute(state: AuthState, path: string): RouteDecision {
  if (!state.session) {
    return PUBLIC.has(path) ? { kind: "render" } : { kind: "redirect", to: "/sign-in" };
  }
  if (!state.me) return { kind: "render" }; // spinner is rendered by the caller while /me loads

  const { platform, tenants, pending_invite } = state.me;

  if (pending_invite) {
    return path === "/accept-invite"
      ? { kind: "render" }
      : { kind: "redirect", to: "/accept-invite" };
  }

  if (platform) return { kind: "render" };

  if (tenants.length > 0) {
    return PLATFORM_ONLY.has(path) ? { kind: "redirect", to: "/" } : { kind: "render" };
  }

  // Unprovisioned.
  return path === "/onboarding"
    ? { kind: "render" }
    : { kind: "redirect", to: "/onboarding" };
}
```

- [ ] **Step 4: Run, expect pass**

```bash
pnpm --filter @xtrusio/web test src/lib/route-resolver.test.ts
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/route-resolver.ts apps/web/src/lib/route-resolver.test.ts
git commit -m "feat(web): pure resolveRoute function for AuthGuard state machine"
```

---

## Task 13: Frontend api.ts wrappers

**Files:**
- Modify: `apps/web/src/lib/api.ts` (already exists; extend)

- [ ] **Step 1: Read existing `api.ts`**

Read the file. Confirm `apiFetch` exists. We're adding typed wrappers.

- [ ] **Step 2: Append the wrappers**

Append to `apps/web/src/lib/api.ts`:

```typescript
import type { MeResponse } from "./route-resolver";

export async function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/me");
}

export async function fetchSignupStatus(): Promise<{ signups_enabled: boolean }> {
  return apiFetch("/api/platform/signup-status");
}

export async function postSignup(email: string, password: string): Promise<void> {
  await apiFetch("/api/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function postOnboarding(workspace_name: string): Promise<{
  tenant: { id: string; slug: string; name: string; role: string };
}> {
  return apiFetch("/api/onboarding/tenants", {
    method: "POST",
    body: JSON.stringify({ workspace_name }),
  });
}

export async function fetchPlatformSettings(): Promise<{
  signups_enabled: boolean;
  updated_at: string;
  updated_by_email: string | null;
}> {
  return apiFetch("/api/platform/settings");
}

export async function putPlatformSettings(signups_enabled: boolean): Promise<{
  signups_enabled: boolean;
}> {
  return apiFetch("/api/platform/settings", {
    method: "PUT",
    body: JSON.stringify({ signups_enabled }),
  });
}
```

- [ ] **Step 3: Typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): api wrappers for signup, onboarding, /me, settings"
```

---

## Task 14: AuthGuard rewrite

**Files:**
- Modify: `apps/web/src/components/auth-guard.tsx` (full rewrite)
- Create: `apps/web/src/components/auth-guard.test.tsx`

- [ ] **Step 1: Write the failing test**

`apps/web/src/components/auth-guard.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthGuard } from "./auth-guard";
import { AuthProvider } from "../lib/auth";

const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useRouter: () => ({ state: { location: { pathname: "/" } }, navigate: navigateMock }),
  useNavigate: () => navigateMock,
  Outlet: () => <div data-testid="outlet" />,
}));

vi.mock("../lib/api", () => ({
  fetchMe: vi.fn(),
}));

import { fetchMe } from "../lib/api";

describe("AuthGuard", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    vi.mocked(fetchMe).mockReset();
  });
  afterEach(() => vi.restoreAllMocks());

  it("redirects unprovisioned user to /onboarding", async () => {
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u",
      email: "x@x.com",
      platform: null,
      tenants: [],
      pending_invite: null,
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // We rely on AuthProvider seeding a fake session for this test; in practice
    // the AuthProvider reads from supabase-js. For the unit-level test we mock
    // supabase via setupTests; see __mocks__ for the helper.
    render(
      <QueryClientProvider client={qc}>
        <AuthProvider>
          <AuthGuard>
            <div>inner</div>
          </AuthGuard>
        </AuthProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/onboarding" }));
  });
});
```

(The test above relies on a Supabase mock at the AuthProvider boundary. The simpler path is to test `resolveRoute` (Task 12) and treat AuthGuard as wiring. A single integration-style test covering one path is enough; we already covered the pure logic.)

- [ ] **Step 2: Implement AuthGuard**

`apps/web/src/components/auth-guard.tsx` (full rewrite):

```tsx
import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useRouter } from "@tanstack/react-router";
import { useAuth } from "../lib/auth";
import { fetchMe } from "../lib/api";
import { resolveRoute } from "../lib/route-resolver";

export function AuthGuard({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const router = useRouter();
  const navigate = useNavigate();
  const pathname = router.state.location.pathname;

  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !!auth.session,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });

  const decision = resolveRoute(
    { session: auth.session ? "s" : null, me: me ?? null },
    pathname,
  );

  useEffect(() => {
    if (decision.kind === "redirect" && pathname !== decision.to) {
      navigate({ to: decision.to });
    }
  }, [decision, pathname, navigate]);

  if (auth.loading || (auth.session && meLoading)) {
    return <div className="grid min-h-screen place-items-center text-muted-foreground">Loading…</div>;
  }
  if (decision.kind === "redirect") return null;
  return <>{children}</>;
}
```

- [ ] **Step 3: Run frontend tests + typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test src/components/auth-guard.test.tsx
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/auth-guard.tsx apps/web/src/components/auth-guard.test.tsx
git commit -m "feat(web): AuthGuard state machine driven by /me"
```

---

## Task 15: `/sign-up` page

**Files:**
- Create: `apps/web/src/routes/sign-up.tsx`
- Create: `apps/web/src/routes/sign-up.test.tsx`

- [ ] **Step 1: Failing test**

`apps/web/src/routes/sign-up.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SignUpPage } from "./sign-up";

vi.mock("../lib/api", () => ({
  fetchSignupStatus: vi.fn(),
  postSignup: vi.fn(),
}));

import { fetchSignupStatus, postSignup } from "../lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SignUpPage />
    </QueryClientProvider>,
  );
}

describe("SignUpPage", () => {
  beforeEach(() => {
    vi.mocked(fetchSignupStatus).mockReset();
    vi.mocked(postSignup).mockReset();
  });

  it("renders disabled message when signups_enabled=false", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: false });
    renderPage();
    await waitFor(() => expect(screen.getByText(/signups are currently disabled/i)).toBeTruthy());
  });

  it("renders form when enabled, submits, shows confirmation screen", async () => {
    vi.mocked(fetchSignupStatus).mockResolvedValue({ signups_enabled: true });
    vi.mocked(postSignup).mockResolvedValue(undefined);
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByLabelText(/email/i));
    await user.type(screen.getByLabelText(/email/i), "alice@example.com");
    await user.type(screen.getByLabelText(/password/i), "Password1!");
    await user.click(screen.getByRole("button", { name: /sign up/i }));
    await waitFor(() => expect(screen.getByText(/check your email/i)).toBeTruthy());
    expect(postSignup).toHaveBeenCalledWith("alice@example.com", "Password1!");
  });
});
```

- [ ] **Step 2: Run, expect fail**

```bash
pnpm --filter @xtrusio/web test src/routes/sign-up.test.tsx
```

- [ ] **Step 3: Implement**

`apps/web/src/routes/sign-up.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { fetchSignupStatus, postSignup } from "../lib/api";
import { errorMessage } from "../lib/error-messages";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

function SignUpPage() {
  const { data: status, isLoading } = useQuery({
    queryKey: ["signup-status"],
    queryFn: fetchSignupStatus,
  });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const m = useMutation({
    mutationFn: () => postSignup(email, password),
    onSuccess: () => setSubmitted(true),
  });

  if (isLoading) return null;
  if (status && !status.signups_enabled) {
    return (
      <main className="grid min-h-screen place-items-center px-6">
        <div className="max-w-md text-center text-muted-foreground">
          Signups are currently disabled. Contact your administrator for an invitation.
        </div>
      </main>
    );
  }
  if (submitted) {
    return (
      <main className="grid min-h-screen place-items-center px-6">
        <div className="max-w-md text-center">
          <h1 className="text-2xl font-semibold">Check your email</h1>
          <p className="mt-2 text-muted-foreground">
            We've sent a confirmation link to <strong>{email}</strong>.
          </p>
        </div>
      </main>
    );
  }
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="text-2xl font-semibold">Create your account</h1>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {m.error ? (
          <p className="text-sm text-destructive">{errorMessage((m.error as Error).message)}</p>
        ) : null}
        <Button type="submit" className="w-full" disabled={m.isPending}>
          {m.isPending ? "Submitting…" : "Sign up"}
        </Button>
      </form>
    </main>
  );
}

export const Route = createFileRoute("/sign-up")({ component: SignUpPage });
export { SignUpPage };
```

- [ ] **Step 4: Regenerate TanStack route tree**

```bash
pnpm --filter @xtrusio/web dev &
sleep 3
kill %1 2>/dev/null || true
```
(The Vite plugin regenerates `routeTree.gen.ts` on dev server start.)

- [ ] **Step 5: Run tests + typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test src/routes/sign-up.test.tsx
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/routes/sign-up.tsx apps/web/src/routes/sign-up.test.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /sign-up page with signups_enabled gate + confirmation screen"
```

---

## Task 16: `/onboarding` page

**Files:**
- Create: `apps/web/src/routes/onboarding.tsx`
- Create: `apps/web/src/routes/onboarding.test.tsx`

- [ ] **Step 1: Failing test**

`apps/web/src/routes/onboarding.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { OnboardingPage } from "./onboarding";

vi.mock("../lib/api", () => ({ postOnboarding: vi.fn() }));
const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => () => ({}),
  useNavigate: () => navigateMock,
}));

import { postOnboarding } from "../lib/api";

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.mocked(postOnboarding).mockReset();
    navigateMock.mockReset();
  });

  it("submits workspace name and navigates to /", async () => {
    vi.mocked(postOnboarding).mockResolvedValue({
      tenant: { id: "t", slug: "acme", name: "Acme", role: "owner" },
    });
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const user = userEvent.setup();
    render(
      <QueryClientProvider client={qc}>
        <OnboardingPage />
      </QueryClientProvider>,
    );
    await user.type(screen.getByLabelText(/workspace name/i), "Acme Corp");
    await user.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/" }));
    expect(postOnboarding).toHaveBeenCalledWith("Acme Corp");
  });
});
```

- [ ] **Step 2: Run, expect fail**

```bash
pnpm --filter @xtrusio/web test src/routes/onboarding.test.tsx
```

- [ ] **Step 3: Implement**

`apps/web/src/routes/onboarding.tsx`:

```tsx
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { postOnboarding } from "../lib/api";
import { errorMessage } from "../lib/error-messages";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";

function OnboardingPage() {
  const [workspaceName, setWorkspaceName] = useState("");
  const navigate = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => postOnboarding(workspaceName),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate({ to: "/" });
    },
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="text-2xl font-semibold">Create your workspace</h1>
        <p className="text-sm text-muted-foreground">
          A workspace is where you and your team will work. You can rename it later.
        </p>
        <div>
          <Label htmlFor="ws">Workspace name</Label>
          <Input
            id="ws"
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            required
            minLength={2}
            maxLength={200}
          />
        </div>
        {m.error ? (
          <p className="text-sm text-destructive">{errorMessage((m.error as Error).message)}</p>
        ) : null}
        <Button type="submit" className="w-full" disabled={m.isPending}>
          {m.isPending ? "Creating…" : "Continue"}
        </Button>
      </form>
    </main>
  );
}

export const Route = createFileRoute("/onboarding")({ component: OnboardingPage });
export { OnboardingPage };
```

- [ ] **Step 4: Run tests + typecheck + regenerate route tree (dev start)**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test src/routes/onboarding.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/onboarding.tsx apps/web/src/routes/onboarding.test.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /onboarding workspace setup page"
```

---

## Task 17: `/settings` expanded with signup toggle

**Files:**
- Modify: `apps/web/src/routes/settings.tsx`
- Create: `apps/web/src/routes/settings.test.tsx`

- [ ] **Step 1: Failing test**

`apps/web/src/routes/settings.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SettingsPage } from "./settings";

vi.mock("../lib/api", () => ({
  fetchPlatformSettings: vi.fn(),
  putPlatformSettings: vi.fn(),
}));

import { fetchPlatformSettings, putPlatformSettings } from "../lib/api";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchPlatformSettings).mockReset();
    vi.mocked(putPlatformSettings).mockReset();
  });

  it("renders the signups toggle and flips it on click", async () => {
    vi.mocked(fetchPlatformSettings).mockResolvedValue({
      signups_enabled: false,
      updated_at: new Date().toISOString(),
      updated_by_email: null,
    });
    vi.mocked(putPlatformSettings).mockResolvedValue({ signups_enabled: true });
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByRole("switch"));
    await user.click(screen.getByRole("switch"));
    await waitFor(() => expect(putPlatformSettings).toHaveBeenCalledWith(true));
  });
});
```

- [ ] **Step 2: Run, expect fail**

```bash
pnpm --filter @xtrusio/web test src/routes/settings.test.tsx
```

- [ ] **Step 3: Implement (rewrite settings.tsx)**

`apps/web/src/routes/settings.tsx`:

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchPlatformSettings, putPlatformSettings } from "../lib/api";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import { PageHeader } from "../components/page-header";

function SettingsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["platform-settings"], queryFn: fetchPlatformSettings });
  const m = useMutation({
    mutationFn: putPlatformSettings,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-settings"] }),
  });
  return (
    <div className="space-y-6">
      <PageHeader title="Platform settings" />
      <section className="rounded-md border p-6">
        <div className="flex items-center justify-between gap-6">
          <div>
            <Label htmlFor="signups" className="text-base font-medium">
              Self-serve signups
            </Label>
            <p className="text-sm text-muted-foreground">
              When enabled, anyone can create an account at <code>/sign-up</code> and bootstrap their own workspace.
            </p>
          </div>
          <Switch
            id="signups"
            checked={data?.signups_enabled ?? false}
            onCheckedChange={(v) => m.mutate(v)}
            disabled={m.isPending}
          />
        </div>
      </section>
    </div>
  );
}

export const Route = createFileRoute("/settings")({ component: SettingsPage });
export { SettingsPage };
```

- [ ] **Step 4: Run tests + typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test src/routes/settings.test.tsx
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/routes/settings.tsx apps/web/src/routes/settings.test.tsx
git commit -m "feat(web): /settings — signups_enabled toggle (super_admin)"
```

---

## Task 18: Manual end-to-end smoke test

**No new files. Manual verification only.**

- [ ] **Step 1: Confirm `.env` has live values**

```bash
grep -c "PROJECT_REF" .env || echo "MISSING — fill values from Supabase before continuing"
```

- [ ] **Step 2: Run migrations against managed Supabase**

```bash
make migrate
```
Expect `0000 → 0001 → 0002` applied cleanly.

- [ ] **Step 3: Bootstrap a super_admin**

```bash
make create-platform-owner email=you@x.com password='YourStrong-Password1'
```

- [ ] **Step 4: Start the stack**

```bash
make dev
```

- [ ] **Step 5: Verify sign-in works**

Open http://localhost:5173/sign-in → log in with the super_admin → confirm you land on `/`.

- [ ] **Step 6: Verify /settings toggles signups**

Navigate to `/settings`. Flip "Self-serve signups" on. Verify the API responds (no error toast).

- [ ] **Step 7: Verify /sign-up disabled state**

In an incognito window, open `/sign-up`. Confirm "Signups are currently disabled." now... wait, you just enabled them. So you should see the form. Toggle off in `/settings` (other window), refresh `/sign-up` → disabled message. Toggle back on.

- [ ] **Step 8: Real signup**

In incognito, sign up with a fresh email you can receive mail at. Submit. Confirm "Check your email" view renders.

- [ ] **Step 9: Confirm the email**

Open your inbox → click the Supabase confirmation link → it returns you to the app authenticated. AuthGuard sees no `platform`, no `tenants`, no `pending_invite` → redirects to `/onboarding`.

- [ ] **Step 10: Complete onboarding**

Enter "End to End Test Co". Submit. You should land on `/` and the sidebar should reflect tenant context (your tenant name visible). Database check:

```bash
psql "$DATABASE_URL" -c "SELECT slug, name FROM tenants ORDER BY created_at DESC LIMIT 5;"
psql "$DATABASE_URL" -c "SELECT user_id, role FROM tenant_memberships ORDER BY created_at DESC LIMIT 5;"
```

- [ ] **Step 11: Verify lint + typecheck + tests all clean**

```bash
make check
```

- [ ] **Step 12: Final commit (if anything was tweaked during smoke)**

```bash
git status
```
Should be clean. If not, fix and commit before declaring done.

---

## Self-review against the spec

After completing all tasks, run this check:

- [ ] Spec §3.1–3.3 (tenant_role, platform_settings, tenant_memberships) — implemented in Task 1.
- [ ] Spec §3.6 RLS policies (platform_settings, tenant_memberships, tenants_member_read) — implemented in Task 1, tested in Task 9.
- [ ] Spec §4.1 `GET /platform/signup-status`, `POST /signup` — Task 6.
- [ ] Spec §4.2 `GET /me`, `POST /onboarding/tenants` — Tasks 7, 8.
- [ ] Spec §4.3 `GET/PUT /platform/settings` — Task 5.
- [ ] Spec §5.1 routes `/sign-up`, `/onboarding`, `/settings` — Tasks 15, 16, 17.
- [ ] Spec §5.2 AuthGuard state machine — Task 14, with pure logic tested in Task 12.
- [ ] Spec §5.3 route component responsibilities — Tasks 15–17.
- [ ] Spec §6 emails — Supabase project config (manual, step 5.1 of spec; not code).
- [ ] Spec §7 testing — Tasks 5–10, 11–17.

If anything in the spec lacks a corresponding task above, add it before declaring this plan complete.

---

## Out of scope (deferred to Plan 2B)

- `platform_invites`, `tenant_invites` tables
- `/platform/users/invites`, `/tenants/{id}/invites`, `/invites/accept` endpoints
- `/accept-invite`, `/users`, `/clients/$slug/users` UI
- pending_invite handling in `/me` (the field exists but is always `null` in 2A)
