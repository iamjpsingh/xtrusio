# HANDOFF — Plan 2 (Settings, Signup, Invites)

**Written:** 2026-05-15
**Branch:** `plan-2-settings-signup-invites` (cut from `main`)
**Status:** Plan 2A merged to `main`. Plan 2B in progress: Tasks 1–6 done, Task 7 next.

This document lets a fresh session on any machine resume exactly where we stopped. Read it top to bottom before doing anything.

---

## ⏩ RESUME HERE — updated 2026-05-16

**Plan 2B is CODE-COMPLETE.** All 14 implementation tasks done (each spec + code-quality reviewed), final whole-implementation review = "Ready to finalize" with its findings fixed. Branch `plan-2-settings-signup-invites`, tree clean, NOT pushed; `main` has Plan 2A + CORS + config externalization + sign-in link (`76f175e`).

**Test baseline:** backend **`81 passed`** (`uv run --directory apps/api pytest tests/ -p no:warnings`), frontend **`29 passed`** deterministic (`pnpm --filter @xtrusio/web test`). ruff/tsc/eslint clean; mypy `--strict src` = 1 pre-existing `jose` baseline only. Alembic single head `0004`.

**Plan 2B commits (all done):** `2a38068` mig0004 · `fb3bc37` models · `bbd4345` can_invite · `b8f8f5e` schemas · `de17ad5` platform invites · `97d26f4` tenant invites · `89b3865` /invites/accept · `de6ad42` /me pending_invite · `d8435d3` RLS tests · `b88b78b` integration · `d8b85d2` FE api wrappers · `ec813d2` /accept-invite · `99a3701` /users UI · `9428241`/`af804d0` /clients/$slug/users · `127fc05` final-review fixes.

**Only remaining = USER-DRIVEN manual smokes (cannot be delegated):**
- **2B-15** invite e2e smoke (see Plan 2B Task 15: super_admin invites editor → email link → /accept-invite → land on /; then incognito self-serve signup → onboard → /clients/<slug>/users invite admin → accept).
- **Plan 2A Task 18** signup-chain smoke (still never run).
Both need: real `.env`, `make dev` (OrbStack up), a bootstrapped owner, real email inboxes.

**Commit convention (user pref, 2026-05-16):** NO `Co-Authored-By` trailer — commits use only the user's git identity.

**Known deferred debt:** (a) sign-up-page/onboarding-page still misuse `ApiError.message` → generic error text (see `project_apierror_message_debt` memory); (b) `revoke_platform_invite` best-effort `list_users()` only scans page 1 (orphan unconfirmed auth users on >50-user platforms; suppressed, non-security).

**Next step:** `superpowers:finishing-a-development-branch` — present merge/PR options to the user (do NOT auto-merge; user chose merge+push for the prior batch but must decide again for Plan 2B).

### Plan-2B execution gotchas (the plan file is STALE — apply these every task)

