# RBAC P6c — Slice 1: Roles CRUD (Platform + Workspace) + Permissions Catalog Endpoint

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the role-CRUD admin UIs for both scopes (custom platform roles, custom per-workspace roles) consuming the P4/P5 APIs already on `main`, plus one tiny new backend endpoint (`GET /api/permissions/catalog`) that lets the frontend render the permission picker. End-of-slice: super_admin can create/edit/delete custom platform roles; workspace owner can do the same per workspace; every mutation lands one row in `rbac_audit_log`.

**Architecture:** Backend `GET /api/permissions/catalog` is a 30-line authenticated-only route that serialises the static `CATALOG` tuple from `apps/api/src/xtrusio_api/rbac/catalog.py`. No service layer, no migration, no permission gate (the data is non-secret and identical for every caller). Frontend introduces a `lib/query-keys.ts` registry and four shared blocks (`<PermissionPicker>`, `<RoleFormDialog>`, `<RolesTable>`, `<DeleteRoleDialog>`) plus a tiny `<Forbidden>` page-gate fallback. Two thin per-scope page components compose those blocks — `platform-roles-page.tsx` (~140 LoC) and `workspace-roles-page.tsx` (~150 LoC) — each owning its own React Query mutations + cache invalidation against `qk.platformRoles()` / `qk.workspaceRoles(wid)`.

**Tech Stack:** FastAPI 0.117, SQLAlchemy 2 async, Pydantic v2, mypy --strict, pytest-asyncio (loop_scope="session"). Frontend: TypeScript (strict, `verbatimModuleSyntax`, `noUncheckedIndexedAccess`), React 19, TanStack Router (file-based), TanStack Query v5, Vitest 2, React Testing Library 16, Tailwind 4, shadcn/Radix primitives, Vite 8.

---

## File Structure

Files are listed in the order the tasks touch them. Every Modify item names the exact line range that gets rewritten so the implementer is not hunting.

### Create

| Path | Purpose |
|---|---|
| `apps/api/src/xtrusio_api/schemas/permission.py` | Pydantic `PermissionDef` + `PermissionsCatalog` schemas. |
| `apps/api/src/xtrusio_api/routes/permissions.py` | `GET /api/permissions/catalog` — authenticated, no perm gate, returns CATALOG serialised. |
| `apps/api/tests/routes/test_permissions_catalog.py` | 200 path, 401 unauth, shape conformance, identical-across-callers, idempotent. |
| `packages/api-types/src/permission.ts` | `PermissionDef` + `PermissionsCatalog` TS mirror. |
| `packages/api-types/src/role.ts` | `PlatformRole*` + `WorkspaceRole*` TS mirrors of the P4/P5 schemas. |
| `apps/web/src/lib/query-keys.ts` | Central registry for every TanStack Query key string-tuple. |
| `apps/web/src/lib/query-keys.test.ts` | Snapshot test that key tuples are stable and don't collide. |
| `apps/web/src/components/forbidden.tsx` | Reusable "you don't have access" fallback for permission-gated routes. |
| `apps/web/src/components/forbidden.test.tsx` | Renders message + Back-to-landing button. |
| `apps/web/src/components/ui/checkbox.tsx` | shadcn `checkbox` primitive (Radix wrapper) — added once, used by `<PermissionPicker>`. |
| `apps/web/src/components/roles/permission-picker.tsx` | Controlled grouped-checkbox picker (per-category select-all). |
| `apps/web/src/components/roles/permission-picker.test.tsx` | Renders by category, toggles, per-category select-all, scope filter. |
| `apps/web/src/components/roles/role-form-dialog.tsx` | Dialog form for create/edit, prefills in edit mode, surfaces inline + footer errors. |
| `apps/web/src/components/roles/role-form-dialog.test.tsx` | Empty in create, prefilled in edit, submit fires payload, key disabled in edit, `role_key_taken` inline. |
| `apps/web/src/components/roles/roles-table.tsx` | Read-only table with system-role badge and conditional action buttons. |
| `apps/web/src/components/roles/roles-table.test.tsx` | Rows render, badge for system, Edit/Delete hidden for system or when `canManage=false`. |
| `apps/web/src/components/roles/delete-role-dialog.tsx` | Confirm modal with cascade warning copy. |
| `apps/web/src/components/roles/delete-role-dialog.test.tsx` | Warning copy present, Confirm fires, Cancel closes silently. |
| `apps/web/src/components/platform-roles-page.tsx` | Per-scope page composing the shared blocks for platform. |
| `apps/web/src/components/platform-roles-page.test.tsx` | Gate, create/edit/delete flows invalidate the right cache key. |
| `apps/web/src/components/workspace-roles-page.tsx` | Per-scope page composing the shared blocks for workspace. |
| `apps/web/src/components/workspace-roles-page.test.tsx` | Gate, create/edit/delete flows invalidate the right cache key. |
| `apps/web/src/routes/_app.platform.roles.tsx` | 3-line file-route mounting `<PlatformRolesPage />`. |

### Modify

| Path | Lines | Change |
|---|---|---|
| `apps/api/src/xtrusio_api/main.py` | 1-29 (imports block + `app.include_router` calls) | Import and register the new `permissions` router alongside the existing ones. |
| `packages/api-types/src/index.ts` | 1 | Add `export * from "./permission";` and `export * from "./role";`. |
| `apps/web/src/lib/api.ts` | 1-159 | Add `fetchPermissionsCatalog`, `fetchPlatformRoles`, `postPlatformRole`, `patchPlatformRole`, `deletePlatformRole`, plus workspace equivalents. Re-use `apiFetch<T>`. |
| `apps/web/src/lib/error-messages.ts` | 1-end (extend) | Add new mappings for `role_key_taken`, `unknown_permission`, `scope_mismatch`, `system_role_immutable`, `single_super_admin_invariant`, `owner_floor`, `privilege_escalation:*`, `invalid cursor`, `role_scope_mismatch`, `membership_not_found`, `platform_user_not_found`. |
| `apps/web/src/lib/error-messages.test.ts` | end (append) | Append per-mapping assertions; verify unknown codes fall through. |
| `apps/web/src/routes/_app.workspace.$workspaceId.roles.tsx` | 1-21 (full) | Replace the placeholder with a 3-line file-route mounting `<WorkspaceRolesPage workspaceId={...} />`. |

### Notes

- TanStack file-route naming reminder (verified against the existing tree): dot segments map to URL segments, `$param` segments are dynamic, the `_app` prefix is a pathless layout route. So `_app.platform.roles.tsx` mounts at `/platform/roles` and inherits the layout from `_app.platform.tsx`.
- The autogenerated `apps/web/src/routeTree.gen.ts` will rewrite itself the next time the Vite dev server / build runs. Do not hand-edit it. The route-tree refresh happens automatically during `pnpm --filter @xtrusio/web build` / `pnpm --filter @xtrusio/web typecheck`.
- This slice does **not** touch migrations. Alembic head stays at `0009`.
- `apps/web/src/lib/me-adapter.ts` already exports `hasPlatformPerm`, `hasWorkspacePerm`, `findTenant`, `getDefaultLandingPath`, `useMe`. The new code consumes those; do not reimplement.

---

## Slice 1A — Backend: permissions catalog endpoint

**Goal:** Ship `GET /api/permissions/catalog`. End-of-section: `curl -H "Authorization: Bearer $token" $api/api/permissions/catalog` returns the full CATALOG tuple as JSON.

### Task 1A.1: Pydantic schemas for the catalog

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/src/xtrusio_api/schemas/permission.py`

- [ ] **Step 1: Write the schema file**

```python
"""Pydantic schemas for the permissions catalog endpoint.

Mirrors `apps/api/src/xtrusio_api/rbac/catalog.py:CATALOG` 1:1. Read-only,
non-secret — exposed to any logged-in caller.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PermissionDef(BaseModel):
    scope: Literal["platform", "workspace"]
    key: str
    category: str
    description: str


class PermissionsCatalog(BaseModel):
    items: list[PermissionDef]
```

- [ ] **Step 2: Sanity-check the import path resolves**

Run: `uv run python -c "from xtrusio_api.schemas.permission import PermissionDef, PermissionsCatalog; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add apps/api/src/xtrusio_api/schemas/permission.py
git commit -m "feat(api): add PermissionDef + PermissionsCatalog schemas"
```

### Task 1A.2: Catalog route — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/tests/routes/test_permissions_catalog.py`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/src/xtrusio_api/routes/permissions.py`

- [ ] **Step 1: Write the failing test**

```python
"""Tests for GET /api/permissions/catalog.

