# P6c/P6d polish — orphaned UI removal + exception narrowing + DELETE consistency

Cleanup pass after P6c + P6d landed. Three small, additive improvements to housekeeping items called out in HANDOFF; zero behavior changes for the happy path.

## Summary

- **Drop orphaned `apps/web/src/components/users-page.tsx` + its `.test.tsx`.** Was the pre-P6d platform-invites UI; no longer mounted by any route after P6d's `<PlatformUsersPage>` replaced `/platform/users`. Backend endpoints (`POST/GET/DELETE /api/platform/users/invites`) still exist for future use — only the orphaned component goes.
- **Narrow `except Exception`** in `services/platform_invites.py:90` and `services/tenant_invites.py:146`. Now catches `(AuthApiError, AuthRetryableError, httpx.HTTPError)` only. Programmer errors and unrelated exceptions propagate instead of being masked as `EmailProviderUnavailableError` — better signal during real incidents.
- **`DELETE /api/platform/users/{user_id}/roles/{grant_id}` consistency check.** `revoke_platform_role_grant` now validates `grant.auth_user_id == user_id`; mismatches raise `GrantNotFoundError` → 404 (don't leak existence). P5's workspace DELETE already pinned on `(id, user_id, workspace_id)` for scope isolation; this brings the platform-side surface to parity. Three existing test call sites updated to pass the new `user_id` kwarg.
- **Mechanical ruff isort cleanup** on `bootstrap.py` and `signup.py` (blank-line normalization).

## Architecture choices

- **`GrantNotFoundError` (not a new error type) for the user_id mismatch.** Don't leak that the grant exists when the requester has the wrong `user_id` in the path. Matches the P5 workspace DELETE semantics (where mismatched workspace_id also returns 404).
- **Narrow exceptions to known transient/network classes.** `AuthApiError` (auth API rejection), `AuthRetryableError` (Supabase signal for retry), `httpx.HTTPError` (transport). Everything else — including the previously-masked `KeyError`, `AttributeError`, programmer mistakes — now surfaces in error tracking + tests rather than being silently labeled `EmailProviderUnavailable`.
- **`users-page.tsx` deletion is intentional.** Re-mounting it at a different route (e.g. `/platform/invites`) was considered and explicitly deferred — the platform-invites UX needs a redesign that integrates with `<PlatformUsersPage>`, not a separate orphaned page. Backend invite endpoints are untouched and remain callable from scripts / future UI.

## Test plan

- [x] `uv run ruff check apps/api` — **All checks passed!**
- [x] `uv run ruff format --check apps/api` — **154 files already formatted**
- [x] `uv run mypy apps/api` — **Success: no issues found in 154 source files**
- [x] `pnpm --filter @xtrusio/web typecheck` — clean
- [x] `pnpm --filter @xtrusio/api-types typecheck` — clean
- [ ] Focused backend pytest on the modified files — deferred until the controller-run end-of-night full `make check` on main finishes (currently in flight against managed Supabase). The changes are statically validated by mypy (function signature change + new required kwarg propagated to test call sites; narrowed exception types preserved).
- [ ] Manual: try `DELETE /api/platform/users/<wrong-uid>/roles/<grant-id>` where `grant-id` belongs to a different user — should return 404.

## What's NOT in this PR — deferred to a future polish round

Each documented in HANDOFF as safe in practice today; not blocking new-feature work:

- **`gotrue` → `supabase_auth` migration.** `supabase 2.10.0` still bundles `gotrue 2.12.4`; the new package name lives in newer `supabase-py`. Requires a major-version dependency upgrade with regression risk. Tracked in HANDOFF.
- **`grant_role` `ON CONFLICT DO NOTHING` + NULLS DISTINCT race** (`rbac/grants.py`). Documented foot-gun for `workspace_id IS NULL` platform grants; existing call sites are safe (reconciler uses NOT EXISTS; onboarding/invite-accept/bootstrap are once-per-user paths). Future fix: explicit SELECT-then-INSERT pattern OR migrate to `UNIQUE NULLS NOT DISTINCT` (PG15+).
- **P5 `grant_workspace_role` concurrent-duplicate-grant race** (`services/workspace_role_grants.py`). Explicit pre-SELECT + INSERT (no ON CONFLICT); two concurrent identical grants → one wins, other raises IntegrityError → 5xx. Acceptable today (workspace.members.manage is rare; concurrent identical grants ≈ zero). Future hardening: `INSERT ... ON CONFLICT DO NOTHING RETURNING ...` with fallback SELECT.

## Next

After this lands + HANDOFF updates the "deferred polish" notes, the foundation is fully ready for the first product feature.
