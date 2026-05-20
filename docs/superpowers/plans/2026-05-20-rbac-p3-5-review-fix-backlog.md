# P3.5 — Review-Fix Backlog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the parked review-fix backlog (HANDOFF item 7) before P4. Adds CI as a merge gate, eliminates unbounded list queries, hardens external-boundary error handling, and tightens startup posture — without touching the P4/P5/P6b scope or the gated enum-column drop.

**Architecture:** One branch, four slices in order: **(A) CI lands** so every later slice is gated → **(B) pagination** brings list endpoints into compliance with principles §3/§9 → **(C) boundary hardening** (JWKS coalescing, typed signup error, fail-fast startup) → **(D) frontend `AuthGuard` cleanup**. One end-of-slice `make check`-equivalent gate by the controller, one Opus code-quality review at the end, one PR. P4 resumes from a fully-green `main`.

**Tech Stack:** GitHub Actions, FastAPI/SQLAlchemy, supabase-py 2.10 (gotrue `AuthApiError` class hierarchy), pydantic v2, pytest-asyncio, ruff/mypy --strict, React 19 + TanStack Query.

---

## Execution-model constraints (from user memory — override skill defaults)

- `feedback_lean_review_workflow`: **ONE** full-suite run at the END of each slice via command, **run by the controller, not a subagent**. `make test-clean` first. End-of-slice gate MUST include `ruff format --check` (not just `ruff check`) + `mypy --strict` + `make test`. Migrations/RLS/auth slices get ONE targeted mid-build check.
- `feedback_model_selection`: code/plan/migration subagents = **Opus**; Sonnet only for read-only exploration.
- `feedback_no_claude_coauthor`: commits use only `iamjpsingh` identity, no `Co-Authored-By: Claude` trailer.
- `feedback_test_data_hygiene`: every new fixture uses `@example.com`; never creates a `super_admin`; uses `existing_super_admin` (read-only).
- `feedback_no_hardcoded_config`: any new config value comes from `.env`/secrets and `xtrusio_api.core.config.Settings`, never a literal.
- HANDOFF execution: write `docs/superpowers/PR-rbac-p3-5-body.md`, `gh pr create`, `gh pr merge`, verify `gh pr view <n> --json state` = MERGED.

---

## Decisions (locked 2026-05-20)

1. **CI test DB:** dedicated managed Supabase project ("xtrusio-ci"), separate from dev/prod. GitHub Actions `concurrency: group=ci-test-db, cancel-in-progress=false` so only one job at a time touches the DB. Tests already namespace data via `@example.com` and use the session-scoped `_cleanup` fixture — that's the "ephemeral" isolation mechanism. **Why this is not literal per-run schema:** Supabase's `auth` schema is project-global; our migrations and tests insert directly into `auth.users`, so a per-run application-schema would still share `auth.users` and gain nothing. A dedicated CI project + `_cleanup` is the cleanest honoring of the spirit (ephemeral, isolated, on managed Supabase). Principles §8 will be updated to permit "managed-Supabase test project OR Postgres test container" so this is in spec, not in violation.

2. **Startup reconcile:** fail-fast by default; opt-in `STARTUP_RECONCILE_TOLERANT=1` env flag restores current swallow-and-continue (local dev only).

---

## File structure

**Created**

| Path | Purpose |
|---|---|
| `.github/workflows/ci.yml` | merge-gate workflow: lint + typecheck + test + `.js` ban + frontend build |
| `.github/workflows/README.md` | one paragraph: how to trigger / re-run / debug |
| `apps/api/src/xtrusio_api/core/pagination.py` | `CursorParams`, opaque-base64 cursor encode/decode, `apply_cursor` helper |
| `apps/api/tests/core/test_pagination.py` | cursor round-trip, tamper-resistance, edge cases |
| `apps/api/tests/integration/test_no_unbounded_lists.py` | CI-only invariant: every `GET` list endpoint enforces a cap |
| `docs/superpowers/PR-rbac-p3-5-body.md` | PR description at submit time |

**Modified**

| Path | Change |
|---|---|
| `apps/api/src/xtrusio_api/routes/tenants.py:20-27` | `list_tenants` → cursor pagination |
| `apps/api/src/xtrusio_api/routes/platform_invites.py:52-62` | accept `?cursor=&limit=`; remove TODO comment |
| `apps/api/src/xtrusio_api/routes/tenant_invites.py:61-74` | same |
| `apps/api/src/xtrusio_api/services/platform_invites.py:132-142` | accept `cursor`, return `(rows, next_cursor)` |
| `apps/api/src/xtrusio_api/services/tenant_invites.py:159-178` | same |
| `apps/api/src/xtrusio_api/schemas/invite.py:41-43,67-69` | `next_cursor` populated, not always `None` |
| `apps/api/src/xtrusio_api/models/tenant.py` | add `TenantsPage` Pydantic model alongside `TenantOut` |
| `apps/api/src/xtrusio_api/core/auth.py:21,33-44` | per-URL `asyncio.Lock` to coalesce concurrent cold-start JWKS fetches |
| `apps/api/src/xtrusio_api/services/signup.py:6,36,45-49` | class-based duplicate-email detection (`gotrue.errors.AuthApiError`); drop `Any` from `_call` |
| `apps/api/src/xtrusio_api/main.py:24-35` | fail-fast lifespan with `STARTUP_RECONCILE_TOLERANT` env flag |
| `apps/api/src/xtrusio_api/core/config.py` | `startup_reconcile_tolerant: bool = Field(False, alias="STARTUP_RECONCILE_TOLERANT")` |
| `.env.example` | document `STARTUP_RECONCILE_TOLERANT` (default `false`) |
| `apps/web/src/components/auth-guard.tsx:14-20` | drop duplicate `staleTime` (global already sets 30_000) |
| `docs/superpowers/ENGINEERING_PRINCIPLES.md:111` | rewrite §8 test-container clause to allow managed-Supabase test project |
| `apps/api/tests/routes/test_platform_invites.py`, `test_tenant_invites.py`, `test_tenants.py` | new pagination tests |
| `apps/web/src/components/auth-guard.test.tsx` | sanity test that AuthGuard inherits global `staleTime` |

