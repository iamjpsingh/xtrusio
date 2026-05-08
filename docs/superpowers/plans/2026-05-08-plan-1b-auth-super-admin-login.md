# Plan 1B — Auth + super_admin login (MVP) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Get the first super_admin bootstrapped via CLI, signed in via the real `/sign-in` page, listing and creating tenants on `/clients` end-to-end.

**Architecture:** Direct auth flow — `@supabase/supabase-js` on the frontend, `python-jose` JWT validation on the FastAPI side. No auth proxying. SQLAlchemy 2.0 async + Alembic for the DB. RLS enabled as defense-in-depth; primary access gate is FastAPI's `require_super_admin` dependency. TanStack Query for frontend data fetching. Memory rules apply: TypeScript-only, no demo data, no custom CSS, no hardcoded colors.

**Tech Stack:** Backend — FastAPI, SQLAlchemy 2.0 async, asyncpg, Alembic, python-jose, pydantic-settings, supabase-py (Admin API), typer. Frontend — `@supabase/supabase-js`, `@tanstack/react-query`. Existing — Supabase CLI (Postgres 17, GoTrue), Tailwind v4, shadcn-ui, TanStack Router.

---

## Files Created / Modified

### Backend (`apps/api/`)
- **Create:**
  - `alembic.ini`
  - `migrations/env.py`
  - `migrations/script.py.mako`
  - `migrations/versions/0001_init_tenants_platform_users.py`
  - `src/xtrusio_api/core/__init__.py`
  - `src/xtrusio_api/core/config.py`
  - `src/xtrusio_api/core/db.py`
  - `src/xtrusio_api/core/auth.py`
  - `src/xtrusio_api/models/__init__.py`
  - `src/xtrusio_api/models/platform_user.py`
  - `src/xtrusio_api/models/tenant.py`
  - `src/xtrusio_api/routes/__init__.py`
  - `src/xtrusio_api/routes/me.py`
  - `src/xtrusio_api/routes/tenants.py`
  - `src/xtrusio_api/scripts/__init__.py`
  - `src/xtrusio_api/scripts/bootstrap.py`
  - `tests/conftest.py`
  - `tests/core/__init__.py`
  - `tests/core/test_auth.py`
  - `tests/routes/__init__.py`
  - `tests/routes/test_me.py`
  - `tests/routes/test_tenants.py`
  - `tests/scripts/__init__.py`
  - `tests/scripts/test_bootstrap.py`
- **Modify:**
  - `pyproject.toml` (deps)
  - `src/xtrusio_api/main.py` (mount routers, lifespan)

### Frontend (`apps/web/`)
- **Create:**
  - `src/lib/supabase.ts`
  - `src/lib/api.ts`
  - `src/lib/auth.tsx`
  - `src/lib/query-client.ts`
  - `src/lib/api.test.ts`
  - `src/lib/auth.test.tsx`
  - `src/components/auth-guard.tsx`
  - `src/components/user-menu.tsx`
  - `src/components/user-menu.test.tsx`
  - `src/components/create-client-dialog.tsx`
- **Modify:**
  - `package.json` (deps)
  - `src/routes/__root.tsx` (wrap providers + auth guard)
  - `src/routes/sign-in.tsx` (real form)
  - `src/routes/clients.tsx` (fetch + create dialog)
  - `src/components/app-topbar.tsx` (show UserMenu)

### Repo root
- **Modify:**
  - `Makefile` (migrate, migrate-down, create-platform-owner targets)
  - `supabase/config.toml` (disable signup + email confirmation)
  - `README.md`
- **Add:**
  - none

---

## Task 1: Add backend dependencies

**Files:**
- Modify: `apps/api/pyproject.toml`

- [ ] **Step 1: Add runtime dependencies**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio
pnpm install >/dev/null 2>&1 || true   # ensure pnpm fine
```

Edit `apps/api/pyproject.toml`. Replace the `dependencies` and `dev` group with:

```toml
[project]
name = "xtrusio-api"
version = "0.0.0"
description = "Xtrusio platform API"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi~=0.115.0",
    "uvicorn[standard]~=0.30.0",
    "pydantic~=2.9.0",
    "pydantic-settings~=2.5.0",
    "sqlalchemy[asyncio]~=2.0.36",
    "asyncpg~=0.30.0",
    "alembic~=1.14.0",
    "python-jose[cryptography]~=3.3.0",
    "supabase~=2.10.0",
    "typer~=0.13.0",
]

[dependency-groups]
dev = [
    "pytest~=8.3.0",
    "pytest-asyncio~=0.24.0",
    "httpx~=0.27.0",
    "ruff~=0.6.0",
    "mypy~=1.11.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/xtrusio_api"]
```

- [ ] **Step 2: Sync workspace**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv sync --all-packages
```

Expected: resolves and installs without errors.

- [ ] **Step 3: Commit**

```bash
git add apps/api/pyproject.toml uv.lock
git commit -m "chore(api): add SQLA async + Alembic + jose + supabase + typer deps"
```

---

## Task 2: Settings + DB engine (`core/config.py` + `core/db.py`)

**Files:**
- Create: `apps/api/src/xtrusio_api/core/__init__.py`
- Create: `apps/api/src/xtrusio_api/core/config.py`
- Create: `apps/api/src/xtrusio_api/core/db.py`

- [ ] **Step 1: Create `core/__init__.py`**

```python
```

(Empty file.)

- [ ] **Step 2: Create `core/config.py`**

```python
"""Application settings loaded from .env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    process_role: str = Field(default="api", alias="XTRUSIO_PROCESS_ROLE")

    database_url: str = Field(alias="DATABASE_URL")
    valkey_url: str = Field(default="redis://localhost:63792/0", alias="VALKEY_URL")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field(alias="SUPABASE_JWT_SECRET")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 3: Create `core/db.py`**

```python
"""Async SQLAlchemy engine + session factory."""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncAttrs, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base for all ORM models."""


_settings = get_settings()
engine = create_async_engine(
    _settings.database_url,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session."""
    async with SessionLocal() as session:
        yield session
```

- [ ] **Step 4: Verify typecheck and ruff**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio
uv run ruff check apps/api/src
uv run mypy apps/api/src
```

Expected: 0 issues.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/core
git commit -m "feat(api/core): settings + async DB engine + Base"
```

---

## Task 3: ORM models (`models/platform_user.py` + `models/tenant.py`)

**Files:**
- Create: `apps/api/src/xtrusio_api/models/__init__.py`
- Create: `apps/api/src/xtrusio_api/models/platform_user.py`
- Create: `apps/api/src/xtrusio_api/models/tenant.py`

- [ ] **Step 1: Create `models/__init__.py`**

```python
"""Re-exports for the ORM models so Alembic can autogenerate against them."""
from .platform_user import PlatformRole, PlatformUser, PlatformUserOut
from .tenant import Tenant, TenantIn, TenantOut

