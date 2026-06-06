# feat(web) — Activity feed UI: normalized table + category filter + structured before→after drawer

Slice B of the unified **Activity = Audit feed** (plan: `docs/superpowers/plans/2026-06-06-activity-feed.md`), consuming the backend from PR #74. Turns the raw audit viewer (machine `action` strings + `JSON.stringify(before/after)`) into a readable activity feed.

## What changed (all `apps/web`)
- **`AuditTable`** — columns now **Time** (deterministic `lib/format.formatDateTime`), **Actor** (email, em-dash fallback), **Action** (human `action_label` as primary, raw machine `action` as a mono subtitle), **Role** (extracted from the snapshot — prefers `role_name`/`name` over `role_key`/`key`/`role`, em-dash when none), **Category** badge, **Target**.
- **`AuditCategoryFilter`** (new, shared) — fetches `GET /api/audit/catalog` (cached for the session), renders a Select; "All categories" maps to no filter. Both pages thread the selected category into the query **key**, so switching it transparently resets the `useInfiniteQuery` accumulator and re-fetches from `cursor=null` with `?category=`.
- **`AuditDetailDrawer`** — replaces raw `JSON.stringify` with a structured **before→after diff table**: union of snapshot keys (humanized labels), changed rows highlighted (`data-changed`), empty sides rendered as an explicit "empty" marker (clean for create/delete), arrays/objects shown as compact JSON leaves. Header shows the action label + category badge.
- **`audit-format.ts`** (new) — pure helpers `roleLabel`, `diffSnapshots`, `humanizeField` (unit-tested).
- Pages now keep the filter visible across loading/error/empty/data states; empty-state copy adapts when a filter is active.

## Tests
New: `audit-format.test.ts` (role-label priority, create/update/delete diffs, JSON-leaf rendering), `audit-category-filter.test.tsx` (renders + wires the catalog query). Updated: `audit-table` / `audit-detail-drawer` component tests for the new columns + diff view; both page tests for the new fetch signature (`(…, category)`) + structured drawer; `query-keys.test.ts` for the category-suffixed audit tuples; MSW `handlers.ts` gains an `/api/audit/catalog` stub.

## Gate
`turbo run lint typecheck` green (0 lint errors in touched files; 6/6 typecheck); **full web vitest 316/316**. No backend/`.env`/migration changes.

## Follow-ups
Slice C — worker/system log → `system` category. GoTrue login/logout → `auth` category stays a flagged operator-decision follow-up. The filter already lists the reserved `auth`/`system` categories (empty until those ingestion paths land).