1. **Migration is `0004`** (done) — plan file says 0003; that slot was the RLS fix.
2. **`mock_supabase_admin` conftest fixture must be extended per service module.** It currently patches `create_client` for `signup`, `platform_invites`, `tenant_invites`. **Task 7's `invite_acceptance` service does NOT call `create_client` (no email send on accept) so no extension needed there — but any future service that does must add its own `monkeypatch.setattr("xtrusio_api.services.<mod>.create_client", _factory)` line.**
3. **Every route/integration test file:** `pytestmark = pytest.mark.asyncio(loop_scope="session")` (plan uses bare `pytest.mark.asyncio` — wrong, breaks shared asyncpg loop).
4. **Service Supabase calls:** `except TimeoutError` AND `except Exception` both `await db.rollback()` then raise `EmailProviderUnavailableError`; timeout from `cfg.supabase_timeout_sec` (one `cfg = get_settings()` per fn, NO hardcoded `_SUPABASE_TIMEOUT`).
5. **`InviteAlreadyAcceptedError` is its own class** (don't reuse `InvitePendingError` for the accepted-guard). Idempotent revoke: missing→204 no-op, already-revoked→204 no-op.
6. **Response schemas hit by `Model.model_validate(<ORM obj>)` need `model_config = ConfigDict(from_attributes=True)`.** Already added to `PlatformInviteResponse` + `TenantInviteResponse` in `schemas/invite.py`. `AcceptInviteResult` is validated from a **dict**, so it does NOT need it.
7. **Backend uses the owner DB connection — RLS does NOT constrain it.** Any list/revoke/read endpoint must enforce authz explicitly in the service (see `tenant_invites._require_owner_or_admin`), never "rely on RLS".
8. **asyncpg rejects multi-statement `text()`** — split semicolon-joined SQL (esp. test cleanup) into separate `db.execute(text(...))` calls.
9. **Posting `role:"owner"`/`"super_admin"` is NOT a 422** — those are valid enum members; `can_invite()`/DB-CHECK reject them → expect 403 `forbidden_role`.
10. **DELETE routes:** `@router.delete(..., status_code=204, response_class=Response)` returning `Response(status_code=204)` (FastAPI 204+body assertion). Established convention.
11. **Accepted lint/type baseline:** ruff clean; mypy = 1 `jose` stub error in `core/auth.py`. Zero NEW. Keep any `# type: ignore` scoped to the exact code (e.g. `[call-arg]` on supabase `data=` kwarg).

### Task 7 specifics (was interrupted mid-prep — DO THIS FIRST when resuming)
Before dispatching 2B-7, verify these (the dispatch was interrupted at exactly this check):
- `apps/api/tests/conftest.py` `make_jwt` `_factory`: **HANDOFF gotcha #7 says it already accepts `user_metadata`** — confirm its current signature/payload; if it already injects `user_metadata`, the plan's Step 1 conftest edit is a no-op/duplicate — don't double-add.
- `apps/api/src/xtrusio_api/core/auth.py` `AuthIdentity` + `require_authenticated`: plan adds a `user_metadata: dict[str,Any]` field. **`grep -rn 'AuthIdentity('` first** — confirm `require_authenticated` is the ONLY constructor (so adding a required field is safe); if anything else constructs it, update those too. `core/auth.py` is shared by every authenticated route (incl. tenant_invites) — a broken `AuthIdentity` breaks the whole suite.
- Task 7 also needs the test-file gotchas #3 (loop_scope) and #8 (split cleanup SQL); plan's `test_invite_acceptance.py` uses bare `pytest.mark.asyncio` and semicolon-joined cleanup DELETEs — correct both in the dispatch.
- `AcceptInviteResult.model_validate(result_dict)` is fine without `from_attributes` (dict input).

### Still-open user-driven items (cannot be delegated)
- **Plan 2A Task 18 manual smoke** — never run. Needs user: restart `make dev` (note: `.env` must exist with the managed-Supabase values + the externalized keys API_HOST/API_PORT/WEB_DEV_PORT/WEB_APP_URL/CORS_ALLOW_ORIGINS/JWKS_*/SUPABASE_TIMEOUT_SEC; see `.env.example`), bootstrap a platform owner (`make create-platform-owner email=… password=…`), then click through.
- **Plan 2B Task 2B-15 manual smoke** — at the very end.

### Memory note
A new feedback memory was added: `feedback_no_hardcoded_config.md` ([[feedback-no-hardcoded-config]]) — all env-varying values come from `.env`; no literals/Field-defaults in py/Makefile/vite.

---

## 1. Where we are

| Item | State |
|---|---|
| Branch | `plan-2-settings-signup-invites`, 20 commits ahead of `main`, working tree clean |
| HEAD | `872a2d6 feat(web): /settings — signups_enabled toggle (super_admin)` |
| Backend tests | 48 passing (`uv run --directory apps/api pytest tests/`) |
| Frontend tests | 20 passing (`pnpm --filter @xtrusio/web test`) |
| Alembic head | `0003_fix_rls_recursion_and_grants` |
| Plan 2A | Tasks 1–17 done. **Task 18 (manual browser smoke) NOT done.** |
| Plan 2B | Not started (15 tasks). |

The two plan files are the source of truth for the remaining work:
- `docs/superpowers/plans/2026-05-14-plan-2a-public-signup-chain.md` (Task 18 = manual smoke)
- `docs/superpowers/plans/2026-05-14-plan-2b-platform-and-tenant-invites.md` (all 15 tasks)
- Spec: `docs/superpowers/specs/2026-05-14-platform-settings-signup-and-invites-design.md`

## 2. First thing on the new machine: recreate `.env`

`.env` and `.env.local` are **gitignored — they do NOT travel with the branch.** Nothing works without `.env`. On the new machine:

```bash
cp .env.example .env
# then fill in the 6 real values from the managed Supabase project:
#   DATABASE_URL              (Direct connection, port 5432, scheme postgresql+asyncpg://)
#   SUPABASE_URL              (https://<ref>.supabase.co)
#   SUPABASE_ANON_KEY
#   SUPABASE_SERVICE_ROLE_KEY
#   SUPABASE_JWKS_URL         (https://<ref>.supabase.co/auth/v1/.well-known/jwks.json)
#   VITE_SUPABASE_URL         (= SUPABASE_URL)
#   VITE_SUPABASE_ANON_KEY    (= SUPABASE_ANON_KEY)
```

Auth is **asymmetric JWKS, not HS256**. There is no `SUPABASE_JWT_SECRET` anymore.

Then:

```bash
make install            # pnpm + uv deps
make db-up              # local Valkey (OrbStack — no host ports, uses xtrusio-valkey.orb.local DNS)
make migrate            # applies 0000→0003 to the Supabase project in DATABASE_URL
make create-platform-owner email=you@x.com password='YourStrong-Pass1'   # if not already bootstrapped
```

Requires Docker (OrbStack) running.

## 3. How to resume the work

We were executing via the **`superpowers:subagent-driven-development`** skill: one fresh subagent per plan task, then a spec-compliance review subagent, then a code-quality review subagent, fix loop, commit, next task. Continue that pattern.

Immediate next step is the user-driven smoke test (Plan 2A Task 18) — cannot be delegated:

1. `make dev`
2. http://localhost:5173/sign-in → log in as the bootstrapped super_admin
3. `/settings` → toggle "Self-serve signups" ON
4. Incognito → http://localhost:5173/sign-up → sign up with a real email
5. Click the Supabase confirmation email link
6. Should redirect to `/onboarding` → enter a workspace name → submit → land on `/`

If smoke passes (or user says skip): start Plan 2B Task 1.

## 4. Gotchas discovered during Plan 2A (save hours — read this)

1. **Alembic renumber for Plan 2B.** The plan file says Plan 2B Task 1 creates `0003_platform_and_tenant_invites.py`. That slot is taken (RLS fix). Plan 2B's first migration must be **`0004_platform_and_tenant_invites.py` with `down_revision = "0003"`**.

2. **RLS recursion (already fixed in `0003`).** Plan 1B's `platform_users_super_admin_all` policy was `FOR ALL` with a `USING` clause that selected from `platform_users` → infinite recursion under any non-superuser role. Migration `0003` introduced `SECURITY DEFINER` helpers `is_super_admin(uid)`, `is_tenant_owner_or_admin(uid, tid)`, `is_tenant_member(uid, tid)` and rewrote the policies to call them. **Any new Plan 2B RLS policy that needs a super_admin / owner / member check MUST call these helper functions, never inline an `EXISTS … FROM platform_users/tenant_memberships` (that reintroduces recursion).**

3. **`authenticated` role needs explicit DML grants.** Alembic-created tables don't inherit Supabase's auto-grants. Migration `0003` granted SELECT/INSERT/UPDATE/DELETE to `authenticated` on the four existing tables. **Plan 2B's migration must `GRANT … TO authenticated` on `platform_invites` and `tenant_invites` too**, or RLS tests fail with "permission denied for table" before the policy is even evaluated.

4. **TanStack Router `autoCodeSplitting: true`** (in `apps/web/vite.config.ts`) strips every non-`Route` export from files in `src/routes/`. Tests can't import a page component from a route file. **Pattern: route file is a thin wrapper (`createFileRoute(...)({ component: X })` importing `X` from `@/components/<name>-page.tsx`); the real component + its test live in `src/components/`.** Established in Tasks 15–17 (`sign-up-page.tsx`, `onboarding-page.tsx`, `settings-page.tsx`). Plan 2B's `/accept-invite`, `/users`, `/clients/$slug/users` must follow it.

5. **pytest asyncio marker.** Use `pytestmark = pytest.mark.asyncio(loop_scope="session")` — asyncpg connections via `SessionLocal` are bound to one event loop across the suite; function-scoped loops raise `InternalClientError: got result for unknown protocol state`.

6. **Supabase Admin is mocked in tests** via the `mock_supabase_admin` fixture in `apps/api/tests/conftest.py` (monkeypatches `xtrusio_api.services.signup.create_client`). For Plan 2B services that call `create_client` from a *different* module, the fixture's monkeypatch target string must be updated/extended to patch that module's `create_client` too.

7. **JWKS test plumbing.** `apps/api/tests/conftest.py` has a session-scoped RSA keypair, an autouse `_patch_jwks` fixture (clears `_JWKS_CACHE` + monkeypatches `xtrusio_api.core.auth._fetch_jwks`), and `make_jwt(sub=..., user_metadata=...)` minting RS256 tokens. Plan 2B's invite-acceptance tests use `make_jwt(..., user_metadata={"platform_invite_id": ...})` etc. — the kwarg already exists.

8. **Reusable auth dep.** `apps/api/src/xtrusio_api/core/auth.py` exports `AuthIdentity` + `require_authenticated` (JWT-valid but no platform_users row required). Plan 2B `/invites/accept` and tenant-invite routes should use this, not `get_current_user`.

9. **Accepted pre-existing baseline (do NOT try to "fix" these):** mypy reports 2 `python-jose` missing-stub errors (`core/auth.py`, `tests/conftest.py`); ruff reports 1 `I001` in `scripts/bootstrap.py`. All three predate this branch. New code must add zero new mypy/ruff errors on top of that baseline.

10. **Missing shadcn primitives** get installed with `pnpm dlx shadcn@latest add <name>` from `apps/web/` (this is how `switch.tsx` landed in Task 17). Commit the generated `ui/<name>.tsx` alongside the page that needs it.

11. **`PageHeader` prop shape** is `{ title: string; description: string; action?: ReactNode }` — `description` is required.

## 5. Engineering rules still in force

`docs/superpowers/ENGINEERING_PRINCIPLES.md`. TS-only frontend, no hardcoded colors, no demo data, `mypy --strict`, no `any`, 500 LoC/file ceiling, every list endpoint paginated, every tenant-scoped table has RLS + RLS tests, every external call has a timeout, every migration reversible. `make check` is the merge contract.

## 6. Plan 2B task list (15 tasks, see plan file for full code)

1. Migration `0004` — `platform_invites` + `tenant_invites` + RLS (+ grants, see gotcha 3)
2. SQLAlchemy models for both invite tables
3. `can_invite()` pure rule helper + TDD
4. Invite pydantic schemas
5. Platform invites service + route (super_admin CRUD)
6. Tenant invites service + route (owner/admin CRUD, role-of-inviter rules)
7. `/invites/accept` generic acceptance endpoint
8. `/me` extended to populate `pending_invite` from JWT metadata + DB row
9. RLS tests for `platform_invites` + `tenant_invites`
10. Integration test: owner invites admin → accept → `/me` reflects role
11. Frontend api.ts invite wrappers
12. `/accept-invite` page (auto-POST on mount)
13. `/users` expanded — platform invite UI
14. `/clients/$slug/users` — tenant invite UI
15. Manual smoke (combined)

After Plan 2B: final whole-branch code review, then `superpowers:finishing-a-development-branch` to merge/PR.

## 7. Memory

Persistent memory lives at `~/.claude/projects/-Users-jpsingh-Developer-Project-xtrusio/memory/` (machine-local, does NOT travel — it's outside the repo). Key entries: project overview, engineering rules. On a new machine the memory dir starts empty; this HANDOFF.md + the spec/plan files are the durable record.
