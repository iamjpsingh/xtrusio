# Spec #5 — Auth + super_admin login (MVP) Design

**Status:** draft, awaiting user review
**Date:** 2026-05-08
**Owner:** platform team
**Depends on:** spec #1 (multi-tenant foundation), spec #4 (frontend foundation), Plan 1A (scaffold), Plan 1A.5 (frontend shell)
**Blocks:** Plan for tenant invites, Plan 1D full RBAC, Plan 1F impersonation/audit log writes
**Memory cross-refs:** `feedback_no_demo_data.md`, `project_auth_flow_architecture.md`, `feedback_frontend_typescript_only.md`, `project_dev_runtime_choice.md`

---

## 1. Purpose & Scope

### 1.1 Purpose

Get the platform's first authenticated user — the **super_admin** — bootstrapped, signed in, and managing real data through the real UI. Establishes the auth-flow plumbing every subsequent plan (tenant invites, RBAC, impersonation, audit) builds on.

The single demonstrable outcome:

> `make create-platform-owner email=you@x.com password=…` → sign in at `/sign-in` → land on `/` → see role in topbar → create + list tenants on `/clients` → sign out.

### 1.2 In scope

1. **Tenants table** + RLS infrastructure (the table is needed even though only super_admin uses it in v1; future plans depend on this shape).
2. **`platform_users` table** with `role` enum (`super_admin`, `admin`, `editor`); only `super_admin` populated in v1.
3. **Bootstrap CLI** (`make create-platform-owner`) — typer-based Python script. Calls Supabase Admin API to create auth user, inserts `platform_users` row.
4. **FastAPI JWT middleware** — validates Supabase-issued JWT on every protected endpoint, returns enriched user.
5. **`/api/me`** — returns role-enriched user.
6. **`/api/tenants`** — `GET` (list, super_admin only) + `POST` (create, super_admin only).
7. **Frontend auth context** — `useAuth()` hook backed by `@supabase/supabase-js`.
8. **Sign-in flow** — real `signInWithPassword` call; redirect to `/` on success; error UX.
9. **Route guard** — root layout redirects unauthenticated users to `/sign-in`.
10. **Topbar user menu** — email + role + sign-out, fed by `/api/me` via TanStack Query.
11. **`/clients` page** — fetches real `/api/tenants`; "Create client" dialog wired up.
12. **Supabase local config** — `enable_signup = false`, `enable_confirmations = false` (invite-only, no email verification locally).
13. **Tests** — JWT middleware unit tests; endpoint auth tests; RLS isolation test on tenants; bootstrap idempotency test; frontend sign-in + auth-provider tests.

### 1.3 Out of scope (deferred to later plans)

| Concern | Lands in |
|---|---|
| `tenant_users` table | next plan after this |
| Tenant invite flow (admin invites a tenant owner) | Plan 1E |
| Magic link login, password reset, email verification | future plan |
| MFA, OAuth (Google/GitHub) | future plan |
| RBAC enforcement for `admin` / `editor` roles | future plan (only super_admin used in v1) |
| Impersonation | Plan 1F |
| Audit log writes (`platform_audit_log`, `tenant_activity_log`, `worker_log` tables and triggers) | Plan 1F |
| Realtime subscriptions | spec #2 implementation plan |
| Frontend pages other than `/sign-in`, `/`, `/clients` are TOUCHED for layout but not for new functionality |

### 1.4 Non-goals

- Building a "demo" or "showcase" workflow with mock tenants.
- Re-implementing what Supabase Auth already does (passwords, JWT issuance, refresh, magic links). Per memory `project_auth_flow_architecture.md`, FastAPI does not proxy auth ceremony.
- Custom invite emails, branded transactional email — deferred until tenant invite flow.

---

## 2. Architecture

### 2.1 Auth flow shape (per memory rule)

```
Browser                       FastAPI                          Supabase
   │                             │                                │
   │  signInWithPassword(email,  │                                │
   │  password)  via supabase-js │                                │
   ├────────────────────────────────────────────────────────────►│
   │                             │                          [verify]
   │  ◄────  JWT + refresh token (stored by supabase-js in localStorage)
   │                             │                                │
   │  GET /api/me                │                                │
   │  Authorization: Bearer <JWT>│                                │
   ├────────────────────────────►│                                │
   │                             │  decode JWT (HS256 +           │
   │                             │  SUPABASE_JWT_SECRET);          │
   │                             │  extract sub (= auth.users.id) │
   │                             │  SELECT FROM platform_users    │
   │                             │  WHERE id = sub                │
   │  ◄──── 200 {user_id, email, role: "super_admin", ...}        │
   │                             │                                │
```

