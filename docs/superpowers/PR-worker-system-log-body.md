# feat(system) — worker/system job-run log: `job_runs` table + outbox instrumentation + operator "System jobs" page

Item #2 of the activity/observability work (plan: `docs/superpowers/plans/2026-06-06-activity-feed.md`, Slice C). Gives operators a view of background-worker activity — "what the worker did, how, what response, on which time" — starting with the invite-email outbox and ready for the future AI-scan / scheduling / queue jobs.

## Backend
- **Migration `0014_job_runs`** — new `job_runs` table (`id bigint`, `job_name`, `status`, `started_at`, `finished_at`, `duration_ms`, `items_processed/succeeded/failed`, `detail jsonb`, `created_at`). Backend-only: **RLS enabled, no policy, no `authenticated` grant** (worker + read endpoint use the owner connection; mirrors `invite_email_outbox`). Two indexes: `(started_at DESC, id DESC)` for the newest-first list, `(job_name, started_at DESC)` for per-job filtering. Up+down migration verified live against managed Supabase.
- **`services/job_runs.py`** — `record_job_run(db, …)` (caller owns tx) + `list_job_runs(db, cursor, limit, job_name)`, cursor-paginated newest-first (HMAC-free base64 `{started_at,id}` token, mirroring the audit-log cursor since `id` is bigint).
- **Outbox instrumentation** — `process_due_batch` now records one `job_runs` row per batch **that actually did work** (idle polls are NOT logged, so the table reflects real activity, not the every-N-second heartbeat). Status is `success` / `partial` / `error` from the succeeded/failed split; failures' error strings go in `detail.errors`. The recording is **best-effort** — a logging failure can never break the email send it describes. `process_due_batch`'s return type is unchanged (`int`), so existing callers/tests are untouched.
- **`GET /api/platform/job-runs`** (`routes/platform_job_runs.py`) — gated by **`platform.audit.read`** (same operator audience as the audit log; avoids a permission-catalog reconcile dependency — a dedicated `platform.system.read` could split it later), cursor-paginated, optional `?job_name=` filter, sanitized `400 invalid cursor`.
- api-types regenerated (idempotent) + `JobRunOut`/`JobRunsPage` re-exported (with the same `detail` `Record<string,unknown>` reconciliation the audit-log mirror uses).

## Frontend
- **`PlatformSystemJobsPage`** at `/platform/system` (gated `platform.audit.read`) — table of Started / Job / Status badge / Duration / item counts; `useInfiniteQuery` + Load-more; row → **`JobRunDetailDrawer`** (timing, counts, and the recorded error list). `job-run-format.ts` helpers (`formatDuration`, `jobStatusVariant`).
- **Nav**: new "System jobs" entry under platform (gated `platform.audit.read`); route-tree regenerated.

## Tests
Backend: `tests/services/test_job_runs.py` (record + newest-first list + cursor pagination + job_name filter + partial-status detail + cursor roundtrip/invalid) and `tests/routes/test_platform_job_runs.py` (401 unauth, 403 unprivileged, 200 shape + job_name filter, 400 invalid cursor) — **9/9 green** vs managed Supabase; rows self-cleaned by unique `job_name`. Frontend: `job-run-format.test.ts` + `platform-system-jobs-page.test.tsx` (forbidden / renders runs / opens drawer with errors).

## Gate
`mypy --strict` clean (220 files); ruff check + format clean; migration up+down verified live; backend targeted 9/9; web `turbo lint typecheck` green + **full vitest 324/324**; api-types regen idempotent; invite-outbox integration regression re-run after the `process_due_batch` change. No signup/auth path touched.

## Follow-ups
GoTrue login/logout → the audit feed's reserved `auth` category remains a flagged operator-decision follow-up (mechanism: Auth Hook / DB webhook / mirror). Future jobs (AI scan, scheduled tasks, queue) record to `job_runs` by calling `record_job_run` — the page + endpoint already generalize over `job_name`.