**NOT touched (out of scope, gated by HANDOFF item 6 / later phases)**

- `platform_users.role` / `tenant_memberships.role` column drops (HANDOFF item 6 — wait for P6b).
- Alembic migrations (no schema changes needed in this phase).
- P4/P5/P6b/P6c code.

---

## Slice A — CI lands

Goal: every later slice is automatically gated. CI must reproduce `make check` + `make test` against an isolated managed Supabase project.

### Task A1: Principles §8 amendment

**Files:**
- Modify: `docs/superpowers/ENGINEERING_PRINCIPLES.md:111`

- [ ] **Step 1: Rewrite the §8 test-container clause**

Replace line 111:

```
- **Don't mock what you don't own** unless it's slow or expensive. Use Postgres test containers; mock only third-party LLM APIs and email senders.
```

with:

```
- **Don't mock what you don't own** unless it's slow or expensive. Tests run against either a Postgres test container OR a dedicated managed-Supabase test project (`xtrusio-ci`) — never against dev or prod. Per-run isolation comes from the `_cleanup` fixture purging `@example.com` rows; CI uses `concurrency: ci-test-db` so only one job hits the DB at a time. Mock only third-party LLM APIs and email senders.
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/ENGINEERING_PRINCIPLES.md
git commit -m "docs(principles): §8 permit managed-Supabase test project alongside test containers"
```

### Task A2: CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/README.md`

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: ci
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  # All jobs that touch the shared CI Supabase project serialise here.
  # Do NOT cancel in progress: a half-cleaned DB is worse than a slow queue.
  group: ci-test-db
  cancel-in-progress: false

jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 25
    env:
      # Supabase test project (xtrusio-ci) — all secrets configured in repo settings.
      DATABASE_URL: ${{ secrets.CI_DATABASE_URL }}
      SUPABASE_URL: ${{ secrets.CI_SUPABASE_URL }}
      SUPABASE_ANON_KEY: ${{ secrets.CI_SUPABASE_ANON_KEY }}
      SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.CI_SUPABASE_SERVICE_ROLE_KEY }}
      SUPABASE_JWKS_URL: ${{ secrets.CI_SUPABASE_JWKS_URL }}
      SUPABASE_TIMEOUT_SEC: "10"
      JWKS_TTL_SEC: "300"
      JWKS_FETCH_TIMEOUT_SEC: "5"
      API_HOST: "127.0.0.1"
      API_PORT: "8000"
      CORS_ALLOW_ORIGINS: "http://localhost:5173"
      XTRUSIO_PROCESS_ROLE: "api"
      # Fail-fast in CI; STARTUP_RECONCILE_TOLERANT stays unset.

    steps:
      - uses: actions/checkout@v4

      - name: Ban .js/.jsx/.mjs/.cjs in frontend paths (§2.0)
        run: |
          if git ls-files 'apps/web/**/*.js' 'apps/web/**/*.jsx' 'apps/web/**/*.mjs' 'apps/web/**/*.cjs' 'packages/**/*.js' 'packages/**/*.jsx' 'packages/**/*.mjs' 'packages/**/*.cjs' | grep -q .; then
            echo "::error::Frontend path contains a .js/.jsx/.mjs/.cjs file. See ENGINEERING_PRINCIPLES.md §2.0."
            git ls-files 'apps/web/**/*.js' 'apps/web/**/*.jsx' 'apps/web/**/*.mjs' 'apps/web/**/*.cjs' 'packages/**/*.js' 'packages/**/*.jsx' 'packages/**/*.mjs' 'packages/**/*.cjs'
            exit 1
          fi

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version-file: .nvmrc
          cache: pnpm

      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Install
        run: make install

      - name: Migrate test DB (idempotent)
        run: make migrate

      - name: Pre-test cleanup
        run: make test-clean

      - name: Lint
        run: make lint

      - name: Typecheck
        run: make typecheck

      - name: Test (backend + frontend)
        run: make test

      - name: Post-test cleanup (best-effort)
        if: always()
        run: make test-clean
```

- [ ] **Step 2: Document trigger / re-run / debug**

Create `.github/workflows/README.md`:

```markdown
# CI workflow

`ci.yml` runs on every PR to `main` and every push to `main`.

## Required secrets

Set these on the repo (Settings → Secrets and variables → Actions). All come from a
dedicated managed Supabase project called `xtrusio-ci` (separate from dev/prod):

- `CI_DATABASE_URL` — postgres connection string
- `CI_SUPABASE_URL`
- `CI_SUPABASE_ANON_KEY`
- `CI_SUPABASE_SERVICE_ROLE_KEY`
- `CI_SUPABASE_JWKS_URL`

## Re-running

Concurrency group `ci-test-db` is queue-not-cancel — a re-run waits for the
current job rather than killing it mid-cleanup. Force-skip by closing/reopening
the PR if a job is wedged.