__all__ = [
    "PlatformRole",
    "PlatformUser",
    "PlatformUserOut",
    "Tenant",
    "TenantIn",
    "TenantOut",
]
```

- [ ] **Step 2: Create `models/platform_user.py`**

```python
"""Platform user model and roles."""
from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import Boolean, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base


class PlatformRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EDITOR = "editor"


class PlatformUser(Base):
    __tablename__ = "platform_users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
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
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sign_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlatformUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    role: PlatformRole
    is_active: bool
    created_at: datetime
    last_sign_in_at: datetime | None = None
```

- [ ] **Step 3: Create `models/tenant.py`**

```python
"""Tenant model."""
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db import Base

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,62}[a-z0-9]$")


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("auth.users.id", ondelete="RESTRICT"), nullable=False
    )


class TenantIn(BaseModel):
    slug: str = Field(min_length=3, max_length=64)
    name: str = Field(min_length=1, max_length=200)

    @field_validator("slug")
    @classmethod
    def _validate_slug(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be 3-64 chars, lowercase, start/end alphanumeric, "
                "allow a-z 0-9 and hyphen between"
            )
        return v


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    created_at: datetime
    updated_at: datetime
    created_by: UUID
```

- [ ] **Step 4: Verify**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio
uv run ruff check apps/api/src
uv run mypy apps/api/src
```

Expected: 0 issues.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/models
git commit -m "feat(api/models): PlatformUser, Tenant, role enum, validators"
```

---

## Task 4: Alembic scaffolding

**Files:**
- Create: `apps/api/alembic.ini`
- Create: `apps/api/migrations/env.py`
- Create: `apps/api/migrations/script.py.mako`

- [ ] **Step 1: Create `apps/api/alembic.ini`**

```ini
[alembic]
script_location = migrations
prepend_sys_path = src
version_path_separator = os
sqlalchemy.url =

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: Create `apps/api/migrations/env.py`**

```python
"""Async Alembic env using SQLAlchemy 2.0 async engine."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from xtrusio_api.core.config import get_settings
from xtrusio_api.core.db import Base
from xtrusio_api.models import Tenant, PlatformUser  # noqa: F401  (register tables on Base)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


run_migrations_online()
```

- [ ] **Step 3: Create `apps/api/migrations/script.py.mako`**

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, Sequence[str], None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 4: Create empty `migrations/versions/` directory**

```bash
mkdir -p apps/api/migrations/versions
touch apps/api/migrations/versions/.gitkeep
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/alembic.ini apps/api/migrations
git commit -m "feat(api): add Alembic scaffolding (async env)"
```

---

## Task 5: Initial migration `0001_init_tenants_platform_users`

**Files:**
- Create: `apps/api/migrations/versions/0001_init_tenants_platform_users.py`

- [ ] **Step 1: Create the migration**

```python
"""init: tenants + platform_users + platform_role enum

Revision ID: 0001
Revises:
Create Date: 2026-05-08

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE platform_role AS ENUM ('super_admin', 'admin', 'editor')")

    op.execute(
        """
        CREATE TABLE tenants (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        citext NOT NULL UNIQUE,
            name        text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            created_by  uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
            CONSTRAINT tenants_slug_format
                CHECK (slug ~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$')
        )
        """
    )
    op.execute("CREATE INDEX tenants_created_by_idx ON tenants(created_by)")

    op.execute(
        """
        CREATE TABLE platform_users (
            id                uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
            email             citext NOT NULL UNIQUE,
            role              platform_role NOT NULL,
            is_active         boolean NOT NULL DEFAULT true,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            last_sign_in_at   timestamptz
        )
        """
    )
    op.execute("CREATE INDEX platform_users_role_idx ON platform_users(role)")

    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenants_super_admin_all ON tenants
            FOR ALL
            TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM platform_users pu
                    WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM platform_users pu
                    WHERE pu.id = auth.uid() AND pu.role = 'super_admin' AND pu.is_active
                )
            )
        """
    )

    op.execute("ALTER TABLE platform_users ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY platform_users_self_select ON platform_users
            FOR SELECT
            TO authenticated
            USING (id = auth.uid())
        """
    )
    op.execute(
        """
        CREATE POLICY platform_users_super_admin_all ON platform_users
            FOR ALL
            TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM platform_users pu2
                    WHERE pu2.id = auth.uid() AND pu2.role = 'super_admin' AND pu2.is_active
                )
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM platform_users pu2
                    WHERE pu2.id = auth.uid() AND pu2.role = 'super_admin' AND pu2.is_active
                )
            )
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER tenants_set_updated_at BEFORE UPDATE ON tenants "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        "CREATE TRIGGER platform_users_set_updated_at BEFORE UPDATE ON platform_users "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS platform_users_set_updated_at ON platform_users")
    op.execute("DROP TRIGGER IF EXISTS tenants_set_updated_at ON tenants")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP TABLE IF EXISTS platform_users")
    op.execute("DROP TABLE IF EXISTS tenants")
    op.execute("DROP TYPE IF EXISTS platform_role")
```

- [ ] **Step 2: Bring up Supabase locally**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio
make db-up
```

- [ ] **Step 3: Apply migration**

```bash
uv run --directory apps/api alembic upgrade head
```

Expected: prints "Running upgrade  -> 0001, init: tenants + platform_users + platform_role enum".

- [ ] **Step 4: Verify in Postgres**

```bash
docker exec supabase_db_xtrusio psql -U postgres -d postgres -c "\d tenants" -c "\d platform_users" -c "\dT platform_role"
```

Expected: both tables exist with the columns from the migration; `platform_role` enum has 3 values.

- [ ] **Step 5: Verify downgrade is clean**

```bash
uv run --directory apps/api alembic downgrade -1
docker exec supabase_db_xtrusio psql -U postgres -d postgres -c "\d tenants" 2>&1 | head -3
```

Expected: "Did not find any relation named 'tenants'." Then re-apply:

```bash
uv run --directory apps/api alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add apps/api/migrations/versions/0001_init_tenants_platform_users.py
git commit -m "feat(api/migrations): 0001 init tenants + platform_users + RLS"
```

---

## Task 6: Test scaffolding (`tests/conftest.py`)

**Files:**
- Create: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/core/__init__.py`
- Create: `apps/api/tests/routes/__init__.py`
- Create: `apps/api/tests/scripts/__init__.py`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p apps/api/tests/core apps/api/tests/routes apps/api/tests/scripts
touch apps/api/tests/core/__init__.py
touch apps/api/tests/routes/__init__.py
touch apps/api/tests/scripts/__init__.py
```

- [ ] **Step 2: Create `apps/api/tests/conftest.py`**

```python
"""Shared pytest fixtures for the api test suite."""
from __future__ import annotations