### 2.2 Key files (new)

```
apps/api/src/xtrusio_api/
├── core/
│   ├── __init__.py
│   ├── config.py                  # pydantic-settings (~80 LoC)
│   ├── db.py                      # async engine + sessionmaker (~80 LoC)
│   ├── auth.py                    # JWT middleware + dependencies (~150 LoC)
│   └── rls.py                     # SET LOCAL helpers (~60 LoC)
├── models/
│   ├── __init__.py
│   ├── tenant.py                  # SQLAlchemy + Pydantic (~150 LoC)
│   └── platform_user.py           # SQLAlchemy + Pydantic + role enum (~150 LoC)
├── routes/
│   ├── __init__.py
│   ├── me.py                      # GET /api/me (~80 LoC)
│   └── tenants.py                 # GET/POST /api/tenants (~180 LoC)
├── scripts/
│   ├── __init__.py
│   └── bootstrap.py               # typer CLI (~200 LoC)
└── main.py                        # mount routers, lifespan (~100 LoC)

apps/api/migrations/
├── env.py                         # Alembic env
├── script.py.mako
└── versions/
    └── 0001_init_tenants_platform_users.py   # creates enum + 2 tables + RLS (~250 LoC)

apps/api/tests/
├── core/
│   ├── test_auth.py               # JWT middleware tests
│   └── test_rls.py
├── routes/
│   ├── test_me.py
│   └── test_tenants.py
├── scripts/
│   └── test_bootstrap.py
└── conftest.py                    # async db fixture, jwt fixture, supabase client mocks

apps/web/src/
├── lib/
│   ├── supabase.ts                # single supabase-js client (~40 LoC)
│   ├── auth.tsx                   # AuthProvider + useAuth hook (~150 LoC)
│   ├── api.ts                     # apiFetch wrapper (~80 LoC)
│   └── query-client.ts            # TanStack Query client (~30 LoC)
├── components/
│   ├── user-menu.tsx              # topbar user menu (replaces ThemeToggle in topbar) (~120 LoC)
│   ├── auth-guard.tsx             # route guard inside __root (~50 LoC)
│   └── create-client-dialog.tsx   # /clients → "Create client" dialog (~180 LoC)
├── routes/
│   ├── __root.tsx                 # MODIFIED: wrap in AuthProvider + QueryClientProvider; auth guard
│   ├── sign-in.tsx                # MODIFIED: wire real signInWithPassword
│   └── clients.tsx                # MODIFIED: fetch /api/tenants; render rows or empty state
└── (other route files unchanged)
```

### 2.3 Modified files