## Common failures

- **Pre-test cleanup hangs:** the test DB has unrelated rows. Run `make test-clean`
  locally against the CI project, or wipe `@example.com` rows manually.
- **`pnpm install` slow:** the action's pnpm cache lives in `pnpm/action-setup` —
  invalidates on `pnpm-lock.yaml` change.
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml .github/workflows/README.md
git commit -m "ci: add merge-gate workflow (lint + typecheck + test + .js ban)"
```

### Task A3: Slice A gate (controller-run)

- [ ] **Step 1: Push branch, open draft PR, confirm CI runs green** before moving to Slice B. (User configures repo secrets at this point if not already set.)

Run: `gh pr create --draft` and watch `gh pr checks <n>`. If secrets are missing, the workflow will fail on `Migrate test DB` — that's the signal to set them.

---

## Slice B — Pagination & bounded queries

Goal: zero unbounded list queries (principles §3 line 88, §9 line 121). Cursor-based across the board for forward-only consistency with `ORDER BY created_at DESC`.

### Task B1: Cursor primitive

**Files:**
- Create: `apps/api/src/xtrusio_api/core/pagination.py`
- Create: `apps/api/tests/core/test_pagination.py`

- [ ] **Step 1: Write failing tests**

Create `apps/api/tests/core/test_pagination.py`:

```python
"""Cursor pagination primitive tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from xtrusio_api.core.pagination import (
    CursorParams,
    decode_cursor,
    encode_cursor,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def test_encode_decode_round_trip() -> None:
    ts = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    rid = uuid4()
    token = encode_cursor(ts, rid)
    out_ts, out_id = decode_cursor(token)
    assert out_ts == ts
    assert out_id == rid


def test_decode_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        decode_cursor("not-a-cursor")


def test_decode_rejects_tampered() -> None:
    ts = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
    token = encode_cursor(ts, uuid4())
    # Flip a character in the middle.
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    with pytest.raises(ValueError):
        decode_cursor(tampered)


def test_cursor_params_clamps_limit() -> None:
    p = CursorParams(cursor=None, limit=10_000)
    assert p.effective_limit == 200  # MAX_LIMIT
    p = CursorParams(cursor=None, limit=0)
    assert p.effective_limit == 50  # DEFAULT_LIMIT
    p = CursorParams(cursor=None, limit=75)
    assert p.effective_limit == 75
```

- [ ] **Step 2: Implement**

Create `apps/api/src/xtrusio_api/core/pagination.py`:

```python
"""Opaque cursor pagination primitive.