import os
import time
from collections.abc import AsyncIterator, Iterator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xtrusio_api.core.config import get_settings
from xtrusio_api.core.db import SessionLocal, engine
from xtrusio_api.main import app
from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

SETTINGS = get_settings()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Per-test session inside a SAVEPOINT; rolled back at end."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            try:
                yield session
            finally:
                await trans.rollback()


@pytest.fixture
def make_jwt() -> Iterator[callable]:
    """Factory to mint a Supabase-shaped JWT for a given sub UUID."""

    def _factory(*, sub: UUID, expired: bool = False) -> str:
        now = int(time.time())
        payload = {
            "sub": str(sub),
            "aud": "authenticated",
            "role": "authenticated",
            "iat": now,
            "exp": now - 60 if expired else now + 3600,
        }
        return jwt.encode(payload, SETTINGS.supabase_jwt_secret, algorithm="HS256")

    yield _factory


@pytest_asyncio.fixture
async def super_admin_user(db_session: AsyncSession) -> AsyncIterator[PlatformUser]:
    """Insert a super_admin platform user. We bypass the auth.users FK by inserting
    directly into auth.users first (Supabase ships this table)."""
    user_id = uuid4()
    email = f"sa-{user_id.hex[:8]}@example.com"
    # Insert auth.users row (Supabase superuser bypasses any auth schema RLS)
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": str(user_id), "email": email},
    )
    pu = PlatformUser(
        id=user_id,
        email=email,
        role=PlatformRole.SUPER_ADMIN,
        is_active=True,
    )
    db_session.add(pu)
    await db_session.flush()
    yield pu


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[AsyncClient]:
    """ASGI in-process client (no real network)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as c:
        yield c
```

- [ ] **Step 3: Verify conftest imports cleanly (it'll fail because main.py and auth aren't built yet — defer until Task 8)**

Skip running tests at this step. The conftest is staged.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/conftest.py apps/api/tests/core/__init__.py apps/api/tests/routes/__init__.py apps/api/tests/scripts/__init__.py
git commit -m "test(api): add conftest with db_session, make_jwt, super_admin_user fixtures"
```

---

## Task 7: JWT middleware — TDD red

**Files:**
- Create: `apps/api/tests/core/test_auth.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for JWT middleware."""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from xtrusio_api.models.platform_user import PlatformUser


pytestmark = pytest.mark.asyncio


