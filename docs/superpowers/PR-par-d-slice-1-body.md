## PAR-D slice 1 — backend perf + correctness

First of two PAR-D slices (the audit's Phase D, backend services + perf). This
slice is the low-risk, no-new-infra half: query perf, signed cursors, and a set
of correctness/polish fixes. Slice 2 (invite outbox + worker, transaction-
ownership, Valkey perm cache, advisory locks) follows.

Spec: `docs/superpowers/specs/2026-05-26-production-audit-remediation-design.md` section 7.

### Findings closed

| ID | Fix |
|---|---|
| **H6** | `/me` no longer runs one perm query per tenant. New `effective_workspace_perms_batch` does a single `array_agg ... GROUP BY workspace_id` over `ANY(:wids)`; the route maps results back per tenant. |
| **H11** | Migration `0011` adds three `rbac_audit_log` indexes — `(scope, workspace_id, created_at DESC)`, `(target_type, target_id)`, `(actor_auth_user_id, created_at DESC)` — built `CONCURRENTLY` via Alembic `autocommit_block` (the production index-add pattern). |
| **M2** | `invite_acceptance` no longer maps *every* `IntegrityError` to `AlreadyProvisioned`; it inspects `e.orig.constraint_name` and only treats the expected uniqueness conflicts as already-provisioned, re-raising anything else. |
| **M4** | All 11 cursor-paginated queries (8 raw-SQL + 3 ORM) switched from the disjunctive `a<:ts OR (a=:ts AND id<:rid)` form to the row-comparator `(a, id) < (:ts, :rid)` so Postgres can range-scan a composite index. |
| **M5** | Pagination cursors are now HMAC-SHA256 signed (`CURSOR_HMAC_KEY`) and verified in constant time on decode; decode also rejects a future timestamp. Forged/tampered cursors → 400. |
| **M8** | `tenant_invites` membership lookup is now case-insensitive (`lower(u.email) = lower(:email)`). |
| **M18** | The unbounded-list invariant test now also flags bare `list[...]` / `Sequence[...]` GET returns (not just the `*Page` suffix), with an explicit bounded-list allowlist. |
| **L3** | `update_platform_role` / `update_workspace_role` use a single `COALESCE` UPDATE for name+description (one `updated_at`). |
| **L5** | Inviting an `editor` platform role is rejected (`400 unsupported_invite_role`) instead of silently provisioning a roleless platform user on accept. |
| **L6** | `revoke_platform_invite`'s best-effort Supabase delete no longer `suppress(Exception)`s — failures log a structured WARN (`supabase_invite_user_delete_failed`) so auth.users orphans are visible. |
| **L7** | `get_settings` name shadows removed: `services.platform_settings.get_settings` → `get_platform_settings`; `routes.workspace_settings.get_settings` → `get_workspace_settings_route`. `core.config.get_settings` keeps the canonical name. |

### New artifacts

- `apps/api/migrations/versions/0011_audit_log_indexes.py`
- `tests/core/test_cursor_signature.py`, `tests/integration/test_me_batched_perms.py`, `tests/integration/test_audit_log_indexes_used.py` (EXPLAIN with `enable_seqscan=off` to prove index usability regardless of table size)
- New required env var `CURSOR_HMAC_KEY` (added to `.env.example`).

### Deferred to slice 2

Invite outbox + worker (H5), caller-owns-transaction convention (M1), Valkey
perm cache (M16), onboarding/reconcile advisory locks (M6/M9), invite-revoke
`SELECT … FOR UPDATE` (L4).

### Verification

- `make` lint + `mypy --strict` + ruff format: green.
- Targeted backend suite across every touched service/route + the 3 new test files: green (run against the managed dev project).
- Migration `0011` applied + downgrade authored.
