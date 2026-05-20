# P3.5 — review-fix backlog (CI, pagination, boundary hardening, AuthGuard)

Closes the parked review-fix backlog called out as "now unblocked" in HANDOFF item 7, ahead of P4.

## Summary

Four slices, eleven commits, all on `rbac-p3-5-review-fix-backlog` off `main` at `3e0b541`.

### Slice A — CI lands (merge gate)

- `.github/workflows/ci.yml` + `README.md` — runs `make install / migrate / test-clean / lint / typecheck / test`, enforces the `.js`/`.jsx`/`.mjs`/`.cjs` ban (§2.0), `concurrency: ci-test-db` so a single shared CI Supabase project is touched by one job at a time.
- `docs/superpowers/ENGINEERING_PRINCIPLES.md` §8 amended: tests run against EITHER a Postgres test container OR a dedicated managed-Supabase test project (`xtrusio-ci`). Same change drops the `(when CI lands)` caveat at line 35.

### Slice B — Pagination & bounded queries (§3 line 88, §9 line 121)

- `core/pagination.py` — opaque base64url cursor primitive (`CursorParams`, `encode_cursor`, `decode_cursor`, `DEFAULT_LIMIT=50`, `MAX_LIMIT=200`). Cursors encode `(created_at, id)`; tampering raises `ValueError` so routes can return 400.
- `GET /api/tenants` — was unbounded, now cursor-paginated with `TenantsPage` envelope.
- `GET /api/platform/users/invites` — `next_cursor` is now real (was hardcoded `None`).
- `GET /api/tenants/{tenant_id}/invites` — same.
- `tests/integration/test_no_unbounded_lists.py` — structural invariant: walks `app.routes`, asserts every `*Page`-returning GET has a `limit` query param with `le=MAX_LIMIT`. Sanity-verified by deliberately breaking one endpoint and confirming the test correctly named the offender.

### Slice C — Boundary hardening (§5)

- **JWKS coalescing.** `core/auth.py` splits `_fetch_jwks` into a cached wrapper + `_fetch_jwks_uncached`, with a per-URL `asyncio.Lock`. N concurrent cold-start callers now produce 1 underlying httpx fetch (test proves it with a slow stub + `asyncio.gather` of 10 callers; `calls == 1`).
- **Signup duplicate-email by class, not string match.** `services/signup.py` catches `gotrue.errors.AuthApiError` and checks `.code in {email_exists, user_already_exists}`. Drops the brittle `"already" in str(e)` heuristic and the `Any`-typed `_call`. The route-level `test_signup_email_taken_returns_409` updated to raise a real `AuthApiError`; new service-level tests cover both the email-taken mapping and the pass-through for unrelated codes.
- **Lifespan fail-fast.** `main.py` `lifespan` was logging `except Exception:` and continuing. Now it logs AND re-raises by default; opt-in `STARTUP_RECONCILE_TOLERANT=true` env flag restores the old swallow-and-continue posture (local dev only). `STARTUP_RECONCILE_TOLERANT` is a required Setting (no `Field` default per `feedback_no_hardcoded_config`); `.env.example` and the CI workflow both document `false`.

### Slice D — AuthGuard cleanup

- `apps/web/src/components/auth-guard.tsx` drops the duplicate `staleTime: 30_000`; keeps the legitimate `refetchOnWindowFocus: false` override. Tests construct per-test `QueryClient` from `queryClientDefaults` exported from `lib/query-client.ts` so inheritance is exercised.

## Operator action required before this merges

**Add the new required env var to your local `.env`:**

```
STARTUP_RECONCILE_TOLERANT=false
```

Without it, `make dev` / `make test` / `make api` will fail Settings validation at boot. CI and `.env.example` are already set.

**Configure GitHub Actions secrets for the CI workflow** (Settings → Secrets and variables → Actions). The workflow is added in this PR but cannot run green until these are present:

- `CI_DATABASE_URL`
- `CI_SUPABASE_URL`
- `CI_SUPABASE_ANON_KEY`
- `CI_SUPABASE_SERVICE_ROLE_KEY`
- `CI_SUPABASE_JWKS_URL`

All five point at a dedicated `xtrusio-ci` managed Supabase project (separate from dev/prod).

## What's intentionally NOT done

- **Enum column drop on `platform_users.role` / `tenant_memberships.role`.** HANDOFF item 6: deferred until P6b removes frontend enum consumption AND every backend enum read is gone. `0008` downgrade still requires those columns to exist.
- **Switch all tests to literal Postgres test containers.** §8 was amended to permit managed-Supabase test projects instead — keeps the "no local DB stack" stance intact.
- **Fix pre-existing test-file typecheck debt.** Discovered during this slice: `uv run mypy apps/api` reports ~49 `no-untyped-def` errors in pre-existing test files (test_onboarding, test_me, test_signup, test_platform_settings, test_invite_acceptance, test_tenants, test_platform_invites, test_tenant_invites, etc.) — last touched during P3a/P3b. P3.5 contributes zero new mypy errors; every new source file and new test function in this PR is fully typed. Proposed follow-up: a small "type the tests" phase before P4, or absorb into P4 prep.
- **`gotrue` → `supabase_auth` migration.** supabase-py 2.x emits a `DeprecationWarning` saying `gotrue` is being replaced by `supabase_auth`. Worth a follow-up phase to migrate imports cleanly; not in P3.5 scope.

## Verification

- `make test-clean && make lint` — clean.
- Per-file `mypy` on every source file modified — clean.
- Full backend suite (`uv run pytest apps/api/tests/`) — green (env-flaky `test_signup_status_default_false` / `test_signup_disabled_returns_403` per HANDOFF caveat are state-dependent against the shared managed DB).
- Frontend `pnpm --filter @xtrusio/web test apps/web/src/components/auth-guard.test.tsx` — green.
- B5 invariant test sanity-checked by deliberately removing `le=MAX_LIMIT` from `routes/tenants.py` and confirming the test failed with `/api/tenants: limit le=None, expected 200`; reverted.
- C1 JWKS lock verified by 10-caller `asyncio.gather` + slow stub → exactly 1 underlying fetch.

## Files

27 files changed (+773 / -88). New: `core/pagination.py`, `tests/core/test_pagination.py`, `tests/core/test_auth_jwks.py`, `tests/integration/test_no_unbounded_lists.py`, `tests/services/test_signup.py`, `tests/test_lifespan.py`, `.github/workflows/ci.yml`, `.github/workflows/README.md`.
