# P6d backend — list endpoints + workspace settings

Adds the three missing backend endpoints the P6c admin UIs were waiting on, so the next phase (P6d frontend) can ship grant-management + workspace-settings UIs without backend gaps. Pure additive — no migration, no behaviour changes to existing routes.

## Summary

- **`GET /api/platform/users`** — cursor-paginated list of platform users with their `granted_role_count` (LEFT JOIN onto `user_roles` filtered to `scope='platform' AND workspace_id IS NULL`). Gated by `platform.users.read`.
- **`GET /api/workspaces/{wid}/members`** — cursor-paginated list of workspace members with their `granted_role_count` (LEFT JOIN onto `user_roles` filtered to `scope='workspace' AND workspace_id=:wid`). Gated by `workspace.members.read`. LEFT JOIN onto `auth.users` for `email` (defensively typed `EmailStr | None` — see deviation §3 below).
- **`GET /api/workspaces/{wid}/settings`** — reads `{id, slug, name, created_at, updated_at}` for the workspace. Gated by `workspace.settings.read`.
- **`PUT /api/workspaces/{wid}/settings`** — updates `name` only (MVP). Gated by `workspace.settings.manage`. Writes one audit-log row via `core/audit.write_audit_event` ONLY when `name` actually changed (no-op writes are not logged).
- **TS mirrors** in `@xtrusio/api-types` + re-exports.
- **Mechanical isort cleanup** in 4 pre-existing files (`scripts/bootstrap.py`, `services/{platform_invites,signup,tenant_invites}.py`) — each was missing a blank line between `sqlalchemy` and `supabase` import groups; `ruff check --fix` applied. Zero behaviour impact.

## Architecture choices

- **Cursor pagination reuses `core/pagination.py:CursorParams`** + the UUID cursor codec, matching `services.platform_role_grants:list_platform_role_grants`. Consistent with every other paginated list endpoint in the codebase.
- **Permission catalog unchanged.** The plan called for adding `workspace.settings.read` + `workspace.settings.manage` — both keys already exist on `main` (added in P5; bound to `owner`/`workspace_admin` via `_workspace()` and explicitly to `editor`/`read_only` in `SYSTEM_ROLE_PERMISSIONS`). Re-adding would be a duplicate-key insert. See deviation §1.
- **Workspace settings is `name`-only for MVP.** The plan's locked decision. `slug` is the URL identifier (separate destructive flow, not in P6d); future polish can add description/logo/timezone via a tenant-attributes JSONB column.
- **No new migration.** All endpoints read existing tables. Alembic head stays at `0009`.
- **Prefix-collision ordering in `main.py`:** `platform_users_router` registered AFTER `platform_role_grants_router` (both share prefix `/api/platform/users`; sub-paths differ). `workspace_members_router` registered BEFORE `workspace_role_grants_router` (same pattern, `/api/workspaces/{wid}/members`). FastAPI matches in declared order — without this discipline, `GET /api/platform/users` would shadow `GET /api/platform/users/{user_id}/roles` and vice-versa.
- **Audit-log no-op skip on settings update.** If `body.name == current.name`, the service returns the existing row without writing an audit event. Avoids audit-log noise for users who hit Save without changing anything.

## Test plan

- [x] `uv run ruff check apps/api` — **All checks passed!**
- [x] `uv run ruff format --check apps/api` — **154 files already formatted**
- [x] `uv run mypy apps/api` — **Success: no issues found in 154 source files**
- [x] Focused pytest on the six new test files — **41/41 PASS** in 612s against managed Supabase
  - Service tests: `test_platform_users.py` (6), `test_workspace_members.py` (5), `test_workspace_settings.py` (6) — 17 total
  - Route tests: `test_platform_users.py` (6), `test_workspace_members.py` (6), `test_workspace_settings.py` (12) — 24 total
- [x] `pnpm --filter @xtrusio/api-types typecheck` — clean
- [ ] Full `STARTUP_RECONCILE_TOLERANT=false make check` — **deferred to one end-of-P6d gate** per user direction. Full sweep runs once after P6d frontend lands.
- [ ] Manual smoke: `GET /api/platform/users` as super_admin returns paginated list with `granted_role_count` populated.
- [ ] Manual smoke: `GET /api/workspaces/{wid}/members` as workspace owner returns own workspace's members with correct counts; another workspace's owner gets 403.
- [ ] Manual smoke: `PUT /api/workspaces/{wid}/settings` renames the workspace; audit log shows one row with `before={name:"old"} after={name:"new"}`; PUT with the same name produces no new audit row.

## Deviations from the plan

1. **Catalog change skipped (already present).** The plan's Section 5 Task A.1 was authored before P5 landed `workspace.settings.read` + `workspace.settings.manage`. Both keys exist on `main` and are already attached to the relevant system roles. No-op for this PR.
2. **Pre-existing isort drift fixed.** `ruff check apps/api` on the baseline had 4 errors in unrelated files (mechanical missing-blank-line between `sqlalchemy` and `supabase` import groups). Fixed via `ruff check --fix` to keep the slice-level gate green. Same pattern as the earlier `chore(api): ruff isort fixes` commits.
3. **`test_list_handles_hard_deleted_auth_user_with_null_email` rewritten.** `tenant_memberships.user_id` FKs to `auth.users(id)` with `ON DELETE CASCADE` (migration `0002`), so "membership row exists, auth row hard-deleted" is unreachable in practice — the cascade always cleans both. Replaced with `test_list_returns_member_email_from_left_join` covering the positive path; null branch is enforced at the schema layer (`EmailStr | None`). Documented inline in the test.

## What's NOT in this PR

- **Frontend UIs** — P6d frontend (`<PlatformUsersPage>`, workspace members list under Slice-3's invite UI, `<WorkspaceSettingsPage>`, shared `<GrantManagerDialog>` + `<RolePicker>`). Separate dispatch / PR.
- **Workspace slug change endpoint** — explicitly out of scope.
- **Workspace deletion** — explicitly out of scope.
- **ETag / If-Match concurrency on settings** — explicitly out of scope.
- **Audit-log filters / search** — explicitly out of scope.

## Next

P6d frontend (the three UIs that consume these endpoints), then a single end-of-P6d full backend pytest sweep + HANDOFF.md update on main pivoting NEXT to "first product feature".
