# P4 — Platform RBAC admin (API + governance)

Ships the platform-side of the RBAC admin surface: `super_admin` can CRUD custom platform roles, grant/revoke role assignments on platform users, and view a paginated audit log. Bundles the deferred-from-P3c governance items (audit-log writes, privilege-escalation guard, single-super_admin invariant, immutable system roles) per HANDOFF item 3.

Backend only — UI deferred to P6c per the agreed split.

## Summary

**Slice A — Foundation (DB triggers + audit infrastructure)**

- Migration `0009`: three DB triggers as defense-in-depth:
  - `enforce_priv_escalation` (BEFORE INSERT on `user_roles`) — actor must hold every permission contained in the target role. Auto-bypasses when `granted_by IS NULL` (system/bootstrap path) and respects an `app.bypass_priv_escalation = on` GUC for the boot reconciler.
  - `reject_system_role_mutation` (BEFORE UPDATE/DELETE on `roles`) — platform-scope `is_system` roles cannot be modified or deleted. Workspace-scope `is_system` roles are per-workspace data (instantiated per workspace per spec §3.3) and cascade-delete with the tenant.
  - `reject_system_role_perm_change` (BEFORE INSERT/UPDATE/DELETE on `role_permissions`) — same platform-scope-only immutability.
- `reconcile_rbac`, `wire_workspace_role_perms`, and `reconcile_user_roles_from_enums` set the bypass GUC so the boot reconciler can re-sync system role permissions without tripping the triggers.
- `core/audit.py` — `write_audit_event(db, *, actor_id, action, target_type, target_id, scope, workspace_id, before, after)`. One row per RBAC mutation, written in the same tx as the mutation; atomicity guaranteed.
- `_cleanup.py` extended to purge `rbac_audit_log`, test-user `user_roles`, and custom roles created by `@example.com` users.

**Slice B — Platform-role CRUD**

- `services/platform_roles.py` — `create_platform_role`, `list_platform_roles` (cursor paginated), `get_platform_role`, `update_platform_role`, `delete_platform_role`. Every mutation: `SET LOCAL app.actor_id`, validate permission keys (catalog membership + scope match), apply change, write audit event. Service-layer `SystemRoleImmutableError` returns a friendly 422 before the DB trigger fires.
- `schemas/platform_role.py` — `PlatformRoleIn / Out / Patch / Page` schemas + grant schemas.
- `routes/platform_roles.py` — `GET/POST/PATCH/DELETE /api/platform/roles[/{id}]`, all gated by `platform.roles.manage`. Exception → HTTP code mapping (404, 409, 422).

**Slice C — Role-grant endpoints (with governance enforcement)**

- `services/platform_role_grants.py` — `grant_platform_role`, `revoke_platform_role_grant`, `list_platform_role_grants` (cursor paginated).
- Service mirrors the DB priv-escalation logic so a non-super_admin trying to grant a role they don't fully hold gets a clean 403 with `missing_perm_key` named, instead of an opaque `insufficient_privilege` from the trigger.
- Single-super_admin invariant: service pre-checks `count(*) FROM user_roles WHERE role.key='super_admin'` and raises `SingleSuperAdminError` → 409. DB partial unique index `user_roles_one_super_admin` is the hard floor.
- `routes/platform_role_grants.py` — `GET/POST /api/platform/users/{user_id}/roles`, `DELETE .../{grant_id}`. POST/DELETE gated by `platform.users.manage`; GET by `platform.users.read`.

**Slice D — Audit-log viewer**

- `schemas/audit_log.py` + `services/platform_audit_log.py` + `routes/platform_audit_log.py`.
- `GET /api/platform/audit-log?cursor=&limit=` — cursor-paginated, filtered to `scope = 'platform'` so workspace events stay out of the platform viewer (those are P5).
- Gated by `platform.audit.read` (held by both seeded platform system roles `super_admin` and `admin`).
- Audit-log `id` is `bigint` (not uuid), so the service uses a local int-based cursor encoder mirroring `core/pagination.encode_cursor`'s wire format.

## Permission gate matrix

