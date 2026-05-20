# Type the tests + ruff format apps/api

Drains pre-existing test-file typecheck debt + ruff format debt so `make check` goes green project-wide. Unblocks P4 from starting on a clean baseline.

## Summary

Discovered during P3.5 (#8) as pre-existing P3a/P3b-era debt. The HANDOFF item "P3.5 surfaced follow-ups" called this out. This PR drains it.

### Slice A — Type `apps/api/tests/routes/*` (commit `f0cb968`)

7 files annotated for `mypy --strict`. Zero behavior changes — only `def` signatures gained `-> None` and arg types from the existing fixture vocabulary (`http_client: AsyncClient`, `make_jwt: Callable[..., str]`, `mock_supabase_admin: MagicMock`, `db_session: AsyncSession`, `existing_super_admin: PlatformUser`, etc.). Plus three `tuple[...]` generics on local helpers (`test_onboarding.py`, `test_tenant_invites.py`, `test_platform_settings.py`).

### Slice B — Type `apps/api/tests/integration/*` + `tests/rls/test_permission_engine_rls.py` (commit `6a9cc93`)

3 files. The integration tests gained `make_jwt: Callable[..., str]` annotations. The RLS test's `dict(<sqlalchemy result>)` form became an annotated dict-comprehension `rows: dict[str, str | None] = {r.policyname: r.qual for r in result}` (V is nullable because `pg_policies.qual` is nullable text — the downstream code already defends with `(rows.get(...) or "")`, confirming).

### Slice C — `ruff format apps/api` (commit `55c2db3`)

16 files reformatted to match the project's `ruff format` rules. Pure mechanical, no semantic change. The format-check on the full `apps/api` tree was the actual blocker on `make lint` going green — the per-file format invocations during P1–P3.5 only formatted files each phase touched, so unrelated files drifted.

## Why this is one PR, not three

All three slices are mechanical (no logic changes) and serve the same goal: `make check` green on `main`. Splitting would be churn for the reviewer with no readability gain.

## Verification

- `uv run mypy apps/api` → `Success: no issues found in 104 source files` (was: 49 errors in 10 files).
- `make lint` → green (was: 16 files would-be-reformatted).
- `make typecheck` → green (frontend `react-refresh` warnings remain — documented pre-existing per HANDOFF).
- `make test` → 152 passed, 2 documented skips, 0 failed (unchanged from `main`).

## Files

26 files modified across `apps/api/`:
- 10 test files (typed)
- 16 source/test files (reformatted, no semantic change)

No source code logic touched. No frontend. No migrations. No new dependencies. No commits with `Co-Authored-By: Claude` per `feedback_no_claude_coauthor`.

## What's NOT in this PR

- The 5 frontend `react-refresh/only-export-components` warnings in `apps/web/` — pre-existing, documented in HANDOFF as accepted baseline.
- The two pyproject.toml `[[tool.mypy.overrides]]` configuration warnings — separate cleanup; doesn't affect the strict typecheck result.
- The `gotrue` → `supabase_auth` migration — separate follow-up phase.
- `services/platform_invites.py:90` / `services/tenant_invites.py:146` broad `except Exception` — separate follow-up phase.

## Next

After merge: `main` is fully green. P4 (Platform RBAC admin) plan at `docs/superpowers/plans/2026-05-20-rbac-p4-platform-admin.md` is ready to execute next.
