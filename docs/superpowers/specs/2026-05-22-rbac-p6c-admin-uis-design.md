# Design — P6c: RBAC admin UIs (consume P4/P5 APIs)

**Date:** 2026-05-22
**Status:** Approved (all sections) — ready for implementation planning
**Builds on:** `main` @ `8e709f7` (P6b merged; Alembic head `0009`; backend 279 / web 74 green).
**Drains from `docs/superpowers/HANDOFF.md`:** the "NEXT — P6c" gated phase.
**Splits off `P6d` (future):** missing list endpoints + grant-management UIs + workspace Settings UI (section 3).

---

## 1. Purpose & goals

Build the platform- and workspace-scope **RBAC admin UIs** that consume the P4 + P5 backend APIs already
on `main`. After P6c, a super_admin can create/edit/delete custom platform roles and read the
platform audit log; a workspace owner can do the same for their own workspace; remaining frontend
enum reads (`UserMenu`, `tenant-users-page`) become permission-driven.

P6c is **frontend-driven** with three tiny backend additions that exist only to unblock the UIs
(section 3). It does NOT ship grant-management UIs or workspace-settings UI — those depend on backend
list-users / settings endpoints that don't exist yet, and were factored into a separate **P6d**
phase per the user's explicit scope decision (brainstorming session 2026-05-22).

### Non-goals (explicitly deferred to P6d)

- `GET /api/platform/users` and `GET /api/workspaces/{wid}/members` list endpoints.
- `GET/PUT /api/workspaces/{wid}/settings` endpoint and the Settings UI.
- Platform + workspace **grant-management** UIs (depend on the list endpoints above).
- ETag/If-Match concurrency for role edits.
- Realtime push of revocation events.
- Removing the workspace Settings placeholder route — its placeholder copy is updated, route stays.

---

## 2. Locked decisions

1. **Three slices, each its own PR + lean review cycle** (per `feedback_lean_review_workflow`):
   - **Slice 1 — Roles CRUD** (platform + workspace), shared building blocks, `GET /api/permissions/catalog`.
   - **Slice 2 — Audit log** (platform + workspace), shared building blocks, audit-event `actor_email` join.
   - **Slice 3 — Members port + nav + cleanup** (pure frontend).
2. **Component reuse model:** shared low-level pieces, per-scope pages on top. No scope-parameterised
   page-level components (avoids `if (scope === "workspace")` accumulation). Shared blocks:
   `<PermissionPicker>`, `<RoleFormDialog>`, `<RolesTable>`, `<DeleteRoleDialog>`,
   `<AuditTable>`, `<AuditDetailDrawer>`, `<LoadMoreButton>`, `<Forbidden>`.
3. **Permission-picker UX:** grouped checkbox list by `category` with per-category select-all
   (collapsible sections). Each checkbox shows description as helper text.
4. **Audit log UX:** dense `[time | actor email | action | target]` table; click a row to open a
   `Sheet` drawer with pretty-printed `before` / `after` JSON.
5. **Pagination UX:** explicit `[Load more]` button driven by the cursor returned from the API.
   Implementation: local `useState<{items, next_cursor}[]>` accumulator + plain `useQuery` per
   cursor change. `useInfiniteQuery` deliberately not adopted (project hasn't used it; existing
   pagination patterns use plain `useQuery` + cursor; keeps test surface flat).
6. **Permission gating:** three layers — sidebar nav filter (already in P6b), per-route component
   `<Forbidden />` fallback (new), backend `require_permission()` (already on every P4/P5 route).
   Backend remains the source of truth; the route gate is purely UX (avoid 403 flash on deep
   links / stale `me` cache).
7. **Permission catalog source:** new authenticated `GET /api/permissions/catalog` endpoint that
   serialises the static `CATALOG` tuple. Frontend cache is `staleTime: Infinity` — catalog only
   changes with a deploy.
8. **Audit-event actor email:** extend `AuditEventOut` with `actor_email: str | None`. Backend
   service does `LEFT JOIN auth.users` so a hard-deleted user (or null actor) yields `None`. UI
   renders "—" for null.
