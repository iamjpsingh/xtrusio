# P6c Slice 2 — Audit log viewers (platform + workspace)

Frontend-driven slice that surfaces the existing `rbac_audit_log` rows through two new read-only viewers — one for super_admins (`/platform/audit-log`) and one per workspace (`/workspace/$wid/audit-log`). One tiny backend change threads `actor_email` through the existing P4/P5 audit-log responses; everything else is consumer-side UI.

## Summary

- **Backend** — `AuditEventOut` gains `actor_email: str | None`. Both `list_platform_audit_events` and `list_workspace_audit_events` `LEFT JOIN auth.users ON rbac_audit_log.actor_auth_user_id = auth.users.id`. `auth.users.id` is PK-indexed, so no new index needed. `None` is correct for system-emitted rows (no actor) and for hard-deleted actors (`ON DELETE SET NULL` per `0006`).
- **Frontend shared blocks** — `<AuditTable>` (dense `[time | actor email | action | target]`), `<AuditDetailDrawer>` (Sheet with pretty-printed before/after JSON, distinguishes "no before" from "no after"), `<LoadMoreButton>` (hidden when `next_cursor === null`).
- **Per-scope pages** — `<PlatformAuditLogPage>` at `/platform/audit-log` gated by `platform.audit.read`; `<WorkspaceAuditLogPage>` at `/workspace/$wid/audit-log` gated by `workspace.audit.read` (replaces the P6b placeholder). Both render `<Forbidden />` when the permission is missing.
- **TS mirrors + fetchers** — `packages/api-types/src/audit-log.ts` (mirrors `apps/api/.../schemas/audit_log.py:AuditEventOut`); two new fetchers in `apps/web/src/lib/api.ts` (`fetchPlatformAuditEvents`, `fetchWorkspaceAuditEvents`).
- **Tests** — backend: 3 new assertions per scope (actor exists / actor null / actor hard-deleted) on top of existing pagination + permission coverage. Frontend: full coverage of the three shared blocks + both per-scope pages.

## Architecture choices

- **Cursor-driven Load-more, not `useInfiniteQuery`.** Local `useState<{items, next_cursor}[]>` accumulator + plain `useQuery` per cursor change. Project hasn't adopted `useInfiniteQuery` anywhere else; following the existing pagination pattern keeps the test surface flat.
- **Hard-deleted actor handling.** `rbac_audit_log.actor_auth_user_id` is `ON DELETE SET NULL` (migration `0006`), so once the actor is hard-deleted both `actor_auth_user_id` and the LEFT JOIN result go null. The original (pre-fix) test asserted `actor_auth_user_id == actor AND actor_email is None` which can never hold once `ON DELETE SET NULL` fires. Replaced with a `sentinel_target` UUID lookup pattern + `actor_auth_user_id is None AND actor_email is None` assertion. Workspace variant additionally needs a secondary actor (the tenant `created_by` FK is `ON DELETE RESTRICT`, so the actor that owns the tenant can't be deleted) — the secondary actor authors the audit event but doesn't own the tenant.
- **No migration.** Alembic head stays at `0009`. The LEFT JOIN is pure read-path; no DDL.
- **Permission gating is three-layered** (unchanged from Slice 1): sidebar nav filter (P6b), per-route component `<Forbidden />` fallback (this slice), backend `require_permission()` (P4/P5). Backend remains source of truth; the route gate is purely UX (avoids 403 flash on deep links / stale `me` cache).

## Test plan

- [x] Focused audit-log pytest — **14/14 PASS** (controller-verified 2026-05-23 against managed Supabase: `apps/api/tests/services/test_platform_audit_log.py` + `apps/api/tests/services/test_workspace_audit_log.py`).
- [x] `pnpm --filter @xtrusio/api-types typecheck` — PASS
- [x] `pnpm --filter @xtrusio/web typecheck` — PASS
- [x] `pnpm --filter @xtrusio/web exec eslint <slice files>` — PASS (no errors, no warnings)
- [x] `pnpm --filter @xtrusio/web exec vitest run src/components/audit/ src/components/platform-audit-log-page.test.tsx src/components/workspace-audit-log-page.test.tsx` — **19/19 PASS**
- [x] `uv run mypy` on the three changed backend files — PASS
- [x] `uv run ruff check apps/api` — PASS
- [x] `uv run ruff format --check apps/api` — PASS
- [ ] Full `STARTUP_RECONCILE_TOLERANT=false make check` — **deferred to a single end-of-P6c gate** per user direction (slice-level fast gates passed; full sweep runs once after all P6c slices land).
- [ ] Manual: super_admin sees their email next to every RBAC mutation they performed in `/platform/audit-log`; clicking opens the drawer with before/after JSON.
- [ ] Manual: workspace owner sees workspace-scope events only at `/workspace/<wid>/audit-log`.
- [ ] Manual: Load more advances the cursor; trailing `next_cursor=null` hides the button.
- [ ] Manual: a workspace `editor` is shown `<Forbidden />` at `/workspace/<their-wid>/audit-log`.

## What's NOT in this PR

- Filters / search on the audit-log tables (cursor stream is unfiltered; filtering is a future polish item, not in any current plan).
- Realtime push of new audit events (`/me`-style polling is fine for the audit scale today).
- Workspace Members invite UI / platform nav additions — Slice 3.
- Grant-management UIs + missing list endpoints (`GET /api/platform/users`, `GET /api/workspaces/{wid}/members`) + workspace Settings UI — **P6d**.

## Next

Slice 3 (Workspace Members invite-only port + platform nav additions for Roles + Audit log + `UserMenu` rewrite + `tenant-users-page` enum→permission), then P6d (the three missing backend endpoints + their consumer UIs to complete the admin surface).
