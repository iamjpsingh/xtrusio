# Type-the-Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drain the pre-existing test-file typecheck debt so `make check` (lint + typecheck + test) finally goes green project-wide. Pure mechanical: add `-> None` returns and arg-type annotations to existing test functions across 10 files. Zero behavior changes.

**Architecture:** Two commits, two slices: (A) `apps/api/tests/routes/*.py` (6 files), (B) `apps/api/tests/integration/*.py` + `apps/api/tests/rls/*.py` (3 + 1 files). One end-of-branch `make check` gate (must reach 0 errors). One PR. P4 then starts from a fully-green baseline.

**Tech Stack:** Python 3.12, `mypy --strict`, pytest-asyncio, `httpx.AsyncClient`, pydantic v2, SQLAlchemy async. Same fixture vocabulary as the existing suite (`http_client`, `make_jwt`, `mock_supabase_admin`, `db_session`, `existing_super_admin`, etc.).

---

## Execution-model constraints (from user memory)

- `feedback_lean_review_workflow`: ONE end-of-branch `make check` gate, run by the controller. Subagents implement; controller gates.
- `feedback_model_selection`: code subagents = Opus.
- `feedback_no_claude_coauthor`: NO `Co-Authored-By: Claude` trailer on commits.
- `feedback_test_data_hygiene`: do NOT change test data semantics — only types. Every fixture that returns `AsyncIterator[X]` must keep its yielded shape.

---

## Error inventory (verified 2026-05-20, post-P3.5 merge)

`uv run mypy apps/api` reports 49 errors across 10 files. All are one of two shapes:

1. **`no-untyped-def`** — `def test_x(fixture_a, fixture_b):` needs `-> None` and arg types from the fixture signatures.
2. **`type-arg`** — `tuple` used as a bare generic; needs `tuple[T, ...]` or specific tuple shape.

Plus one variant in `test_permission_engine_rls.py:379-380`:
- **`var-annotated` + `arg-type`** — `rows = dict((row.x, row.y) for row in result)` needs an explicit `dict[K, V]` annotation; SQLAlchemy's `Sequence[Row[Any]]` doesn't satisfy `Iterable[tuple[K, V]]` without help.

Per-file error counts (controller-verified):

| File | Errors |
|---|---|
| `tests/routes/test_tenant_invites.py` | 12 |
| `tests/routes/test_platform_invites.py` | 7 |
| `tests/routes/test_me.py` | 4 |
| `tests/routes/test_onboarding.py` | 4 |
| `tests/routes/test_signup.py` | 3 |
| `tests/routes/test_invite_acceptance.py` | 5 |
| `tests/routes/test_platform_settings.py` | 7 |
| `tests/integration/test_invite_full_flow.py` | 1 |
| `tests/integration/test_signup_to_tenant_flow.py` | 1 |
| `tests/rls/test_permission_engine_rls.py` | 2 (the var-annotated case) |
| **total** | **46** (the remaining 3 are pyproject.toml config warnings, not file errors) |

---

## Type vocabulary (use these names verbatim — they already exist in `conftest.py`)

| Identifier | Type |
|---|---|
| `http_client` | `httpx.AsyncClient` |
| `make_jwt` | `Callable[..., str]` |
| `mock_supabase_admin` | `unittest.mock.MagicMock` |
| `db_session` | `sqlalchemy.ext.asyncio.AsyncSession` |
| `existing_super_admin` | `xtrusio_api.models.platform_user.PlatformUser` |
| `monkeypatch` | `pytest.MonkeyPatch` |
| `jwks_keypair` | `dict[str, Any]` |
| Test function return | `None` |

Local fixtures defined inside individual files (e.g., `platform_admin_user`, `unprivileged_user`, `_seed_owner`) yield/return whatever their existing implementation produces — match the existing yield type. If unclear, read the fixture body to confirm before annotating.

For SQLAlchemy `text(...)` results: explicit `dict[str, object]` for parameter dicts; `dict[<key_type>, <value_type>]` for any comprehension that needs `var-annotated`.

---

## File structure

**Modified (10 files, all under `apps/api/tests/`)**