async def test_missing_token_returns_401(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/me")
    assert res.status_code == 401


async def test_malformed_token_returns_401(http_client: AsyncClient) -> None:
    res = await http_client.get("/api/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


async def test_expired_token_returns_401(http_client: AsyncClient, make_jwt) -> None:
    token = make_jwt(sub=uuid4(), expired=True)
    res = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


async def test_unprovisioned_user_returns_401(http_client: AsyncClient, make_jwt) -> None:
    """Valid JWT but no platform_users row for that sub."""
    token = make_jwt(sub=uuid4())
    res = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


async def test_super_admin_returns_200(
    http_client: AsyncClient, make_jwt, super_admin_user: PlatformUser
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == super_admin_user.email
    assert body["role"] == "super_admin"
```

- [ ] **Step 2: Run, verify FAIL**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio
uv run pytest apps/api/tests/core/test_auth.py -v
```

Expected: every test fails because `xtrusio_api.main` and `core.auth` and the `/api/me` route don't exist yet — likely import errors.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/core/test_auth.py
git commit -m "test(api/core): add failing JWT middleware tests"
```

---

## Task 8: JWT middleware + `/api/me` — TDD green

**Files:**
- Create: `apps/api/src/xtrusio_api/core/auth.py`
- Create: `apps/api/src/xtrusio_api/routes/__init__.py`
- Create: `apps/api/src/xtrusio_api/routes/me.py`
- Modify: `apps/api/src/xtrusio_api/main.py`

- [ ] **Step 1: Create `core/auth.py`**

```python
"""JWT validation + auth dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .db import get_db
from ..models.platform_user import PlatformRole, PlatformUser

_ALGO = "HS256"
_AUDIENCE = "authenticated"


@dataclass
class CurrentUser:
    user_id: UUID
    email: str
    role: PlatformRole
    is_active: bool


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,  # type: ignore[assignment]
) -> CurrentUser:
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

    row = (
        await db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not provisioned")
    if not row.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user disabled")
    return CurrentUser(
        user_id=row.id, email=row.email, role=row.role, is_active=row.is_active
    )


async def require_super_admin(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if user.role != PlatformRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "super_admin required")
    return user
```

- [ ] **Step 2: Create `routes/__init__.py`**

```python
```

(Empty file.)

- [ ] **Step 3: Create `routes/me.py`**

```python
"""GET /api/me — returns enriched current user."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..models.platform_user import PlatformUser, PlatformUserOut

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me", response_model=PlatformUserOut)
async def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformUser:
    row = (
        await db.execute(select(PlatformUser).where(PlatformUser.id == user.user_id))
    ).scalar_one()
    return row
```

- [ ] **Step 4: Update `main.py`**

```python
"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

from .routes import me as me_routes

app = FastAPI(title="Xtrusio API", version="0.0.0")
app.include_router(me_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio
uv run pytest apps/api/tests/core/test_auth.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Run lint and typecheck**

```bash
uv run ruff check apps/api/src apps/api/tests
uv run mypy apps/api/src
```

Expected: 0 issues.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/xtrusio_api/core/auth.py apps/api/src/xtrusio_api/routes apps/api/src/xtrusio_api/main.py
git commit -m "feat(api): JWT middleware + GET /api/me"
```

---

## Task 9: `/api/tenants` — TDD red

**Files:**
- Create: `apps/api/tests/routes/test_tenants.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for /api/tenants list + create."""
from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from xtrusio_api.models.platform_user import PlatformRole, PlatformUser

pytestmark = pytest.mark.asyncio


async def test_list_requires_super_admin(http_client: AsyncClient, make_jwt) -> None:
    """No JWT → 401."""
    res = await http_client.get("/api/tenants")
    assert res.status_code == 401


async def test_list_403_for_non_super_admin(
    http_client: AsyncClient, make_jwt, db_session: AsyncSession
) -> None:
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
    db_session.add(
        PlatformUser(id=user_id, email=email, role=PlatformRole.EDITOR, is_active=True)
    )
    await db_session.flush()

    token = make_jwt(sub=user_id)
    res = await http_client.get("/api/tenants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403


async def test_list_empty_for_super_admin(
    http_client: AsyncClient, make_jwt, super_admin_user: PlatformUser
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.get("/api/tenants", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json() == []


async def test_create_tenant_succeeds(
    http_client: AsyncClient, make_jwt, super_admin_user: PlatformUser
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.post(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "acme-corp", "name": "Acme Corp"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["slug"] == "acme-corp"
    assert body["name"] == "Acme Corp"
    assert "id" in body


async def test_create_tenant_slug_conflict(
    http_client: AsyncClient, make_jwt, super_admin_user: PlatformUser
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    headers = {"Authorization": f"Bearer {token}"}
    a = await http_client.post(
        "/api/tenants", headers=headers, json={"slug": "globex", "name": "Globex"}
    )
    assert a.status_code == 201
    b = await http_client.post(
        "/api/tenants", headers=headers, json={"slug": "globex", "name": "Globex 2"}
    )
    assert b.status_code == 409


async def test_create_tenant_invalid_slug(
    http_client: AsyncClient, make_jwt, super_admin_user: PlatformUser
) -> None:
    token = make_jwt(sub=super_admin_user.id)
    res = await http_client.post(
        "/api/tenants",
        headers={"Authorization": f"Bearer {token}"},
        json={"slug": "Bad Slug!", "name": "X"},
    )
    assert res.status_code == 422
```

- [ ] **Step 2: Run, verify FAIL**

```bash
uv run pytest apps/api/tests/routes/test_tenants.py -v
```

Expected: every test fails (404 from missing endpoints, etc).

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/routes/test_tenants.py
git commit -m "test(api/routes): add failing /api/tenants tests"
```

---

## Task 10: `/api/tenants` — TDD green

**Files:**
- Create: `apps/api/src/xtrusio_api/routes/tenants.py`
- Modify: `apps/api/src/xtrusio_api/main.py`

- [ ] **Step 1: Create `routes/tenants.py`**

```python
"""GET/POST /api/tenants."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, require_super_admin
from ..core.db import get_db
from ..models.tenant import Tenant, TenantIn, TenantOut

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[Tenant]:
    rows = (
        await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    ).scalars().all()
    return list(rows)


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantIn,
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    tenant = Tenant(slug=body.slug, name=body.name, created_by=user.user_id)
    db.add(tenant)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "slug already taken") from e
    await db.refresh(tenant)
    return tenant
```

- [ ] **Step 2: Update `main.py`**

```python
"""FastAPI application entrypoint."""
from __future__ import annotations

from fastapi import FastAPI

from .routes import me as me_routes
from .routes import tenants as tenants_routes

app = FastAPI(title="Xtrusio API", version="0.0.0")
app.include_router(me_routes.router)
app.include_router(tenants_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 3: Run tests, verify PASS**

```bash
uv run pytest apps/api/tests/routes/test_tenants.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Verify lint + mypy**

```bash
uv run ruff check apps/api/src apps/api/tests
uv run mypy apps/api/src
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/tenants.py apps/api/src/xtrusio_api/main.py
git commit -m "feat(api): GET + POST /api/tenants (super_admin required)"
```

---

## Task 11: Bootstrap CLI — TDD red

**Files:**
- Create: `apps/api/src/xtrusio_api/scripts/__init__.py`
- Create: `apps/api/tests/scripts/test_bootstrap.py`

- [ ] **Step 1: Create empty `scripts/__init__.py`**

```bash
mkdir -p apps/api/src/xtrusio_api/scripts
touch apps/api/src/xtrusio_api/scripts/__init__.py
```

- [ ] **Step 2: Write failing test**

```python
"""Tests for the bootstrap CLI."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from xtrusio_api.models.platform_user import PlatformRole, PlatformUser
from xtrusio_api.scripts.bootstrap import _run

pytestmark = pytest.mark.asyncio


async def _fake_supabase_create_user(email: str, user_id: str) -> MagicMock:
    """Build a Supabase admin response shape matching `auth.admin.create_user`."""
    user = MagicMock()
    user.user.id = user_id
    user.user.email = email
    return user


async def test_bootstrap_creates_super_admin(db_session: AsyncSession) -> None:
    user_id = str(uuid4())
    email = f"owner-{user_id[:8]}@example.com"

    # Pre-insert auth.users (in real prod, supabase admin would do this)
    await db_session.execute(
        text(
            "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, "
            "email_confirmed_at, created_at, updated_at) VALUES "
            "(:id, '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', "
            ":email, '', now(), now(), now())"
        ),
        {"id": user_id, "email": email},
    )
    await db_session.flush()

    fake_resp = MagicMock()
    fake_resp.user.id = user_id
    fake_resp.user.email = email
    sb = MagicMock()
    sb.auth.admin.create_user.return_value = fake_resp

    with patch("xtrusio_api.scripts.bootstrap.create_client", return_value=sb):
        with patch(
            "xtrusio_api.scripts.bootstrap.SessionLocal",
            new=lambda: _make_ctx(db_session),
        ):
            await _run(email=email, password="hunter2!", force=False)

    pu = (
        await db_session.execute(select(PlatformUser).where(PlatformUser.email == email))
    ).scalar_one()
    assert pu.role == PlatformRole.SUPER_ADMIN
    assert pu.is_active is True


async def test_bootstrap_refuses_second_run(
    db_session: AsyncSession, super_admin_user: PlatformUser
) -> None:
    """If a super_admin already exists, the CLI exits non-zero unless --force."""
    sb = MagicMock()
    with patch("xtrusio_api.scripts.bootstrap.create_client", return_value=sb):
        with patch(
            "xtrusio_api.scripts.bootstrap.SessionLocal",
            new=lambda: _make_ctx(db_session),
        ):
            with pytest.raises(SystemExit) as exc:
                await _run(email="another@example.com", password="x", force=False)
    assert exc.value.code == 1


def _make_ctx(session: AsyncSession):
    """Wrap an existing session in a no-op context manager (so `async with` works)."""

    class _Ctx:
        async def __aenter__(self) -> AsyncSession:
            return session

        async def __aexit__(self, *exc_info: object) -> None:
            pass

    return _Ctx()
```

- [ ] **Step 3: Run, verify FAIL**

```bash
uv run pytest apps/api/tests/scripts/test_bootstrap.py -v
```

Expected: import error (`xtrusio_api.scripts.bootstrap` not found).

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/scripts/__init__.py apps/api/tests/scripts/test_bootstrap.py
git commit -m "test(api/scripts): add failing bootstrap CLI tests"
```

---

## Task 12: Bootstrap CLI — TDD green

**Files:**
- Create: `apps/api/src/xtrusio_api/scripts/bootstrap.py`

- [ ] **Step 1: Create the CLI**

```python
"""CLI to bootstrap the first platform super_admin.

Usage:
    python -m xtrusio_api.scripts.bootstrap create-platform-owner \\
        --email owner@example.com --password '...'
"""
from __future__ import annotations

import asyncio
import sys
from typing import Annotated

import typer
from sqlalchemy import select
from supabase import create_client

from ..core.config import get_settings
from ..core.db import SessionLocal
from ..models.platform_user import PlatformRole, PlatformUser

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def create_platform_owner(
    email: Annotated[str, typer.Option("--email", help="Owner email address")],
    password: Annotated[str, typer.Option("--password", help="Initial password")],
    force: Annotated[
        bool, typer.Option("--force", help="Override existing super_admin check")
    ] = False,
) -> None:
    """Create the platform's first super_admin (Supabase auth + platform_users row)."""
    asyncio.run(_run(email=email, password=password, force=force))


async def _run(*, email: str, password: str, force: bool) -> None:
    settings = get_settings()
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async with SessionLocal() as db:
        existing = (
            await db.execute(
                select(PlatformUser).where(PlatformUser.role == PlatformRole.SUPER_ADMIN)
            )
        ).scalar_one_or_none()
        if existing and not force:
            typer.echo(
                f"❌ super_admin already exists: {existing.email}. "
                f"Re-run with --force to override.",
                err=True,
            )
            sys.exit(1)

        result = sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        if result.user is None:
            typer.echo("❌ Supabase did not return a user.", err=True)
            sys.exit(2)

        db.add(
            PlatformUser(
                id=result.user.id,
                email=email,
                role=PlatformRole.SUPER_ADMIN,
                is_active=True,
            )
        )
        await db.commit()

    typer.echo(f"✅ super_admin created: {email}")
    typer.echo("   Sign in at http://localhost:5173/sign-in")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run tests, verify PASS**

```bash
uv run pytest apps/api/tests/scripts/test_bootstrap.py -v
```

Expected: 2 passed.

- [ ] **Step 3: Verify lint + mypy**

```bash
uv run ruff check apps/api/src apps/api/tests
uv run mypy apps/api/src
```

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/scripts/bootstrap.py
git commit -m "feat(api): bootstrap CLI for first super_admin"
```

---

## Task 13: Makefile + Supabase config

**Files:**
- Modify: `Makefile`
- Modify: `supabase/config.toml`

- [ ] **Step 1: Update `Makefile` — add `migrate`, `migrate-down`, `create-platform-owner` targets**

Find the `.PHONY` line and update it:

```makefile
.PHONY: help install env env-force supabase-start supabase-stop supabase-status valkey-up valkey-down db-up db-down db-logs api worker web dev lint format typecheck test check clean migrate migrate-down create-platform-owner
```

Update the `help` block to include the new targets (insert under `make install`):

```makefile
	@echo "  make migrate         - apply pending Alembic migrations"
	@echo "  make migrate-down    - revert one Alembic migration"
	@echo "  make create-platform-owner email=... password=...  - bootstrap first super_admin"
```

Append to the bottom of the file (before `clean:`):

```makefile
migrate:
	uv run --directory apps/api alembic upgrade head

migrate-down:
	uv run --directory apps/api alembic downgrade -1

create-platform-owner:
	@if [ -z "$(email)" ] || [ -z "$(password)" ]; then \
		echo "Usage: make create-platform-owner email=you@x.com password=..."; \
		exit 1; \
	fi
	XTRUSIO_PROCESS_ROLE=api uv run --directory apps/api \
		python -m xtrusio_api.scripts.bootstrap create-platform-owner \
		--email "$(email)" --password "$(password)"
```

- [ ] **Step 2: Update `supabase/config.toml` to disable signup + email confirmation**

Find the `[auth]` block and modify:

```toml
[auth]
enabled = true
site_url = "http://localhost:5173"
additional_redirect_urls = ["http://localhost:5173"]
jwt_expiry = 3600
enable_refresh_token_rotation = true
refresh_token_reuse_interval = 10
enable_signup = false
enable_anonymous_sign_ins = false
```

Find the `[auth.email]` block and modify:

```toml
[auth.email]
enable_signup = false
double_confirm_changes = true
enable_confirmations = false
secure_password_change = true
```

(Leave the rest of `config.toml` untouched.)

- [ ] **Step 3: Restart Supabase to apply config**

```bash
make db-down
make db-up
```

- [ ] **Step 4: Verify `make migrate` works against the running DB**

```bash
make migrate-down 2>/dev/null || true
make migrate
```

Expected: "Running upgrade  -> 0001".

- [ ] **Step 5: Commit**

```bash
git add Makefile supabase/config.toml
git commit -m "feat: Makefile migrate + bootstrap targets; disable Supabase signup"
```

---

## Task 14: Frontend dependencies

**Files:**
- Modify: `apps/web/package.json`

- [ ] **Step 1: Add deps**

```bash
pnpm --filter @xtrusio/web add @supabase/supabase-js@^2.46.0 @tanstack/react-query@^5.59.0
```

- [ ] **Step 2: Commit**

```bash
git add apps/web/package.json pnpm-lock.yaml
git commit -m "chore(web): add @supabase/supabase-js + @tanstack/react-query"
```

---

## Task 15: Supabase client + Query client + apiFetch

**Files:**
- Create: `apps/web/src/lib/supabase.ts`
- Create: `apps/web/src/lib/query-client.ts`
- Create: `apps/web/src/lib/api.ts`
- Create: `apps/web/src/lib/api.test.ts`

- [ ] **Step 1: Create `apps/web/src/lib/supabase.ts`**

```ts
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
if (!url || !anonKey) {
  throw new Error("VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set in .env");
}

export const supabase = createClient(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  },
});
```

- [ ] **Step 2: Create `apps/web/src/lib/query-client.ts`**

```ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});
```

- [ ] **Step 3: Create the failing test FIRST: `apps/web/src/lib/api.test.ts`**

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./api";

vi.mock("./supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    },
  },
}));

import { supabase } from "./supabase";

describe("apiFetch", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("attaches Authorization header when a session exists", async () => {
    vi.mocked(supabase.auth.getSession).mockResolvedValueOnce({
      data: { session: { access_token: "abc.def.ghi" } },
    } as never);
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    await apiFetch<{ ok: boolean }>("/api/me");
    const call = vi.mocked(fetch).mock.calls[0]!;
    const headers = call[1]?.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer abc.def.ghi");
  });

  it("omits Authorization header when no session", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    await apiFetch<{ ok: boolean }>("/api/me");
    const call = vi.mocked(fetch).mock.calls[0]!;
    const headers = call[1]?.headers as Headers;
    expect(headers.get("Authorization")).toBeNull();
  });

  it("throws ApiError on non-2xx", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "nope" }), { status: 401 }),
    );
    await expect(apiFetch("/api/me")).rejects.toBeInstanceOf(ApiError);
  });
});
```

