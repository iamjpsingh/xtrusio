## PAR-D slice 2b-i — caller-owns-transaction + invite-revoke race-safety

The mechanical, no-email-semantics-change half of PAR-D's invite/tx work.
The heavier invite-outbox + worker rewrite (H5) and the two invite-create
services' transaction move land in **slice 2b-ii**.

Spec: `docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` section 7.

### Findings closed

| ID | Fix |
|---|---|
| **M1 (partial)** | Caller-owns-transaction convention for the three non-Supabase services: `onboarding.create_tenant_with_owner`, `platform_settings.update_settings`, and `invite_acceptance._accept_platform`/`_accept_tenant` drop their `db.commit()`. The routes now commit on success and roll back on every typed error. `invite_acceptance` switches `commit`→`flush` so the M2 `IntegrityError`→`AlreadyProvisioned` mapping still fires in the service; the route owns the commit. (`platform_invites` + `tenant_invites` create still self-commit — they move with the H5 outbox in 2b-ii.) |
| **L4** | `revoke_platform_invite` / `revoke_tenant_invite` lock the invite row with `SELECT … FOR UPDATE`, so two concurrent revokes serialise — the loser re-reads `revoked_at` set and no-ops idempotently instead of both racing past the early-return (and double-calling Supabase delete). |

### Notes

- Routes build their response from the live (pre-commit) ORM attributes, then
  commit, to avoid expire-on-commit reloads.
- Service-level tests that call these services directly and verify in a fresh
  session now commit explicitly (the services no longer do). `test_onboarding_race`
  (added in 2a, when the service still self-committed) updated likewise.

### Deferred to slice 2b-ii

Invite-email outbox table + worker (H5), `create_platform_invite` /
`create_tenant_invite` transaction move (M1 remainder) — the Supabase calls move
out of the request path into the worker.

### Verification

- ruff + ruff format + `mypy --strict` green.
- Targeted backend suite (onboarding, platform-settings, invite-accept, both
  invite revokes, signup→tenant + invite full-flow integration) green against the
  managed dev project.