| Path | Change |
|---|---|
| `tests/routes/test_tenant_invites.py` | annotate ~12 test functions + 1 `tuple[...]` generic at line 67 |
| `tests/routes/test_platform_invites.py` | annotate ~7 test functions |
| `tests/routes/test_me.py` | annotate 4 test functions |
| `tests/routes/test_onboarding.py` | annotate 4 test functions + 1 `tuple[...]` generic at line 15 |
| `tests/routes/test_signup.py` | annotate 3 test functions |
| `tests/routes/test_invite_acceptance.py` | annotate 5 test functions |
| `tests/routes/test_platform_settings.py` | annotate 6 test functions + 1 `tuple[...]` generic at line 17 |
| `tests/integration/test_invite_full_flow.py` | annotate 1 test function |
| `tests/integration/test_signup_to_tenant_flow.py` | annotate 1 test function |
| `tests/rls/test_permission_engine_rls.py` | add explicit `rows: dict[<K>, <V>] = ...` annotation at line 379 |

**NOT touched**
- Any source file under `apps/api/src/`
- Any test outside the list above (already clean)
- `pyproject.toml` (the two `[[tool.mypy.overrides]]` config warnings are unrelated; address in a separate cleanup if desired)

---

## Slice A — `tests/routes/*.py`

Goal: 6 test files in `apps/api/tests/routes/` annotated to satisfy `mypy --strict`. One commit at the end of the slice.

### Task A1: Annotate `test_signup.py` + `test_me.py` + `test_onboarding.py` + `test_invite_acceptance.py`

**Files:**
- Modify: `apps/api/tests/routes/test_signup.py` (3 funcs)
- Modify: `apps/api/tests/routes/test_me.py` (4 funcs)
- Modify: `apps/api/tests/routes/test_onboarding.py` (4 funcs + tuple generic at line 15)
- Modify: `apps/api/tests/routes/test_invite_acceptance.py` (5 funcs)

- [ ] **Step 1: Read each file's top imports + first 2-3 test signatures**

For each of the 4 files, do `Read` once to see the import block and the existing test signatures. This is needed because some files may use local fixtures whose types must be inferred from their bodies.

- [ ] **Step 2: Annotate every untyped test function**

For each `def test_*(...):` that mypy flagged in this file:
- Add `-> None` after the parameter list, before `:`
- Add the corresponding type annotation to each parameter, using the type vocabulary above
- If the param name doesn't match the vocabulary table, read the fixture (likely in `conftest.py` or local in the file) to determine its yielded type
- Do NOT change the function body, just the signature

Example transformation:
```python
# before
async def test_signup_invalid_email_returns_422(http_client, jwks_keypair, mock_supabase_admin):
    ...

# after
async def test_signup_invalid_email_returns_422(
    http_client: AsyncClient,
    jwks_keypair: dict[str, Any],
    mock_supabase_admin: MagicMock,
) -> None:
    ...
```

Imports to add (only if not already present):
- `from typing import Any` (only if `Any` is now used)
- `from collections.abc import Callable` (only if `Callable` is now used)
- `from httpx import AsyncClient`
- `from unittest.mock import MagicMock`
- `from xtrusio_api.models.platform_user import PlatformUser` (only if used)

Stay consistent with the file's existing import style.

- [ ] **Step 3: Fix the `tuple[...]` generic at `test_onboarding.py:15`**

Read line 15. It's likely a fixture return-type or a local helper that uses bare `tuple`. Replace with the specific shape, e.g., `tuple[UUID, str]` or `tuple[Any, ...]`. Pick the most-specific form supported by the function's body.

- [ ] **Step 4: Run mypy ONLY on these 4 files**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv run mypy apps/api/tests/routes/test_signup.py apps/api/tests/routes/test_me.py apps/api/tests/routes/test_onboarding.py apps/api/tests/routes/test_invite_acceptance.py 2>&1 | tail -15
```

Expected: `Success: no issues found` for all 4 files (ignoring pyproject.toml config warnings).

If any error remains: read the error, the function in question, and fix. Do NOT silence with `# type: ignore` unless the underlying issue is a known mypy quirk you can document inline with a 1-line justification.