- [ ] **Step 4: Create `apps/web/src/lib/api.ts`**

```ts
import { supabase } from "./supabase";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}: ${JSON.stringify(body)}`);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type") && init?.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  const res = await fetch(`${baseUrl}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
```

- [ ] **Step 5: Run tests, verify PASS**

```bash
pnpm --filter @xtrusio/web test api
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib
git commit -m "feat(web/lib): supabase client + query client + apiFetch (with tests)"
```

---

## Task 16: AuthProvider + useAuth — TDD

**Files:**
- Create: `apps/web/src/lib/auth.tsx`
- Create: `apps/web/src/lib/auth.test.tsx`

- [ ] **Step 1: Write failing test `apps/web/src/lib/auth.test.tsx`**

```tsx
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";

const subscribeMock = vi.fn();
const unsubscribeMock = vi.fn();
const signInMock = vi.fn();
const signOutMock = vi.fn();

vi.mock("./supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: (cb: (event: string, s: unknown) => void) => {
        subscribeMock(cb);
        return { data: { subscription: { unsubscribe: unsubscribeMock } } };
      },
      signInWithPassword: signInMock,
      signOut: signOutMock,
    },
  },
}));

function TestProbe() {
  const { user, signIn, signOut } = useAuth();
  return (
    <div>
      <span data-testid="email">{user?.email ?? "NONE"}</span>
      <button onClick={() => void signIn("a@b.c", "x")}>signin</button>
      <button onClick={() => void signOut()}>signout</button>
    </div>
  );
}

