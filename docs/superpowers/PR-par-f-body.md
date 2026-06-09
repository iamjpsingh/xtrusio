## PAR-F — CI / testing / migrations

Closes the final phase of the 2026-05-26 production audit (spec section 9). Addresses **H12, H13, H14, H15, M19, M20, M21, L12, L13, L15**. This phase gates everything PAR-A…E shipped. Implemented as two halves on one branch — backend+infra (`1766e03`) and frontend+packages (`5bd808a`) — plus a codegen-idempotency fix (`85a0550`).

> **Note:** the user explicitly greenlit the CI/CD work for this gating phase, overriding the standing "defer CI/CD until local dev is fully working" rule. CI jobs that need the `xtrusio-ci` managed-Supabase secrets stay **advisory** until those secrets are added; the api-types-drift gate runs with placeholder env and is live immediately.

### Backend + infra (`1766e03`)

| ID | Fix |
|---|---|
| **H12** (F.1) | `ci.yml` rewritten into two test jobs: an **ephemeral-Postgres** job (`pgvector/pgvector:pg16` + `.github/ci/ephemeral-db-bootstrap.sql` that stubs `auth.users` + extensions) running the 61 tests that don't need Supabase (`-m "not requires_supabase"`, `cancel-in-progress: true`), and a **`supabase-test`** job (managed CI project) for the 341 Supabase/JWT/multi-connection tests (keeps the serialized `ci-test-db` group, `cancel-in-progress: false`). Partition is automatic: a conftest hook tags a test `requires_supabase` if it requests a Supabase fixture or its module references `SessionLocal`/`auth.users`. **conftest changes are purely additive — local `make check` behavior is unchanged (402 tests, markers inert without `-m`).** |
| **H14** (F.4) | `tests/scripts/test_bootstrap_main.py` covers `bootstrap.main()` (platform_users row, super_admin grant, idempotency) with a **mocked Supabase admin client** and a session bound to a rolled-back outer transaction (`join_transaction_mode="create_savepoint"`) — so **no super_admin is ever committed** to the shared DB (test-data-hygiene preserved; verified 0 stray after run). Allow-listed in the no-super-admin guard. |
| **H15** (F.5) | `security.yml`: `pip-audit`, `pnpm audit --audit-level=high`, `gitleaks`, CodeQL (python + javascript-typescript), a stubbed Trivy job, and backend/frontend coverage gates (70/60 floors). `.github/dependabot.yml` (pip/npm/github-actions, weekly). `.gitleaks.toml` (default rules + `.env.example` allowlist). |
| **M19** (F.6) | The two env-flaky signup tests (`test_signup_status_default_false`, `test_signup_disabled_returns_403`) marked `@pytest.mark.xfail(strict=False)`. |
| **M20** (F.7) | `0008_retire_enum_disjunct.py` upgrade guard: refuses to run on a populated DB with empty `user_roles` (no-op on a correctly-migrated DB). |
| **M21** (F.8) | `docs/superpowers/migration-style.md` (CONCURRENTLY indexes, two-step NOT NULL, batched backfills; 0010/0011 as canonical examples), referenced from `ENGINEERING_PRINCIPLES.md`. |
| **L12** (F.9) | Pre-push hook (mypy + turbo typecheck + smoke pytest) via pre-commit `stages: [pre-push]` + `scripts/pre-push.sh`; `make install` now runs `pre-commit install`. Pre-commit comment updated (CI now exists; full check runs on push + PR). |
| **L13** (F.10) | `mise.toml` patch-pinned (node 22.22.2 / python 3.12.13 / pnpm 10.0.0). `docker-compose.local.yml` + `make dev-local` for opt-in local Postgres; `ENGINEERING_PRINCIPLES.md` documents it (default stays managed Supabase). |
| **L15** (F.11) | `Tenant.created_by` gains an ORM-level `ForeignKey("auth.users.id", ondelete="RESTRICT")`, resolved via a minimal `auth.users` Table stub in the same metadata. Safe because the project uses no `create_all`/autogenerate and `context.configure` doesn't set `include_schemas` — the stub is never emitted by a migration. |