- `apps/api/pyproject.toml` — add `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `python-jose[cryptography]`, `pydantic-settings`, `supabase`, `typer`.
- `apps/web/package.json` — add `@supabase/supabase-js`, `@tanstack/react-query`.
- `Makefile` — add `create-platform-owner` target, `migrate` / `migrate-down` targets.
- `supabase/config.toml` — disable signup + email confirmation.
- `apps/api/src/xtrusio_api/main.py` — mount new routers, lifespan for DB engine.
- `.env.example` — already has `SUPABASE_JWT_SECRET`, `SUPABASE_SECRET_KEY`, `DATABASE_URL`. No new vars.
- `README.md` — document the bootstrap step + sign-in flow.
- `apps/api/src/xtrusio_api/__init__.py` — package version export.

---

## 3. Data Model

### 3.1 Migration `0001_init_tenants_platform_users`

```python
# apps/api/migrations/versions/0001_init_tenants_platform_users.py
"""init: tenants + platform_users + platform_role enum"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Enum
    op.execute("CREATE TYPE platform_role AS ENUM ('super_admin', 'admin', 'editor')")

    # 2. tenants
    op.execute("""
        CREATE TABLE tenants (
            id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        citext NOT NULL UNIQUE,
            name        text NOT NULL,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now(),
            created_by  uuid NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
            CHECK (slug ~ '^[a-z][a-z0-9-]{1,62}[a-z0-9]$')
        )
    """)
    op.execute("CREATE INDEX tenants_created_by_idx ON tenants(created_by)")

    # 3. platform_users
    op.execute("""
        CREATE TABLE platform_users (
            id                uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
            email             citext NOT NULL UNIQUE,
            role              platform_role NOT NULL,
            is_active         boolean NOT NULL DEFAULT true,
            created_at        timestamptz NOT NULL DEFAULT now(),
            updated_at        timestamptz NOT NULL DEFAULT now(),
            last_sign_in_at   timestamptz
        )
    """)
    op.execute("CREATE INDEX platform_users_role_idx ON platform_users(role)")

    # 4. RLS — defense-in-depth, NOT primary access control in v1
    #
    # Honest accounting: FastAPI connects to Postgres as the `postgres` superuser
    # (DATABASE_URL points at supabase-postgres). Superuser BYPASSES RLS entirely.
    # Therefore in v1, RLS is a defense-in-depth layer for direct DB access
    # (Supabase Studio, future Realtime subscriptions, future PostgREST exposure
    # if we ever turn it on), NOT the primary gate for our API.
    #
    # The PRIMARY gate for /api/* is FastAPI's `require_super_admin` Depends.
    # The RLS policies below protect against accidents at the DB layer.
    #
    # When we move to a least-privilege DB role for FastAPI in a future plan,
    # OR add tenant_users with non-super-admin scoping, we'll wire `SET LOCAL
    # app.tenant_id` into the request middleware and tighten the policies.

    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    # Allow `authenticated` role (used by Supabase PostgREST + Realtime) full
    # access ONLY if they're a super_admin per the platform_users join.
    op.execute("""
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
    """)
    # Future plan adds a tenant-scoped policy that uses
    # current_setting('app.tenant_id') for non-super-admin tenant_users.

    op.execute("ALTER TABLE platform_users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY platform_users_self_select ON platform_users
            FOR SELECT
            TO authenticated
            USING (id = auth.uid())
    """)
    op.execute("""
        CREATE POLICY platform_users_super_admin_all ON platform_users
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
    """)
    # Note: `service_role` (used by FastAPI's bootstrap script via Supabase
    # Admin API) bypasses RLS by default. FastAPI's normal request path uses
    # the `postgres` superuser via DATABASE_URL — also bypasses RLS.

    # 7. Updated-at triggers
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER tenants_set_updated_at
            BEFORE UPDATE ON tenants
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE TRIGGER platform_users_set_updated_at
            BEFORE UPDATE ON platform_users
            FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS platform_users_set_updated_at ON platform_users")
    op.execute("DROP TRIGGER IF EXISTS tenants_set_updated_at ON tenants")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP TABLE IF EXISTS platform_users")
    op.execute("DROP TABLE IF EXISTS tenants")
    op.execute("DROP TYPE IF EXISTS platform_role")
```

### 3.2 SQLAlchemy + Pydantic models

```python
# apps/api/src/xtrusio_api/models/platform_user.py
import enum
from datetime import datetime
from uuid import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean, Enum as SAEnum, DateTime
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase
from pydantic import BaseModel, ConfigDict, EmailStr


class Base(AsyncAttrs, DeclarativeBase): ...


