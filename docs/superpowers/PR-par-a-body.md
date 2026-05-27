# PAR-A — Auth / security perimeter (audit C1, C2, H8, M22)

First phase of the **Production Audit Remediation** (PAR) sprint. Closes the perimeter findings from the 2026-05-26 audit (`docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` §4).

## Summary

- **C1 — JWT verification hardened.** Algorithms pinned to `RS256` only; `header.alg` validated BEFORE the JWKS lookup; `iss/aud/exp/iat/sub` required-claim enforcement; `iss` pinned to `<supabase_url>/auth/v1`; `aud` stays `"authenticated"` (Supabase default).
- **C2 — Invite metadata moved to `app_metadata`.** Was: invite ids written via `data={...}` → `user_metadata` (user-writable via the Supabase JS client). Now: post-create `admin.update_user_by_id(..., app_metadata={...})` (service-role-only writable). Acceptance reads from `app_metadata`. Closes the takeover surface where a leaked invite UUID + matching email = account hijack.
- **H8 — Rate limiting + signup non-enumeration.**
  - SlowAPI wired to Valkey (single backend, dev + prod, per spec §14):
    - `/api/signup` — 5/IP/hour
    - `/api/invites/accept` — 10/IP/hour
    - `/api/onboarding/tenants` — 5/user/hour
    - `AUTHED_CATCHALL_RATE` constant (60/user/min) defined for the later auth-catch-all rollout.
  - `/api/signup` no longer enumerates: existing email triggers a Supabase `reset_password_for_email` instead of returning 409. Both paths return identical `202 confirm_email_sent`. `EmailTakenError` is now internal-only.
- **M22 — `PrivilegeEscalationError` 403 body sanitized.** Was: `f"privilege_escalation: {e.missing_perm_key}"` (RBAC-graph enumeration oracle). Now: constant `"privilege_escalation"`. `missing_perm_key` stays on the exception for server-side logging only.

## New tests

- `tests/routes/test_jwt_verification.py` — adversarial JWT minting (wrong alg, missing iss, wrong iss, missing aud, expired, missing sub). Each adversarial token must produce 401.
- `tests/routes/test_invite_app_metadata.py` — invitee with invite-id forged via `user_metadata` rejected; legitimately admin-set `app_metadata` accepted.
- `tests/routes/test_rate_limit.py` — asserts the four perimeter routes have registered rate limits (config-only, doesn't burst Valkey).
- `tests/routes/test_signup_no_enumeration.py` — POST `/signup` with new vs existing email returns identical 202 bodies.
- `tests/routes/test_privilege_escalation_sanitized.py` — triggers a `PrivilegeEscalationError`; asserts 403 body is exactly `"privilege_escalation"` (no perm key leaked).

## Existing tests updated

8 files modified to match the new behavior (removing old `email_taken` 409 expectations, removing `f"privilege_escalation: <key>"` assertions, etc.):
`tests/integration/test_invite_full_flow.py`, `tests/routes/test_invite_acceptance.py`, `tests/routes/test_me.py`, `tests/routes/test_platform_invites.py`, `tests/routes/test_platform_role_grants.py`, `tests/routes/test_signup.py`, `tests/routes/test_tenant_invites.py`, `tests/routes/test_workspace_role_grants.py`, plus shared fixtures in `tests/conftest.py`.

## New runtime artifacts

- `apps/api/src/xtrusio_api/core/rate_limit.py` — SlowAPI singleton + per-route limit constants, Valkey-backed (no in-memory fallback).

## Dependencies added

- `slowapi` (rate limiting)

## Spec

- `docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` — full PAR remediation plan (60 findings across 6 phases A–F); this PR ships Phase A.

## Documentation

- `docs/superpowers/HANDOFF.md` updated — pivots NEXT from "first product feature" to PAR-B → PAR-F remediation roadmap.

## Test plan

- [x] `ruff check` ✅
- [x] `ruff format --check` ✅ (160 files)
- [x] `mypy --strict` ✅ (0 issues, 160 source files)
- [x] `turbo lint` ✅ (no new violations on `main`)
- [x] `turbo typecheck` ✅
- [x] `vitest` ✅
- [x] `pytest apps/api/tests` ✅ (207 passed via session-mode Supavisor pooler; 1 transient pooler statement-timeout flake on `test_workspace_members::test_list_grant_count_per_member`, re-run green in isolation)

## Operator notes

- The dev `DATABASE_URL` had to switch to the Supavisor session-mode pooler (`aws-1-ap-southeast-1.pooler.supabase.com:5432`) because Supabase has retired the direct `db.<project>.supabase.co` hostname for this project. The full pooler-aware engine config (with `NullPool` + transaction-mode `statement_cache_size=0` + `statement_timeout` etc.) lands in PAR-B.
- No code change to `core/db.py` in this PR — `.env` is gitignored; the pool config rewrite is PAR-B scope.

## What's next

PAR-B (DB pool + JWKS rotation + observability) starts after this merges — addresses C3, H7, M13, M14, L1, L2, L16.
