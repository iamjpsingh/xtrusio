# P5 — Workspace RBAC admin (roles, grants, audit log)

Backend-only per-workspace RBAC admin API, scope-isolated to one `workspace_id` and gated by the `workspace.*` permission catalog. Mirrors the P4 platform-admin surface with the workspace dimension threaded through every read/write.

## Summary

- **Workspace role CRUD** — `GET/POST /api/workspaces/{wid}/roles`, `GET/PATCH/DELETE /api/workspaces/{wid}/roles/{role_id}` gated by `workspace.roles.manage`. Custom (non-`is_system`) roles only; the four per-workspace system roles (`owner`/`admin`/`editor`/`read_only`) are immutable via a service-layer guard.
- **Workspace role grants** — `GET/POST /api/workspaces/{wid}/members/{uid}/roles` and `DELETE /api/workspaces/{wid}/members/{uid}/roles/{grant_id}`. `GET` gated by `workspace.members.read`; mutations by `workspace.members.manage`. Service enforces (1) `tenant_memberships` membership pre-check, (2) per-workspace privilege-escalation pre-check (friendly 403 before the `0009` DB trigger fires), (3) ≥1-active-owner floor on revoke (no DB trigger covers this — service is the sole guard, returns 409).
- **Workspace audit log** — `GET /api/workspaces/{wid}/audit-log` gated by `workspace.audit.read`. Cursor-paginated; rows filtered to `scope='workspace' AND workspace_id=:wid`.

## Architecture choices

- **No new migration.** Reuses `0009`'s priv-escalation trigger (which already dispatches to `has_workspace_perm` when `workspace_id IS NOT NULL`) and `core/audit.write_audit_event`. `0009.reject_system_role_mutation` deliberately scopes to `scope='platform'` only (lines 119–120, with comment at 102–109 explicitly delegating workspace immutability to P5 service-layer) — so the workspace `SystemRoleImmutableError` guard is load-bearing, not friendly-first.
- **Scope isolation is load-bearing.** Every read/write filters on `workspace_id`. The grant DELETE is pinned on `(id, user_id, workspace_id)` — without this triple a workspace-A owner could revoke a workspace-B grant by knowing its uuid.
- **Cursor codec reuse.** `services.workspace_audit_log` imports `_encode_audit_cursor`/`_decode_audit_cursor` from `services.platform_audit_log` (bigint id, distinct from the uuid-id `core/pagination.py` primitive).
- **Idempotent grant.** `grant_workspace_role` does explicit SELECT-then-INSERT to dodge the documented `UNIQUE NULLS DISTINCT` foot-gun (HANDOFF §follow-ups); workspace grants always have `workspace_id IS NOT NULL` so the trap doesn't actually fire here, but the explicit pattern lets us return the existing row for true idempotency.

## Test plan

- [x] `STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check` green (run by controller, see end-of-phase output).
- [x] Per-slice fast checks ran against fresh DB after each commit: Slice B 22/22, Slice C 23/23, Slice D 8/8 (3 service + 5 route).
- [x] Scope-isolation regression coverage: `test_get_workspace_role_404_cross_workspace`, `test_update_role_from_other_workspace_404s`, `test_grant_role_from_other_workspace_404s`, `test_delete_404_cross_workspace_grant_id`, `test_filters_to_this_workspace`.
- [x] `≥1-owner floor`: `test_revoke_owner_floor_409_when_last_owner` + `test_revoke_owner_204_when_two_owners` + `test_delete_409_owner_floor`.
- [x] Service-layer priv-escalation pre-check ahead of DB trigger: `test_grant_raises_privilege_escalation` + `test_post_403_privilege_escalation`.

## What's NOT in this PR

- UI — deferred to P6c per scope split (HANDOFF §NEXT).
- HANDOFF §follow-ups items (`gotrue → supabase_auth` migration, broad-except narrowing, platform `grant_id`/`user_id` consistency polish, `UNIQUE NULLS NOT DISTINCT` migration). Each is a deliberate non-goal of P5.
- Frontend permission-driven nav / shells (P6b).

## Next

P6b — pinned `/me` effective-perms TS contract + permission-driven nav + Platform/Workspace shells. P6c — RBAC admin UIs consuming P4/P5 APIs.
