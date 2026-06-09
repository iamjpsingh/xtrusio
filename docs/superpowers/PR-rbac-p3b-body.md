## Summary

RBAC **Phase 3b — backend permission enforcement** (the enforcement switch). Builds on merged P3a. **No migration; single Alembic head `0007`.**

Replaces every enum-role backend authz check with the `0007` SECURITY DEFINER resolvers via one reusable primitive, and extends `/me` with effective permission keys.

- **`core/permissions.py`** (new, single authz primitive): `has_permission` / `require_permission` (scope inferred from key prefix → calls `has_platform_perm` / `has_workspace_perm`, the same `0007` functions that back RLS — single source of truth; bound params; `workspace.*` w/o workspace_id → deny; 403 `permission_denied`), + `effective_platform_perms` / `effective_workspace_perms` for `/me`.
- **All 10 endpoints + the 3 `tenant_invites` service checks converted** to the spec role→permission matrix (POST/GET platform invites→`platform.users.invite`, DELETE→`platform.users.manage`; settings GET→`platform.settings.read` [newly gated], PUT→`platform.settings.manage`; tenants GET→`platform.clients.read`, POST→`platform.clients.manage`; tenant-invite create→`workspace.members.invite`, list/revoke→`workspace.members.manage`). Identity deps (provisioned/active guards) **preserved** — `require_permission` is layered after them. `can_invite()` business rule unchanged.
- **`/me` additive**: `MeResponse.platform_permissions` + `TenantContext.permissions` added; existing `platform`(role)/`tenants[].role` kept (frontend P6b removes them later — no break).
- Dead code removed (grep-zero refs): `require_super_admin`, `_require_owner_or_admin`, `NotOwnerOrAdminError`. Kept: `get_current_user`/`require_authenticated`/`AuthIdentity`/`can_invite`/`NotAMemberError`/`ForbiddenRoleError`.

**This intentionally changes authorization** (per spec section 10 — not behaviour-preserving; that was P3a): platform `admin` now correctly gains operational perms (clients/users/settings); only `platform.roles.manage`-gated stays super_admin-only; `editor`/`read_only` do NOT gain workspace `members.manage`/`invite` (verified against `SYSTEM_ROLE_PERMISSIONS`). Precondition (every enum principal resolver-visible) satisfied by merged P3a.

Spec: `docs/superpowers/specs/2026-05-17-rbac-rls-rearchitecture-design.md` section 5/section 8/section 10. Plan: `docs/superpowers/plans/2026-05-19-rbac-p3b-permission-enforcement.md`.

## Test status

Full backend suite from a **clean DB** (`make test-clean` first — required): **0 failed / 0 error**, only the 2 documented vacuous `test_migration_0006` skips (env-flaky `test_signup` passed this run). Affected route/auth + `/me` tests **reframed to the permission model** (net stronger: removed negatives only returned with a `detail == "permission_denied"` assertion + a new positive test proving the intended authz change; 3 removed / 8 added). `test_no_super_admin_creation` guard still green. ruff/mypy = documented baseline only (4 I001 + 1 jose). Single head `0007`. Final whole-slice review: no Critical/Important — READY TO MERGE.

## Accepted deferred Minor (non-blocking)

`/me` calls `effective_workspace_perms` per tenant (N+1); consistent with the plan's "single query each" helper design; tenant-per-user counts small — future optimization, not a correctness/contract issue.

## Out of scope (P3c / later)

audit-log writes; privilege-escalation guard + DB trigger; single-super_admin Python enforcement; migration `0008` retiring the `OR 0003-enum` disjunct; dropping enum columns; frontend `/me` consumption / permission-driven nav / two shells (P6b/P6c). 🔒 Enum columns may be dropped ONLY after P3a (done) + P3b (this) + P3c rewrites the `0007` helpers to pure-resolver.

## Test Plan

- [ ] CI/reviewer: `uv run --directory apps/api python -m tests._cleanup` then `uv run --directory apps/api pytest tests/ -q` → 0 failed (only env-flaky `test_signup` state-dependent + 2 documented vacuous skips)
- [ ] Spot-check the conversion map: each converted endpoint enforces its spec'd permission key; identity active/provisioned guards intact
- [ ] `uv run --directory apps/api alembic heads` = single `0007` (no migration)
- [ ] Confirm platform `admin` gains ops perms; `editor`/`read_only` do NOT gain workspace manage (intended)