9. **Role-delete cascade behaviour:** `user_roles.role_id ON DELETE CASCADE` (confirmed in migration
   `0006`, ref `services/platform_roles.py:311` docstring). Deleting a role silently revokes every
   grant of it. `<DeleteRoleDialog>` shows a generic warning ("Anyone currently granted this role
   will lose it"). A precise count requires a `GET /api/.../roles/{id}/grants?count_only` style
   endpoint — out of scope; P6d follow-up consideration only if needed.
10. **TanStack Query keys** live in `lib/query-keys.ts` (new). All consumers read keys via
    `qk.platformRoles()`, `qk.workspaceRoles(wid)`, `qk.platformAudit()`, `qk.workspaceAudit(wid)`,
    `qk.workspaceInvites(wid)`, `qk.permissionsCatalog()`. Never stringly-typed.
11. **Error mapping** lives in the existing `lib/error-messages.ts` — extended with the new backend
    error codes (section 5.4).
12. **Adds one shadcn primitive: `checkbox`.** The current `apps/web/src/components/ui/` set has no
    `checkbox.tsx` (verified: `tabs, card, popover, sheet, scroll-area, label, sonner, tooltip,
    switch, breadcrumb, command, avatar, dialog, badge, sidebar, table, separator, button,
    dropdown-menu, select, textarea, input, skeleton`). Slice 1 adds `ui/checkbox.tsx` via
    `pnpm dlx shadcn@latest add checkbox` (standard Radix `@radix-ui/react-checkbox` wrapper, ~30
    LoC, no behavioural risk). All other primitives the design needs (Dialog, Sheet, Table, Button,
    Badge, Tooltip, ScrollArea) already exist.

---

## 3. Scope split: P6c vs P6d

| Surface | P6c (this phase) | P6d (future) |
|---|---|---|
| Platform Roles CRUD UI | ✅ | — |
| Platform Audit log UI | ✅ | — |
| Workspace Roles CRUD UI (per workspace) | ✅ | — |
| Workspace Audit log UI (per workspace) | ✅ | — |
| Workspace Members page | invite UI only (port from `tenant-users-page`) | + member list once endpoint exists |
| Workspace Settings page | placeholder copy updated only (no API ref) | full UI |
| Platform Roles + grants navigation | ✅ adds Roles + Audit log to platform nav | — |
| `<UserMenu>` rewrite | ✅ | — |
| `tenant-users-page` enum → permission | ✅ | — |
| `GET /api/permissions/catalog` | ✅ (~20 LoC, Slice 1) | — |
| `AuditEventOut.actor_email` LEFT JOIN | ✅ (~10 LoC each, Slice 2) | — |
| `GET /api/platform/users` | — | ✅ |
| `GET /api/workspaces/{wid}/members` | — | ✅ |
| `GET/PUT /api/workspaces/{wid}/settings` | — | ✅ |
| Platform grant-management UI | — | ✅ (depends on list users endpoint) |
| Workspace grant-management UI | — | ✅ (depends on list members endpoint) |
| Workspace Settings UI | — | ✅ (depends on settings endpoint) |

---

## 4. Architecture

### 4.1 File tree (new + edited)

```
Slice 1 — Roles CRUD
  apps/web/src/routes/_app.platform.roles.tsx                       NEW (3-line route)
  apps/web/src/routes/_app.workspace.$workspaceId.roles.tsx         REPLACE placeholder
  apps/web/src/components/platform-roles-page.tsx                   NEW (~140 LoC)
  apps/web/src/components/workspace-roles-page.tsx                  NEW (~150 LoC)
  apps/web/src/components/roles/permission-picker.tsx               NEW (~120 LoC) shared
  apps/web/src/components/roles/role-form-dialog.tsx                NEW (~140 LoC) shared
  apps/web/src/components/roles/roles-table.tsx                     NEW (~80 LoC)  shared
  apps/web/src/components/roles/delete-role-dialog.tsx              NEW (~60 LoC)  shared
  apps/web/src/components/forbidden.tsx                             NEW (~30 LoC)  shared
  apps/web/src/components/ui/checkbox.tsx                           NEW (shadcn add)
  apps/web/src/lib/api.ts                                           EXTEND (+role/catalog fetchers)
  apps/web/src/lib/query-keys.ts                                    NEW (~30 LoC)
  packages/api-types/src/permission.ts                              NEW
  packages/api-types/src/role.ts                                    NEW
  packages/api-types/src/index.ts                                   EXTEND
  apps/api/src/xtrusio_api/routes/permissions.py                    NEW (~30 LoC)
  apps/api/src/xtrusio_api/schemas/permission.py                    NEW (~25 LoC)
  apps/api/src/xtrusio_api/main.py                                  EDIT (include_router)
  apps/api/tests/routes/test_permissions_catalog.py                 NEW (~50 LoC)

Slice 2 — Audit log
  apps/web/src/routes/_app.platform.audit-log.tsx                   NEW
  apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx     REPLACE placeholder
  apps/web/src/components/platform-audit-log-page.tsx               NEW (~110 LoC)
  apps/web/src/components/workspace-audit-log-page.tsx              NEW (~110 LoC)
  apps/web/src/components/audit/audit-table.tsx                     NEW (~100 LoC) shared
  apps/web/src/components/audit/audit-detail-drawer.tsx             NEW (~80 LoC)  shared
  apps/web/src/components/audit/load-more-button.tsx                NEW (~30 LoC)  shared
  apps/web/src/lib/api.ts                                           EXTEND (+audit fetchers)
  packages/api-types/src/audit-log.ts                               NEW
  apps/api/src/xtrusio_api/schemas/audit_log.py                     EDIT (+actor_email)
  apps/api/src/xtrusio_api/services/platform_audit_log.py           EDIT (LEFT JOIN auth.users)
  apps/api/src/xtrusio_api/services/workspace_audit_log.py          EDIT (LEFT JOIN auth.users)
  apps/api/tests/services/test_platform_audit_log.py                EDIT (assert actor_email)
  apps/api/tests/services/test_workspace_audit_log.py               EDIT (same)

Slice 3 — Members + nav + cleanup
  apps/web/src/routes/_app.workspace.$workspaceId.members.tsx       REPLACE placeholder
  apps/web/src/components/workspace-members-page.tsx                NEW (~160 LoC)
  apps/web/src/lib/nav.ts                                           EXTEND (+platform Roles, Audit log)
  apps/web/src/components/user-menu.tsx                             REWRITE (use useMe, drop local Me)
  apps/web/src/components/tenant-users-page.tsx                     EDIT (canInvite via hasWorkspacePerm)
  apps/web/src/routes/_app.workspace.$workspaceId.settings.tsx      EDIT (drop /api ref in copy)
```

500 LoC ceiling respected: every page file < 200, every shared block < 150.

### 4.2 Component contracts (shared blocks)

| Block | Stateless? | Props | Emits |
|---|---|---|---|
| `<PermissionPicker>` | yes | `catalog: PermissionDef[]`, `scope: "platform"\|"workspace"`, `value: string[]`, `onChange(string[])` | `onChange` |
| `<RoleFormDialog>` | local state for fields | `mode: "create"\|"edit"`, `role?: Role`, `catalog`, `scope`, `pending: bool`, `error: string\|null`, `onSubmit(payload)`, `open`, `onOpenChange` | `onSubmit`, `onOpenChange` |
| `<RolesTable>` | yes | `roles: Role[]`, `canManage: bool`, `onEdit(r)`, `onDelete(r)` | `onEdit`, `onDelete` |
| `<DeleteRoleDialog>` | yes | `role: Role\|null`, `pending: bool`, `onConfirm()`, `onOpenChange` | `onConfirm`, `onOpenChange` |
| `<AuditTable>` | yes | `events: AuditEvent[]`, `onSelect(e)` | `onSelect` |
| `<AuditDetailDrawer>` | yes | `event: AuditEvent\|null`, `onOpenChange` | `onOpenChange` |
| `<LoadMoreButton>` | yes | `nextCursor: string\|null`, `pending: bool`, `onClick()` | `onClick` |
| `<Forbidden>` | yes | `landingPath: string` | — |

### 4.3 Page contracts

Each per-scope page is a thin composition:

```
PlatformRolesPage / WorkspaceRolesPage
  - useMe() → permission gate; render <Forbidden /> on fail
  - useQuery(qk.permissionsCatalog())
  - useQuery(qk.{platform,workspace}Roles(wid?))
  - useState for dialog open + edit-target
  - useMutation × 3 (create / update / delete) → on success: invalidate qk.{platform,workspace}Roles
  - renders <PageHeader>, <RolesTable>, <RoleFormDialog>, <DeleteRoleDialog>

PlatformAuditLogPage / WorkspaceAuditLogPage
  - useMe() → permission gate
  - useState<{items, next_cursor}[]> accumulator
  - useQuery for the latest cursor (refetched when "Load more" clicked)
  - useState for selected event (drawer)
  - renders <PageHeader>, <AuditTable>, <LoadMoreButton>, <AuditDetailDrawer>

WorkspaceMembersPage
  - useMe() → permission gate (workspace.members.read)
  - useQuery(qk.workspaceInvites(wid))
  - useMutation × 2 (postTenantInvite / deleteTenantInvite)
  - renders <PageHeader>, invite section, "member listing ships in P6d" notice
```

### 4.4 Data flow — cache & invalidation

| Mutation | Invalidates |
|---|---|
| create/update/delete platform role | `qk.platformRoles()` |
| create/update/delete workspace role (wid) | `qk.workspaceRoles(wid)` |
| post/delete workspace invite (wid) | `qk.workspaceInvites(wid)` |
| (audit log entries are emitted as a side effect of every above — audit caches stay stale by design; refresh on user action) |

`qk.permissionsCatalog()` uses `staleTime: Infinity, gcTime: Infinity` — one fetch per session.

### 4.5 Permission gates (defence in depth)

1. **Sidebar nav** — `nav.ts.required_perm` filter (existing from P6b).
2. **Route component** — `if (!hasPlatformPerm(me, key)) return <Forbidden landingPath={getDefaultLandingPath(me)} />`.
3. **Backend** — `require_permission()` on every P4/P5 endpoint (existing).
4. **RLS** — defence-in-depth, unchanged (project rule).

Per-action gates (Edit / Delete / Invite / Revoke buttons) read perms via `useMe()` and pass a `canManage` / `canInvite` prop down to the shared block. Hidden buttons remain belt-and-suspenders even though the page gate has already passed.

---

## 5. Backend additions (tiny, scoped to P6c)

### 5.1 `GET /api/permissions/catalog` (Slice 1)

- Auth: any logged-in user (no `require_permission` — data is non-secret and identical for all callers).
- Response: `PermissionsCatalog { items: PermissionDef[] }` where
  `PermissionDef { scope: "platform"|"workspace", key: str, category: str, description: str }`.
- Implementation: ~one route, returns `CATALOG` tuple serialised. No service layer.
- Cacheable: yes (no `Cache-Control` header set — relies on TanStack Query `staleTime: Infinity`).
- No new tables, no migration.

### 5.2 `AuditEventOut.actor_email` (Slice 2)

- Schema change: `actor_email: str | None` added to `AuditEventOut`.
- Service change: `list_platform_audit_events` and `list_workspace_audit_events` add
  `LEFT JOIN auth.users ON auth.users.id = rbac_audit_log.actor_auth_user_id`, project `email`.
- `None` when `actor_auth_user_id IS NULL` OR the auth user has been hard-deleted.
- No migration, no new index (existing FK index is sufficient for the join).

### 5.3 No migration in P6c

P6c is a no-migration phase (Alembic head stays at `0009`). The two backend additions are
schema-edit + new-route only.

### 5.4 Error mapping additions

Extend `apps/web/src/lib/error-messages.ts`:

| Backend code | User-facing message | Surface |
|---|---|---|
| `role_key_taken` | "A role with this key already exists." | inline (key field) |
| `unknown_permission: <key>` | "Unknown permission: \<key\>. Refresh the page." | dialog footer |
| `scope_mismatch` | "That permission belongs to a different scope." | dialog footer |
| `system_role_immutable` | "System roles can't be modified." | toast |
| `single_super_admin_invariant` | "You can't remove the last super admin." | (pre-mapped for P6d grant UI) |
| `owner_floor` | "You can't revoke the last workspace owner." | (pre-mapped for P6d) |
| `privilege_escalation:<perm>` | "You can't grant a role with a permission you lack: \<perm\>." | (pre-mapped for P6d) |
| `invalid cursor` | "Couldn't load more events. Try refreshing." | toast |
| `role_scope_mismatch` | "That role belongs to a different scope." | dialog footer (defensive) |
| `membership_not_found` | "That user isn't a member of this workspace." | (pre-mapped for P6d) |
| `platform_user_not_found` | "That user isn't a platform user." | (pre-mapped for P6d) |

---

## 6. Test plan

### 6.1 Backend tests

| File | What it asserts |
|---|---|
| `tests/routes/test_permissions_catalog.py` *(new)* | 200 + every CATALOG entry present; 401 unauthenticated; payload shape matches schema; identical for super_admin / editor / generic-logged-in caller; idempotent |
| `tests/services/test_platform_audit_log.py` *(extend)* | `actor_email` populated when actor exists; `None` when actor_auth_user_id null; `None` when auth user hard-deleted; existing cursor/pagination tests unchanged |
| `tests/services/test_workspace_audit_log.py` *(extend)* | Same three assertions, workspace-scope |

### 6.2 Frontend tests (vitest)

| File | What it covers |
|---|---|
| `roles/permission-picker.test.tsx` | Catalog grouping by category; checkbox toggle calls `onChange`; per-category select-all scoped; `scope` filter |
| `roles/role-form-dialog.test.tsx` | Create-mode empty; edit-mode prefilled; submit payload; key field disabled in edit; `role_key_taken` inline |
| `roles/roles-table.test.tsx` | Row render; `is_system` badge + Edit/Delete hidden; `canManage=false` hides actions; callback fires |
| `roles/delete-role-dialog.test.tsx` | Cascade warning copy present; confirm fires once; cancel closes silently |
| `platform-roles-page.test.tsx` | Perm gate → `<Forbidden />`; with perm renders table + Create; mutations invalidate `qk.platformRoles()` |
| `workspace-roles-page.test.tsx` | Same as platform, scoped by `workspaceId` + `hasWorkspacePerm` gate |
| `audit/audit-table.test.tsx` | 4 columns; "—" for null actor_email; click-row fires `onSelect`; truncated target_id + tooltip |
| `audit/audit-detail-drawer.test.tsx` | Before/after JSON; before-null (create) / after-null (delete); close fires |
| `audit/load-more-button.test.tsx` | "Load more" → "Loading…" + disabled while pending; hidden when no `next_cursor` |
| `platform-audit-log-page.test.tsx` | Perm gate; accumulating-pages on load-more; row click opens drawer with right event |
| `workspace-audit-log-page.test.tsx` | Same, workspace-scope |
| `workspace-members-page.test.tsx` | Perm gate; invite/revoke reuse existing tested patterns; "ships in P6d" notice; `canInvite` via `hasWorkspacePerm` |
| `user-menu.test.tsx` *(rewrite)* | Uses `useMe()`; no duplicate `useQuery(['me'])`; renders email + super_admin badge; sign-out fires |
| `tenant-users-page.test.tsx` *(extend)* | `canInvite` from `hasWorkspacePerm(me, tid, "workspace.members.invite")`, not enum |
| `lib/query-keys.test.ts` *(new)* | Snapshot keys; collisions guarded |
| `lib/error-messages.test.ts` *(extend)* | New code mappings render right copy; unknown falls through |

### 6.3 Gate run cadence (per `feedback_lean_review_workflow`)

- **One** end-of-slice controller gate:
  `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check`.
- **One** Opus code-quality review per slice (`/ultrareview`-style), then PR + `gh pr merge`.
- **No** mid-slice full-suite runs — slices touch zero migrations, zero RLS, zero auth.
- Manual browser smoke (USER-DRIVEN) per slice: log in as super_admin, click through the new routes,
  verify role CRUD + audit entries appear; repeat as workspace owner.

---

## 7. Risks & accepted trade-offs

| Risk | Decision |
|---|---|
| Two admins editing the same role: no ETag, last-write-wins | Accepted — admin RBAC is low-concurrency. P6d could add If-Match if a real collision is observed. |
| Stale catalog after a backend deploy → submit hits `422 unknown_permission` | Accepted — UI shows "Refresh the page" message; rare; deploy-time only. |
| Role-delete silently cascades to all grants | Surfaced in `<DeleteRoleDialog>` with generic warning copy; precise count requires a new endpoint, out of scope. |
| Members page is invite-only during P6c → confusing if a user has no pending invites | Mitigated by explicit "Member listing ships in P6d" notice card on the page. |
| `actor_email` LEFT JOIN scans `auth.users` per audit page | Acceptable — `auth.users.id` is PK-indexed; page size capped at `MAX_LIMIT`. Confirm in review if performance flag rises. |
| The route gate uses `useMe()` cached value, so a revocation propagates only on the next `me` refetch | Accepted — `me` already refetches on tab focus + invalidation hooks; instant revocation is the backend's responsibility (already enforced via resolver). |

---

## 8. Out-of-scope, parked for later

- **LATE enum-column cleanup** (per HANDOFF item 6): drop `platform_users.role` / `tenant_memberships.role`
  columns + enum types. Still blocked by `/me` (P3b additive), onboarding, invite-accept, bootstrap
  writes, and `0008` downgrade path. P6c removes the last frontend enum-CONSUMERS but legitimate
  enum-WRITERS remain.
- **`gotrue` → `supabase_auth` migration** (P3.5 follow-up backlog).
- **Narrow `except Exception` in invite services** (P3.5 follow-up).
- **`grant_role` NULLS NOT DISTINCT migration** (P3.5 follow-up).
- **P5 grant concurrent-duplicate race hardening** (P5 follow-up).

---

## 9. Durable record

Spec: this file. HANDOFF: `docs/superpowers/HANDOFF.md` — to be updated post-merge of each slice
(per existing convention). PR bodies: `docs/superpowers/PR-rbac-p6c-slice-{1,2,3}-body.md` per slice.
Plan: `docs/superpowers/plans/2026-05-22-rbac-p6c-admin-uis.md` (to be written next via
`writing-plans` skill).
