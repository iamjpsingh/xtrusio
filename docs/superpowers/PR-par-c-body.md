## PAR-C slice 1 — RBAC defense-in-depth (DB integrity)

Closes audit findings **C5, H10, M17** and the **6.2.7** RLS refinement, plus **M3**
(single-super_admin grant race). Part of the 2026-05-26 production-audit
remediation (`docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md`,
section 6).

### What changed

**Migration `0010_rbac_integrity.py`** (single Alembic head → `0010`):

- **M17** — `set_updated_at()` recreated with `SET search_path = pg_catalog, public`
  (closes the search-path-injection surface on a trigger fn).
- **C5** — `roles_super_admin_pinned_id` CHECK constraint pins the platform
  `super_admin` system role to its well-known id `…00a1`. The 0006 single-
  super_admin partial unique index can only enforce "one super_admin" while the
  role keeps the id its predicate references; this stops the role being
  recreated under a different id.
- **H10** — `trg_user_roles_owner_floor` (`BEFORE DELETE ON user_roles`): the
  ≥1-owner floor is now a DB trigger, not service-only. It takes
  `SELECT … FOR UPDATE` on the workspace's owner role row so two concurrent
  owner-revokes serialise — the loser sees `last_owner` and rolls back. Guards:
  honours the `app.bypass_priv_escalation` GUC (so purge/reconcile can delete
  owner grants) and skips cascade-originated deletes via `pg_trigger_depth() > 1`
  (deleting an `auth.users` row cascades into `user_roles` without tripping the
  floor).
- **6.2.7** — `tenant_memberships` FOR-ALL owner/admin policy split into explicit
  per-action policies (member SELECT; owner/admin INSERT/UPDATE/DELETE). The
  pre-existing self-read + super_admin policies are untouched.

**Service / route:**

- **M3** — `grant_platform_role` wraps the INSERT in `try/except IntegrityError`;
  a race past the count pre-check that violates `user_roles_one_super_admin`
  becomes `SingleSuperAdminError` → 409 (was an unhandled 500).
- **H10 route** — the workspace revoke route maps the DB `last_owner`
  (check_violation) → 409 `owner_floor`, matching the service-side
  `OwnerFloorError`. The stale "owner-only" docstring is corrected
  (`workspace_admin` also holds `workspace.members.manage`, so the service
  count-check is a friendly guard, not the real serialiser — the trigger is).

**Tests:** new `tests/migrations/test_0010_rbac_integrity.py` — C5 constraint
presence + seed satisfaction, owner-floor blocks-last / allows-when-another /
**concurrent-race (exactly one wins)** / system-GUC bypass, M17 search_path
pin, 6.2.7 policy split.

### Deferred to PAR-C slice 2 (coupled, needs operator provisioning)

These three move together because they share the system-grant bypass-marker
redesign and an external dependency:

- **M15 / C4 role-gated bypass** — the separate `xtrusio_reconciler` DB role +
  `RECONCILE_DATABASE_URL`. Requires minting a role on managed Supabase
  (password + Supavisor DSN); the trigger role-gating breaks boot/seed reconcile
  until that's provisioned.
- **`granted_by NOT NULL` + system sentinel** — blocked by the
  `granted_by → auth.users ON DELETE SET NULL` FK (NOT NULL conflicts with SET
  NULL) and by the onboarding/invite/bootstrap paths that rely on the
  `granted_by IS NULL` trigger short-circuit.
- **H9 `_set_actor` dependency lift** — H9's security core (no actor leak across
  pooled connections) was already closed in PAR-B by the `checkin` RESET
  listener. Lifting the per-service `_set_actor` into the auth dependency would
  break ~30 direct-service tests and belongs with the bypass-marker rework.

### Verification

- `make check` (ruff + ruff format + turbo lint + mypy --strict + turbo
  typecheck + vitest 177) green.
- Backend pytest green against the managed dev project.
- Migration applied + downgrade authored (reversible).