### Frontend + packages (`5bd808a`, `85a0550`)

| ID | Fix |
|---|---|
| **H13** (F.3) | `packages/api-types` switched from hand-written mirrors to **OpenAPI codegen**: `scripts/generate.ts` dumps `app.openapi()` → `openapi-typescript` → `generated/openapi.d.ts` (committed); `src/*.ts` are now thin re-exports keeping every public type name `apps/web` imports. `pnpm api-types:generate` + a live `.github/workflows/api-types-drift.yml` gate (placeholder env, so it's enforcing immediately). **`85a0550`:** the generator now prettier-formats its output so regeneration is idempotent (raw `openapi-typescript` output ≠ the pre-commit-formatted committed file would otherwise fail the drift gate). **Surfaced real backend schema imprecision the manual mirrors hid:** `AuditEventOut.before/after` are typed `dict[str, Any]|None` → FastAPI emits an empty-object schema (`Record<string, never>|null`); reconciled via a type override in `audit-log.ts` (no app-logic change) — a typed Pydantic snapshot model is flagged as backend follow-up. |
| **H13** (F.2) | **MSW** infra (`src/test/msw/*`) with api-types-typed handlers; 3 representative pages converted (`platform-roles`, `platform-users`, `platform-audit-log`) to exercise the api-fetch↔schema alignment via real-shape responses (remaining mocked-api tests left as follow-up — gate is "vitest stays green"). MSW is installed **per-file**, not globally, to avoid perturbing unrelated Radix-dropdown tests. **Playwright**: `playwright.config.ts` + `tests/e2e/admin-smoke.spec.ts` (sign-in → roles CRUD → audit log → sign-out; creds from `process.env`, self-skips when absent) + `.github/workflows/e2e.yml` (advisory until secrets + real env). vitest `exclude` drops `tests/e2e/**`. Frontend coverage gate (`@vitest/coverage-v8`, 60% floor) wired and enforcing (~74% statements locally). |

### Verification
- Backend: `mypy --strict` clean (182 files), ruff + format clean, 402 tests collect with no errors; new/changed tests (bootstrap, signup-xfail, no-super-admin guard, migrations) pass; 0 stray super_admin after the bootstrap test. **Full backend suite run as the integrative gate (this phase touches test infra).**
- Frontend: `turbo run lint typecheck test` 9/9 green (no cache), **vitest 193 passed (41 files)**.
- Codegen: `pnpm api-types:generate` is idempotent — regenerate → `git diff --exit-code packages/api-types/generated/` clean (verified across 3 runs); the drift gate will pass.

### Deviations
- Coverage gate enforced in CI + `make test-cov`, **not** in `make check` (keeps local fast — explicit user preference).
- Ephemeral CI image is `pgvector/pgvector:pg16` (migration 0000 needs the `vector` extension), not bare `postgres:16`.
- F.1 savepoint isolation is **additive CI infrastructure only** — the existing managed-DB suite and its multi-connection/commit tests are untouched (a blanket savepoint fixture would break the outbox/race/reconcile tests).
- MSW per-file (not global); 3 pages converted, rest follow-up.

### Operator artifacts still required (CI advisory until set)
GitHub Actions secrets for `xtrusio-ci`: `CI_DATABASE_URL`, `CI_SUPABASE_URL`, `CI_SUPABASE_ANON_KEY`, `CI_SUPABASE_SERVICE_ROLE_KEY`, `CI_SUPABASE_JWKS_URL`; e2e secrets (`E2E_ADMIN_EMAIL/PASSWORD`, `E2E_VITE_SUPABASE_*`). The api-types-drift gate needs none of these.

### Known pre-existing (not introduced here)
`test_lifespan.py` fails when run in isolation (structlog `PrintLogger` quirk; reproduces on clean `main`) — passes in the full suite. PAR-C slice 2 (reconciler role) remains blocked on operator provisioning.
