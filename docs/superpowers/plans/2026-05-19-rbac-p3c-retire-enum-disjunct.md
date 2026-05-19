# RBAC P3c — Retire the Transition-Safe Enum Disjunct (lean plan)

> Lean model: build the whole slice in one coherent pass; ONE targeted RLS check + ONE full suite run by the controller; ONE final review. Migration/RLS slice → the lean "one targeted mid-build check" exception applies. Code subagent = Opus.

**Goal:** Migration `0008` rewrites the three `0007` helpers (`is_super_admin`, `is_tenant_owner_or_admin`, `is_tenant_member`) from the transition-safe `resolver OR 0003-enum` form to **pure resolver** — completing the enum→resolver cutover. The legacy enum fallback is now redundant and removed: P3a made every principal resolver-visible (`user_roles` written on every create + reconcile backfill + startup self-heal; gate proved `memberships_without_grant 0`, `active_platform_without_grant 0`), and P3b made the backend resolver-authoritative.

**SCOPE (deliberately lean — see rationale):** ONLY (a) migration `0008` (pure-resolver helpers, fully reversible) and (b) reframing the pre-RBAC `tests/rls/` fixtures to grant `user_roles` (the enum fallback they relied on is intentionally gone — mirror P3b's reframing). **DEFERRED to bundle with P4/P5** (where the human role/permission-mutation endpoints that make them meaningful actually exist): audit-log writes, privilege-escalation guard + DB trigger, single-super_admin *service-layer* enforcement. **DEFERRED to a dedicated late cleanup** (after P6b removes frontend enum consumption and all backend enum reads are gone): dropping `platform_users.role` / `tenant_memberships.role` columns + the `platform_role`/`tenant_role` enum types. Rationale: building audit/escalation infra for mutation endpoints that don't exist yet is premature; dropping enum columns now would break P3b's still-additive `/me` (returns `platform.role`/`tenants[].role`) and every enum-writing path (onboarding/invite-accept/bootstrap) — those legitimately stay until their consumers are gone.

**Builds on merged P3b** (`main` @ `6df5650`). No new tables; single Alembic head becomes `0008`.

---

## Task 1 — migration `0008_retire_enum_disjunct`

Create `apps/api/migrations/versions/0008_retire_enum_disjunct.py` (header/typing exactly like `0007`; `revision="0008"`, `down_revision="0007"`; pure raw SQL; one statement per `op.execute`; no app imports).

`upgrade()` — `CREATE OR REPLACE` the 3 helpers to PURE resolver (same signatures → every existing `0003`/`0004` policy that calls them is untouched; `SECURITY DEFINER STABLE SET search_path = public` preserved):

```python
def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_super_admin(uid uuid) RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$ SELECT has_platform_perm(uid, 'platform.roles.manage') $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_owner_or_admin(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$ SELECT has_workspace_perm(uid, tid, 'workspace.members.manage') $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_tenant_member(uid uuid, tid uuid)
            RETURNS boolean
        LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1 FROM user_roles
                WHERE auth_user_id = uid AND workspace_id = tid
            )
        $$
        """
    )
```

`downgrade()` — restore the EXACT `0007` transition-safe `resolver OR 0003-enum` bodies verbatim (reversible; copy them byte-for-byte from `0007_rls_permission_engine.py` lines 114-158: `is_super_admin` = `has_platform_perm(uid,'platform.roles.manage') OR EXISTS(platform_users WHERE id=uid AND role='super_admin' AND is_active)`; `is_tenant_owner_or_admin` = `has_workspace_perm(uid,tid,'workspace.members.manage') OR EXISTS(tenant_memberships WHERE user_id=uid AND tenant_id=tid AND role IN ('owner','admin'))`; `is_tenant_member` = `EXISTS(user_roles WHERE auth_user_id=uid AND workspace_id=tid) OR EXISTS(tenant_memberships WHERE user_id=uid AND tenant_id=tid)`; all `SECURITY DEFINER STABLE SET search_path = public`).

## Task 2 — reframe pre-RBAC `tests/rls/` fixtures to the resolver model

Removing the enum fallback means any pre-RBAC RLS test whose ephemeral principal gets visibility via a raw `tenant_memberships`/`platform_users` INSERT (no `user_roles` grant) will now (correctly) be denied by `is_tenant_member`/`is_tenant_owner_or_admin`/`is_super_admin`. These tests validate the RLS POLICIES (unchanged) — they just need their ephemeral principals to be resolver-visible, exactly like P3b reframed the route tests. For EACH failing pre-RBAC rls test (likely in `test_tenants_rls.py`, `test_tenant_invites_rls.py`, `test_tenant_memberships_rls.py`, `test_platform_invites_rls.py`, `test_platform_settings_rls.py`): where it creates the ephemeral tenant + a `tenant_memberships` row, ALSO seed that tenant's 4 workspace system roles + wire role_permissions + `grant_role` the matching workspace role (reuse the P3a/P3b ephemeral pattern: the 0006-friendly role seed + `wire_workspace_role_perms` + `grant_role`); FK-safe `finally` teardown (`user_roles`→`role_permissions`→`roles`→…). Platform-scope: a non-super_admin principal stays non-super_admin (no grant) — `is_super_admin` false via pure resolver, same negative outcome (no change needed for the negative tests). The positive super_admin path uses the read-only `existing_super_admin` fixture (already resolver-visible via the live reconcile — verified in P3a/P3b). NEVER create/grant a super_admin in a test (P1 index + `test_no_super_admin_creation` guard). Do NOT weaken/delete any assertion — only add the resolver-side grant so the policy is exercised via the resolver instead of the retired enum fallback. `test_permission_engine_rls.py` already uses the resolver model — leave it.

---

## Verify (lean — controller-run)

1. **Targeted RLS check mid-build** (lean exception, controller, NOT full suite): `uv run --directory apps/api python -m tests._cleanup` then `make migrate` (applies `0008`; `alembic current`=0008) then `uv run --directory apps/api pytest tests/rls/ -q` — ALL green (pre-RBAC tests now pass via resolver grants; `test_permission_engine_rls` unaffected). Then `make migrate-down` → `alembic current`=0007 → `uv run --directory apps/api pytest tests/rls/ -q -k "not permission_engine"` still green (downgrade restored the OR-form) → `make migrate` back to `0008`. Fix before continuing.
2. **One full run at the end** (controller): `make test-clean` then `uv run --directory apps/api pytest tests/ -q` — 0 failed except the 2 documented env-flaky `test_signup` (state-dependent) + the 2 documented vacuous skips. `uv run ruff check apps/api` + `uv run mypy --strict apps/api/src` (baseline only). `uv run --directory apps/api alembic heads` single `0008`.
3. **One final code-quality review** (Opus, whole slice): `0008` pure-resolver bodies correct + signatures unchanged (policies untouched) + downgrade byte-restores the `0007` OR-form (reversible); the rls-test reframing only ADDS resolver grants (no weakened/removed assertions, hygiene preserved); behaviour: every real/seeded principal still resolves identically, only the now-redundant enum fallback removed. Then finishing → PR → merge.

## Self-review

Completes spec §5's "P3 retires the legacy disjunct ... pure-resolver form" — the keystone that makes the enum→resolver cutover final. Safe because P3a (resolver-visible principals) + P3b (resolver-authoritative backend) are merged. Reversible (`0008` downgrade restores the exact `0007` transition-safe bodies). Deferred items (audit/escalation-guard/single-super_admin-service/enum-column-drop) explicitly scoped out with rationale — they belong with P4/P5 / a late cleanup, not here. Risk: a pre-RBAC rls test left un-reframed would fail (caught by the mandatory mid-build `tests/rls/` check).