The route is authenticated but ungated — every logged-in caller gets the
same payload because the catalog is non-secret data. Tests assert: 200 + every
CATALOG entry present + shape conformance + identical payload for
super_admin / editor / generic-logged-in caller + 401 unauthenticated +
idempotence across calls.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from xtrusio_api.rbac.catalog import CATALOG

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_catalog_unauthenticated_401(client: AsyncClient) -> None:
    resp = await client.get("/api/permissions/catalog")
    assert resp.status_code == 401


async def test_catalog_returns_every_permission(
    client: AsyncClient, super_admin_token: str
) -> None:
    resp = await client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    keys_in_payload = {item["key"] for item in body["items"]}
    keys_in_catalog = {p.key for p in CATALOG}
    assert keys_in_payload == keys_in_catalog


async def test_catalog_shape_conforms(
    client: AsyncClient, super_admin_token: str
) -> None:
    resp = await client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    body = resp.json()
    for item in body["items"]:
        assert set(item.keys()) == {"scope", "key", "category", "description"}
        assert item["scope"] in {"platform", "workspace"}
        assert isinstance(item["key"], str) and item["key"]
        assert isinstance(item["category"], str) and item["category"]
        assert isinstance(item["description"], str) and item["description"]


async def test_catalog_identical_for_editor_and_super_admin(
    client: AsyncClient, super_admin_token: str, platform_editor_token: str
) -> None:
    s = (
        await client.get(
            "/api/permissions/catalog",
            headers={"Authorization": f"Bearer {super_admin_token}"},
        )
    ).json()
    e = (
        await client.get(
            "/api/permissions/catalog",
            headers={"Authorization": f"Bearer {platform_editor_token}"},
        )
    ).json()
    assert s == e


async def test_catalog_idempotent(
    client: AsyncClient, super_admin_token: str
) -> None:
    first = await client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    second = await client.get(
        "/api/permissions/catalog",
        headers={"Authorization": f"Bearer {super_admin_token}"},
    )
    assert first.json() == second.json()
