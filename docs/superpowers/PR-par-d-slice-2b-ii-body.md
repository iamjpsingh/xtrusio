## PAR-D slice 2b-ii — invite-email outbox + invite-create caller-owns-tx

The last of PAR-D. Closes **H5** (Supabase call inside an open DB transaction)
and the **M1 remainder** (the two invite-create services).

Spec: `docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` section 7.

### ⚠️ Behavior change (intended)

Invite emails are now sent **asynchronously**. `POST` invite endpoints insert
the invite row + an outbox row in one transaction, commit, and return `201`
immediately — they no longer make a Supabase call on the request path, so they
**no longer return `502 email_provider_unavailable`** synchronously. A background
worker sends the email and retries with backoff. The invite's `supabase_user_id`
(platform invites) becomes eventually-consistent (written by the worker); this
is benign since acceptance can't precede the email arriving.

### Findings closed

| ID | Fix |
|---|---|
| **H5** | New `invite_email_outbox` table (migration `0012`) + in-process worker (`core/outbox_worker.py`, lifespan `asyncio` task, `OUTBOX_POLL_SEC` poll). `services/invite_outbox.py` provides `enqueue_invite_email` (request path, same tx as the invite row) and `process_due_batch` (worker): it claims due rows under `FOR UPDATE SKIP LOCKED`, bumps `next_attempt_at` by a lease and **commits before** doing the Supabase calls — so the Supabase HTTP call holds **no** DB transaction (can't trip `idle_in_transaction_session_timeout`) — then records success (writing `supabase_user_id` back to platform invites) or backs off on failure. |
| **M1 (remainder)** | `create_platform_invite` / `create_tenant_invite` drop their `db.commit()` and inline Supabase calls; the routes commit on success / roll back on typed errors and build the response from the live pre-commit ORM row. All five PAR-D services are now caller-owns-tx. |

### New artifacts

- Migration `0012_invite_email_outbox.py` (RLS-on, backend-only table).
- `services/invite_outbox.py`, `core/outbox_worker.py`.
- New required env var `OUTBOX_POLL_SEC` (in `.env.example`).
- `tests/integration/test_invite_outbox.py` (send→succeed + writeback, failure→backoff). Reworked invite-create happy-path tests to assert an outbox row is enqueued (Supabase untouched on the request path). `_cleanup.py` sweeps outbox rows by payload email.

### Cleanup

- The dead `EmailProviderUnavailableError` (no longer raised by the invite-create services) is removed from both invite services + their route handlers. `signup` keeps its own copy — signup still calls Supabase synchronously and is unaffected.

### Verification

- ruff + ruff format + `mypy --strict` green.
- Targeted backend suite (outbox worker, both invite-create + revoke, invite full-flow, invite-accept) green against the managed dev project. The worker is not started in tests (ASGITransport runs no lifespan); `test_invite_outbox` drives `process_due_batch` directly with a mocked Supabase client.
