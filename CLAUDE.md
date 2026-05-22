# CLAUDE.md — Xtrusio project rules for AI assistants

These rules override default agent behaviour for this repository. Apply them on every task.

## Model selection (non-negotiable)

- **Opus 4.7 with MAX effort** for every implementer subagent, every reviewer subagent (spec compliance, code quality, security), every plan/spec/migration writer, every fix subagent. The controller itself runs on Opus max. "High" is NOT acceptable — the user has explicitly locked it at max (`/model` set to "Opus 4.7 (1M context) with max effort").
- **Sonnet** ONLY for the `Explore` agent or pure read-only file-content lookups ("where is X defined", surface-mapping). If the subagent forms an opinion about code, that is NOT reading — use Opus.
- **Haiku is forbidden.** Do not use Haiku for "small" tasks, "quick" reviews, or to save tokens. The user pays for Opus and expects it everywhere except pure exploration.

## Execution cadence (slice-level batching, not per-task)

The default "subagent-driven-development" flow of `implementer → spec reviewer → code-quality reviewer` PER TASK is the WRONG default here. Use this instead:

1. **One implementer dispatch per chunk**, not per task. A "chunk" = a logically cohesive set of files (e.g. "all api-types mirror files", "all shared UI blocks", "both per-scope page components"). Aim for ≤3 implementer dispatches per slice.
2. The implementer writes ALL code AND ALL tests for the chunk in one go. TDD per file inside the subagent is fine; what's forbidden is the controller spawning a separate subagent per file.
3. **One code-quality review at the end of the chunk** (or end-of-slice if the slice is one chunk). Reviewer reads the entire chunk's diff at once. Not per-file, not per-commit.
4. **One test gate at the end of the slice** — `make test-clean && make check` run by the controller directly (NOT by a subagent). Includes `ruff format --check` (not just `ruff check`) + `mypy --strict` + `turbo typecheck` + vitest. Iterate to green.
5. Skip the spec-reviewer stage for trivial work (verbatim file writes, type mirrors, route boilerplate). Use it ONLY when the implementer made a judgement call worth a sanity check (invented a fixture, restructured, etc.).
6. Then PR + merge.

**Exception:** for migrations, RLS policies, and auth/permission gates only, run ONE targeted mid-build sanity check (single focused command by the controller, not the full suite).

**Why:** The user already burned 8+ hours on a previous phase running full DB tests per file. They explicitly said: "you write 10 line for 10 min testing that 10 line 10 hours i don't want it make sure don't waste my time." Don't waste their time.

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

- Don't dispatch a subagent for every file — batch into chunks.
- Don't dispatch a "spec reviewer" for trivial verbatim file writes.
- Don't use Haiku. Ever.
- Don't use Sonnet for anything that exercises code judgement.
- Don't run the full backend test suite from a subagent — the controller runs it once at end-of-slice.
- Don't justify a model downgrade with "to save tokens" or "the task is small". Both are explicitly disallowed.