```

If the project's conftest doesn't already expose a `platform_editor_token` fixture but a similar one with a different name exists, use that name; do not add a new fixture in this task. Search via:
`grep -rn "def super_admin_token\|def platform_editor_token\|def workspace_owner_token" apps/api/tests/conftest.py`
and adjust the test fixture names to whatever already exists. The intent is "any-logged-in-non-super-admin token".

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest apps/api/tests/routes/test_permissions_catalog.py -v`
Expected: FAIL with `404 Not Found` for every `200`-asserting case (route doesn't exist yet).

- [ ] **Step 3: Write the route**

```python
"""GET /api/permissions/catalog — read-only, non-secret.

The catalog is identical for every logged-in caller. No permission gate
because the data is non-secret (it's already visible in any 403 error
message), and gating it would just make the frontend permission picker
brittle for low-privilege users it shouldn't be brittle for.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ..core.auth import CurrentUser, get_current_user
from ..rbac.catalog import CATALOG
from ..schemas.permission import PermissionDef, PermissionsCatalog

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


@router.get("/catalog", response_model=PermissionsCatalog)
async def get_catalog(
    _user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PermissionsCatalog:
    return PermissionsCatalog(
        items=[
            PermissionDef(
                scope=p.scope,
                key=p.key,
                category=p.category,
                description=p.description,
            )
            for p in CATALOG
        ]
    )
```

- [ ] **Step 4: Register the router in `main.py`**

Open `apps/api/src/xtrusio_api/main.py`. In the existing `from .routes import …` block (around lines 14-27), add:

```python
from .routes import permissions as permissions_routes
```

Then in the `app.include_router(...)` block lower in the file, add:

```python
app.include_router(permissions_routes.router)
```

Match the ordering pattern used by the other routers (alphabetical near `platform_*` is fine).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest apps/api/tests/routes/test_permissions_catalog.py -v`
Expected: all 5 tests PASS.

- [ ] **Step 6: Run mypy + ruff on the touched files**

Run:
```bash
uv run mypy apps/api/src/xtrusio_api/routes/permissions.py apps/api/src/xtrusio_api/schemas/permission.py
uv run ruff check apps/api/src/xtrusio_api/routes/permissions.py apps/api/src/xtrusio_api/schemas/permission.py apps/api/tests/routes/test_permissions_catalog.py
uv run ruff format --check apps/api/src/xtrusio_api/routes/permissions.py apps/api/src/xtrusio_api/schemas/permission.py apps/api/tests/routes/test_permissions_catalog.py
```
Expected: each command exits 0.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/xtrusio_api/routes/permissions.py apps/api/src/xtrusio_api/main.py apps/api/tests/routes/test_permissions_catalog.py
git commit -m "feat(api): GET /api/permissions/catalog"
```

---

## Slice 1B — Frontend foundation (api-types + lib/api + query-keys + error-messages)

**Goal:** Add the TS mirrors and the shared infrastructure that every Slice-1 UI block will import. No UI yet.

### Task 1B.1: api-types — PermissionDef + PermissionsCatalog

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/packages/api-types/src/permission.ts`

- [ ] **Step 1: Write the type file**

```ts
// packages/api-types/src/permission.ts
// Mirror of apps/api/src/xtrusio_api/schemas/permission.py. Frontend fetches
// /api/permissions/catalog once per session (staleTime: Infinity); the data
// only changes with a backend deploy.

export type PermissionScope = "platform" | "workspace";

export type PermissionDef = {
  scope: PermissionScope;
  key: string;
  category: string;
  description: string;
};

export type PermissionsCatalog = {
  items: PermissionDef[];
};
```

- [ ] **Step 2: Commit**

```bash
git add packages/api-types/src/permission.ts
git commit -m "feat(api-types): PermissionDef + PermissionsCatalog"
```

### Task 1B.2: api-types — PlatformRole* + WorkspaceRole*

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/packages/api-types/src/role.ts`

- [ ] **Step 1: Write the type file**

```ts
// packages/api-types/src/role.ts
// Mirror of apps/api/src/xtrusio_api/schemas/platform_role.py and
// apps/api/src/xtrusio_api/schemas/workspace_role.py. The Grant types are
// included now so future P6d code (grant-management UIs) can import them
// without another api-types release.

import type { PermissionKey } from "./me";

export type PlatformRoleIn = {
  key: string;
  name: string;
  description: string | null;
  permission_keys: PermissionKey[];
};

export type PlatformRolePatch = {
  name?: string | null;
  description?: string | null;
  permission_keys?: PermissionKey[] | null;
};

export type PlatformRoleOut = {
  id: string;
  key: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permission_keys: PermissionKey[];
  created_at: string;
  updated_at: string;
};

export type PlatformRolesPage = {
  items: PlatformRoleOut[];
  next_cursor: string | null;
};

export type PlatformRoleGrantIn = { role_id: string };

export type PlatformRoleGrantOut = {
  id: string;
  auth_user_id: string;
  role_id: string;
  role_key: string;
  granted_at: string;
  granted_by: string | null;
};

export type PlatformRoleGrantsPage = {
  items: PlatformRoleGrantOut[];
  next_cursor: string | null;
};

export type WorkspaceRoleIn = PlatformRoleIn;
export type WorkspaceRolePatch = PlatformRolePatch;

export type WorkspaceRoleOut = PlatformRoleOut & { workspace_id: string };

export type WorkspaceRolesPage = {
  items: WorkspaceRoleOut[];
  next_cursor: string | null;
};

export type WorkspaceRoleGrantIn = { role_id: string };

export type WorkspaceRoleGrantOut = {
  id: string;
  auth_user_id: string;
  workspace_id: string;
  role_id: string;
  role_key: string;
  granted_at: string;
  granted_by: string | null;
};

export type WorkspaceRoleGrantsPage = {
  items: WorkspaceRoleGrantOut[];
  next_cursor: string | null;
};
```

- [ ] **Step 2: Commit**

```bash
git add packages/api-types/src/role.ts
git commit -m "feat(api-types): PlatformRole* + WorkspaceRole* mirrors"
```

### Task 1B.3: api-types — re-export

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/packages/api-types/src/index.ts` (full file)

- [ ] **Step 1: Read current contents**

Run: `cat packages/api-types/src/index.ts`
Expected: `export * from "./me";`

- [ ] **Step 2: Replace with the new re-export set**

```ts
export * from "./me";
export * from "./permission";
export * from "./role";
```

- [ ] **Step 3: Verify the package typechecks**

Run: `pnpm --filter @xtrusio/api-types typecheck`
Expected: exit 0, no errors.

- [ ] **Step 4: Commit**

```bash
git add packages/api-types/src/index.ts
git commit -m "feat(api-types): re-export permission + role"
```

### Task 1B.4: query-keys registry — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/lib/query-keys.test.ts`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/lib/query-keys.ts`

- [ ] **Step 1: Write the failing test**

```ts
// apps/web/src/lib/query-keys.test.ts
import { describe, expect, it } from "vitest";
import { qk } from "./query-keys";

describe("qk — TanStack Query key registry", () => {
  it("returns a stable tuple for permissionsCatalog", () => {
    expect(qk.permissionsCatalog()).toEqual(["permissions", "catalog"]);
  });

  it("returns a stable tuple for platformRoles", () => {
    expect(qk.platformRoles()).toEqual(["platform", "roles"]);
  });

  it("namespaces workspaceRoles by workspaceId", () => {
    expect(qk.workspaceRoles("wid-1")).toEqual(["workspace", "wid-1", "roles"]);
    expect(qk.workspaceRoles("wid-2")).not.toEqual(qk.workspaceRoles("wid-1"));
  });

  it("returns a stable tuple for platformAudit", () => {
    expect(qk.platformAudit()).toEqual(["platform", "audit-log"]);
  });

  it("namespaces workspaceAudit by workspaceId", () => {
    expect(qk.workspaceAudit("wid-1")).toEqual([
      "workspace",
      "wid-1",
      "audit-log",
    ]);
  });

  it("namespaces workspaceInvites by workspaceId", () => {
    expect(qk.workspaceInvites("wid-1")).toEqual([
      "workspace",
      "wid-1",
      "invites",
    ]);
  });

  it("does not collide platform vs workspace namespaces", () => {
    expect(qk.platformRoles()[0]).not.toEqual(qk.workspaceRoles("any")[0]);
    expect(qk.platformAudit()[0]).not.toEqual(qk.workspaceAudit("any")[0]);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @xtrusio/web exec vitest run src/lib/query-keys.test.ts`
Expected: FAIL ("Cannot find module './query-keys'").

- [ ] **Step 3: Write the registry**

```ts
// apps/web/src/lib/query-keys.ts
// Central registry for every TanStack Query key tuple. Every consumer must
// import keys from here (never inline strings) so cache invalidation never
// silently misses.

export const qk = {
  permissionsCatalog: () => ["permissions", "catalog"] as const,
  platformRoles: () => ["platform", "roles"] as const,
  workspaceRoles: (workspaceId: string) =>
    ["workspace", workspaceId, "roles"] as const,
  platformAudit: () => ["platform", "audit-log"] as const,
  workspaceAudit: (workspaceId: string) =>
    ["workspace", workspaceId, "audit-log"] as const,
  workspaceInvites: (workspaceId: string) =>
    ["workspace", workspaceId, "invites"] as const,
};
```

- [ ] **Step 4: Run to verify it passes**

Run: `pnpm --filter @xtrusio/web exec vitest run src/lib/query-keys.test.ts`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/lib/query-keys.ts apps/web/src/lib/query-keys.test.ts
git commit -m "feat(web): qk — central TanStack Query key registry"
```

### Task 1B.5: lib/api — role + catalog fetchers

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/lib/api.ts` (append after the existing `postAcceptInvite` at line 159)

- [ ] **Step 1: Add the new imports at the top of the file**

Open `apps/web/src/lib/api.ts`. Replace the existing `import type { MeResponse } from "@xtrusio/api-types";` line (line 2) with:

```ts
import type {
  MeResponse,
  PermissionsCatalog,
  PlatformRoleIn,
  PlatformRoleOut,
  PlatformRolePatch,
  PlatformRolesPage,
  WorkspaceRoleIn,
  WorkspaceRoleOut,
  WorkspaceRolePatch,
  WorkspaceRolesPage,
} from "@xtrusio/api-types";
```

- [ ] **Step 2: Append the fetchers at the bottom of the file**

After the existing `postAcceptInvite` function (the last function in the file), append:

```ts
// ----- Permissions catalog (P6c Slice 1A) -----

export async function fetchPermissionsCatalog(): Promise<PermissionsCatalog> {
  return apiFetch<PermissionsCatalog>("/api/permissions/catalog");
}

// ----- Platform role CRUD (consumes P4 routes) -----

export async function fetchPlatformRoles(
  cursor?: string,
): Promise<PlatformRolesPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<PlatformRolesPage>(`/api/platform/roles${qs}`);
}

export async function postPlatformRole(
  body: PlatformRoleIn,
): Promise<PlatformRoleOut> {
  return apiFetch<PlatformRoleOut>("/api/platform/roles", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function patchPlatformRole(
  id: string,
  body: PlatformRolePatch,
): Promise<PlatformRoleOut> {
  return apiFetch<PlatformRoleOut>(`/api/platform/roles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deletePlatformRole(id: string): Promise<void> {
  await apiFetch(`/api/platform/roles/${id}`, { method: "DELETE" });
}

// ----- Workspace role CRUD (consumes P5 routes) -----

export async function fetchWorkspaceRoles(
  workspaceId: string,
  cursor?: string,
): Promise<WorkspaceRolesPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<WorkspaceRolesPage>(
    `/api/workspaces/${workspaceId}/roles${qs}`,
  );
}

export async function postWorkspaceRole(
  workspaceId: string,
  body: WorkspaceRoleIn,
): Promise<WorkspaceRoleOut> {
  return apiFetch<WorkspaceRoleOut>(`/api/workspaces/${workspaceId}/roles`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function patchWorkspaceRole(
  workspaceId: string,
  id: string,
  body: WorkspaceRolePatch,
): Promise<WorkspaceRoleOut> {
  return apiFetch<WorkspaceRoleOut>(
    `/api/workspaces/${workspaceId}/roles/${id}`,
    {
      method: "PATCH",
      body: JSON.stringify(body),
    },
  );
}

export async function deleteWorkspaceRole(
  workspaceId: string,
  id: string,
): Promise<void> {
  await apiFetch(`/api/workspaces/${workspaceId}/roles/${id}`, {
    method: "DELETE",
  });
}
```

- [ ] **Step 3: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0, no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): role + catalog fetchers in lib/api"
```

### Task 1B.6: error-messages — extend for new codes + TDD

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/lib/error-messages.ts`
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/lib/error-messages.test.ts`

- [ ] **Step 1: Read the current mapping**

Run: `cat apps/web/src/lib/error-messages.ts`
Note the existing shape — the new mappings must extend the same export, not replace it.

- [ ] **Step 2: Write failing tests appended to `error-messages.test.ts`**

```ts
// Append at the bottom of apps/web/src/lib/error-messages.test.ts

import { errorMessage } from "./error-messages";

describe("errorMessage — P6c Slice 1 codes", () => {
  it("maps role_key_taken", () => {
    expect(errorMessage("role_key_taken")).toBe(
      "A role with this key already exists.",
    );
  });
  it("maps system_role_immutable", () => {
    expect(errorMessage("system_role_immutable")).toBe(
      "System roles can't be modified.",
    );
  });
  it("maps role_scope_mismatch", () => {
    expect(errorMessage("role_scope_mismatch")).toBe(
      "That role belongs to a different scope.",
    );
  });
  it("maps scope_mismatch", () => {
    expect(errorMessage("scope_mismatch")).toBe(
      "That permission belongs to a different scope.",
    );
  });
  it("maps an unknown_permission key with the offending key surfaced", () => {
    expect(errorMessage("unknown_permission: workspace.unknown")).toBe(
      "Unknown permission: workspace.unknown. Refresh the page.",
    );
  });
  it("maps single_super_admin_invariant", () => {
    expect(errorMessage("single_super_admin_invariant")).toBe(
      "You can't remove the last super admin.",
    );
  });
  it("maps owner_floor", () => {
    expect(errorMessage("owner_floor")).toBe(
      "You can't revoke the last workspace owner.",
    );
  });
  it("maps a privilege_escalation key with the offending perm surfaced", () => {
    expect(errorMessage("privilege_escalation: platform.roles.manage")).toBe(
      "You can't grant a role with a permission you lack: platform.roles.manage.",
    );
  });
  it("maps membership_not_found", () => {
    expect(errorMessage("membership_not_found")).toBe(
      "That user isn't a member of this workspace.",
    );
  });
  it("maps platform_user_not_found", () => {
    expect(errorMessage("platform_user_not_found")).toBe(
      "That user isn't a platform user.",
    );
  });
  it("falls through to the existing default for unknown codes", () => {
    const result = errorMessage("definitely-not-a-real-code");
    expect(result).toBeTruthy();
  });
});
```

- [ ] **Step 3: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/lib/error-messages.test.ts`
Expected: every new assertion FAILs because the mappings don't exist yet.

- [ ] **Step 4: Extend `error-messages.ts`**

Open `apps/web/src/lib/error-messages.ts`. The file's existing shape is a `Record<string, string>` plus an `errorMessage(code)` function. Add the new entries to the record:

```ts
// In the existing mapping object, add:
"role_key_taken": "A role with this key already exists.",
"system_role_immutable": "System roles can't be modified.",
"role_scope_mismatch": "That role belongs to a different scope.",
"scope_mismatch": "That permission belongs to a different scope.",
"single_super_admin_invariant": "You can't remove the last super admin.",
"owner_floor": "You can't revoke the last workspace owner.",
"membership_not_found": "That user isn't a member of this workspace.",
"platform_user_not_found": "That user isn't a platform user.",
"invalid cursor": "Couldn't load more events. Try refreshing.",
```

Then add a prefix-matching branch to `errorMessage(code)` for the two suffixed codes:

```ts
// At the top of errorMessage(code), before the table lookup:
if (code.startsWith("unknown_permission: ")) {
  const key = code.slice("unknown_permission: ".length);
  return `Unknown permission: ${key}. Refresh the page.`;
}
if (code.startsWith("privilege_escalation: ")) {
  const perm = code.slice("privilege_escalation: ".length);
  return `You can't grant a role with a permission you lack: ${perm}.`;
}
```

If the existing `errorMessage` function's structure differs from what's expected here, adapt to match — the rule is: prefix codes are handled first, then exact-match table lookup, then a default fallback.

- [ ] **Step 5: Run to verify it passes**

Run: `pnpm --filter @xtrusio/web exec vitest run src/lib/error-messages.test.ts`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/lib/error-messages.ts apps/web/src/lib/error-messages.test.ts
git commit -m "feat(web): error-message mappings for P6c codes"
```

---

## Slice 1C — Shared UI building blocks (TDD each)

**Goal:** Six shared blocks under `apps/web/src/components/`. Every block is stateless or owns only its own form state; data fetching happens in the page-level components above them. Every block has a unit test before the implementation lands.

### Task 1C.1: shadcn checkbox primitive

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/ui/checkbox.tsx`

- [ ] **Step 1: Add the shadcn primitive via the CLI**

Run from the repo root:

```bash
cd apps/web && pnpm dlx shadcn@latest add checkbox --yes && cd ../..
```

Expected: a new file `apps/web/src/components/ui/checkbox.tsx` (Radix wrapper, ~30 LoC). If the CLI prompts about overwrites or component config, accept defaults; the project already has `components.json`. Also installs `@radix-ui/react-checkbox` if missing.

- [ ] **Step 2: Confirm the file looks right**

Run: `head -10 apps/web/src/components/ui/checkbox.tsx`
Expected: a `Checkbox` named export, importing from `@radix-ui/react-checkbox`. If the file doesn't exist, write it manually following the shadcn convention used by `apps/web/src/components/ui/switch.tsx` for reference structure.

- [ ] **Step 3: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/ui/checkbox.tsx apps/web/package.json pnpm-lock.yaml
git commit -m "chore(web): add shadcn checkbox primitive"
```

### Task 1C.2: `<Forbidden />` page-gate fallback — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/forbidden.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/forbidden.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/forbidden.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Forbidden } from "./forbidden";

describe("<Forbidden />", () => {
  it("renders the access-denied message and a link to the landing path", () => {
    render(<Forbidden landingPath="/platform" />);
    expect(
      screen.getByText(/don't have access|don't have permission/i),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /go back|home/i });
    expect(link).toHaveAttribute("href", "/platform");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/forbidden.test.tsx`
Expected: FAIL ("Cannot find module './forbidden'").

- [ ] **Step 3: Write the component**

`<EmptyState>`'s `action` prop expects an `{ label, onClick }` shape (verified in `apps/web/src/components/empty-state.tsx`), not a ReactNode — so passing a `<Link>` isn't possible. Render the icon + copy + link as siblings instead:

```tsx
// apps/web/src/components/forbidden.tsx
import { Link } from "@tanstack/react-router";
import { ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";

export function Forbidden({ landingPath }: { landingPath: string }) {
  return (
    <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card p-8 text-center">
      <div className="rounded-full bg-muted p-3">
        <ShieldOff className="h-6 w-6 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-semibold tracking-tight">
        You don't have access to this page
      </h2>
      <p className="max-w-md text-sm text-muted-foreground">
        Your account doesn't have permission for this view. If you think that's
        a mistake, ask a workspace owner or platform super admin.
      </p>
      <Button asChild variant="outline" className="mt-2">
        <Link to={landingPath}>Go back</Link>
      </Button>
    </div>
  );
}
```

(The markup mirrors `<EmptyState>` so the design language matches; we just don't go through the `<EmptyState>` component because it doesn't support a Link-as-action.)

- [ ] **Step 4: Run to verify it passes**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/forbidden.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/forbidden.tsx apps/web/src/components/forbidden.test.tsx
git commit -m "feat(web): <Forbidden /> page-gate fallback"
```

### Task 1C.3: `<PermissionPicker />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/permission-picker.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/permission-picker.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/roles/permission-picker.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PermissionDef } from "@xtrusio/api-types";
import { PermissionPicker } from "./permission-picker";

const CATALOG: PermissionDef[] = [
  {
    scope: "platform",
    key: "platform.roles.manage",
    category: "Access control",
    description: "Create/edit/delete platform roles",
  },
  {
    scope: "platform",
    key: "platform.users.read",
    category: "Platform users",
    description: "View platform users",
  },
  {
    scope: "platform",
    key: "platform.users.invite",
    category: "Platform users",
    description: "Invite platform users",
  },
  {
    scope: "workspace",
    key: "workspace.roles.manage",
    category: "Access control",
    description: "Create/edit/delete workspace roles",
  },
  {
    scope: "workspace",
    key: "workspace.members.read",
    category: "Members",
    description: "View workspace members",
  },
];

describe("<PermissionPicker />", () => {
  it("renders only the permissions matching the scope prop", () => {
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("platform.roles.manage")).toBeInTheDocument();
    expect(screen.queryByText("workspace.roles.manage")).not.toBeInTheDocument();
  });

  it("groups permissions by category", () => {
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={() => {}}
      />,
    );
    expect(screen.getByText("Access control")).toBeInTheDocument();
    expect(screen.getByText("Platform users")).toBeInTheDocument();
  });

  it("emits onChange with the toggled key added", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={onChange}
      />,
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.roles.manage/i }),
    );
    expect(onChange).toHaveBeenCalledWith(["platform.roles.manage"]);
  });

  it("emits onChange with the toggled key removed when already present", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={["platform.roles.manage"]}
        onChange={onChange}
      />,
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.roles.manage/i }),
    );
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("per-category select-all adds every key in that category and only that category", async () => {
    const onChange = vi.fn();
    render(
      <PermissionPicker
        catalog={CATALOG}
        scope="platform"
        value={[]}
        onChange={onChange}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /select all platform users/i }),
    );
    expect(onChange).toHaveBeenCalledWith(
      expect.arrayContaining(["platform.users.read", "platform.users.invite"]),
    );
    const arg = onChange.mock.calls[0]![0] as string[];
    expect(arg).not.toContain("platform.roles.manage");
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/permission-picker.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/src/components/roles/permission-picker.tsx
import { useMemo } from "react";
import type { PermissionDef, PermissionScope } from "@xtrusio/api-types";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

type Props = {
  catalog: PermissionDef[];
  scope: PermissionScope;
  value: string[];
  onChange: (next: string[]) => void;
};

export function PermissionPicker({ catalog, scope, value, onChange }: Props) {
  const filtered = useMemo(
    () => catalog.filter((p) => p.scope === scope),
    [catalog, scope],
  );
  const byCategory = useMemo(() => {
    const map = new Map<string, PermissionDef[]>();
    for (const p of filtered) {
      const list = map.get(p.category) ?? [];
      list.push(p);
      map.set(p.category, list);
    }
    return Array.from(map.entries()).map(([category, perms]) => ({
      category,
      perms,
    }));
  }, [filtered]);

  const selected = useMemo(() => new Set(value), [value]);

  function toggle(key: string) {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    onChange(Array.from(next));
  }

  function selectAllForCategory(perms: PermissionDef[]) {
    const next = new Set(selected);
    for (const p of perms) next.add(p.key);
    onChange(Array.from(next));
  }

  return (
    <div className="space-y-6">
      {byCategory.map(({ category, perms }) => (
        <section key={category} className="space-y-2">
          <header className="flex items-center justify-between">
            <h3 className="text-sm font-medium tracking-tight">{category}</h3>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => selectAllForCategory(perms)}
              aria-label={`Select all ${category}`}
            >
              Select all
            </Button>
          </header>
          <ul className="space-y-2">
            {perms.map((p) => {
              const id = `perm-${p.key}`;
              return (
                <li key={p.key} className="flex items-start gap-3">
                  <Checkbox
                    id={id}
                    checked={selected.has(p.key)}
                    onCheckedChange={() => toggle(p.key)}
                    aria-label={p.key}
                  />
                  <div className="space-y-0.5">
                    <Label htmlFor={id} className="font-mono text-xs">
                      {p.key}
                    </Label>
                    <p className="text-xs text-muted-foreground">
                      {p.description}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/permission-picker.test.tsx`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/roles/permission-picker.tsx apps/web/src/components/roles/permission-picker.test.tsx
git commit -m "feat(web): <PermissionPicker /> grouped checkbox picker"
```

### Task 1C.4: `<RoleFormDialog />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/role-form-dialog.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/role-form-dialog.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/roles/role-form-dialog.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PermissionDef, PlatformRoleOut } from "@xtrusio/api-types";
import { RoleFormDialog } from "./role-form-dialog";

const CATALOG: PermissionDef[] = [
  {
    scope: "platform",
    key: "platform.users.read",
    category: "Platform users",
    description: "View platform users",
  },
  {
    scope: "platform",
    key: "platform.users.invite",
    category: "Platform users",
    description: "Invite platform users",
  },
];

const EXISTING: PlatformRoleOut = {
  id: "role-1",
  key: "dispatcher",
  name: "Dispatcher",
  description: "Routes incoming requests",
  is_system: false,
  permission_keys: ["platform.users.read"],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

describe("<RoleFormDialog />", () => {
  it("renders an empty form in create mode", () => {
    render(
      <RoleFormDialog
        mode="create"
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error={null}
        onSubmit={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByLabelText(/key/i)).toHaveValue("");
    expect(screen.getByLabelText(/name/i)).toHaveValue("");
  });

  it("prefills name/description/permissions in edit mode and disables the key field", () => {
    render(
      <RoleFormDialog
        mode="edit"
        role={EXISTING}
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error={null}
        onSubmit={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(screen.getByLabelText(/key/i)).toHaveValue("dispatcher");
    expect(screen.getByLabelText(/key/i)).toBeDisabled();
    expect(screen.getByLabelText(/name/i)).toHaveValue("Dispatcher");
    expect(
      screen.getByRole("checkbox", { name: /platform.users.read/i }),
    ).toBeChecked();
  });

  it("calls onSubmit with the form payload on save", async () => {
    const onSubmit = vi.fn();
    render(
      <RoleFormDialog
        mode="create"
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error={null}
        onSubmit={onSubmit}
        onOpenChange={() => {}}
      />,
    );
    await userEvent.type(screen.getByLabelText(/key/i), "auditor");
    await userEvent.type(screen.getByLabelText(/name/i), "Auditor");
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.users.read/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(onSubmit).toHaveBeenCalledWith({
      key: "auditor",
      name: "Auditor",
      description: null,
      permission_keys: ["platform.users.read"],
    });
  });

  it("renders the error message in the footer", () => {
    render(
      <RoleFormDialog
        mode="create"
        catalog={CATALOG}
        scope="platform"
        open
        pending={false}
        error="A role with this key already exists."
        onSubmit={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(
      screen.getByText(/role with this key already exists/i),
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/role-form-dialog.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/src/components/roles/role-form-dialog.tsx
import { useEffect, useState } from "react";
import type {
  PermissionDef,
  PermissionScope,
  PlatformRoleOut,
  WorkspaceRoleOut,
} from "@xtrusio/api-types";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { PermissionPicker } from "./permission-picker";

type RoleLike = PlatformRoleOut | WorkspaceRoleOut;

export type RoleFormPayload = {
  key: string;
  name: string;
  description: string | null;
  permission_keys: string[];
};

type Props = {
  mode: "create" | "edit";
  role?: RoleLike;
  catalog: PermissionDef[];
  scope: PermissionScope;
  open: boolean;
  pending: boolean;
  error: string | null;
  onSubmit: (payload: RoleFormPayload) => void;
  onOpenChange: (open: boolean) => void;
};

export function RoleFormDialog({
  mode,
  role,
  catalog,
  scope,
  open,
  pending,
  error,
  onSubmit,
  onOpenChange,
}: Props) {
  const [key, setKey] = useState(role?.key ?? "");
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [permissionKeys, setPermissionKeys] = useState<string[]>(
    role?.permission_keys ?? [],
  );

  // Reset state whenever the dialog is opened with a different role.
  useEffect(() => {
    if (open) {
      setKey(role?.key ?? "");
      setName(role?.name ?? "");
      setDescription(role?.description ?? "");
      setPermissionKeys(role?.permission_keys ?? []);
    }
  }, [open, role]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      key,
      name,
      description: description.trim() === "" ? null : description,
      permission_keys: permissionKeys,
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Create role" : `Edit role — ${role?.name}`}
          </DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="role-key">Key</Label>
              <Input
                id="role-key"
                value={key}
                onChange={(e) => setKey(e.target.value)}
                pattern="^[a-z][a-z0-9_]*$"
                disabled={mode === "edit"}
                required
              />
              <p className="text-xs text-muted-foreground">
                lower_snake_case, e.g. <code>dispatcher</code>
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role-name">Name</Label>
              <Input
                id="role-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="role-description">Description (optional)</Label>
            <Textarea
              id="role-description"
              value={description ?? ""}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
          <div className="space-y-1.5">
            <Label>Permissions</Label>
            <PermissionPicker
              catalog={catalog}
              scope={scope}
              value={permissionKeys}
              onChange={setPermissionKeys}
            />
          </div>
          {error ? (
            <p className="text-sm text-destructive">{error}</p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/role-form-dialog.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/roles/role-form-dialog.tsx apps/web/src/components/roles/role-form-dialog.test.tsx
git commit -m "feat(web): <RoleFormDialog /> create/edit dialog"
```

### Task 1C.5: `<RolesTable />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/roles-table.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/roles-table.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/roles/roles-table.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PlatformRoleOut } from "@xtrusio/api-types";
import { RolesTable } from "./roles-table";

const ROLES: PlatformRoleOut[] = [
  {
    id: "r1",
    key: "super_admin",
    name: "Super admin",
    description: null,
    is_system: true,
    permission_keys: [],
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
  {
    id: "r2",
    key: "dispatcher",
    name: "Dispatcher",
    description: "Routes requests",
    is_system: false,
    permission_keys: ["platform.users.read"],
    created_at: "2026-05-22T00:00:00Z",
    updated_at: "2026-05-22T00:00:00Z",
  },
];

describe("<RolesTable />", () => {
  it("renders every role", () => {
    render(
      <RolesTable
        roles={ROLES}
        canManage
        onEdit={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText("super_admin")).toBeInTheDocument();
    expect(screen.getByText("dispatcher")).toBeInTheDocument();
  });

  it("shows a system badge for is_system rows and hides their action buttons", () => {
    render(
      <RolesTable
        roles={ROLES}
        canManage
        onEdit={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.getByText(/system/i)).toBeInTheDocument();
    // The super_admin row's action buttons should be hidden.
    const superRow = screen.getByText("super_admin").closest("tr")!;
    expect(superRow.querySelector('[aria-label^="Edit"]')).toBeNull();
    expect(superRow.querySelector('[aria-label^="Delete"]')).toBeNull();
    // The dispatcher row's buttons should be present.
    const dispatcherRow = screen.getByText("dispatcher").closest("tr")!;
    expect(dispatcherRow.querySelector('[aria-label^="Edit"]')).not.toBeNull();
  });

  it("hides all action buttons when canManage is false", () => {
    render(
      <RolesTable
        roles={ROLES}
        canManage={false}
        onEdit={() => {}}
        onDelete={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /edit/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });

  it("fires onEdit / onDelete with the row's role", async () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    render(
      <RolesTable
        roles={ROLES}
        canManage
        onEdit={onEdit}
        onDelete={onDelete}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /edit dispatcher/i }),
    );
    expect(onEdit).toHaveBeenCalledWith(ROLES[1]);
    await userEvent.click(
      screen.getByRole("button", { name: /delete dispatcher/i }),
    );
    expect(onDelete).toHaveBeenCalledWith(ROLES[1]);
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/roles-table.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/src/components/roles/roles-table.tsx
import { Pencil, Trash2 } from "lucide-react";
import type { PlatformRoleOut, WorkspaceRoleOut } from "@xtrusio/api-types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type RoleLike = PlatformRoleOut | WorkspaceRoleOut;

type Props = {
  roles: RoleLike[];
  canManage: boolean;
  onEdit: (r: RoleLike) => void;
  onDelete: (r: RoleLike) => void;
};

export function RolesTable({ roles, canManage, onEdit, onDelete }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Key</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Permissions</TableHead>
          <TableHead className="w-32" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {roles.map((r) => {
          const lock = r.is_system;
          return (
            <TableRow key={r.id}>
              <TableCell className="font-mono text-xs">{r.key}</TableCell>
              <TableCell>
                <div className="flex items-center gap-2">
                  <span>{r.name}</span>
                  {lock ? <Badge variant="secondary">System</Badge> : null}
                </div>
                {r.description ? (
                  <p className="text-xs text-muted-foreground">
                    {r.description}
                  </p>
                ) : null}
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {r.permission_keys.length}{" "}
                {r.permission_keys.length === 1 ? "permission" : "permissions"}
              </TableCell>
              <TableCell className="text-right">
                {canManage && !lock ? (
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Edit ${r.key}`}
                      onClick={() => onEdit(r)}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={`Delete ${r.key}`}
                      onClick={() => onDelete(r)}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ) : null}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/roles-table.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/roles/roles-table.tsx apps/web/src/components/roles/roles-table.test.tsx
git commit -m "feat(web): <RolesTable /> with system badge + conditional actions"
```

### Task 1C.6: `<DeleteRoleDialog />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/delete-role-dialog.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/roles/delete-role-dialog.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/roles/delete-role-dialog.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { PlatformRoleOut } from "@xtrusio/api-types";
import { DeleteRoleDialog } from "./delete-role-dialog";

const ROLE: PlatformRoleOut = {
  id: "r1",
  key: "dispatcher",
  name: "Dispatcher",
  description: null,
  is_system: false,
  permission_keys: ["platform.users.read"],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

describe("<DeleteRoleDialog />", () => {
  it("renders the cascade-warning copy", () => {
    render(
      <DeleteRoleDialog
        role={ROLE}
        pending={false}
        onConfirm={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(
      screen.getByText(/anyone currently granted this role will lose it/i),
    ).toBeInTheDocument();
  });

  it("fires onConfirm once on confirm", async () => {
    const onConfirm = vi.fn();
    render(
      <DeleteRoleDialog
        role={ROLE}
        pending={false}
        onConfirm={onConfirm}
        onOpenChange={() => {}}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("closes silently on cancel without firing onConfirm", async () => {
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <DeleteRoleDialog
        role={ROLE}
        pending={false}
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("does not render when role is null", () => {
    render(
      <DeleteRoleDialog
        role={null}
        pending={false}
        onConfirm={() => {}}
        onOpenChange={() => {}}
      />,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/delete-role-dialog.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/src/components/roles/delete-role-dialog.tsx
import type { PlatformRoleOut, WorkspaceRoleOut } from "@xtrusio/api-types";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

type Props = {
  role: PlatformRoleOut | WorkspaceRoleOut | null;
  pending: boolean;
  onConfirm: () => void;
  onOpenChange: (open: boolean) => void;
};

export function DeleteRoleDialog({
  role,
  pending,
  onConfirm,
  onOpenChange,
}: Props) {
  return (
    <Dialog open={role !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete role — {role?.name}</DialogTitle>
          <DialogDescription>
            This action can't be undone. Anyone currently granted this role
            will lose it (revocation cascades immediately).
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={pending}
          >
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={onConfirm}
            disabled={pending}
          >
            {pending ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/roles/delete-role-dialog.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/roles/delete-role-dialog.tsx apps/web/src/components/roles/delete-role-dialog.test.tsx
git commit -m "feat(web): <DeleteRoleDialog /> with cascade-warning copy"
```

---

## Slice 1D — Per-scope page components + routes

### Task 1D.1: `<PlatformRolesPage />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/platform-roles-page.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/platform-roles-page.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/platform-roles-page.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, PermissionsCatalog } from "@xtrusio/api-types";
import { PlatformRolesPage } from "./platform-roles-page";

const ME_WITH: MeResponse = {
  user_id: "u-1",
  email: "super@xtrusio.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.roles.manage"],
  tenants: [],
  pending_invite: null,
};

const ME_WITHOUT: MeResponse = {
  ...ME_WITH,
  platform_permissions: [],
};

const CATALOG: PermissionsCatalog = {
  items: [
    {
      scope: "platform",
      key: "platform.users.read",
      category: "Platform users",
      description: "View platform users",
    },
  ],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchPermissionsCatalog: vi.fn(),
    fetchPlatformRoles: vi.fn(),
    postPlatformRole: vi.fn(),
    patchPlatformRole: vi.fn(),
    deletePlatformRole: vi.fn(),
  };
});

import * as api from "@/lib/api";

function renderWith(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <PlatformRolesPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchPermissionsCatalog).mockResolvedValue(CATALOG);
  vi.mocked(api.fetchPlatformRoles).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
});

describe("<PlatformRolesPage />", () => {
  it("renders <Forbidden /> when me lacks platform.roles.manage", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITHOUT);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByText(/don't have access|don't have permission/i),
      ).toBeInTheDocument();
    });
  });

  it("renders table + Create button when perm is held", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /create role/i }),
      ).toBeInTheDocument();
    });
  });

  it("posts a new role and invalidates the platform-roles cache key", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.postPlatformRole).mockResolvedValue({
      id: "r-new",
      key: "auditor",
      name: "Auditor",
      description: null,
      is_system: false,
      permission_keys: ["platform.users.read"],
      created_at: "2026-05-22T00:00:00Z",
      updated_at: "2026-05-22T00:00:00Z",
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      screen.getByRole("button", { name: /create role/i }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /create role/i }),
    );
    await userEvent.type(screen.getByLabelText(/key/i), "auditor");
    await userEvent.type(screen.getByLabelText(/name/i), "Auditor");
    await userEvent.click(
      screen.getByRole("checkbox", { name: /platform.users.read/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(api.postPlatformRole).toHaveBeenCalledWith({
        key: "auditor",
        name: "Auditor",
        description: null,
        permission_keys: ["platform.users.read"],
      });
    });
    // After invalidation, fetchPlatformRoles is re-called.
    await waitFor(() => {
      expect(vi.mocked(api.fetchPlatformRoles)).toHaveBeenCalledTimes(2);
    });
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/platform-roles-page.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the page**

```tsx
// apps/web/src/components/platform-roles-page.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { PlatformRoleOut } from "@xtrusio/api-types";
import {
  deletePlatformRole,
  errorCode,
  fetchPermissionsCatalog,
  fetchPlatformRoles,
  patchPlatformRole,
  postPlatformRole,
} from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import {
  getDefaultLandingPath,
  hasPlatformPerm,
  useMe,
} from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { RolesTable } from "@/components/roles/roles-table";
import {
  RoleFormDialog,
  type RoleFormPayload,
} from "@/components/roles/role-form-dialog";
import { DeleteRoleDialog } from "@/components/roles/delete-role-dialog";

export function PlatformRolesPage() {
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.roles.manage")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body />;
}

function Body() {
  const qc = useQueryClient();
  const { data: catalog } = useQuery({
    queryKey: qk.permissionsCatalog(),
    queryFn: fetchPermissionsCatalog,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const { data: rolesPage } = useQuery({
    queryKey: qk.platformRoles(),
    queryFn: () => fetchPlatformRoles(),
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<PlatformRoleOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<PlatformRoleOut | null>(
    null,
  );
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (body: RoleFormPayload) => postPlatformRole(body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformRoles() });
      setCreateOpen(false);
      setFormError(null);
    },
    onError: (e) => setFormError(errorMessage(errorCode(e))),
  });

  const update = useMutation({
    mutationFn: (args: { id: string; body: RoleFormPayload }) =>
      patchPlatformRole(args.id, args.body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformRoles() });
      setEditTarget(null);
      setFormError(null);
    },
    onError: (e) => setFormError(errorMessage(errorCode(e))),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deletePlatformRole(id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.platformRoles() });
      setDeleteTarget(null);
    },
  });

  return (
    <>
      <PageHeader
        title="Platform roles"
        description="Custom platform-scope roles and their permission sets. System roles can't be edited."
        action={
          <Button
            onClick={() => {
              setFormError(null);
              setCreateOpen(true);
            }}
          >
            Create role
          </Button>
        }
      />
      <RolesTable
        roles={rolesPage?.items ?? []}
        canManage
        onEdit={(r) => {
          setFormError(null);
          setEditTarget(r as PlatformRoleOut);
        }}
        onDelete={(r) => setDeleteTarget(r as PlatformRoleOut)}
      />
      <RoleFormDialog
        mode="create"
        catalog={catalog?.items ?? []}
        scope="platform"
        open={createOpen}
        pending={create.isPending}
        error={formError}
        onSubmit={(p) => create.mutate(p)}
        onOpenChange={(o) => {
          if (!o) setFormError(null);
          setCreateOpen(o);
        }}
      />
      <RoleFormDialog
        mode="edit"
        role={editTarget ?? undefined}
        catalog={catalog?.items ?? []}
        scope="platform"
        open={editTarget !== null}
        pending={update.isPending}
        error={formError}
        onSubmit={(p) =>
          editTarget && update.mutate({ id: editTarget.id, body: p })
        }
        onOpenChange={(o) => {
          if (!o) {
            setFormError(null);
            setEditTarget(null);
          }
        }}
      />
      <DeleteRoleDialog
        role={deleteTarget}
        pending={remove.isPending}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget.id)}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null);
        }}
      />
    </>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/platform-roles-page.test.tsx`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/platform-roles-page.tsx apps/web/src/components/platform-roles-page.test.tsx
git commit -m "feat(web): <PlatformRolesPage /> consuming P4 role CRUD"
```

### Task 1D.2: `_app.platform.roles` file-route

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/routes/_app.platform.roles.tsx`

- [ ] **Step 1: Write the route file**

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { PlatformRolesPage } from "@/components/platform-roles-page";

export const Route = createFileRoute("/_app/platform/roles")({
  component: PlatformRolesPage,
});
```

- [ ] **Step 2: Typecheck to refresh `routeTree.gen.ts`**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0. The generated route tree refreshes automatically; do not hand-edit `routeTree.gen.ts`.

- [ ] **Step 3: Commit (include the regenerated route tree)**

```bash
git add apps/web/src/routes/_app.platform.roles.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /platform/roles file-route"
```

### Task 1D.3: `<WorkspaceRolesPage />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/workspace-roles-page.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/workspace-roles-page.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/workspace-roles-page.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { MeResponse, PermissionsCatalog } from "@xtrusio/api-types";
import { WorkspaceRolesPage } from "./workspace-roles-page";

const WID = "wid-1";

const ME_OWNER: MeResponse = {
  user_id: "u-1",
  email: "owner@acme.com",
  platform: null,
  platform_permissions: [],
  tenants: [
    {
      id: WID,
      slug: "acme",
      name: "Acme",
      role: "owner",
      permissions: ["workspace.roles.manage"],
    },
  ],
  pending_invite: null,
};

const ME_NOT_OWNER: MeResponse = {
  ...ME_OWNER,
  tenants: [
    {
      ...ME_OWNER.tenants[0]!,
      role: "editor",
      permissions: ["workspace.members.read"],
    },
  ],
};

const CATALOG: PermissionsCatalog = {
  items: [
    {
      scope: "workspace",
      key: "workspace.members.read",
      category: "Members",
      description: "View workspace members",
    },
  ],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchPermissionsCatalog: vi.fn(),
    fetchWorkspaceRoles: vi.fn(),
    postWorkspaceRole: vi.fn(),
    patchWorkspaceRole: vi.fn(),
    deleteWorkspaceRole: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchPermissionsCatalog).mockResolvedValue(CATALOG);
  vi.mocked(api.fetchWorkspaceRoles).mockResolvedValue({
    items: [],
    next_cursor: null,
  });
});

function renderWith(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceRolesPage workspaceId={WID} />
    </QueryClientProvider>,
  );
}

describe("<WorkspaceRolesPage />", () => {
  it("renders <Forbidden /> when me lacks workspace.roles.manage for this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NOT_OWNER);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByText(/don't have access|don't have permission/i),
      ).toBeInTheDocument();
    });
  });

  it("renders table + Create button when perm is held for this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /create role/i }),
      ).toBeInTheDocument();
    });
  });

  it("posts a new role scoped to this workspace and invalidates the workspace-scoped cache key", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.postWorkspaceRole).mockResolvedValue({
      id: "r-new",
      workspace_id: WID,
      key: "viewer",
      name: "Viewer",
      description: null,
      is_system: false,
      permission_keys: ["workspace.members.read"],
      created_at: "2026-05-22T00:00:00Z",
      updated_at: "2026-05-22T00:00:00Z",
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByRole("button", { name: /create role/i }));
    await userEvent.click(
      screen.getByRole("button", { name: /create role/i }),
    );
    await userEvent.type(screen.getByLabelText(/key/i), "viewer");
    await userEvent.type(screen.getByLabelText(/name/i), "Viewer");
    await userEvent.click(
      screen.getByRole("checkbox", { name: /workspace.members.read/i }),
    );
    await userEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(api.postWorkspaceRole).toHaveBeenCalledWith(WID, {
        key: "viewer",
        name: "Viewer",
        description: null,
        permission_keys: ["workspace.members.read"],
      });
    });
    await waitFor(() => {
      expect(vi.mocked(api.fetchWorkspaceRoles)).toHaveBeenCalledTimes(2);
    });
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/workspace-roles-page.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the page**

```tsx
// apps/web/src/components/workspace-roles-page.tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { WorkspaceRoleOut } from "@xtrusio/api-types";
import {
  deleteWorkspaceRole,
  errorCode,
  fetchPermissionsCatalog,
  fetchWorkspaceRoles,
  patchWorkspaceRole,
  postWorkspaceRole,
} from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { qk } from "@/lib/query-keys";
import {
  getDefaultLandingPath,
  hasWorkspacePerm,
  useMe,
} from "@/lib/me-adapter";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { RolesTable } from "@/components/roles/roles-table";
import {
  RoleFormDialog,
  type RoleFormPayload,
} from "@/components/roles/role-form-dialog";
import { DeleteRoleDialog } from "@/components/roles/delete-role-dialog";

export function WorkspaceRolesPage({ workspaceId }: { workspaceId: string }) {
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.roles.manage")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body workspaceId={workspaceId} />;
}

function Body({ workspaceId }: { workspaceId: string }) {
  const qc = useQueryClient();
  const { data: catalog } = useQuery({
    queryKey: qk.permissionsCatalog(),
    queryFn: fetchPermissionsCatalog,
    staleTime: Infinity,
    gcTime: Infinity,
  });
  const { data: rolesPage } = useQuery({
    queryKey: qk.workspaceRoles(workspaceId),
    queryFn: () => fetchWorkspaceRoles(workspaceId),
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<WorkspaceRoleOut | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<WorkspaceRoleOut | null>(
    null,
  );
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (body: RoleFormPayload) => postWorkspaceRole(workspaceId, body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.workspaceRoles(workspaceId) });
      setCreateOpen(false);
      setFormError(null);
    },
    onError: (e) => setFormError(errorMessage(errorCode(e))),
  });

  const update = useMutation({
    mutationFn: (args: { id: string; body: RoleFormPayload }) =>
      patchWorkspaceRole(workspaceId, args.id, args.body),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.workspaceRoles(workspaceId) });
      setEditTarget(null);
      setFormError(null);
    },
    onError: (e) => setFormError(errorMessage(errorCode(e))),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteWorkspaceRole(workspaceId, id),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.workspaceRoles(workspaceId) });
      setDeleteTarget(null);
    },
  });

  return (
    <>
      <PageHeader
        title="Workspace roles"
        description="Custom workspace-scope roles and their permission sets. System roles can't be edited."
        action={
          <Button
            onClick={() => {
              setFormError(null);
              setCreateOpen(true);
            }}
          >
            Create role
          </Button>
        }
      />
      <RolesTable
        roles={rolesPage?.items ?? []}
        canManage
        onEdit={(r) => {
          setFormError(null);
          setEditTarget(r as WorkspaceRoleOut);
        }}
        onDelete={(r) => setDeleteTarget(r as WorkspaceRoleOut)}
      />
      <RoleFormDialog
        mode="create"
        catalog={catalog?.items ?? []}
        scope="workspace"
        open={createOpen}
        pending={create.isPending}
        error={formError}
        onSubmit={(p) => create.mutate(p)}
        onOpenChange={(o) => {
          if (!o) setFormError(null);
          setCreateOpen(o);
        }}
      />
      <RoleFormDialog
        mode="edit"
        role={editTarget ?? undefined}
        catalog={catalog?.items ?? []}
        scope="workspace"
        open={editTarget !== null}
        pending={update.isPending}
        error={formError}
        onSubmit={(p) =>
          editTarget && update.mutate({ id: editTarget.id, body: p })
        }
        onOpenChange={(o) => {
          if (!o) {
            setFormError(null);
            setEditTarget(null);
          }
        }}
      />
      <DeleteRoleDialog
        role={deleteTarget}
        pending={remove.isPending}
        onConfirm={() => deleteTarget && remove.mutate(deleteTarget.id)}
        onOpenChange={(o) => {
          if (!o) setDeleteTarget(null);
        }}
      />
    </>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/workspace-roles-page.test.tsx`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/workspace-roles-page.tsx apps/web/src/components/workspace-roles-page.test.tsx
git commit -m "feat(web): <WorkspaceRolesPage /> consuming P5 role CRUD"
```

### Task 1D.4: Replace the `_app.workspace.$workspaceId.roles` placeholder

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.roles.tsx` (full file rewrite — current placeholder is at lines 1-21)

- [ ] **Step 1: Write the new file**

```tsx
import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceRolesPage } from "@/components/workspace-roles-page";

export const Route = createFileRoute("/_app/workspace/$workspaceId/roles")({
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/roles",
  });
  return <WorkspaceRolesPage workspaceId={workspaceId} />;
}
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/routes/_app.workspace.$workspaceId.roles.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /workspace/\$id/roles now consumes <WorkspaceRolesPage />"
```

---

## Slice 1 Wrap — End-of-slice verification, review, PR, merge

### Task 1W.1: Controller-run end-of-slice gate

This task is controller-run (NOT delegated to a subagent), per `feedback_lean_review_workflow`.

- [ ] **Step 1: Reset the test DB**

Run: `STARTUP_RECONCILE_TOLERANT=false make test-clean`
Expected: exit 0, "clean" reset, then full backend pytest finishes; record pass/fail counts.

- [ ] **Step 2: Full lint + typecheck + frontend test gate**

Run: `STARTUP_RECONCILE_TOLERANT=false make check`
Expected: exit 0. This must include `ruff check`, `ruff format --check`, `mypy --strict apps/api`, `turbo typecheck`, and `vitest run` across the web package. A slice can be lint-clean but format-dirty (happened in P3c) — `ruff format --check` is the guard.

- [ ] **Step 3: Smoke check manually (USER-DRIVEN)**

Hand back to user. The user runs `make dev`, logs in as super_admin, browses to `/platform/roles`, exercises create + edit + delete, then to `/workspace/<wid>/roles` as a workspace owner and exercises the same. The user also confirms `rbac_audit_log` rows appear after each mutation.

### Task 1W.2: Opus code-quality review

This task is controller-run; the user invokes `/ultrareview` against the slice branch (or whatever flow the project has adopted). Apply any blocking review findings before opening the PR. Non-blocking nits can be parked in HANDOFF for a later phase.

### Task 1W.3: Open the PR

- [ ] **Step 1: Write the PR body**

Save to `docs/superpowers/PR-rbac-p6c-slice-1-body.md`. Include:

```markdown
## Summary

- Add `GET /api/permissions/catalog` — authenticated-only, no perm gate, returns the static CATALOG tuple. ~30 LoC route + ~25 LoC schemas + 5 tests.
- Add `<PermissionPicker>`, `<RoleFormDialog>`, `<RolesTable>`, `<DeleteRoleDialog>`, `<Forbidden>` shared blocks.
- Ship `<PlatformRolesPage>` at `/platform/roles` and `<WorkspaceRolesPage>` at `/workspace/$id/roles`, consuming the P4 + P5 role-CRUD APIs already on `main`.
- Central `qk` TanStack Query key registry at `apps/web/src/lib/query-keys.ts`.
- Error-message mappings for `role_key_taken`, `unknown_permission`, `system_role_immutable`, `single_super_admin_invariant`, `owner_floor`, `privilege_escalation:*`, and friends (also covers P6d codes pre-emptively so error-mapping doesn't need a second edit later).
- Adds shadcn `checkbox` primitive.

No migration. Alembic head stays at `0009`.

## Test plan

- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean` green
- [ ] `STARTUP_RECONCILE_TOLERANT=false make check` green (ruff check + ruff format --check + mypy --strict + turbo typecheck + vitest)
- [ ] Manual: super_admin can create/edit/delete a custom platform role, audit row appears
- [ ] Manual: workspace owner can create/edit/delete a custom workspace role for their workspace, audit row appears
- [ ] Manual: a workspace `editor` is shown `<Forbidden />` at `/workspace/<their-wid>/roles`
- [ ] Manual: clicking Delete on a custom role shows the cascade warning copy

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 2: Open the PR**

Run:
```bash
gh pr create --title "P6c Slice 1 — Roles CRUD + permissions catalog" \
  --body "$(cat docs/superpowers/PR-rbac-p6c-slice-1-body.md)"
```

### Task 1W.4: Merge + HANDOFF update

- [ ] **Step 1: Merge the PR after CI is green**

Run:
```bash
gh pr merge <PR#> --squash
gh pr view <PR#> --json state  # confirm "MERGED"
```

- [ ] **Step 2: Update HANDOFF.md**

Open `docs/superpowers/HANDOFF.md`. Move "P6c Slice 1" from the NEXT block into the "Done & merged" table at the top with a one-line summary and commit hash. Update the prose lead-in to reflect that Slice 1 is merged and Slice 2 (Audit log) is next.

- [ ] **Step 3: Commit the HANDOFF update separately**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(handoff): mark P6c Slice 1 merged; pivot NEXT to Slice 2"
git push
```

---

## Self-review checklist (run before declaring Slice 1 done)

- [ ] Every spec section 3 row marked P6c is implemented or explicitly out-of-scope-for-Slice-2/3
- [ ] No `TBD` / `TODO` markers in shipped code or tests
- [ ] Every test file has at least one assertion that exercises an error path (not only happy paths)
- [ ] `qk.*` is the only source of TanStack Query keys in Slice 1 code (no inline `["platform","roles"]`)
- [ ] `is_system` roles cannot be Edit/Deleted from the UI
- [ ] `<Forbidden />` is rendered (not redirected) for permission-denied — keeps URL intact for sharing
- [ ] `make check` exits 0 from a CLEAN DB (`STARTUP_RECONCILE_TOLERANT=false make test-clean` first)
- [ ] HANDOFF.md updated post-merge
