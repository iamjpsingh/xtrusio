# auth-sec slice 1 — close privilege-escalation via role-definition edit

## Summary

Closes a **verified-exploitable privilege-escalation vulnerability** (CWE-269 / CWE-639) in the RBAC role-management path.

The role **grant** path already enforced "you cannot grant a permission you do not hold" (`_find_missing_perm` → `PrivilegeEscalationError`). The role **definition** create/edit path did **not** — it rewrote `role_permissions` after only an existence/scope check (`_validate_perm_keys`). Because the DB privilege-escalation trigger fires only on `user_roles` (never on `role_permissions`), and `reject_system_role_perm_change` only covers **platform system** roles, a **custom** role's permission set could be edited with no actor-authorization check at all.

### Exploit (now closed)

A delegate granted a custom role holding only `platform.roles.manage` (or `workspace.roles.manage`) clears the route gate, then `PATCH`es a custom role assigned to themselves to add a permission they do **not** hold — e.g. `platform.clients.manage`, or in a workspace `workspace.members.manage` / `workspace.settings.manage`. The addition takes effect immediately (the authz gate reads `role_permissions` live; it is never cached). This escalates the delegate to effectively co-owner, bypassing both the service pre-check and every DB trigger.

## Fix

**Invariant enforced** (matches the existing grant path + Kubernetes RBAC + OWASP "you-cannot-grant-what-you-lack"):

> On role **create** or **update**, the full resulting `permission_keys` set must be a subset of the actor's own effective permissions in that scope (platform scope for platform roles; the specific path `workspace_id` for workspace roles). Otherwise raise `PrivilegeEscalationError`.

- **Service layer (primary gate):** added scope-local `_find_missing_perm` helpers + the guard to `create_platform_role`, `update_platform_role`, `create_workspace_role`, `update_workspace_role`. They resolve the requested keys through the **same** `has_platform_perm` / `has_workspace_perm` SECURITY DEFINER resolvers the live authz gate and grant path use — no divergence. `_validate_perm_keys` (existence/scope) is retained. Update evaluates the **resulting** set, not the delta; name/description-only edits (`permission_keys is None`) skip the check; empty set is allowed (∅ ⊆ actor).
- **Route layer:** `PrivilegeEscalationError` is caught in the create/update handlers and returned as a **sanitized** `HTTPException(403, "privilege_escalation")` — byte-identical to the grant-path sanitization. The missing permission key is **server-side WARN-logged only**, never in the response body (no enumeration leak).

**Not in this slice (deliberate follow-up):** a `role_permissions` INSERT/UPDATE DB-trigger as defense-in-depth. The service-layer check is the complete primary gate per the project's "backend permission checks are the primary gate; RLS/triggers catch what's missed" doctrine. The DB trigger is entangled with the deferred reconciler-role / bypass-marker rework and ships separately.

## Why super_admin / owner / tenant-creation are not affected

`has_platform_perm` / `has_workspace_perm` resolve purely through `user_roles → roles → role_permissions` with no super_admin/owner short-circuit. super_admin and owner pass only because their seeded role sets are the full catalog (`SYSTEM_ROLE_PERMISSIONS`), so `_find_missing_perm` always returns `None` for them. Onboarding/reconcile seed `role_permissions` via `wire_workspace_role_perms`, **not** through the guarded create/update services, so tenant creation is untouched.

## Tests

- **Negative (the exploit):** a `*.roles.manage`-only delegate cannot create or update a platform/workspace role to add a permission they lack → `PrivilegeEscalationError`. These fail on revert (the DB trigger does not cover custom roles).
- **Positive:** super_admin / workspace owner can set any catalog perm; an actor can add a perm they *do* hold; name/description-only edits don't trip the guard.
- **Route:** the sanitized 403 body is a bare constant with no permission key.

34 targeted tests pass against the managed Supabase project; full `make check` gate (ruff format --check, mypy --strict, turbo typecheck, vitest, full backend pytest) run by the controller at end of slice.

## Security review

Independent reviewer verdict: **APPROVE — no blockers.** Confirmed completeness (all three `role_permissions` write sites enumerated; the two actor-controlled ones are guarded, reconcile is system-only), correctness (same resolver as authz), no legitimate-flow breakage, sanitized error, and load-bearing tests.

## Files

- `apps/api/src/xtrusio_api/services/platform_roles.py`
- `apps/api/src/xtrusio_api/services/workspace_roles.py`
- `apps/api/src/xtrusio_api/routes/platform_roles.py`
- `apps/api/src/xtrusio_api/routes/workspace_roles.py`
- `apps/api/tests/services/test_platform_roles.py`
- `apps/api/tests/services/test_workspace_roles.py`
- `apps/api/tests/routes/test_privilege_escalation_sanitized.py`