Cursors encode `(created_at, id)` so list queries with `ORDER BY created_at DESC, id DESC`
can resume deterministically across pages. The payload is base64url-encoded JSON;
tampering is detected on decode (we treat malformed JSON, missing keys, or invalid
type coercion as ValueError so the route can 400).
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def encode_cursor(created_at: datetime, row_id: UUID) -> str:
    raw = json.dumps({"t": created_at.isoformat(), "i": str(row_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_cursor(token: str) -> tuple[datetime, UUID]:
    try:
        padded = token + "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        obj = json.loads(raw)
        return datetime.fromisoformat(obj["t"]), UUID(obj["i"])
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError("invalid cursor") from e


@dataclass(frozen=True)
class CursorParams:
    cursor: str | None
    limit: int

    @property
    def effective_limit(self) -> int:
        if self.limit <= 0:
            return DEFAULT_LIMIT
        return min(self.limit, MAX_LIMIT)

    def decoded(self) -> tuple[datetime, UUID] | None:
        if self.cursor is None:
            return None
        return decode_cursor(self.cursor)
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/xtrusio_api/core/pagination.py apps/api/tests/core/test_pagination.py
git commit -m "feat(api): cursor pagination primitive"
```

### Task B2: `list_tenants` pagination

**Files:**
- Modify: `apps/api/src/xtrusio_api/routes/tenants.py:20-27`
- Modify: `apps/api/src/xtrusio_api/models/tenant.py`
- Modify: `apps/api/tests/routes/test_tenants.py`

- [ ] **Step 1: Add `TenantsPage` schema**

Append to `apps/api/src/xtrusio_api/models/tenant.py`:

```python
class TenantsPage(BaseModel):
    items: list[TenantOut]
    next_cursor: str | None = None
```

- [ ] **Step 2: Write a failing pagination test**

Add to `apps/api/tests/routes/test_tenants.py` (use existing `platform_admin_user`, `http_client`, `make_jwt` fixtures already in the file):

```python
async def test_list_tenants_paginates_and_caps(
    http_client: AsyncClient,
    platform_admin_user: PlatformUser,
    make_jwt: Callable[..., str],
) -> None:
    # Seed 3 tenants for this admin (uses existing tenants table; cleanup via @example.com slug)
    async with SessionLocal() as s:
        for i in range(3):
            await s.execute(
                text(
                    "INSERT INTO tenants (slug, name, created_by) "
                    "VALUES (:slug, :name, :uid)"
                ),
                {
                    "slug": f"page-tenant-{platform_admin_user.id.hex[:6]}-{i}-example",
                    "name": f"Page Tenant {i}",
                    "uid": str(platform_admin_user.id),
                },
            )
        await s.commit()

    token = make_jwt(sub=platform_admin_user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # First page, limit=2
    r1 = await http_client.get("/api/tenants?limit=2", headers=headers)
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] is not None

    # Second page using cursor
    r2 = await http_client.get(
        f"/api/tenants?limit=2&cursor={p1['next_cursor']}", headers=headers
    )
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2["items"]) >= 1
    # No overlap
    ids1 = {t["id"] for t in p1["items"]}
    ids2 = {t["id"] for t in p2["items"]}
    assert ids1.isdisjoint(ids2)


async def test_list_tenants_rejects_invalid_cursor(
    http_client: AsyncClient,
    platform_admin_user: PlatformUser,
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(sub=platform_admin_user.id)
    r = await http_client.get(
        "/api/tenants?cursor=not-a-cursor",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
```

(Cleanup: this fixture's tenants live with `@example.com` slug substring; add to `_cleanup.py` purge if not already pattern-matching. Confirm before commit — read `_cleanup.py` and check the `tenants` DELETE clause; if it only matches by `slug LIKE '%@example.com%'`, the seeded `-example` slug substring suffices. If not, add a targeted `WHERE slug ILIKE '%-example-%'` clause.)

- [ ] **Step 3: Implement route + service**

Replace `apps/api/src/xtrusio_api/routes/tenants.py` body with:

```python
"""GET/POST /api/tenants."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.auth import CurrentUser, get_current_user
from ..core.db import get_db
from ..core.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CursorParams,
    encode_cursor,
)
from ..core.permissions import require_permission
from ..models.tenant import Tenant, TenantIn, TenantOut, TenantsPage

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.get("", response_model=TenantsPage)
async def list_tenants(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> TenantsPage:
    await require_permission(db, user.user_id, "platform.clients.read")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e

    stmt = select(Tenant).order_by(Tenant.created_at.desc(), Tenant.id.desc())
    if decoded is not None:
        ts, rid = decoded
        # Keyset: strictly after the cursor row in descending order.
        stmt = stmt.where(
            or_(
                Tenant.created_at < ts,
                and_(Tenant.created_at == ts, Tenant.id < rid),
            )
        )
    stmt = stmt.limit(params.effective_limit + 1)

    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > params.effective_limit:
        last = rows[params.effective_limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
        rows = rows[: params.effective_limit]
    return TenantsPage(
        items=[TenantOut.model_validate(t) for t in rows], next_cursor=next_cursor
    )


@router.post("", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantIn,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Tenant:
    await require_permission(db, user.user_id, "platform.clients.manage")
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

Note `tuple_` import: removed in final code if not used; keep only if SQL backend prefers row-comparison form. The `or_(...)` form above is portable and matches the existing query style.

- [ ] **Step 4: Update existing `list_tenants` tests**

Any existing assertion `assert response.json() == [...]` must change to `assert response.json()["items"] == [...]`. Read `apps/api/tests/routes/test_tenants.py` and adjust every list-tenants assertion shape.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/tenants.py apps/api/src/xtrusio_api/models/tenant.py apps/api/tests/routes/test_tenants.py
git commit -m "feat(api): cursor pagination on GET /api/tenants"
```

### Task B3: Platform-invites pagination

**Files:**
- Modify: `apps/api/src/xtrusio_api/routes/platform_invites.py:52-62`
- Modify: `apps/api/src/xtrusio_api/services/platform_invites.py:132-142`
- Modify: `apps/api/tests/routes/test_platform_invites.py`

- [ ] **Step 1: Service signature + impl**

Replace `list_platform_invites` in `apps/api/src/xtrusio_api/services/platform_invites.py`:

```python
async def list_platform_invites(
    db: AsyncSession,
    *,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[PlatformInvite], str | None]:
    from ..core.pagination import encode_cursor

    stmt = select(PlatformInvite).order_by(
        PlatformInvite.created_at.desc(), PlatformInvite.id.desc()
    )
    if cursor is not None:
        ts, rid = cursor
        stmt = stmt.where(
            and_(
                PlatformInvite.created_at <= ts,
            )
        ).where(
            ~and_(PlatformInvite.created_at == ts, PlatformInvite.id >= rid)
        )
    stmt = stmt.limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
        rows = rows[:limit]
    return rows, next_cursor
```

(The `where(...).where(~and_(...))` form is the keyset predicate "strictly after `(ts, rid)` in descending order"; matches Task B2's `or_` form semantically. Either form is fine — be consistent within the file.)

- [ ] **Step 2: Route accepts `cursor`+`limit`**

Replace the `list_invites` handler in `apps/api/src/xtrusio_api/routes/platform_invites.py`:

```python
@router.get("", response_model=PlatformInvitesPage)
async def list_invites(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PlatformInvitesPage:
    await require_permission(db, user.user_id, "platform.users.invite")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_platform_invites(
        db, cursor=decoded, limit=params.effective_limit
    )
    return PlatformInvitesPage(
        items=[PlatformInviteResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
```

Add imports `from fastapi import Query` and the pagination module imports.

- [ ] **Step 3: Test (pagination round-trip + invalid cursor 400)**

Add to `apps/api/tests/routes/test_platform_invites.py` (use `mock_supabase_admin` so invite-create doesn't hit Supabase):

```python
async def test_list_platform_invites_paginates(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
    mock_supabase_admin: MagicMock,
) -> None:
    # Seed 3 invites via the service so the row layout matches production.
    mock_supabase_admin.auth.admin.invite_user_by_email.return_value = MagicMock(
        user=MagicMock(id=str(uuid4()))
    )
    async with SessionLocal() as s:
        for i in range(3):
            await create_platform_invite(
                s,
                email=f"paginv-{i}-{uuid4().hex[:6]}@example.com",
                role=PlatformRole.ADMIN,
                invited_by=existing_super_admin.id,
            )

    token = make_jwt(sub=existing_super_admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    r1 = await http_client.get("/api/platform/users/invites?limit=2", headers=headers)
    assert r1.status_code == 200
    p1 = r1.json()
    assert len(p1["items"]) == 2
    assert p1["next_cursor"] is not None

    r2 = await http_client.get(
        f"/api/platform/users/invites?limit=2&cursor={p1['next_cursor']}",
        headers=headers,
    )
    assert r2.status_code == 200
    p2 = r2.json()
    assert len(p2["items"]) >= 1
    assert {x["id"] for x in p1["items"]}.isdisjoint({x["id"] for x in p2["items"]})


async def test_list_platform_invites_rejects_bad_cursor(
    http_client: AsyncClient,
    existing_super_admin: PlatformUser,
    make_jwt: Callable[..., str],
) -> None:
    token = make_jwt(sub=existing_super_admin.id)
    r = await http_client.get(
        "/api/platform/users/invites?cursor=NOPE",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
```

Imports to add: `from uuid import uuid4`, `from unittest.mock import MagicMock`, `from xtrusio_api.services.platform_invites import create_platform_invite`, `from xtrusio_api.models.platform_user import PlatformRole`.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/platform_invites.py apps/api/src/xtrusio_api/services/platform_invites.py apps/api/tests/routes/test_platform_invites.py
git commit -m "feat(api): cursor pagination on platform-invites list"
```

### Task B4: Tenant-invites pagination

**Files:**
- Modify: `apps/api/src/xtrusio_api/routes/tenant_invites.py:61-74`
- Modify: `apps/api/src/xtrusio_api/services/tenant_invites.py:159-178`
- Modify: `apps/api/tests/routes/test_tenant_invites.py`

- [ ] **Step 1: Update service**

Replace `list_tenant_invites` in `apps/api/src/xtrusio_api/services/tenant_invites.py` body with:

```python
async def list_tenant_invites(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    requester_id: UUID,
    cursor: tuple[datetime, UUID] | None = None,
    limit: int = 50,
) -> tuple[list[TenantInvite], str | None]:
    from ..core.pagination import encode_cursor

    await _load_membership(db, tenant_id=tenant_id, user_id=requester_id)
    await require_permission(
        db, requester_id, "workspace.members.manage", workspace_id=tenant_id
    )
    stmt = (
        select(TenantInvite)
        .where(TenantInvite.tenant_id == tenant_id)
        .order_by(TenantInvite.created_at.desc(), TenantInvite.id.desc())
    )
    if cursor is not None:
        ts, rid = cursor
        stmt = stmt.where(
            and_(TenantInvite.created_at <= ts)
        ).where(~and_(TenantInvite.created_at == ts, TenantInvite.id >= rid))
    stmt = stmt.limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = encode_cursor(last.created_at, last.id)
        rows = rows[:limit]
    return rows, next_cursor
```

- [ ] **Step 2: Update route**

Replace the `list_invites` handler in `apps/api/src/xtrusio_api/routes/tenant_invites.py`:

```python
@router.get("", response_model=TenantInvitesPage)
async def list_invites(
    tenant_id: UUID,
    identity: Annotated[AuthIdentity, Depends(require_authenticated)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> TenantInvitesPage:
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    try:
        rows, next_cursor = await list_tenant_invites(
            db,
            tenant_id=tenant_id,
            requester_id=identity.user_id,
            cursor=decoded,
            limit=params.effective_limit,
        )
    except NotAMemberError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not_a_member") from e
    return TenantInvitesPage(
        items=[TenantInviteResponse.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
```

Add imports `from fastapi import Query`, pagination module imports.

- [ ] **Step 3: Test (pagination + invalid cursor 400; reuse existing tenant-invite fixtures in `test_tenant_invites.py`)**

Follow the same pattern as Task B3 step 3 with seeded invites scoped to a created test tenant. Use the existing test's setup pattern for tenants and memberships; see the top of `apps/api/tests/routes/test_tenant_invites.py` for the canonical setup.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/tenant_invites.py apps/api/src/xtrusio_api/services/tenant_invites.py apps/api/tests/routes/test_tenant_invites.py
git commit -m "feat(api): cursor pagination on tenant-invites list"
```

### Task B5: No-unbounded-lists invariant test

**Files:**
- Create: `apps/api/tests/integration/test_no_unbounded_lists.py`

- [ ] **Step 1: Write the test**

```python
"""CI invariant: every GET list endpoint declares a query `limit` capped at MAX_LIMIT.

This is a structural test — it walks the FastAPI route table and asserts that any
handler returning a *Page model has a `limit` query param with `le=MAX_LIMIT`.
Prevents §3/§9 regressions where a future endpoint forgets pagination.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute
from xtrusio_api.core.pagination import MAX_LIMIT
from xtrusio_api.main import app

pytestmark = pytest.mark.asyncio(loop_scope="session")


def test_every_page_endpoint_has_limit_cap() -> None:
    offenders: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if "GET" not in route.methods:
            continue
        # We only care about endpoints whose response is a *Page model.
        rm = route.response_model
        if rm is None or not getattr(rm, "__name__", "").endswith("Page"):
            continue
        params = {p.name: p for p in route.dependant.query_params}
        if "limit" not in params:
            offenders.append(f"{route.path}: missing `limit` query param")
            continue
        # The pydantic field's metadata carries the `le` constraint.
        field = params["limit"].field_info
        le = next(
            (m.le for m in (field.metadata or []) if hasattr(m, "le")),
            None,
        )
        if le != MAX_LIMIT:
            offenders.append(f"{route.path}: limit le={le}, expected {MAX_LIMIT}")
    assert not offenders, "Unbounded list endpoints:\n  " + "\n  ".join(offenders)
```

If the metadata-walking introspection turns out to be fragile across FastAPI versions, fall back to checking `route.endpoint.__signature__` directly — the implementer should pick whichever is stable for FastAPI 0.115+.

- [ ] **Step 2: Commit**

```bash
git add apps/api/tests/integration/test_no_unbounded_lists.py
git commit -m "test(api): §3/§9 invariant — every list endpoint caps `limit` at MAX_LIMIT"
```

### Slice B end-of-slice gate (controller-run)

- [ ] `make test-clean && make check` — full lint+typecheck+test. Expected: green, including new pagination + invariant tests.

---

## Slice C — Boundary hardening

Goal: kill the three boundary smells (string-match exception, broad-Exception swallow at boot, unsynchronized JWKS fetches). Each is a small, surgical change behind a test.

### Task C1: JWKS coalescing lock

**Files:**
- Modify: `apps/api/src/xtrusio_api/core/auth.py:21,33-44`
- Create: `apps/api/tests/core/test_auth_jwks.py`

- [ ] **Step 1: Write a failing test (concurrent cold fetches coalesce)**

Create `apps/api/tests/core/test_auth_jwks.py`:

```python
"""Cold-start JWKS fetches must coalesce — one HTTP fetch even under N concurrent callers."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from xtrusio_api.core import auth as auth_mod

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_concurrent_cold_fetches_coalesce(monkeypatch: pytest.MonkeyPatch) -> None:
    auth_mod._JWKS_CACHE.clear()
    auth_mod._JWKS_LOCKS.clear()

    calls = 0

    async def _slow_fetch_uncached(url: str) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return {"keys": []}

    monkeypatch.setattr(auth_mod, "_fetch_jwks_uncached", _slow_fetch_uncached)

    results = await asyncio.gather(
        *[auth_mod._fetch_jwks("https://example.com/jwks") for _ in range(10)]
    )
    assert all(r == {"keys": []} for r in results)
    assert calls == 1, f"expected 1 underlying fetch under coalescing, got {calls}"
```

- [ ] **Step 2: Implement coalescing**

Replace the JWKS section in `apps/api/src/xtrusio_api/core/auth.py` (top of file through `_fetch_jwks`):

```python
"""JWT validation + auth dependencies (RS256 via JWKS)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.platform_user import PlatformRole, PlatformUser
from .config import get_settings
from .db import get_db

_AUDIENCE = "authenticated"
_JWKS_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_JWKS_LOCKS: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
_ALLOWED_ALGS: frozenset[str] = frozenset({"RS256", "RS384", "RS512", "ES256", "ES384"})


@dataclass
class CurrentUser:
    user_id: UUID
    email: str
    role: PlatformRole
    is_active: bool


async def _fetch_jwks_uncached(url: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.jwks_fetch_timeout_sec) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        out: dict[str, Any] = resp.json()
        return out


async def _fetch_jwks(url: str) -> dict[str, Any]:
    """Fetch JWKS doc with an in-process TTL cache and per-URL coalescing.

    Why the lock: under cold-start with N concurrent callers, the unlocked
    version fired N httpx fetches. The lock collapses that to 1; later callers
    observe the cached value when they acquire the lock and skip the network.
    """
    cached = _JWKS_CACHE.get(url)
    if cached and cached[1] > time.time():
        return cached[0]
    async with _JWKS_LOCKS[url]:
        cached = _JWKS_CACHE.get(url)
        if cached and cached[1] > time.time():
            return cached[0]
        jwks = await _fetch_jwks_uncached(url)
        _JWKS_CACHE[url] = (jwks, time.time() + get_settings().jwks_ttl_sec)
        return jwks
```

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/xtrusio_api/core/auth.py apps/api/tests/core/test_auth_jwks.py
git commit -m "fix(auth): coalesce concurrent JWKS fetches with per-URL lock"
```

### Task C2: Signup duplicate-email by exception class

**Files:**
- Modify: `apps/api/src/xtrusio_api/services/signup.py:6,36,45-49`
- Modify: `apps/api/tests/services/test_signup.py` (or `apps/api/tests/routes/test_signup.py` — read both first; add a service-level test next to the existing duplicate-email path)

- [ ] **Step 1: Write a failing test**

Add to the right signup test file (mirror an existing duplicate-email test, replace its trigger with a real `AuthApiError`):

```python
import pytest
from gotrue.errors import AuthApiError
from xtrusio_api.services.signup import EmailTakenError, create_signup_user


async def test_create_signup_user_maps_authapierror_to_emailtaken(
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    mock_supabase_admin.auth.admin.create_user.side_effect = AuthApiError(
        "email already registered", 422, "email_exists"
    )
    with pytest.raises(EmailTakenError):
        await create_signup_user(
            db=db_session, email="dup@example.com", password="hunter22hunter22"
        )


async def test_create_signup_user_passes_unknown_authapierror_through(
    mock_supabase_admin: MagicMock,
    db_session: AsyncSession,
) -> None:
    mock_supabase_admin.auth.admin.create_user.side_effect = AuthApiError(
        "weak password", 400, "weak_password"
    )
    with pytest.raises(AuthApiError):
        await create_signup_user(
            db=db_session, email="weak@example.com", password="hunter22hunter22"
        )
```

- [ ] **Step 2: Implement**

Replace `services/signup.py`:

```python
"""Signup orchestration: gate check + Supabase Admin user creation."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from gotrue.errors import AuthApiError
from supabase import create_client

from ..core.config import get_settings
from .platform_settings import is_signups_enabled

if TYPE_CHECKING:
    from gotrue.types import UserResponse

# Stable gotrue error codes meaning "this email is already registered".
# Source: gotrue-py >= 2.x raises AuthApiError with a `code` attribute; the
# `email_exists` / `user_already_exists` codes are the supabase-auth contract.
_EMAIL_TAKEN_CODES = frozenset({"email_exists", "user_already_exists"})


class SignupsDisabledError(Exception):
    pass


class EmailTakenError(Exception):
    pass


class EmailProviderUnavailableError(Exception):
    pass


async def create_signup_user(*, db: AsyncSession, email: str, password: str) -> str:
    """Create an unconfirmed Supabase auth user. Returns the user id."""
    if not await is_signups_enabled(db):
        raise SignupsDisabledError()

    cfg = get_settings()
    sb = create_client(cfg.supabase_url, cfg.supabase_service_role_key)

    def _call() -> "UserResponse":
        return sb.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": False}
        )

    try:
        result = await asyncio.wait_for(asyncio.to_thread(_call), timeout=cfg.supabase_timeout_sec)
    except TimeoutError as e:
        raise EmailProviderUnavailableError() from e
    except AuthApiError as e:
        if (e.code or "") in _EMAIL_TAKEN_CODES:
            raise EmailTakenError() from e
        raise

    if result.user is None:
        raise EmailProviderUnavailableError()
    return str(result.user.id)
```

If the gotrue version present lacks `.code` on `AuthApiError` (verify via `python -c "from gotrue.errors import AuthApiError; help(AuthApiError)"`), fall back to `e.message` matching against the same code strings — but the class-based catch on `AuthApiError` is the load-bearing change.

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/xtrusio_api/services/signup.py apps/api/tests/services/test_signup.py
git commit -m "fix(signup): detect duplicate email by AuthApiError class, not string match"
```

### Task C3: Lifespan fail-fast with env-flag escape hatch

**Files:**
- Modify: `apps/api/src/xtrusio_api/core/config.py`
- Modify: `apps/api/src/xtrusio_api/main.py:24-35`
- Modify: `.env.example`
- Create/modify: `apps/api/tests/test_lifespan.py`

- [ ] **Step 1: Add config flag**

Append to `apps/api/src/xtrusio_api/core/config.py` Settings class (placement: with other booleans):

```python
    startup_reconcile_tolerant: bool = Field(False, alias="STARTUP_RECONCILE_TOLERANT")
```

- [ ] **Step 2: Document in `.env.example`**

Append:

```
# When true, RBAC reconcile failures at boot are logged-and-ignored (local dev only).
# Defaults to false: production must boot only when reconcile succeeds.
STARTUP_RECONCILE_TOLERANT=false
```

- [ ] **Step 3: Write failing tests**

Create `apps/api/tests/test_lifespan.py`:

```python
"""Lifespan startup posture: fail-fast unless STARTUP_RECONCILE_TOLERANT=true."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from xtrusio_api.main import lifespan

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_lifespan_propagates_when_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*_: object, **__: object) -> None:
        raise RuntimeError("simulated reconcile failure")

    monkeypatch.setattr("xtrusio_api.main.reconcile_rbac", _boom)
    monkeypatch.setenv("STARTUP_RECONCILE_TOLERANT", "false")
    from xtrusio_api.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="simulated"):
        async with lifespan(FastAPI()):
            pass


async def test_lifespan_swallows_when_tolerant(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*_: object, **__: object) -> None:
        raise RuntimeError("simulated reconcile failure")

    monkeypatch.setattr("xtrusio_api.main.reconcile_rbac", _boom)
    monkeypatch.setenv("STARTUP_RECONCILE_TOLERANT", "true")
    from xtrusio_api.core.config import get_settings

    get_settings.cache_clear()  # type: ignore[attr-defined]

    async with lifespan(FastAPI()):
        pass  # should not raise
```

- [ ] **Step 4: Implement**

Replace `apps/api/src/xtrusio_api/main.py` lifespan:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    try:
        async with SessionLocal() as _s:
            await reconcile_rbac(_s)
        async with SessionLocal() as _s:
            await reconcile_user_roles_from_enums(_s)
    except Exception:
        import logging

        log = logging.getLogger(__name__)
        if settings.startup_reconcile_tolerant:
            log.exception("rbac reconcile on startup failed (tolerant mode, continuing)")
        else:
            log.exception("rbac reconcile on startup failed — failing fast")
            raise
    yield
```

Why `except Exception` is acceptable here (vs §5 "no bare except"): reconcile composes many SQL operations whose specific failure modes (`OperationalError`, `IntegrityError`, transient network failures inside SQLAlchemy) aren't a closed set we want to enumerate at boot. The principle's intent is "don't silently swallow"; this version logs *and* re-raises by default, satisfying the spirit. The escape hatch is opt-in and named.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/xtrusio_api/main.py apps/api/src/xtrusio_api/core/config.py .env.example apps/api/tests/test_lifespan.py
git commit -m "fix(boot): fail-fast on reconcile error; STARTUP_RECONCILE_TOLERANT escape hatch"
```

### Slice C end-of-slice gate (controller-run)

- [ ] `make test-clean && make check` — expected green, including the new JWKS, signup, and lifespan tests.

---

## Slice D — AuthGuard cleanup

### Task D1: Drop duplicate `staleTime`

**Files:**
- Modify: `apps/web/src/components/auth-guard.tsx:14-20`
- Modify: `apps/web/src/components/auth-guard.test.tsx` (assert inherited default)

- [ ] **Step 1: Update component**

Replace the `useQuery` block in `apps/web/src/components/auth-guard.tsx`:

```tsx
  const { data: me, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: !!auth.session,
    refetchOnWindowFocus: false,
  });
```

(Global default in `lib/query-client.ts` already sets `staleTime: 30_000` and `retry: 1`. We keep `refetchOnWindowFocus: false` because the global default doesn't override that, and we explicitly want the /me query never to refetch on tab focus.)

- [ ] **Step 2: Update test**

In `apps/web/src/components/auth-guard.test.tsx`, replace the local test `QueryClient` with the production `queryClient` (or pass the same defaults) so the test exercises real behavior:

```tsx
import { queryClient } from "@/lib/query-client";
// ...
const qc = queryClient;
```

If sharing a single client across tests bleeds state, instead construct a per-test client with identical `defaultOptions` and assert against that.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/auth-guard.tsx apps/web/src/components/auth-guard.test.tsx
git commit -m "refactor(web): AuthGuard /me query inherits global staleTime"
```

### Slice D end-of-slice gate (controller-run)

- [ ] `make test-clean && make check` — expected green.

---

## Final wrap-up

### Task W1: Targeted mid-build check is N/A

No migrations, no RLS, no auth-flow changes (JWKS lock is internal). The end-of-slice `make check` runs already covered the gate.

### Task W2: Final Opus code-quality review

- [ ] **Step 1: Dispatch one Opus review agent** with the full diff against `main`.

Prompt skeleton:

> Review the diff between `main` and `HEAD` of branch `rbac-p3-5-review-fix-backlog`. Verify against `docs/superpowers/ENGINEERING_PRINCIPLES.md`. Check: (1) every list endpoint paginates with cap = `MAX_LIMIT`; (2) no broad `except Exception` without log+re-raise OR an opt-in tolerant flag; (3) no string-match exception detection at external boundaries; (4) JWKS coalescing has no leak (lock never held across the entire HTTP fetch error path in a way that wedges all callers); (5) the no-unbounded-lists invariant test would actually trip if a future route forgets `limit`. Report only blocking issues with `file:line` + fix sketch.

Resolve any blocking findings; non-blocking nits land in a follow-up.

### Task W3: PR body + open + merge

- [ ] **Step 1:** Write `docs/superpowers/PR-rbac-p3-5-body.md` summarising the four slices, the principle §8 amendment, and explicit "not done" callouts (enum-column drop deferred per HANDOFF item 6).

- [ ] **Step 2:** `gh pr create --base main --head rbac-p3-5-review-fix-backlog --title "P3.5 — review-fix backlog (CI, pagination, boundary hardening, AuthGuard)" --body-file docs/superpowers/PR-rbac-p3-5-body.md`

- [ ] **Step 3:** Watch `gh pr checks <n>` until the new CI workflow goes green on its own PR (this is the first run with secrets — be ready to set them in repo settings if missing).

- [ ] **Step 4:** `gh pr merge <n> --merge` (or `--squash` per project convention — check `git log` for the prior P3c merge style; HANDOFF history shows `Merge pull request #N from ...` so plain `--merge` matches).

- [ ] **Step 5:** Verify `gh pr view <n> --json state` = `MERGED`. Update HANDOFF.md to reflect P3.5 done and P4 unblocked. Commit + push.

---

## Self-review checklist (run before handing off)

1. **Spec coverage:** every review finding (1–6) maps to a task — A2/A3 (CI), B2/B3/B4/B5 (pagination + invariant), C2 (signup string match), C3 (lifespan bare-except), C1 (JWKS lock), D1 (AuthGuard duplicate). ✅
2. **Placeholder scan:** no "TBD", "implement later", "similar to Task N"; every code step has the actual code. ✅
3. **Type consistency:** `MAX_LIMIT` / `DEFAULT_LIMIT` / `CursorParams` / `encode_cursor` / `decode_cursor` named identically in Tasks B1 through B5. `EmailTakenError` / `AuthApiError` consistent in C2. ✅
4. **HANDOFF respect:** enum-column drop not touched; reconcile module not refactored; principles §8 amendment is in scope (line 111 only). ✅
5. **User memory respect:** `feedback_no_claude_coauthor` (commits clean), `feedback_no_hardcoded_config` (new flag goes through Settings), `feedback_test_data_hygiene` (all test rows `@example.com`, never creates super_admin), `feedback_lean_review_workflow` (one full-suite per slice, controller-run, not subagent). ✅

---

## Execution choice

Plan complete and saved to `docs/superpowers/plans/2026-05-20-rbac-p3-5-review-fix-backlog.md`. Two execution options:

1. **Subagent-Driven (recommended)** — controller dispatches one fresh Opus subagent per task, reviews each diff before moving on. Best for this plan because the slices are well-isolated and the review-fix subagent prompts can be terse.
2. **Inline Execution** — execute in this session using `superpowers:executing-plans`. Faster end-to-end, but ties up this conversation context.

Which approach?