describe("AuthProvider", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("starts with no user", async () => {
    render(
      <AuthProvider>
        <TestProbe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("NONE"));
  });

  it("signIn forwards to supabase and updates session via onAuthStateChange", async () => {
    signInMock.mockResolvedValueOnce({ error: null });
    render(
      <AuthProvider>
        <TestProbe />
      </AuthProvider>,
    );
    await waitFor(() => expect(subscribeMock).toHaveBeenCalled());
    await act(async () => {
      screen.getByText("signin").click();
    });
    expect(signInMock).toHaveBeenCalledWith({ email: "a@b.c", password: "x" });

    // Simulate Supabase emitting SIGNED_IN
    const cb = subscribeMock.mock.calls[0]![0];
    await act(async () => {
      cb("SIGNED_IN", { user: { id: "u1", email: "a@b.c" } });
    });
    await waitFor(() => expect(screen.getByTestId("email").textContent).toBe("a@b.c"));
  });

  it("signOut calls supabase.auth.signOut", async () => {
    signOutMock.mockResolvedValueOnce({ error: null });
    render(
      <AuthProvider>
        <TestProbe />
      </AuthProvider>,
    );
    await act(async () => {
      screen.getByText("signout").click();
    });
    expect(signOutMock).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pnpm --filter @xtrusio/web test lib/auth
```

Expected: import error — `./auth` not found.

- [ ] **Step 3: Create `apps/web/src/lib/auth.tsx`**

```tsx
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Session, User } from "@supabase/supabase-js";
import { supabase } from "./supabase";

type AuthState = {
  user: User | null;
  session: Session | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<{ error: string | null }>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    void supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setLoading(false);
    });
    return () => {
      mounted = false;
      sub.subscription.unsubscribe();
    };
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user: session?.user ?? null,
      session,
      loading,
      signIn: async (email: string, password: string) => {
        const { error } = await supabase.auth.signInWithPassword({ email, password });
        return { error: error?.message ?? null };
      },
      signOut: async () => {
        await supabase.auth.signOut();
      },
    }),
    [session, loading],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
```

- [ ] **Step 4: Run tests, verify PASS**

```bash
pnpm --filter @xtrusio/web test lib/auth
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/auth.tsx apps/web/src/lib/auth.test.tsx
git commit -m "feat(web/lib): AuthProvider + useAuth (with tests)"
```

---

## Task 17: AuthGuard + root route wrap

**Files:**
- Create: `apps/web/src/components/auth-guard.tsx`
- Modify: `apps/web/src/routes/__root.tsx`

- [ ] **Step 1: Create `auth-guard.tsx`**

```tsx
import { type ReactNode } from "react";
import { Navigate, useRouterState } from "@tanstack/react-router";
import { useAuth } from "@/lib/auth";

const PUBLIC_ROUTES = new Set<string>(["/sign-in"]);

export function AuthGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const { location } = useRouterState();
  const isPublic = PUBLIC_ROUTES.has(location.pathname);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-sm text-muted-foreground">Loading…</div>
      </div>
    );
  }
  if (!user && !isPublic) {
    return <Navigate to="/sign-in" />;
  }
  if (user && isPublic) {
    return <Navigate to="/" />;
  }
  return <>{children}</>;
}
```

- [ ] **Step 2: Update `apps/web/src/routes/__root.tsx`**

```tsx
import { Outlet, createRootRoute, useRouterState } from "@tanstack/react-router";
import { QueryClientProvider } from "@tanstack/react-query";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/app-sidebar";
import { AppTopbar } from "@/components/app-topbar";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/lib/auth";
import { AuthGuard } from "@/components/auth-guard";
import { queryClient } from "@/lib/query-client";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  const { location } = useRouterState();
  const isAuthRoute = location.pathname === "/sign-in";

  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthGuard>
            {isAuthRoute ? (
              <main className="min-h-screen bg-background p-6">
                <Outlet />
              </main>
            ) : (
              <SidebarProvider>
                <AppSidebar />
                <SidebarInset>
                  <AppTopbar />
                  <main className="flex-1 p-6">
                    <Outlet />
                  </main>
                </SidebarInset>
              </SidebarProvider>
            )}
            <Toaster richColors closeButton position="bottom-right" />
          </AuthGuard>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}
