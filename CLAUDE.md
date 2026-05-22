# CLAUDE.md — Xtrusio project rules for AI assistants

These rules override default agent behaviour for this repository. Apply them on every task.

## Model selection (non-negotiable)

- **Opus 4.7 with MAX effort** for every implementer subagent, every reviewer subagent (spec compliance, code quality, security), every plan/spec/migration writer, every fix subagent. The controller itself runs on Opus max. "High" is NOT acceptable — the user has explicitly locked it at max (`/model` set to "Opus 4.7 (1M context) with max effort").
- **Sonnet** ONLY for the `Explore` agent or pure read-only file-content lookups ("where is X defined", surface-mapping). If the subagent forms an opinion about code, that is NOT reading — use Opus.
- **Haiku is forbidden.** Do not use Haiku for "small" tasks, "quick" reviews, or to save tokens. The user pays for Opus and expects it everywhere except pure exploration.

## Execution cadence (radically lean — refined 2026-05-23)

The default "subagent-driven-development" flow of `implementer → spec reviewer → code-quality reviewer` PER TASK is the WRONG default here. Use this instead:

### Inside the implementer subagent (per chunk)

1. **Write all the code AND all the tests for the chunk in one go**, file by file, with NO intermediate test runs.
2. **Drop per-file commits** — make ONE commit at the end of the chunk with all files staged together. Commit message names the chunk (e.g. "feat(web): Slice 1 UI building blocks — checkbox, Forbidden, PermissionPicker, RoleFormDialog, RolesTable, DeleteRoleDialog").
3. **Drop per-file test runs** — do NOT run vitest after each component. Run typecheck + the full chunk's tests ONCE at the very end of the chunk. If they pass, commit. If they fail, fix, then commit.
4. Skip TDD-style "write failing test first → red → implementation → green" inside the subagent. Just write the component AND its tests together — the controller's end-of-slice gate is the actual quality net, not micro-red-green loops.

### Controller orchestration

1. **One implementer dispatch per chunk** — a chunk is a logically cohesive set of files (e.g. "all api-types mirror files", "all 6 UI building blocks", "both per-scope page components"). Aim for ≤3 implementer dispatches per slice.
2. **Skip the spec-reviewer stage** for almost everything. Use it ONLY when the implementer materially adapted the spec (invented a fixture, restructured something) — and even then, fold it into the end-of-slice code-quality review.
3. **One code-quality review at the end of the slice** (NOT per chunk). Reviewer reads the entire slice's diff.
4. **One test gate at the end of the slice** — `make test-clean && make check` run by the controller directly (NOT by a subagent). Includes `ruff format --check` (not just `ruff check`) + `mypy --strict` + `turbo typecheck` + vitest. Iterate to green.
5. Then PR + merge.

**Exception (still applies):** for migrations, RLS policies, and auth/permission gates only, run ONE targeted mid-build sanity check (single focused command by the controller, not the full suite).

### Why

The user explicitly said (2026-05-23 reinforcement after I dispatched a per-file-commit + per-file-test-run chunk):

> "we are taking too much time for just simple task. drop the per-file commits, drop the per-file test runs inside the subagent, let the subagent write the whole chunk in one go and run typecheck/tests ONCE at the very end."

Earlier (2026-05-19): "you write 10 line for 10 min testing that 10 line 10 hours i don't want it make sure don't waste my time."

Don't waste their time. The slice-level gate (controller-run `make check` + Opus reviewer) is the actual quality discipline — everything before it should move as fast as possible.

## Code-quality bar (non-negotiable)

- TypeScript only on the frontend.
- No hardcoded colors — use design tokens / CSS variables.
- No demo data, no fake users, no example payloads checked into source.
- 500 LoC ceiling per file. If you're approaching it, split with intent, don't refactor randomly.
- `mypy --strict` on the Python backend.
- RLS is defense-in-depth, not the sole authorization layer — backend permission checks via `require_permission()` are the primary gate; RLS catches what's missed.
- Clean, reusable, scalable code by DESIGN. Quality is not something a per-file test discovers — it's a discipline applied while writing.

## Branch + PR convention

- Each P-phase slice gets its own feature branch (`rbac-p6c-slice-1-roles-crud`, etc.) and its own PR.
- PR body lives at `docs/superpowers/PR-rbac-<phase>-body.md`, opened via `gh pr create`, merged via `gh pr merge --squash`.
- After merge, update `docs/superpowers/HANDOFF.md` in a separate commit on `main`.

## Docs that drive everything

- **`docs/superpowers/HANDOFF.md`** — single source of truth for "where we are". Update post-merge.
- **`docs/superpowers/specs/YYYY-MM-DD-*.md`** — design decisions per phase.
- **`docs/superpowers/plans/YYYY-MM-DD-*.md`** — implementation plans per phase / slice.

## What NOT to do

- Don't dispatch a subagent for every file — batch into chunks (≤3 per slice).
- Don't dispatch a "spec reviewer" — fold spec-compliance into the end-of-slice code-quality review.
- Don't make per-file commits inside a chunk — ONE commit per chunk with all files staged together.
- Don't run per-file vitest / pytest inside the chunk subagent — ONE typecheck + test run at end of chunk.
- Don't use TDD-style red-green loops inside the subagent — write code + tests together, run once at end.
- Don't use Haiku. Ever.
- Don't use Sonnet for anything that exercises code judgement.
- Don't run the full backend test suite from a subagent — the controller runs it once at end-of-slice.
- Don't justify a model downgrade with "to save tokens" or "the task is small". Both are explicitly disallowed.
- Don't waste the user's time with ceremony. The slice-level gate is the actual quality net.