| Endpoint | Gate |
|---|---|
| Roles CRUD (create/list/get/edit/delete) | `platform.roles.manage` |
| Role grants list | `platform.users.read` |
| Role grants create / revoke | `platform.users.manage` |
| Audit-log viewer | `platform.audit.read` |

All gates use the existing `require_permission(db, user_id, key)` primitive from P3b. No new permission keys added — every key needed already lives in `apps/api/src/xtrusio_api/rbac/catalog.py`.

## Verification

- **`make lint`** — clean.
- **`uv run mypy apps/api`** — `Success: no issues found in 123 source files`.
- **Full backend suite** — **226 passed, 3 documented skips, 0 failed** (the documented skips: B5 invariant + 2 vacuous P1 backfill assertions).
- **B5 invariant (P3.5)** — automatically passes; the four new GET endpoints all declare `limit: Query(ge=0, le=MAX_LIMIT)`.
- **Migration `0009` reversibility** — `alembic downgrade 0009 -> 0008` + `alembic upgrade 0008 -> 0009` exercised cleanly.

## Discovered follow-ups (not in P4 scope)

1. **`grant_role` in `rbac/grants.py` shares a latent `ON CONFLICT DO NOTHING` + `NULLS DISTINCT` bug** for `workspace_id IS NULL` platform-scope grants — `(auth_user_id, role_id, NULL)` won't match an existing row under Postgres' default NULLS DISTINCT semantics. Existing call sites are safe in practice (reconciler uses `NOT EXISTS`; onboarding/invite-acceptance are once-per-user paths). P4's new grant service uses an explicit `SELECT then INSERT` to avoid the issue. Follow-up phase could either:
   - Migrate the `user_roles` unique constraint to `NULLS NOT DISTINCT` (PG15+).
   - Backport the explicit SELECT pattern into `grant_role`.
2. **Pre-existing test-typing debt** in 10 RBAC-era test files — handled in PR #10 (type-the-tests). No new debt introduced by P4.
3. **`gotrue` → `supabase_auth` migration** — supabase-py 2.x DeprecationWarning. Independent of P4.
4. **DELETE `/{user_id}/roles/{grant_id}` doesn't verify `grant.auth_user_id == user_id`** — `grant_id` is globally unique so a mismatched `user_id` in the path is harmless, but consistency check would be a polish item.

## What's intentionally NOT in this PR

- **Frontend admin UI** — deferred to P6c per the agreed scope split. Permission-driven nav (P6b) needs to land first so the admin UI can fit the new shell.
- **Workspace RBAC admin** — P5.
- **Enum-column drop** (`platform_users.role` / `tenant_memberships.role`) — HANDOFF item 6, still gated by P6b removing frontend enum consumption.
- **New permission keys** — none needed; the catalog already has `platform.roles.manage`, `platform.users.manage`, `platform.audit.read`.

## Commits

```
3172817 feat(rbac): GET /api/platform/audit-log (cursor-paginated, platform.audit.read gated)
1763e24 feat(rbac): platform user role-grant REST endpoints
60137bf feat(rbac): platform-role grant/revoke service + priv-escalation + single-super_admin guards
12bc319 feat(rbac): GET/POST/PATCH/DELETE /api/platform/roles endpoints
99a5c4e feat(rbac): platform-role CRUD service + audit + immutable-system guard
f4d8cfa feat(rbac): platform-role pydantic schemas
55e23bb fix(rbac): narrow immutable-system-roles trigger to platform scope only
df7d7bd fix(rbac): priv-escalation trigger auto-bypasses when granted_by IS NULL
9608dd9 feat(rbac): write_audit_event helper + AuditLog model + _cleanup coverage
7db1864 feat(rbac): 0009 — priv-escalation + immutable-system-roles DB triggers + reconciler bypass
```

## After merge

- P5 (Workspace RBAC admin) becomes the next gated phase.
- Then P6b (frontend permission-driven shell), then P6c (admin UI consuming P4+P5 APIs).
- Once P6b removes the frontend's enum consumption, the late-cleanup migration can drop `platform_users.role` / `tenant_memberships.role` columns (HANDOFF item 6).