- [ ] **Step 5: Run the actual tests to confirm zero behavior change**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run --directory apps/api python -m tests._cleanup && STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_signup.py apps/api/tests/routes/test_me.py apps/api/tests/routes/test_onboarding.py apps/api/tests/routes/test_invite_acceptance.py -v 2>&1 | tail -20
```

Expected: same test count as before, same passing.

### Task A2: Annotate `test_tenant_invites.py` + `test_platform_invites.py` + `test_platform_settings.py`

**Files:**
- Modify: `apps/api/tests/routes/test_tenant_invites.py` (12 funcs + tuple generic at line 67)
- Modify: `apps/api/tests/routes/test_platform_invites.py` (7 funcs)
- Modify: `apps/api/tests/routes/test_platform_settings.py` (6 funcs + tuple generic at line 17)

Same procedure as Task A1.

- [ ] **Step 1: Read each file's top + first few test signatures**

`test_tenant_invites.py` is the heaviest — it has local fixtures like `_seed_owner` returning `(user_id, tenant_id)`. Read `_seed_owner` to confirm its actual return shape so the `tuple[...]` annotation is precise.

- [ ] **Step 2: Annotate every untyped test function**

Same vocabulary, same transformation. Pay attention to local helpers — they may need annotation too if they appear in mypy's error list.

- [ ] **Step 3: Fix the `tuple[...]` generics**

- `test_tenant_invites.py:67` — read context; likely `tuple[UUID, UUID]` for `(user_id, tenant_id)`.
- `test_platform_settings.py:17` — read context; likely `tuple[Any, Any]` or similar.

- [ ] **Step 4: Run mypy on these 3 files**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv run mypy apps/api/tests/routes/test_tenant_invites.py apps/api/tests/routes/test_platform_invites.py apps/api/tests/routes/test_platform_settings.py 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 5: Run the actual tests**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false uv run --directory apps/api python -m tests._cleanup && STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/routes/test_tenant_invites.py apps/api/tests/routes/test_platform_invites.py apps/api/tests/routes/test_platform_settings.py -v 2>&1 | tail -20
```

Expected: all pass.

### Task A3: Lint, format, commit Slice A

