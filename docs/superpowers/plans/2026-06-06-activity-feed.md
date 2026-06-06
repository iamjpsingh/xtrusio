# Plan — Unified Activity = Audit feed (2026-06-06)

Closes the audit's "see every SaaS-level action in one normalized feed with filters"
requirement. The existing `rbac_audit_log` + the two cursor-paginated viewers
(`GET /api/platform/audit-log`, `GET /api/workspaces/{wid}/audit-log`) ARE the feed;
today they only cover RBAC role/grant/settings mutations (~25% of mutations) and the
UI renders raw `action` strings + `JSON.stringify(before/after)`. This plan (1) backfills
audit coverage to the rest of the mutation surface, (2) adds a human-readable event
catalog (label + category) + a category filter, and (3) normalizes the frontend table
+ drawer.

**No migration.** `rbac_audit_log` already accepts arbitrary `action`/`target_type`/
`target_id` strings (`String(64/32/64)`), `actor_auth_user_id` is nullable, `before`/`after`
are `jsonb`. A dedicated `source` column is deliberately NOT added — `category` carries the
source distinction (reserved `auth`/`system` categories), so GoTrue/worker ingestion can
land later with zero schema churn.

---

## Slice A — backend (THIS dispatch)

### A1. `role_name` in grant/revoke payloads
The 4 grant/revoke services currently put `role_key` (machine key) in the audit
`before`/`after`. Add `role_name` (the human display name) alongside it — select `r.name`
where each loads the role, add `"role_name": <name>` to the payload. Files:
`services/platform_role_grants.py` (grant `after`, revoke `before`),
`services/workspace_role_grants.py` (grant `after`, revoke `before`). Keep `role_key`.

### A2. Audit coverage backfill
Add a `write_audit_event(...)` call (same tx — it never commits) to each mutation below.
**tx-ownership matters:** `revoke_platform_invite` and `revoke_tenant_invite` SELF-COMMIT
(`await db.commit()`) — the audit write MUST come BEFORE that commit. All others are
caller-owns-tx (flush, route commits) — write before `return`.

| service / fn | action | scope | workspace_id | target_type / target_id | actor | payload |
|---|---|---|---|---|---|---|
| `platform_invites.create_platform_invite` | `platform_invite.create` | platform | — | `invite` / invite.id | `invited_by` | after: `{email, role}` |
| `platform_invites.revoke_platform_invite` *(pre-commit)* | `platform_invite.revoke` | platform | — | `invite` / invite.id | — (no actor arg → pass the invite's `invited_by`? NO — add no actor; leave `actor_id` = the route's caller) | before: `{email, role}` |
| `tenant_invites.create_tenant_invite` | `tenant_invite.create` | workspace | `tenant_id` | `invite` / invite.id | `inviter_id` | after: `{email, role}` |
| `tenant_invites.revoke_tenant_invite` *(pre-commit)* | `tenant_invite.revoke` | workspace | `tenant_id` | `invite` / invite.id | `requester_id` | before: `{email, role}` |
| `invite_acceptance._accept_platform` | `platform_invite.accept` | platform | — | `invite` / invite_id | `user_id` | after: `{email, role}` |
| `invite_acceptance._accept_tenant` | `tenant_invite.accept` | workspace | `invite.tenant_id` | `invite` / invite_id | `user_id` | after: `{email, role}` |
| `onboarding.create_tenant_with_owner` | `tenant.create` | workspace | new tenant.id | `tenant` / tenant.id | `user_id` | after: `{slug, name}` |
| `platform_user_provision.create_platform_user` | `platform_user.create` | platform | — | `platform_user` / new user id | `actor_id` | after: `{email, role}` |
| `platform_settings.update_settings` | `platform.settings.updated` | platform | — | `platform_settings` / `'1'` | `updated_by` | before/after: `{signups_enabled}` |

Notes:
- `revoke_platform_invite(db, *, invite_id)` has **no actor param**. Add `actor_id: UUID`
  as a required kw-arg and thread it from the route (the route already has the caller).
  Do the same for any other fn missing the actor. Keep signatures minimal + typed.
- For revokes, capture the `before` payload from the loaded invite row BEFORE setting
  `revoked_at` / committing.
- Email values in payloads are already in the system (invite rows store them); no new PII
  exposure beyond what the audit log already records (actor_email is LEFT-JOINed today).
- Roles in payloads: store the enum `.value` string (e.g. `"admin"`), not the object.

### A3. Event catalog (`core/audit_catalog.py`, new)
A single source of truth mapping each `action` → `(label, category)`. Pure data + two
helpers. No I/O. Categories (declare ALL, including the two reserved-empty future ones so
the filter dropdown is forward-ready):

