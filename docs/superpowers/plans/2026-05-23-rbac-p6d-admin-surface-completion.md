# RBAC P6d — Admin surface completion (list endpoints + grant UIs + workspace settings)

> **For agentic workers:** This plan is implemented in two dispatches: **P6d-A** (backend) first, then **P6d-B** (frontend) after the backend's api-types are committed. ONE Opus subagent per dispatch, ship-it style.

**Date:** 2026-05-23
**Status:** Approved — ready for implementation
**Builds on:** `main` after P6c Slices 1 + 2 + 3 land. Single Alembic head `0009`.
**Drains from `docs/superpowers/HANDOFF.md`:** the "NEXT — P6d" gated phase.

---

## 1. Goal

Complete the RBAC admin surface so a super_admin and a workspace owner can do **every** admin action through the UI: list platform users, list workspace members, grant/revoke roles to specific users, and rename their workspace. After P6d the app is "ready for the first product feature" — no remaining admin-surface gaps.

### Explicitly out of scope (parked)

- Member invitation flow on the workspace settings page (already covered by Slice 3's Members port).
- Workspace slug change (slug is the URL — separate destructive flow, not in P6d).
- Workspace deletion (separate destructive flow).
- ETag/If-Match concurrency on settings.
- Audit-log filters / search.
- Role-delete dialog cascade count UX (handled in Slice 1 already; precise count remains generic).
- Realtime push of grants/revokes.

---

## 2. Locked decisions

1. **Two atomic dispatches:** P6d-A (backend = 3 endpoints + tests + api-types mirrors), P6d-B (frontend = 3 UIs + tests). The frontend dispatch starts after P6d-A's api-types are committed.
2. **No migration.** All 3 endpoints read/write existing tables; no DDL.
3. **Workspace settings — MVP is `name` only.** The `tenants` table has `slug` (immutable in this flow), `name` (mutable), `created_at`/`updated_at` (server-managed). For P6d, the only mutable field is `name`. Future polish can add description/logo/timezone via a tenant-attributes JSONB column — not in P6d.
4. **Permission gates:**
   - `GET /api/platform/users` → `platform.users.read`
   - `GET /api/workspaces/{wid}/members` → `workspace.members.read`
   - `GET /api/workspaces/{wid}/settings` → `workspace.settings.read` (NEW catalog entry — see section 5)
   - `PUT /api/workspaces/{wid}/settings` → `workspace.settings.manage` (NEW catalog entry — see section 5)
5. **Pagination:** `GET /api/platform/users` and `GET /api/workspaces/{wid}/members` use the existing `core/pagination.py:CursorParams` + UUID cursor codec, matching `services.platform_role_grants:list_platform_role_grants` for consistency.
6. **Response shape — `PlatformUserListItemOut`:** `{ id: UUID, email: str, role: PlatformRole, is_active: bool, created_at: datetime, last_sign_in_at: datetime | None, granted_role_count: int }`. `granted_role_count` is a left-joined count from `user_roles` filtered to `scope='platform' AND workspace_id IS NULL`. The full grant list per user is fetched separately via the existing `GET /api/platform/users/{user_id}/roles` endpoint (P4).
7. **Response shape — `WorkspaceMemberListItemOut`:** `{ user_id: UUID, email: str, role: TenantRole, joined_at: datetime, granted_role_count: int }` where `joined_at = tenant_memberships.created_at`. `granted_role_count` from `user_roles` filtered to `scope='workspace' AND workspace_id=:wid`.
8. **Audit-log writes** on `PUT /api/workspaces/{wid}/settings` only (the GETs are read-only and untracked, matching audit-log convention). Settings mutation writes `action='workspace.settings.updated'` with before/after JSON diff of the changed fields.
9. **Frontend grant-management UI design:** each user/member row has a `[Manage roles]` button that opens a `<GrantManagerDialog>` Sheet. Inside: existing grants listed with revoke buttons, plus an `[Add grant]` row that opens a role-picker (filtered to the user's manageable scope). Reuses the existing `<PermissionPicker>` and shadcn primitives.
10. **No new shadcn primitives** — Sheet + Button + Badge + Select already exist (verified by Slice 1).
11. **TanStack Query keys:** extend `lib/query-keys.ts` with `qk.platformUsers()`, `qk.platformUsersWithCursor(cursor)`, `qk.workspaceMembers(wid)`, `qk.workspaceMembersWithCursor(wid, cursor)`, `qk.workspaceSettings(wid)`. Match the Slice 1 patterns.

---

## 3. New permission catalog entries

Add to `apps/api/src/xtrusio_api/rbac/catalog.py` (the static `CATALOG` tuple):

```python
PermissionDef(
    key="workspace.settings.read",
    description="Read this workspace's settings.",
    category="Workspace settings",
    scope="workspace",
),
PermissionDef(
    key="workspace.settings.manage",
    description="Edit this workspace's settings (rename, etc.).",
    category="Workspace settings",
    scope="workspace",
),
```

Both default-attach to the `owner` and `admin` workspace system roles via the existing `SYSTEM_ROLE_BINDINGS` table in the same file. The system-role reconciler picks them up on next startup / `make rbac-seed`.

**No `platform.users.read` / `platform.users.manage` entries** — they already exist on `main` (added in P4).

**No `workspace.members.read` / `workspace.members.manage` entries** — they already exist on `main` (added in P5).

---

## 4. File tree

### P6d-A (backend)

```
Create:
  apps/api/src/xtrusio_api/routes/platform_users.py          NEW — GET /api/platform/users
  apps/api/src/xtrusio_api/routes/workspace_members.py       NEW — GET /api/workspaces/{wid}/members
  apps/api/src/xtrusio_api/routes/workspace_settings.py      NEW — GET/PUT /api/workspaces/{wid}/settings
  apps/api/src/xtrusio_api/services/platform_users.py        NEW — list_platform_users service
  apps/api/src/xtrusio_api/services/workspace_members.py     NEW — list_workspace_members service
  apps/api/src/xtrusio_api/services/workspace_settings.py    NEW — get_workspace_settings / update_workspace_settings
  apps/api/src/xtrusio_api/schemas/platform_user_list.py     NEW — PlatformUserListItemOut + PlatformUsersPage
  apps/api/src/xtrusio_api/schemas/workspace_member_list.py  NEW — WorkspaceMemberListItemOut + WorkspaceMembersPage
  apps/api/src/xtrusio_api/schemas/workspace_settings.py     NEW — WorkspaceSettingsOut + WorkspaceSettingsUpdate
  apps/api/tests/services/test_platform_users.py             NEW — list + pagination + scope-isolation
  apps/api/tests/services/test_workspace_members.py          NEW — list + pagination + scope-isolation
  apps/api/tests/services/test_workspace_settings.py         NEW — get + put + audit-write + permission gating
  apps/api/tests/routes/test_platform_users.py               NEW — route-level gating + 200/403/404
  apps/api/tests/routes/test_workspace_members.py            NEW — route-level gating + 200/403/404
  apps/api/tests/routes/test_workspace_settings.py           NEW — route-level gating + 200/403/404 + 422 validation
  packages/api-types/src/platform-user-list.ts               NEW — TS mirror
  packages/api-types/src/workspace-member-list.ts            NEW — TS mirror
  packages/api-types/src/workspace-settings.ts               NEW — TS mirror

Modify:
  apps/api/src/xtrusio_api/main.py                           +3 router.include_router lines
  apps/api/src/xtrusio_api/rbac/catalog.py                   +2 PermissionDef + binding rows
  packages/api-types/src/index.ts                            +3 re-export lines
```

### P6d-B (frontend)

```
Create:
  apps/web/src/components/platform-users-page.tsx               NEW — page body
  apps/web/src/components/platform-users-page.test.tsx          NEW
  apps/web/src/components/workspace-members-list-page.tsx       NEW — adds the LIST half to the Members page (alongside Slice-3's invite UI)
  apps/web/src/components/workspace-members-list-page.test.tsx  NEW
  apps/web/src/components/workspace-settings-page.tsx           NEW — page body
  apps/web/src/components/workspace-settings-page.test.tsx      NEW
  apps/web/src/components/grants/grant-manager-dialog.tsx       NEW — shared by platform + workspace grant flows
  apps/web/src/components/grants/grant-manager-dialog.test.tsx  NEW
  apps/web/src/components/grants/role-picker.tsx                NEW — single-role select scoped to platform OR workspace
  apps/web/src/components/grants/role-picker.test.tsx           NEW
  apps/web/src/routes/_app.platform.users.tsx                   REPLACE (currently a placeholder) — file-route mounts <PlatformUsersPage />

Modify:
  apps/web/src/lib/api.ts                                    +6 fetchers (list users / list members / get-put settings / list grants × 2 already exist from P4/P5 — confirm)
  apps/web/src/lib/query-keys.ts                             +5 qk entries (per section 2 decision 11)
  apps/web/src/lib/error-messages.ts                         +error keys for new failure modes (e.g. workspace_not_found, settings_validation_error)
  apps/web/src/components/workspace-members-page.tsx         (created in Slice 3) — embed the LIST UI under the invite section
  apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx  REPLACE placeholder with file-route mounting <WorkspaceSettingsPage workspaceId={...} />
```

---

## 5. P6d-A — Backend

### Task A.1: New permission catalog entries

**File:** `apps/api/src/xtrusio_api/rbac/catalog.py`

- [ ] **Step 1:** Add the two `PermissionDef` entries from section 3 to the `CATALOG` tuple. Keep them in alphabetical order with the rest of `workspace.*` keys.
- [ ] **Step 2:** Add the binding rows to `SYSTEM_ROLE_BINDINGS` so `owner` and `admin` workspace system roles get both new perms by default.

### Task A.2: `GET /api/platform/users`

**Service** at `services/platform_users.py`:

```python
async def list_platform_users(
    db: AsyncSession,
    *,
    cursor: UUID | None,
    limit: int,
) -> tuple[list[PlatformUserListRow], str | None]:
    """List all platform users with their granted-role count.

    Ordered by id ASC. Cursor is the last id of the previous page.
    Returns (rows, next_cursor) where rows is a list of mappings
    {id, email, role, is_active, created_at, last_sign_in_at, granted_role_count}.
    """
```

Use a `SELECT platform_users.* , COUNT(user_roles.id) AS granted_role_count FROM platform_users LEFT JOIN user_roles ON user_roles.auth_user_id = platform_users.id AND user_roles.workspace_id IS NULL GROUP BY platform_users.id ORDER BY platform_users.id LIMIT :limit+1` with cursor `WHERE platform_users.id > :cursor`.

**Schema** at `schemas/platform_user_list.py`:

```python
class PlatformUserListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: EmailStr
    role: PlatformRole
    is_active: bool
    created_at: datetime
    last_sign_in_at: datetime | None
    granted_role_count: int


class PlatformUsersPage(BaseModel):
    items: list[PlatformUserListItemOut]
    next_cursor: str | None = None
```

**Route** at `routes/platform_users.py`:

```python
router = APIRouter(prefix="/api/platform/users", tags=["platform-users"])


@router.get("", response_model=PlatformUsersPage)
async def list_users(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PlatformUsersPage:
    await require_permission(db, user.user_id, "platform.users.read")
    params = CursorParams(cursor=cursor, limit=limit)
    try:
        decoded = params.decoded()
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from e
    rows, next_cursor = await list_platform_users(db, cursor=decoded, limit=params.effective_limit)
    return PlatformUsersPage(
        items=[PlatformUserListItemOut.model_validate(r) for r in rows],
        next_cursor=next_cursor,
    )
```

**Note:** the route prefix collides with the existing `routes/platform_role_grants.py` (which also uses `prefix="/api/platform/users"`). Both routers can coexist — they declare different sub-paths (`""` vs `"/{user_id}/roles"`). Register **after** `platform_role_grants_router` in `main.py` to keep the include order stable.

**Tests** at `tests/services/test_platform_users.py` and `tests/routes/test_platform_users.py`:

- Service: `test_list_empty_returns_empty_page`, `test_list_orders_by_id_asc`, `test_list_paginates_via_cursor`, `test_list_includes_granted_role_count`, `test_list_distinguishes_zero_grants_from_non_existent_user`.
- Route: `test_list_200_for_super_admin`, `test_list_403_for_non_platform_user`, `test_list_403_for_platform_user_without_users_read`, `test_list_400_on_invalid_cursor`.

### Task A.3: `GET /api/workspaces/{wid}/members`

**Service** at `services/workspace_members.py`:

```python
async def list_workspace_members(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: UUID | None,
    limit: int,
) -> tuple[list[WorkspaceMemberListRow], str | None]:
    """List members of a workspace with their granted-role count.

    Ordered by tenant_memberships.id ASC. Cursor is the last id.
    Joins to auth.users for email; joins to user_roles for the count.
    """
```

Use:
```sql
SELECT tm.id AS membership_id,
       tm.user_id,
       au.email,
       tm.role,
       tm.created_at AS joined_at,
       COUNT(ur.id) AS granted_role_count
FROM tenant_memberships tm
LEFT JOIN auth.users au ON au.id = tm.user_id
LEFT JOIN user_roles ur ON ur.auth_user_id = tm.user_id AND ur.workspace_id = :wid
WHERE tm.tenant_id = :wid
  AND (:cursor IS NULL OR tm.id > :cursor)
GROUP BY tm.id, au.email
ORDER BY tm.id
LIMIT :limit + 1
```

**Schema** at `schemas/workspace_member_list.py`:

```python
class WorkspaceMemberListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: UUID
    email: EmailStr | None  # null if auth.users row hard-deleted
    role: TenantRole
    joined_at: datetime
    granted_role_count: int


class WorkspaceMembersPage(BaseModel):
    items: list[WorkspaceMemberListItemOut]
    next_cursor: str | None = None
```

**Route** at `routes/workspace_members.py` — mirror the platform_users route shape:

```python
router = APIRouter(prefix="/api/workspaces/{workspace_id}/members", tags=["workspace-members"])


@router.get("", response_model=WorkspaceMembersPage)
async def list_members(
    workspace_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=0, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> WorkspaceMembersPage:
    await require_permission(db, user.user_id, "workspace.members.read", workspace_id=workspace_id)
    # ... cursor decode + service call + response build (same pattern as platform_users)
```

**Note:** the prefix collides with `routes/workspace_role_grants.py` which uses `/api/workspaces/{workspace_id}/members/{user_id}/roles`. Both routers coexist — different sub-paths. Register `workspace_members_router` **before** `workspace_role_grants_router` in main.py so FastAPI matches `""` and `"/{user_id}/roles"` correctly.

**Tests** at `tests/services/test_workspace_members.py` and `tests/routes/test_workspace_members.py`:

- Service: `test_list_empty_workspace_returns_empty_page`, `test_list_orders_by_membership_id_asc`, `test_list_paginates_via_cursor`, `test_list_filters_to_this_workspace_only` (scope isolation), `test_list_handles_hard_deleted_auth_user_with_null_email`, `test_list_includes_grant_count_per_member`.
- Route: `test_list_200_for_workspace_owner`, `test_list_403_for_non_member`, `test_list_403_for_member_without_members_read`, `test_list_404_for_nonexistent_workspace_with_members_read_grant_only_at_other_workspace`, `test_list_400_on_invalid_cursor`.

### Task A.4: `GET/PUT /api/workspaces/{wid}/settings`

**Service** at `services/workspace_settings.py`:

```python
class WorkspaceNotFoundError(LookupError):
    """The workspace_id doesn't match any tenants row."""


async def get_workspace_settings(
    db: AsyncSession,
    *,
    workspace_id: UUID,
) -> WorkspaceSettingsRow:
    """Return {id, slug, name, created_at, updated_at} for the workspace.

    Raises WorkspaceNotFoundError if the tenant doesn't exist.
    """


async def update_workspace_settings(
    db: AsyncSession,
    *,
    actor_id: UUID,
    workspace_id: UUID,
    name: str,
) -> WorkspaceSettingsRow:
    """Update the workspace's name. Writes an audit-log row with before/after.

    Raises WorkspaceNotFoundError if missing.
    """
```

The update uses `core/audit.write_audit_event` with:
- `scope="workspace"`, `workspace_id=workspace_id`
- `actor_auth_user_id=actor_id`
- `action="workspace.settings.updated"`
- `target_type="tenant"`, `target_id=workspace_id`
- `before={"name": old_name}`, `after={"name": new_name}`

Only write the audit row if `name` actually changed (no-op writes are not logged).

**Schema** at `schemas/workspace_settings.py`:

```python
class WorkspaceSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    slug: str
    name: str
    created_at: datetime
    updated_at: datetime


class WorkspaceSettingsUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
```

**Route** at `routes/workspace_settings.py`:

```python
router = APIRouter(prefix="/api/workspaces/{workspace_id}/settings", tags=["workspace-settings"])


@router.get("", response_model=WorkspaceSettingsOut)
async def get_settings(
    workspace_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceSettingsOut:
    await require_permission(db, user.user_id, "workspace.settings.read", workspace_id=workspace_id)
    try:
        row = await get_workspace_settings(db, workspace_id=workspace_id)
    except WorkspaceNotFoundError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace_not_found") from e
    return WorkspaceSettingsOut.model_validate(row)


@router.put("", response_model=WorkspaceSettingsOut)
async def put_settings(
    workspace_id: UUID,
    body: WorkspaceSettingsUpdate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceSettingsOut:
    await require_permission(db, user.user_id, "workspace.settings.manage", workspace_id=workspace_id)
    try:
        row = await update_workspace_settings(
            db, actor_id=user.user_id, workspace_id=workspace_id, name=body.name
        )
        await db.commit()
    except WorkspaceNotFoundError as e:
        await db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, "workspace_not_found") from e
    return WorkspaceSettingsOut.model_validate(row)
```

**Tests** at `tests/services/test_workspace_settings.py` and `tests/routes/test_workspace_settings.py`:

- Service: `test_get_returns_settings`, `test_get_raises_when_workspace_not_found`, `test_update_changes_name_and_writes_audit`, `test_update_noop_does_not_write_audit`, `test_update_raises_when_workspace_not_found`.
- Route: `test_get_200_for_workspace_owner`, `test_get_403_without_settings_read`, `test_get_404_for_nonexistent_workspace_with_settings_read_grant_at_other_workspace`, `test_put_200_renames`, `test_put_403_without_settings_manage`, `test_put_422_on_empty_name`, `test_put_422_on_oversized_name`.

### Task A.5: TS mirrors + re-exports

For each new schema file in `packages/api-types/src/`, create a `.ts` mirror that **exactly** matches the Pydantic shape:

```ts
// platform-user-list.ts
import type { PlatformRole } from "./me"; // reuse existing enum mirror

export interface PlatformUserListItem {
  id: string; // UUID
  email: string;
  role: PlatformRole;
  is_active: boolean;
  created_at: string; // ISO 8601
  last_sign_in_at: string | null;
  granted_role_count: number;
}

export interface PlatformUsersPage {
  items: PlatformUserListItem[];
  next_cursor: string | null;
}
```

Similarly for `workspace-member-list.ts` and `workspace-settings.ts`. Then add `export * from "./platform-user-list"` (etc.) to `packages/api-types/src/index.ts`.

### Task A.6: Wire routers in `main.py`

Add the three `app.include_router(...)` lines for the new routers. Order matters for the prefix collisions noted above:
- `app.include_router(platform_users_routes.router)` **after** `platform_role_grants_routes.router`
- `app.include_router(workspace_members_routes.router)` **before** `workspace_role_grants_routes.router`
- `app.include_router(workspace_settings_routes.router)` — order doesn't matter; place near the other `workspace_*` registrations

### Task A.7: Backend end-of-slice gate

```bash
uv run ruff check apps/api
uv run ruff format --check apps/api
uv run mypy apps/api
uv run pytest apps/api/tests/services/test_platform_users.py \
              apps/api/tests/services/test_workspace_members.py \
              apps/api/tests/services/test_workspace_settings.py \
              apps/api/tests/routes/test_platform_users.py \
              apps/api/tests/routes/test_workspace_members.py \
              apps/api/tests/routes/test_workspace_settings.py -v
pnpm --filter @xtrusio/api-types typecheck
```

Expected: all green. Do NOT run the full `pytest apps/api/tests` — the controller runs that at the very end of the night after all PRs land.

### Task A.8: Commit + push

One atomic commit:
```
feat(api): P6d backend — list endpoints + workspace settings + 2 new perm catalog entries

- GET /api/platform/users (cursor-paginated; gated by platform.users.read; includes granted_role_count)
- GET /api/workspaces/{wid}/members (cursor-paginated; gated by workspace.members.read)
- GET/PUT /api/workspaces/{wid}/settings (gated by workspace.settings.{read,manage})
- 2 new catalog perms: workspace.settings.read, workspace.settings.manage (bound to owner+admin system roles)
- TS mirrors in @xtrusio/api-types + re-exports
- audit-log write on settings.updated (only when name actually changed)
```

No `Co-Authored-By` trailers. Author = user's GitHub identity.

---

## 6. P6d-B — Frontend

**Pre-flight:** confirm `packages/api-types/src/index.ts` re-exports the three new types from P6d-A. Confirm `apps/web/src/lib/api.ts` already has `fetchPlatformRoleGrants` / `fetchWorkspaceRoleGrants` (P4/P5); if not, add them.

### Task B.1: Fetchers + query keys

**`apps/web/src/lib/api.ts`** — add:
```ts
export async function fetchPlatformUsers(cursor: string | null): Promise<PlatformUsersPage> { ... }
export async function fetchWorkspaceMembers(workspaceId: string, cursor: string | null): Promise<WorkspaceMembersPage> { ... }
export async function fetchWorkspaceSettings(workspaceId: string): Promise<WorkspaceSettingsOut> { ... }
export async function updateWorkspaceSettings(workspaceId: string, body: { name: string }): Promise<WorkspaceSettingsOut> { ... }
```

If `fetchPlatformRoleGrants(userId, cursor)` and `fetchWorkspaceRoleGrants(workspaceId, userId, cursor)` don't already exist, add them too (they should — P4/P5 had them).

**`apps/web/src/lib/query-keys.ts`** — add:
```ts
platformUsers: () => ["platform-users"] as const,
platformUsersWithCursor: (cursor: string | null) => ["platform-users", cursor] as const,
workspaceMembers: (wid: string) => ["workspace-members", wid] as const,
workspaceMembersWithCursor: (wid: string, cursor: string | null) => ["workspace-members", wid, cursor] as const,
workspaceSettings: (wid: string) => ["workspace-settings", wid] as const,
```

**`apps/web/src/lib/error-messages.ts`** — add user-friendly messages for `workspace_not_found`, `single_super_admin_invariant`, etc. if not already mapped.

### Task B.2: Shared `<RolePicker>` component

`apps/web/src/components/grants/role-picker.tsx` — wraps shadcn `<Select>` to render a single-role chooser scoped to either `platform` or `workspace`. Fetches the role list via the existing P4/P5 endpoints (`GET /api/platform/roles` or `GET /api/workspaces/{wid}/roles`) with `staleTime: 60_000`. Props:
```ts
type RolePickerProps =
  | { scope: "platform"; value: string | null; onChange: (id: string) => void }
  | { scope: "workspace"; workspaceId: string; value: string | null; onChange: (id: string) => void };
```

Tests cover both scopes, loading state, empty list state, selection.

### Task B.3: Shared `<GrantManagerDialog>` Sheet

`apps/web/src/components/grants/grant-manager-dialog.tsx` — Sheet that opens when user clicks `[Manage roles]` on a user/member row. Shows:
- Header: "{email} — manage roles"
- Existing grants list (each row: role name + badge + `[Revoke]` button)
- An `[Add grant]` section with `<RolePicker>` + `[Grant]` button
- Footer: dismiss button

Props (discriminated by scope):
```ts
type GrantManagerDialogProps =
  | { scope: "platform"; userId: string; email: string; onClose: () => void }
  | { scope: "workspace"; workspaceId: string; userId: string; email: string; onClose: () => void };
```

On grant/revoke success, invalidate the relevant `qk.*` keys so the parent list re-renders with updated `granted_role_count`. On error, show inline footer error using `lib/error-messages`.

Tests cover both scopes, happy paths, error mappings, single-super_admin invariant guard, privilege-escalation guard.

### Task B.4: `<PlatformUsersPage>` at `/platform/users`

`apps/web/src/components/platform-users-page.tsx`:
- Gated by `hasPlatformPerm(me, "platform.users.read")` — renders `<Forbidden />` if missing.
- Renders an `<AuditTable>`-style table: `[email | role | grants | last sign in | actions]`.
- `[Manage roles]` button on each row opens `<GrantManagerDialog scope="platform" userId={user.id} email={user.email} />`.
- Load-more pagination via `<LoadMoreButton>` (the Slice 2 shared block).
- Empty state: "No platform users yet."

Replace the existing placeholder at `apps/web/src/routes/_app.platform.users.tsx` with a file-route that mounts `<PlatformUsersPage />`.

Tests at `.test.tsx` cover: gate, list render, pagination, dialog open/close, empty state.

### Task B.5: Workspace members LIST UI (extends the Slice-3 Members page)

`apps/web/src/components/workspace-members-list-page.tsx`:
- Gated by `hasWorkspacePerm(me, wid, "workspace.members.read")` — renders `<Forbidden />` if missing.
- Renders the members table: `[email | role | grants | joined | actions]`.
- `[Manage roles]` per row opens `<GrantManagerDialog scope="workspace" workspaceId={wid} userId={member.user_id} email={member.email} />` (gated by `workspace.members.manage`).
- Load-more pagination.

Modify the Slice-3 `apps/web/src/components/workspace-members-page.tsx` to embed the LIST section UNDER the existing invite section, separated by a divider. Both halves share the same page route.

Tests cover: gate (separately from invite gate), list render, dialog open/close, manage-roles gating.

### Task B.6: `<WorkspaceSettingsPage>`

`apps/web/src/components/workspace-settings-page.tsx`:
- Gated by `hasWorkspacePerm(me, wid, "workspace.settings.read")` for view, `workspace.settings.manage` for edit (inputs disabled if read-only).
- Form fields: `name` (text input, max 200 chars, required). `slug`, `created_at` shown read-only below.
- `[Save]` button triggers `updateWorkspaceSettings(wid, { name })`. On success, invalidate `qk.workspaceSettings(wid)` and show a toast ("Settings saved").
- Inline form error on 422 / 403; uses `lib/error-messages`.

Replace the existing placeholder at `apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx` with a file-route that mounts `<WorkspaceSettingsPage workspaceId={...} />`.

Tests cover: gate (read+manage), happy save, validation error, network error, no-op submit (button stays enabled / disabled — pick simpler).

### Task B.7: Frontend end-of-slice gate

```bash
pnpm --filter @xtrusio/api-types typecheck
pnpm --filter @xtrusio/web typecheck
pnpm --filter @xtrusio/web exec eslint <slice files>
pnpm --filter @xtrusio/web exec vitest run
```

Expected: all green. Do NOT run the full `make check` — controller runs that at end of night.

### Task B.8: Commit + push

One atomic commit:
```
feat(web): P6d frontend — platform users + workspace members list + settings + shared grant-manager

- New <PlatformUsersPage> at /platform/users (gated by platform.users.read)
- New <WorkspaceMembersListPage> embedded in /workspace/$wid/members under Slice-3's invite UI
- New <WorkspaceSettingsPage> at /workspace/$wid/settings (gated by workspace.settings.{read,manage})
- Shared <GrantManagerDialog> + <RolePicker> consumed by both scopes
- New fetchers + qk entries + error mappings
```

---

## 7. End-of-P6d verification (controller)

After both P6d-A and P6d-B PRs are merged, the controller runs the single full gate:

```bash
STARTUP_RECONCILE_TOLERANT=false make test-clean
STARTUP_RECONCILE_TOLERANT=false make check
```

Expected: all green from a clean DB. The full backend pytest sweep covers all ~300+ tests; the frontend vitest covers all components.

Iterate to green at controller level — no subagent re-dispatch needed for lint/typecheck fixes.

---

## 8. PR + merge sequence

### P6d-A PR

Branch: `rbac-p6d-backend-list-endpoints`. PR body at `docs/superpowers/PR-rbac-p6d-backend-body.md` written by the subagent at end-of-implementation.

```bash
gh pr create --title "P6d backend — list endpoints + workspace settings + 2 new perms" \
  --body "$(cat docs/superpowers/PR-rbac-p6d-backend-body.md)" --base main
```

User reviews + squash-merges.

### P6d-B PR

Branch: `rbac-p6d-frontend-admin-uis` (off main after P6d-A merges so api-types are present). PR body at `docs/superpowers/PR-rbac-p6d-frontend-body.md`.

```bash
gh pr create --title "P6d frontend — grant management + workspace settings UI" \
  --body "$(cat docs/superpowers/PR-rbac-p6d-frontend-body.md)" --base main
```

User reviews + squash-merges.

### HANDOFF update

After both merge, controller updates `docs/superpowers/HANDOFF.md`:
- Move P6c (all 3 slices) + P6d into the Done & merged table.
- Pivot NEXT to "first product feature" (TBD by user).
- Optionally schedule the LATE cleanup (drop legacy enum columns) once every backend enum read is gone.

---

## 9. Self-review checklist (before declaring P6d done)

- [ ] `platform.users.read` user can list all platform users from `/platform/users`.
- [ ] Non-super-admin platform user cannot list via the same page (sees `<Forbidden />`).
- [ ] Workspace owner can list members at `/workspace/$wid/members` (LIST section visible).
- [ ] Workspace editor cannot list (no `workspace.members.read`) — sees `<Forbidden />` on the LIST section while still seeing the invite UI gate (if they have invite perm) — confirm this UX is not weird.
- [ ] Hard-deleted auth user shows up as null email in the workspace member list — UI renders "—".
- [ ] `<GrantManagerDialog>` correctly invalidates list-cache on grant/revoke (count badge updates without a page reload).
- [ ] Single-super_admin invariant blocked at grant-time with a user-friendly error (not just 409).
- [ ] Privilege-escalation blocked at grant-time (try granting a perm you don't have).
- [ ] `<WorkspaceSettingsPage>`: rename writes an audit row visible at `/workspace/$wid/audit-log` immediately on refresh.
- [ ] Rename to the same name is a no-op (no audit row written).
- [ ] 422 on empty name shows inline form error, not a generic toast.
- [ ] No `Co-Authored-By: Claude` lines anywhere in the diff.
- [ ] No `!` non-null assertions in any new frontend file.
- [ ] No hardcoded colors. No demo data. No new files exceed 500 LoC.
- [ ] `make check` exits 0 from a clean DB.
- [ ] HANDOFF updated post-merge.