- [ ] **Step 1: ruff format + check the 7 modified files**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv run ruff format apps/api/tests/routes/test_signup.py apps/api/tests/routes/test_me.py apps/api/tests/routes/test_onboarding.py apps/api/tests/routes/test_invite_acceptance.py apps/api/tests/routes/test_tenant_invites.py apps/api/tests/routes/test_platform_invites.py apps/api/tests/routes/test_platform_settings.py && uv run ruff check apps/api/tests/routes/test_signup.py apps/api/tests/routes/test_me.py apps/api/tests/routes/test_onboarding.py apps/api/tests/routes/test_invite_acceptance.py apps/api/tests/routes/test_tenant_invites.py apps/api/tests/routes/test_platform_invites.py apps/api/tests/routes/test_platform_settings.py
```

Expected: clean (auto-format will adjust line wrapping in any newly-multi-line signatures).

- [ ] **Step 2: Commit Slice A**

```bash
git add apps/api/tests/routes/test_signup.py apps/api/tests/routes/test_me.py apps/api/tests/routes/test_onboarding.py apps/api/tests/routes/test_invite_acceptance.py apps/api/tests/routes/test_tenant_invites.py apps/api/tests/routes/test_platform_invites.py apps/api/tests/routes/test_platform_settings.py
git commit -m "test(api): type apps/api/tests/routes/* for mypy --strict"
```

---

## Slice B — `tests/integration/*.py` + `tests/rls/*.py`

### Task B1: Annotate `test_invite_full_flow.py` + `test_signup_to_tenant_flow.py`

**Files:**
- Modify: `apps/api/tests/integration/test_invite_full_flow.py` (1 func at line 17)
- Modify: `apps/api/tests/integration/test_signup_to_tenant_flow.py` (1 func at line 18)

- [ ] **Step 1: Annotate the two test functions**

Same procedure as Slice A. Each file has exactly one offender — quick.

- [ ] **Step 2: Run mypy on these 2 files**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv run mypy apps/api/tests/integration/test_invite_full_flow.py apps/api/tests/integration/test_signup_to_tenant_flow.py 2>&1 | tail -10
```

Expected: clean.

### Task B2: Annotate `test_permission_engine_rls.py`

**File:**
- Modify: `apps/api/tests/rls/test_permission_engine_rls.py` (var-annotated case at lines 379-380)

- [ ] **Step 1: Read lines 370-390 of the file**

The errors are:
- `line 379: Need type annotation for "rows" (hint: "rows: dict[<type>, <type>] = ...")`
- `line 380: Argument 1 to "dict" has incompatible type "Sequence[Row[Any]]"; expected "Iterable[tuple[Never, Never]]"`

So the existing code is something like:
```python
rows = dict(...)
```
or
```python
rows = dict((r.col1, r.col2) for r in result)
```

- [ ] **Step 2: Determine the actual key/value types**

Read the SQL or the row construction to figure out what `r.col1` and `r.col2` are. Likely UUID + str, or str + str. Add an explicit annotation:

```python
rows: dict[UUID, str] = {r.col1: r.col2 for r in result}
```

Using a dict-comprehension form (rather than `dict(...)`) plus explicit annotation resolves both errors at once.

If the actual key/value types are not obvious from one screen of context, STOP and report — don't guess.

- [ ] **Step 3: Run mypy on this file**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv run mypy apps/api/tests/rls/test_permission_engine_rls.py 2>&1 | tail -10
```

Expected: clean.

### Task B3: Lint, format, commit Slice B

- [ ] **Step 1: Format + lint**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && uv run ruff format apps/api/tests/integration/test_invite_full_flow.py apps/api/tests/integration/test_signup_to_tenant_flow.py apps/api/tests/rls/test_permission_engine_rls.py && uv run ruff check apps/api/tests/integration/test_invite_full_flow.py apps/api/tests/integration/test_signup_to_tenant_flow.py apps/api/tests/rls/test_permission_engine_rls.py
```

- [ ] **Step 2: Commit Slice B**

```bash
git add apps/api/tests/integration/test_invite_full_flow.py apps/api/tests/integration/test_signup_to_tenant_flow.py apps/api/tests/rls/test_permission_engine_rls.py
git commit -m "test(api): type integration + rls tests for mypy --strict"
```

---

## End-of-branch gate (controller-run)

- [ ] **Step 1: Run the canonical `make check`**

```bash
cd /Users/jpsingh/Developer/Projects/xtrusio && STARTUP_RECONCILE_TOLERANT=false make test-clean && STARTUP_RECONCILE_TOLERANT=false make check 2>&1 | tail -30
```

Expected: `make lint` clean, `make typecheck` clean (mypy reports 0 errors), `make test` green (152 passed, 2 skipped, same as before P3.5).

If mypy reports any remaining error: read the error, identify the file, dispatch a fix subagent for it. Do NOT proceed to PR with red mypy.

- [ ] **Step 2: Final Opus code-quality review**

Dispatch one Opus review against the full branch diff. Prompt focus: "purely mechanical typing — verify no test function body was changed; verify every annotation matches its fixture's actual yield type (no `Any` where a concrete type is available); flag any test where the annotation reveals a pre-existing bug (e.g., a fixture that yields the wrong shape)."

Resolve any blocking findings. Non-blocking nits land in a follow-up.

- [ ] **Step 3: PR body + open + merge**

Write `docs/superpowers/PR-type-the-tests-body.md` (short — this is mechanical):

```markdown
# Type the tests

Drains pre-existing test-file typecheck debt so `make check` goes green.

## Summary

10 test files annotated for `mypy --strict`. Zero behavior changes — only `def` signatures gained return + arg types, plus three `tuple[...]` generics and one `dict[K, V]` annotation in `test_permission_engine_rls.py`. Full backend suite still 152 passed, 2 documented skips, 0 failed.

Discovered during P3.5 (#8) as pre-existing P3a/P3b-era debt; HANDOFF item "P3.5 surfaced follow-ups" called this out.

## Verification

- `uv run mypy apps/api` — 0 errors (was 49).
- `make test` — 152 passed (unchanged).
- `make check` — green (was red on typecheck).

## Files

10 files under `apps/api/tests/` modified. No source code touched.
```

Then:
```bash
gh pr create --base main --head type-the-tests --title "test(api): type all backend tests for mypy --strict" --body-file docs/superpowers/PR-type-the-tests-body.md
gh pr checks <n>  # CI will be red on missing secrets but the local gate was the contract
gh pr merge <n> --merge
git checkout main && git pull --ff-only
git push origin --delete type-the-tests
git branch -D type-the-tests
```

---

## Self-review checklist

1. **Coverage:** every file in the 10-file inventory has a task. ✅
2. **No placeholders:** every step has a concrete command or transformation example. ✅
3. **Type consistency:** the vocabulary table is the single source of truth; tasks reference it. ✅
4. **Scope discipline:** no source-file edits; no fixture refactoring; no test-body changes. ✅
5. **HANDOFF respect:** unblocks `make check` on `main` so P4 starts from a clean baseline. ✅
6. **User memory respect:** no Co-Authored-By; `STARTUP_RECONCILE_TOLERANT=false` prefix on every test run; @example.com untouched. ✅
