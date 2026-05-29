## PAR-D slice 2a — concurrency locks + Valkey perm cache

Second PAR-D slice. This is the **additive, isolated** half of PAR-D's infra
work — advisory locks + the Valkey permission cache. The riskier invite-flow
rewrite (caller-owns-tx M1 + invite outbox H5 + invite-revoke `FOR UPDATE` L4)
is deliberately left for **slice 2b** since it changes user-facing email-delivery
semantics.

Spec: `docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` §7.

### Findings closed

| ID | Fix |
|---|---|
| **M6** | Onboarding race: two parallel `POST /onboarding/tenants` for one user both passed the membership existence-check and each created a tenant. `create_tenant_with_owner` now takes a `pg_advisory_xact_lock` keyed on the user id (two-int form, `0x4F4E` namespace), making check-then-create atomic; it auto-releases at commit. Different users never block each other. |
| **M9** | Boot reconcile race: N workers each ran the (idempotent but expensive) `reconcile_rbac`. The lifespan now gates it behind `pg_try_advisory_lock(0x52424143)` held on a dedicated connection; losers log `rbac_reconcile_skipped_lock_held` and skip. Reconcile is idempotent, so a missed lock (e.g. a pooler that doesn't pin the session) only costs a redundant pass, never correctness. |
| **M16** | Valkey configured but never consumed. New `core/perm_cache.py` caches the effective-permission lists behind `GET /me` (`effective_platform_perms` + the batched per-workspace path), TTL `PERM_CACHE_TTL_SEC` (30s). **The authz gate (`require_permission` → resolvers) is never cached** — a stale entry only affects `/me` display, never an access decision. Invalidated on grant/revoke (`grant_role`, `grant_platform_role`/`revoke_platform_role_grant`, `grant_workspace_role`/`revoke_workspace_role_grant`); the short TTL bounds the rest. Every cache op is best-effort: a Valkey outage degrades to a DB read (logged WARN), so it can never take `/me` down. Client has 2s connect/socket timeouts to fail fast. |

### New artifacts

- `core/perm_cache.py` (async Valkey client, error-tolerant get/set/mget/invalidate/clear).
- New required env var `PERM_CACHE_TTL_SEC` (in `.env.example`); explicit `redis~=7.4.0` dep (was transitive via `limits[redis]`).
- Tests: `test_perm_cache.py` (skips if Valkey down), `test_onboarding_race.py` (concurrent + sequential), `test_reconcile_single_worker.py` (lock-exclusion primitive).
- Autouse conftest fixture clears the perm cache per test (deterministic regardless of Valkey availability).

### Deferred to slice 2b

Caller-owns-transaction convention (M1), invite-email outbox + worker (H5),
invite-revoke `SELECT … FOR UPDATE` (L4) — the coupled invite-flow rewrite.

### Verification

- ruff + ruff format + `mypy --strict` green.
- Targeted backend suite (perm cache, onboarding race, reconcile lock, `/me`, grants/revokes, invite-accept, onboarding) green against the managed dev project.