- `roles` — role create/update/delete (platform + workspace)
- `grants` — role grant/revoke (platform + workspace)
- `invites` — invite create/revoke/accept (platform + tenant)
- `members` — (reserved; member add/remove if added later)
- `workspaces` — `tenant.create`
- `users` — `platform_user.create`
- `settings` — platform + workspace settings updated
- `auth` — RESERVED (GoTrue login/logout/password — empty for now)
- `system` — RESERVED (worker/job runs — empty for now)

Map every action string A2 introduces + the existing ones (`platform_role.create/update/
delete`, `workspace_role.*`, `*_role.grant/revoke`, `workspace.settings.updated`). Labels are
imperative/human: "Granted platform role", "Invited workspace member", "Created workspace",
"Updated platform settings", etc.

Helpers:
```python
def describe_action(action: str) -> tuple[str, str]:
    """Return (label, category). Unknown action → (title-cased fallback, "other")."""
def categories() -> list[tuple[str, str]]:
    """[(key, label), ...] for the filter dropdown, stable order."""
```
`"other"` is the catch-all category for any legacy/unknown action — include it in
`categories()` so old rows remain filterable.

### A4. Enrich `AuditEventOut` (computed fields)
Add two Pydantic `@computed_field` properties derived from `self.action` via the catalog —
NO service change, they serialize automatically:
```python
@computed_field
@property
def action_label(self) -> str: return describe_action(self.action)[0]
@computed_field
@property
def category(self) -> str: return describe_action(self.action)[1]
```
(There is no existing `category` field on the model — confirm before adding; if a name
clash, call them `action_label`/`action_category`.)

### A5. Catalog endpoint
`GET /api/audit/catalog` → `{ categories: [{key,label}], actions: [{action,label,category}] }`,
gated on `get_current_user` ONLY (non-secret metadata, mirrors `routes/permissions.py`).
New `routes/audit_catalog.py` + `schemas/audit_catalog.py`; register in `main.py`.

### A6. Category filter on both list endpoints
Add `category: str | None = Query(None)` to `GET /api/platform/audit-log` and
`GET /api/workspaces/{wid}/audit-log`. In the service, resolve `category` → the set of
action strings in that category (from the catalog) and add `AND action = ANY(:actions)` to
the SELECT, threaded INTO the existing cursor predicate (filter ANDs with the cursor row
comparator — do not break pagination). Unknown/`None` category → no filter. An empty-action
category (e.g. `auth`) → `action = ANY('{}')` → zero rows (correct).

### A7. Regenerate api-types
The new endpoint, the `category` query param, and the two computed fields change the
OpenAPI schema. Run the api-types codegen and COMMIT the regenerated
`packages/api-types/generated/openapi.d.ts` (+ any re-export) so the `api-types-drift` gate
passes. Re-export `AuditCatalog` types.

### A8. Tests (backend)
- One test per backfilled mutation asserting the audit row lands (action, scope,
  workspace_id, actor, payload keys incl. `role_name` for grants). Reuse existing
  service/route test files where they exist.
- `describe_action` unit test incl. unknown-action fallback.
- Catalog endpoint: 200 shape + authed-only.
- Filter: a row of category X is returned for `?category=X` and excluded for `?category=Y`;
  cursor pagination still works WITH a filter applied.

### A8 gate (controller runs)
`make lint` + `make typecheck` (`mypy --strict`) + `ruff format --check` + targeted backend
tests for every touched service/route + the new catalog/filter tests + api-types codegen
idempotent (drift gate clean). Non-enumeration unaffected (no signup/auth path touched).

---

## Slice B — frontend (NEXT dispatch, after A merges)

Consumes A's API. In `apps/web`:
- `AuditTable`: columns **Time** (formatted via `lib/format.ts`), **Actor** (email, fallback
  to short id), **Action** (render `action_label`, with the raw action as a subtle mono
  subtitle or tooltip), **Role** (pull `role_name`/`role_key` from `after`/`before` when the
  category is `grants`/`roles`; em-dash otherwise), **Target**, **Category** badge.
- **Category filter**: fetch `GET /api/audit/catalog`, render a dropdown/segmented control;
  selecting a category sets the `?category=` query param and refetches (works with the
  `useInfiniteQuery` already on these pages — reset on filter change).
- **`AuditDetailDrawer`**: replace raw `JSON.stringify` with a structured before→after
  diff (key/value rows, changed keys highlighted), human field labels, monospace only for
  ids/JSON leaves. Graceful for null before/after (create/delete).
- Tests: table renders label + role column; filter drives the query param; drawer renders a
  before/after diff and handles null sides.
- Gate: `turbo run lint typecheck test` green.

---

## Slice C — worker/system log (LATER, item #2)
Capture response + duration in `invite_email_outbox` processing, generalize a `job_runs`
record (migration), feed the `system` category, operator "System/Jobs" page. Separate slice;
GoTrue login/logout (`auth` category) stays a flagged operator-decision follow-up.