class PlatformRole(str, enum.Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    EDITOR = "editor"


class PlatformUser(Base):
    __tablename__ = "platform_users"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    role: Mapped[PlatformRole] = mapped_column(
        SAEnum(PlatformRole, name="platform_role", create_constraint=False, native_enum=True),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PlatformUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    role: PlatformRole
    is_active: bool
    created_at: datetime
    last_sign_in_at: datetime | None
```

Equivalent file `models/tenant.py` for `Tenant` + `TenantIn` (slug + name) + `TenantOut`.

---

## 4. Backend Implementation

### 4.1 `core/config.py` — Pydantic Settings

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    process_role: str = Field(default="api", alias="XTRUSIO_PROCESS_ROLE")
    database_url: str = Field(alias="DATABASE_URL")
    valkey_url: str = Field(alias="VALKEY_URL")

    supabase_url: str = Field(alias="SUPABASE_URL")
    supabase_anon_key: str = Field(alias="SUPABASE_ANON_KEY")
    supabase_service_role_key: str = Field(alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_jwt_secret: str = Field(alias="SUPABASE_JWT_SECRET")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


def get_settings() -> Settings:
    return Settings()
```

### 4.2 `core/db.py` — Async engine

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import sessionmaker
from .config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
```

### 4.3 `core/auth.py` — JWT validation + dependencies

```python
from typing import Annotated
from uuid import UUID
from fastapi import Depends, Header, HTTPException, status
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .config import get_settings
from .db import get_db
from ..models.platform_user import PlatformUser, PlatformRole


_ALGO = "HS256"
_AUDIENCE = "authenticated"


class CurrentUser:
    """Per-request principal."""
    def __init__(self, user_id: UUID, email: str, role: PlatformRole, is_active: bool) -> None:
        self.user_id = user_id
        self.email = email
        self.role = role
        self.is_active = is_active


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = ...,
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
    user_id = UUID(sub)

    row = (
        await db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not provisioned")
    if not row.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user disabled")
    return CurrentUser(row.id, row.email, row.role, row.is_active)


async def require_super_admin(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if user.role != PlatformRole.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "super_admin required")
    return user
```

### 4.4 Routes

```python
# apps/api/src/xtrusio_api/routes/me.py
from fastapi import APIRouter, Depends
from typing import Annotated
from ..core.auth import CurrentUser, get_current_user
from ..models.platform_user import PlatformUserOut

router = APIRouter(prefix="/api", tags=["me"])

@router.get("/me", response_model=PlatformUserOut)
async def me(user: Annotated[CurrentUser, Depends(get_current_user)]) -> dict:
    return {
        "id": user.user_id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": ...,    # joined from db row in actual impl
        "last_sign_in_at": ...,
    }
```

```python
# apps/api/src/xtrusio_api/routes/tenants.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from ..core.auth import CurrentUser, require_super_admin
from ..core.db import get_db
from ..models.tenant import Tenant, TenantIn, TenantOut

router = APIRouter(prefix="/api/tenants", tags=["tenants"])

@router.get("", response_model=list[TenantOut])
async def list_tenants(
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TenantOut]:
    rows = (await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))).scalars().all()
    return [TenantOut.model_validate(r) for r in rows]

@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantIn,
    user: Annotated[CurrentUser, Depends(require_super_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantOut:
    tenant = Tenant(slug=body.slug, name=body.name, created_by=user.user_id)
    db.add(tenant)
    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "slug already taken") from e
    await db.refresh(tenant)
    return TenantOut.model_validate(tenant)
```

### 4.5 Bootstrap CLI (`scripts/bootstrap.py`)

```python
import asyncio
import sys
from typing import Annotated
import typer
from supabase import create_client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import get_settings
from ..core.db import SessionLocal
from ..models.platform_user import PlatformUser, PlatformRole

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def create_platform_owner(
    email: Annotated[str, typer.Option(..., "--email", help="Owner email")],
    password: Annotated[str, typer.Option(..., "--password", help="Initial password")],
    force: Annotated[bool, typer.Option("--force", help="Override existing super_admin check")] = False,
) -> None:
    """Create the very first platform super_admin (Supabase auth user + platform_users row)."""
    asyncio.run(_run(email=email, password=password, force=force))


async def _run(*, email: str, password: str, force: bool) -> None:
    settings = get_settings()
    sb = create_client(settings.supabase_url, settings.supabase_service_role_key)

    async with SessionLocal() as db:  # type: AsyncSession
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

        # Create Supabase auth user (idempotent: catch existing)
        result = sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        auth_user = result.user
        if auth_user is None:
            typer.echo("❌ Supabase did not return a user.", err=True)
            sys.exit(2)

        db.add(
            PlatformUser(
                id=auth_user.id,
                email=email,
                role=PlatformRole.SUPER_ADMIN,
                is_active=True,
            )
        )
        await db.commit()

    typer.echo(f"✅ super_admin created: {email}")
    typer.echo(f"   Sign in at http://localhost:5173/sign-in")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

Makefile addition:

```makefile
create-platform-owner:
	@if [ -z "$(email)" ] || [ -z "$(password)" ]; then \
		echo "Usage: make create-platform-owner email=you@x.com password=..."; \
		exit 1; \
	fi
	XTRUSIO_PROCESS_ROLE=api uv run --directory apps/api \
		python -m xtrusio_api.scripts.bootstrap create-platform-owner \
		--email "$(email)" --password "$(password)"

migrate:
	uv run --directory apps/api alembic upgrade head

migrate-down:
	uv run --directory apps/api alembic downgrade -1
```

### 4.6 Alembic config (`apps/api/alembic.ini` + `apps/api/migrations/env.py`)

Standard async Alembic setup pointing at `DATABASE_URL` from settings. Migrations run inside the existing `apps/api` package (so they share the model imports).

---

## 5. Frontend Implementation

### 5.1 Supabase client (`apps/web/src/lib/supabase.ts`)

```ts
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
if (!url || !anonKey) {
  throw new Error("VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY must be set");
}
export const supabase = createClient(url, anonKey, {
  auth: {
    persistSession: true,
    autoRefreshToken: true,
    detectSessionInUrl: false,
  },
});
```

### 5.2 Auth context (`apps/web/src/lib/auth.tsx`)

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
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
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return { error: error?.message ?? null };
  };

  const signOut = async () => {
    await supabase.auth.signOut();
  };

  return (
    <AuthContext.Provider value={{ user: session?.user ?? null, session, loading, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
```

### 5.3 API helper (`apps/web/src/lib/api.ts`)

```ts
import { supabase } from "./supabase";

const baseUrl = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API ${status}: ${JSON.stringify(body)}`);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { data: { session } } = await supabase.auth.getSession();
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
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

### 5.4 Auth guard (`apps/web/src/components/auth-guard.tsx`)

Simple component wrapping `Outlet`. If session is loading → spinner. If no session and route ≠ `/sign-in` → `<Navigate to="/sign-in" />`. If session and route = `/sign-in` → `<Navigate to="/" />`.

### 5.5 Sign-in form (`apps/web/src/routes/sign-in.tsx` — modified)

Replaces the placeholder with a real form: `useState` for email/password, `useAuth().signIn`, error display via `sonner` toast on failure, navigate to `/` on success.

### 5.6 User menu (`apps/web/src/components/user-menu.tsx`)

shadcn `DropdownMenu` triggered by an avatar. Fetches `/api/me` via TanStack Query. Shows email + role badge. Sign-out item.

### 5.7 `/clients` (modified)

Uses TanStack Query to fetch `/api/tenants`. Renders shadcn `Table` with rows OR `EmptyState` if empty. "Create client" button enabled — opens `CreateClientDialog` (form with `slug`, `name` fields, Zod-validated, calls `POST /api/tenants`, invalidates the list query on success).

### 5.8 `/users` and `/sign-in` route guard exception

`/sign-in` is the only route that may render without a session. The auth guard handles this by allowlisting `/sign-in`.

---

## 6. Supabase local config tweaks (`supabase/config.toml`)

```toml
[auth]
enable_signup = false                    # invite-only

[auth.email]
enable_signup = false
enable_confirmations = false             # no email-verification step locally
```

These mean: only the bootstrap script + future invite flow can create users. No public sign-up form on the frontend will ever succeed.

---

## 7. Tests

### 7.1 Backend (pytest)

| Test | Asserts |
|---|---|
| `test_auth_missing_token` | 401 when no Authorization header |
| `test_auth_malformed_token` | 401 when Bearer token isn't a valid JWT |
| `test_auth_expired_token` | 401 when JWT exp < now |
| `test_auth_unprovisioned_user` | 401 when JWT valid but no platform_users row |
| `test_auth_disabled_user` | 403 when is_active=False |
| `test_auth_super_admin_required` | 403 when role != super_admin |
| `test_me_returns_user` | 200 + correct shape with valid token |
| `test_tenants_list_empty` | 200 + [] |
| `test_tenants_create` | 201 + row visible in list afterwards |
| `test_tenants_slug_conflict` | 409 on duplicate slug |
| `test_tenants_not_super_admin` | 403 when role=admin/editor |
| `test_rls_tenants_isolation` | direct DB query connected as `authenticated` role (NOT superuser) with `request.jwt.claims` set for a non-super-admin user returns 0 rows even when rows exist |
| `test_bootstrap_creates_owner` | first run creates user + platform_users row |
| `test_bootstrap_refuses_second` | second run errors unless --force |

Fixtures in `conftest.py`:
- `db_session`: per-test transaction, rolled back at end (no real Supabase auth user needed for most).
- `valid_jwt`: produces a signed JWT with the test SUPABASE_JWT_SECRET, configurable `sub` and `role`.
- `super_admin_user`: ensures a `platform_users` row exists with role=super_admin and a matching JWT.

### 7.2 Frontend (Vitest)

| Test | Asserts |
|---|---|
| `apiFetch attaches Authorization` | when session exists, header present |
| `apiFetch throws ApiError on 401` | rejects with status=401 |
| `AuthProvider populates session` | after `signIn`, useAuth returns the session |
| `AuthProvider clears on signOut` | session = null after signOut |
| `sign-in shows error on bad credentials` | toast error, no redirect |
| `sign-in redirects on success` | navigate to "/" called |
| `clients route empty state` | when GET returns [], EmptyState renders |
| `clients route renders rows` | when GET returns 2 tenants, table has 2 rows |

Frontend tests mock `supabase.auth.*` and `fetch`. No real Supabase contact.

### 7.3 Coverage target

≥ 80% on new code per `ENGINEERING_PRINCIPLES` section 9.

---

## 8. Local Verification (DoD commands)

```bash
make install
make db-up                                  # Supabase + Valkey
make migrate                                # apply 0001 migration
make create-platform-owner email=you@x.com password=SecurePass123!
make dev                                    # API + web

# In a second shell:
curl -s http://localhost:8000/api/me                                     # 401
TOKEN=...                                                                 # paste from supabase status / browser
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/me   # 200 super_admin

# In browser: http://localhost:5173/sign-in
# Sign in → land on /
# Topbar shows email + super_admin badge
# Navigate to /clients → empty state
# Click "Create client" → fill slug + name → submit → row appears
# Sign out → /sign-in
```

---

## 9. Open Questions

1. **Email confirmation**: deliberately disabled locally. In self-hosted prod we'll enable it and route through Resend (deferred to deploy plan).
2. **Refresh token rotation**: handled by `supabase-js` automatically. We just trust the access token in JWT middleware.
3. **JWT expiry**: Supabase default is 1 hour for access tokens. Frontend's auto-refresh handles continuity.
4. **`auth.users` → `platform_users` cascade on delete**: `ON DELETE CASCADE`. Deleting a Supabase auth user also drops their platform_users row. Reasonable for v1.
5. **`tenants.created_by` references `auth.users(id)`**: not `platform_users.id`, because in the future tenant_users may also create tenants (via impersonation). This avoids changing the FK later.

---

## 10. Success Criteria

The plan is "v1 done" when:

1. `make migrate` applies `0001` cleanly; `make migrate-down` reverses it cleanly.
2. `make create-platform-owner email=… password=…` creates the first super_admin; refuses on second run; `--force` overrides.
3. Sign in at `/sign-in` with bootstrap credentials succeeds; redirects to `/`.
4. Topbar user menu shows email + role badge.
5. `/clients` empty state renders. "Create client" dialog creates a tenant; row appears.
6. Refresh after sign-in: still signed in.
7. Sign-out: returned to `/sign-in`.
8. `GET /api/me` without token → 401. With invalid token → 401. With valid super_admin token → 200.
9. `GET /api/tenants` as non-super_admin → 403.
10. RLS isolation test passes: a non-super-admin authenticated session sees zero `tenants` rows even when rows exist.
11. `make check` exits 0; `uv run pre-commit run --all-files` passes; bootstrap test idempotency passes.
12. Zero hardcoded colors, zero `.js` files, zero mock data — existing rules still pass.
13. README updated with bootstrap step + sign-in flow.

---

## 11. Cross-References

- Spec #1 — `docs/superpowers/specs/2026-05-07-multi-tenant-foundation-design.md` (tenancy, identity, RBAC at high level)
- Spec #4 — `docs/superpowers/specs/2026-05-08-frontend-foundation-shell-design.md` (where the routes/layout we're modifying came from)
- Memory: `feedback_no_demo_data.md`, `project_auth_flow_architecture.md`, `feedback_frontend_typescript_only.md`, `project_dev_runtime_choice.md`, `feedback_ci_cd_after_local.md`, `project_production_architecture.md`