```

- [ ] **Step 3: Verify typecheck**

```bash
pnpm --filter @xtrusio/web typecheck
```

Expected: 0 issues.

- [ ] **Step 4: Verify smoke test still passes** (the existing `routes/index.test.tsx` may need a small adjustment because routes now require AuthProvider in scope; the previous test already wraps in ThemeProvider but not in AuthProvider, so it'll trip on `useAuth` from AuthGuard).

Update `apps/web/src/routes/index.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RouterProvider, createMemoryHistory, createRouter } from "@tanstack/react-router";
import { QueryClientProvider, QueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { AuthProvider } from "@/lib/auth";
import { routeTree } from "@/routeTree.gen";

vi.mock("@/lib/supabase", () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: { user: { id: "u1", email: "test@example.com" } } } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => {} } } }),
      signInWithPassword: vi.fn(),
      signOut: vi.fn(),
    },
  },
}));

function renderAt(initial: string) {
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [initial] }),
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ThemeProvider attribute="class" defaultTheme="system">
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

describe("/ Dashboard route", () => {
  it("renders the welcome empty state when authenticated", async () => {
    renderAt("/");
    expect(
      await screen.findByRole("heading", { name: /welcome to xtrusio/i }),
    ).toBeInTheDocument();
  });
});
```

```bash
pnpm --filter @xtrusio/web test
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/auth-guard.tsx apps/web/src/routes/__root.tsx apps/web/src/routes/index.test.tsx
git commit -m "feat(web): wrap app in AuthProvider + QueryClientProvider + AuthGuard"
```

---

## Task 18: Wire up the sign-in form

**Files:**
- Modify: `apps/web/src/routes/sign-in.tsx`

- [ ] **Step 1: Replace the placeholder form with a real one**

```tsx
import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

export const Route = createFileRoute("/sign-in")({
  component: SignInRoute,
});

