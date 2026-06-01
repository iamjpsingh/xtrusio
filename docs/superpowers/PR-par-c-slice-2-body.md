# PAR-C slice 2 — reconciler role + role-gated bypass + `_set_actor` lift (C4, H9, M15)

Closes the final 3 audit findings. With this, **all 60 PAR findings are code-complete.** Backend-only; no frontend, no behavior change for the dev/test path (every new piece is operator-gated behind `RECONCILE_DATABASE_URL`).

## Summary

- **C4** — `enforce_priv_escalation` (0009) is recreated as **`SECURITY INVOKER`** and its bypass branch is **role-gated** on `current_user = 'xtrusio_reconciler'`; the trigger is broadened to **`INSERT OR UPDATE`**. The `granted_by IS NULL` short-circuit is **kept** (documented) — onboarding's owner self-grant and invite-accept depend on it.
- **M15** — a least-privileged **`xtrusio_reconciler`** DB role (created `NOLOGIN`, **no credential in source**) carries the reconcile. `RECONCILE_DATABASE_URL` + `core/reconciler_db.py` give it a separate engine; boot reconcile (`main.py`) and `python -m xtrusio_api.rbac` use it when set, else **fall back to the request engine with a warning** (dev-safe). Permissive RLS policies let the non-owner role read/write the 7 tables reconcile touches.
- **H9** — the four identical per-service `_set_actor` helpers (`platform_roles`, `platform_role_grants`, `workspace_roles`, `workspace_role_grants`) collapse into one shared **`core.permissions.set_actor`**. (The PAR-B `checkin` RESET of `app.actor_id` / `app.bypass_priv_escalation` already ships.)

## Why `SECURITY INVOKER` is load-bearing

0009 had `enforce_priv_escalation` as `SECURITY DEFINER`, under which `current_user` is the **function owner** (`postgres`) — so a `current_user = 'xtrusio_reconciler'` gate could **never** match. Recreating it `SECURITY INVOKER` makes `current_user` reflect the **session role**, which is what the gate needs. The perm-walk still works because `has_platform_perm` / `has_workspace_perm` (0007) are themselves `SECURITY DEFINER` and run with their own privileges.

## Two deliberate omissions (both would otherwise break things)

- **No `GRANT SET ON PARAMETER app.bypass_priv_escalation`.** It requires superuser — managed-Supabase `postgres` is not one, so it would **abort the whole migration**. It's also functionally inert (custom placeholder GUCs are session-settable by any role; the trigger's `current_user` gate is the real control). *Caught in adversarial review before this PR.*
- **§6.2.3 `granted_by NOT NULL` + system sentinel stays DEFERRED.** `granted_by` is `REFERENCES auth.users(id) ON DELETE SET NULL` (NOT NULL conflicts), the sentinel's FK target is the Supabase-owned `auth.users`, and onboarding + invite-accept self-grant with `granted_by=NULL` relying on the short-circuit. Dropping it without rerouting those request-path flows would break onboarding + invite-accept — unsafe without a live DB to validate.

## Why the RLS policies exist (the critical fix)

The backend bypasses RLS by connecting as the table **owner** (`postgres`). `xtrusio_reconciler` is a **non-owner**, so without explicit policies RLS denies it every read (0 rows → silent mis-reconciliation) and every write. `ALTER ROLE … BYPASSRLS` needs superuser (unavailable), so the migration adds permissive `{tbl}_reconciler_all FOR ALL TO xtrusio_reconciler USING(true) WITH CHECK(true)` policies on exactly the tables reconcile touches: `permissions`, `roles`, `role_permissions`, `user_roles`, `tenants`, `platform_users`, `tenant_memberships`. (For `user_roles` the priv-escalation trigger still governs escalation; the policy only lifts RLS.)

## Scope of the role-gate (no overclaim)

Only `enforce_priv_escalation` is role-gated. The 0009 immutability triggers (`reject_system_role_mutation`, `reject_system_role_perm_change`) and the 0010 owner-floor still honour the bypass GUC from **any** role **by design** — onboarding's `wire_workspace_role_perms` re-seeds `is_system role_permissions` on the request path and needs the un-gated bypass. No shipped request-path code sets the GUC, and `require_permission()` remains the primary gate. Role-gating those is out of C4's scope (spec §6.2.1/§6.2.2) and deferred.

## Review

Reviewed by a 6-dimension adversarial workflow (28 agents: DB-trigger security, regression trace, engine plumbing, migration portability, type/style gate, spec/test compliance) with each finding independently verified, plus a focused fix-verification pass. **Two CRITICAL bugs were caught and fixed pre-commit**, both masked by the dev fallback (a green local run would not have surfaced them):
1. Reconciler subject to RLS → fixed with the permissive policies above.
2. `GRANT SET ON PARAMETER` aborts the migration on Supabase → removed.

## ⚠️ Operator steps (before relying on the production reconciler path)

1. After `make migrate` applies `0013` (creates the role `NOLOGIN`): `ALTER ROLE xtrusio_reconciler LOGIN PASSWORD '<strong-password>';`
2. Set `RECONCILE_DATABASE_URL=postgresql+asyncpg://xtrusio_reconciler:<PW>@db.<ref>.supabase.co:5432/postgres`.
3. **Smoke-test live** — boot with the DSN set and confirm reconcile reads non-zero rows + writes succeed. This path **cannot** be validated in dev (there reconcile runs as `postgres`/owner; the `TO xtrusio_reconciler` policies are inert). Until smoke-tested, leave `RECONCILE_DATABASE_URL` unset — the dev fallback is safe and correct.

## Test plan

- [x] `uv run ruff check` (apps/api + migration + test) — PASS
- [x] `uv run ruff format --check` — PASS
- [x] `uv run mypy apps/api` — PASS (187 files)
- [x] Migration chain linear: `0012 → 0013`; `python -m py_compile` on all changed modules — PASS
- [x] New `tests/migrations/test_0013_reconciler_role.py` — introspection (SECURITY INVOKER, role-gate source, `INSERT OR UPDATE` tgtype, role exists least-privileged) + behavioural (bypass GUC **inert** on the request role; positive reconciler-role path guarded by `SET ROLE`). **Not run this session** (pytest deferred per standing instruction; the full backend suite is the operator's end-of-slice gate).
- [ ] Live smoke-test of the `RECONCILE_DATABASE_URL` path — operator step (cannot run in dev).