function SignInRoute() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error } = await signIn(email, password);
    setLoading(false);
    if (error) {
      setError(error);
      return;
    }
    void navigate({ to: "/" });
  };

  return (
    <div className="flex min-h-[480px] items-center justify-center">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">Sign in</CardTitle>
          <CardDescription>
            Use the credentials created via <code>make create-platform-owner</code>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@company.com"
                disabled={loading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                disabled={loading}
              />
            </div>
            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "Signing in…" : "Continue"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Verify typecheck + tests still pass**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test
```

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/routes/sign-in.tsx
git commit -m "feat(web): wire real sign-in form to supabase signInWithPassword"
```

---

## Task 19: UserMenu + topbar integration

**Files:**
- Create: `apps/web/src/components/user-menu.tsx`
- Modify: `apps/web/src/components/app-topbar.tsx`

- [ ] **Step 1: Create `user-menu.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { LogOut } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Me = {
  id: string;
  email: string;
  role: "super_admin" | "admin" | "editor";
  is_active: boolean;
};

export function UserMenu() {
  const { user, signOut } = useAuth();
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<Me>("/api/me"),
    enabled: Boolean(user),
  });

  const initial = (me?.email ?? user?.email ?? "?").slice(0, 1).toUpperCase();
  const role = me?.role;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="User menu" className="rounded-full">
          <Avatar className="h-8 w-8">
            <AvatarFallback>{initial}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium">{me?.email ?? user?.email ?? "Loading…"}</span>
            {role && (
              <Badge variant="secondary" className="w-fit text-xs">
                {role.replace("_", " ")}
              </Badge>
            )}
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => void signOut()}>
          <LogOut className="mr-2 h-4 w-4" />
          <span>Sign out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

- [ ] **Step 2: Update `apps/web/src/components/app-topbar.tsx`** to render `UserMenu` and `ThemeToggle` in the right-side cluster

```tsx
import { useRouterState } from "@tanstack/react-router";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { SearchTrigger } from "@/components/search-trigger";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { platformNav } from "@/lib/nav";

function findLabel(pathname: string): string {
  if (pathname === "/") return "Dashboard";
  const item = platformNav.find((n) => n.to === pathname);
  if (item) return item.label;
  if (pathname === "/sign-in") return "Sign in";
  return pathname.replace(/^\//, "");
}

export function AppTopbar() {
  const { location } = useRouterState();
  const label = findLabel(location.pathname);

  return (
    <header className="bg-background sticky top-0 z-10 flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/">Xtrusio</BreadcrumbLink>
          </BreadcrumbItem>
          {location.pathname !== "/" && (
            <>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{label}</BreadcrumbPage>
              </BreadcrumbItem>
            </>
          )}
        </BreadcrumbList>
      </Breadcrumb>
      <div className="ml-auto flex items-center gap-2">
        <SearchTrigger />
        <ThemeToggle />
        <UserMenu />
      </div>
    </header>
  );
}
```

- [ ] **Step 3: Verify typecheck + tests**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/user-menu.tsx apps/web/src/components/app-topbar.tsx
git commit -m "feat(web): UserMenu in topbar (email + role badge + sign out)"
```

---

## Task 20: `/clients` — fetch + create dialog

**Files:**
- Create: `apps/web/src/components/create-client-dialog.tsx`
- Modify: `apps/web/src/routes/clients.tsx`

- [ ] **Step 1: Create `create-client-dialog.tsx`**

```tsx
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ApiError, apiFetch } from "@/lib/api";

type CreateBody = { slug: string; name: string };
type Tenant = {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  updated_at: string;
  created_by: string;
};

export function CreateClientDialog({ trigger }: { trigger: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: (body: CreateBody) =>
      apiFetch<Tenant>("/api/tenants", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["tenants"] });
      setOpen(false);
      setSlug("");
      setName("");
      toast.success("Client created");
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError && err.status === 409
          ? "That slug is already taken."
          : err instanceof Error
            ? err.message
            : "Could not create client.";
      toast.error(msg);
    },
  });

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    create.mutate({ slug, name });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Create client</DialogTitle>
          <DialogDescription>
            Onboard a new tenant. The slug appears in URLs and cannot be changed later.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="slug">Slug</Label>
            <Input
              id="slug"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase())}
              required
              pattern="^[a-z][a-z0-9-]{1,62}[a-z0-9]$"
              placeholder="acme-corp"
              disabled={create.isPending}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              minLength={1}
              maxLength={200}
              placeholder="Acme Corp"
              disabled={create.isPending}
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create client"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Update `apps/web/src/routes/clients.tsx`**

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { EmptyState } from "@/components/empty-state";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { apiFetch } from "@/lib/api";
import { CreateClientDialog } from "@/components/create-client-dialog";

type Tenant = {
  id: string;
  slug: string;
  name: string;
  created_at: string;
  updated_at: string;
  created_by: string;
};

export const Route = createFileRoute("/clients")({
  component: ClientsRoute,
});

function ClientsRoute() {
  const { data, isLoading } = useQuery({
    queryKey: ["tenants"],
    queryFn: () => apiFetch<Tenant[]>("/api/tenants"),
  });

  const action = (
    <CreateClientDialog trigger={<Button>Create client</Button>} />
  );

  if (isLoading) {
    return (
      <>
        <PageHeader
          title="Client tenants"
          description="Companies onboarded to the platform."
          action={action}
        />
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </>
    );
  }

  if (!data || data.length === 0) {
    return (
      <>
        <PageHeader
          title="Client tenants"
          description="Companies onboarded to the platform."
          action={action}
        />
        <EmptyState
          icon={Building2}
          title="No client tenants yet"
          description="Create your first one with the button above."
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Client tenants"
        description="Companies onboarded to the platform."
        action={action}
      />
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Slug</TableHead>
            <TableHead>Created</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((t) => (
            <TableRow key={t.id}>
              <TableCell className="font-medium">{t.name}</TableCell>
              <TableCell className="text-muted-foreground font-mono">{t.slug}</TableCell>
              <TableCell className="text-muted-foreground tabular-nums">
                {new Date(t.created_at).toLocaleDateString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}
```

- [ ] **Step 3: Verify typecheck + tests**

```bash
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web test
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/create-client-dialog.tsx apps/web/src/routes/clients.tsx
git commit -m "feat(web): /clients fetches /api/tenants + Create client dialog"
```

---

## Task 21: README updates

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a "Bootstrap the first user" section** near the top, after the "First-time setup" block

Insert after the existing "First-time setup" section:

```md
## Bootstrap the first super_admin

Once the local stack is up and migrations are applied, create the first platform owner via CLI:

```bash
make migrate
make create-platform-owner email=you@x.com password='SecurePass123!'
```

Then sign in at http://localhost:5173/sign-in with those credentials.
```

- [ ] **Step 2: Verify the file lints clean**

```bash
pnpm exec prettier --check README.md
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs(readme): document bootstrap + sign-in"
```

---

## Task 22: End-to-end DoD validation

This task has **no file changes**. It's the definition-of-done gate.

- [ ] **Step 1: Bring the stack down clean and back up**

```bash
make db-down
make db-up
```

- [ ] **Step 2: Migrate**

```bash
make migrate
```

Expected: prints "Running upgrade  -> 0001".

- [ ] **Step 3: Bootstrap the first owner**

```bash
make create-platform-owner email=test@example.com password='TestPass123!'
```

Expected: prints "✅ super_admin created: test@example.com".

- [ ] **Step 4: Re-running refuses**

```bash
make create-platform-owner email=second@example.com password='X' || echo "(refused as expected)"
```

Expected: error "super_admin already exists" + the "(refused as expected)" message.

- [ ] **Step 5: Run all tests**

```bash
make check
uv run pre-commit run --all-files
```

Expected: both exit 0.

- [ ] **Step 6: Manually test sign-in flow**

```bash
make dev
```

In a browser:
1. Open http://localhost:5173 — redirected to /sign-in
2. Sign in with `test@example.com` / `TestPass123!` — land on `/`
3. Open the topbar user menu — see email + "super admin" badge
4. Navigate to `/clients` — empty state with enabled "Create client" button
5. Click "Create client" — dialog opens — fill `acme` / `Acme Corp` — submit
6. Row appears in the table
7. Click user menu → "Sign out" — redirected to `/sign-in`
8. Refresh while signed in (sign in again first) — still signed in

If any step fails, fix it and re-commit before claiming done.

- [ ] **Step 7: Tear down**

```bash
make db-down
```

- [ ] **Step 8: Commit completion marker (optional)**

```bash
git commit --allow-empty -m "chore: Plan 1B complete — auth + super_admin login verified"
```

---

## Plan 1B — Definition of Done

When all of the following are true, Plan 1B is complete:

1. `make migrate` applies `0001_init_tenants_platform_users` cleanly; `make migrate-down` reverses it cleanly.
2. `make create-platform-owner email=… password=…` creates the first super_admin; refuses on second run; `--force` overrides.
3. Sign in at `/sign-in` succeeds; redirects to `/`.
4. Topbar user menu shows email + role badge.
5. `/clients` empty state renders. "Create client" dialog creates a tenant; row appears in the table.
6. Refresh after sign-in: still signed in.
7. Sign-out: returned to `/sign-in`.
8. `GET /api/me` without token → 401. With invalid token → 401. With valid super_admin → 200.
9. `GET /api/tenants` as non-super_admin → 403.
10. `POST /api/tenants` with duplicate slug → 409. With invalid slug → 422.
11. All backend tests pass: `uv run pytest apps/api/tests` exits 0 (≥ 13 tests).
12. All frontend tests pass: `pnpm --filter @xtrusio/web test` exits 0.
13. `make check` exits 0; `uv run pre-commit run --all-files` passes.
14. Zero hardcoded colors, zero `.js`/`.jsx`/`.mjs`/`.cjs` files, zero mock data — existing rules still pass.
15. The repo has zero `.github/workflows/*` files (project policy).

---

## Notes for the Engineer

- **TDD discipline**: every endpoint and the JWT middleware are TDD-driven (test → fail → impl → pass). The bootstrap CLI is also TDD'd. Routes use real Postgres via the `db_session` fixture (transaction-rolled-back per test).
- **Why use real Postgres in tests instead of an in-memory SQLite?** Our migration uses citext, custom enums, RLS, triggers, and FKs to `auth.users`. Only Postgres supports all of this. Tests run against the local Supabase Postgres on `:54322`. Each test gets a transaction that's rolled back.
- **`auth.users` insert in fixtures**: Supabase manages this table; in production the bootstrap script + invite flows are the only writers. In tests we insert directly to satisfy the FK without involving GoTrue.
- **`disableTransitionOnChange` is on `ThemeProvider`**: prevents flash of cross-fade animations when OS-level theme changes (already from Plan 1A.5).
- **JWT secret**: `SUPABASE_JWT_SECRET` from `.env` (populated by `make env`) must match what Supabase signs with. Don't hand-edit it — re-run `make env-force` if Supabase ever rotates it.
- **What about `tenant_users`?** They're deliberately NOT in this plan. The tenant invite + tenant_user model lands in the next plan, where we'll also wire up real RLS policy enforcement using `app.tenant_id`.
- **Don't skip Task 22.** The end-to-end gate catches issues that pass unit tests but break the user flow.

---

## What This Plan Does NOT Include

These are intentionally deferred:

- `tenant_users` table + tenant invite flow (next plan)
- Magic link login, password reset, email verification (future)
- MFA, OAuth (Google/GitHub) (future)
- Full RBAC enforcement for `admin` / `editor` roles (future — only super_admin in v1)
- Impersonation (Plan 1F)
- Audit log writes (Plan 1F)
- Realtime subscriptions
- GitHub Actions / CI runners (deferred per project policy)
