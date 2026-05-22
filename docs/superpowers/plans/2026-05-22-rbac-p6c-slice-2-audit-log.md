# RBAC P6c — Slice 2: Audit log viewers (Platform + Workspace)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the platform-scope and per-workspace audit-log viewer UIs consuming `GET /api/platform/audit-log` and `GET /api/workspaces/{wid}/audit-log` already on `main`, plus extend `AuditEventOut` to carry `actor_email` (a LEFT JOIN onto `auth.users`) so each row renders something human-readable. End-of-slice: a super_admin viewing `/platform/audit-log` sees every platform RBAC mutation in reverse-chrono order with a "Load more" button and a side-drawer for inspecting `before` / `after` JSON; a workspace owner sees the same scoped to their workspace at `/workspace/<wid>/audit-log`.

**Architecture:** Backend change is two ~5-line LEFT JOIN additions in the existing audit-log services + one field on the response schema; no migration. Frontend adds three shared blocks (`<AuditTable>`, `<AuditDetailDrawer>`, `<LoadMoreButton>`) plus two per-scope page components (`<PlatformAuditLogPage>`, `<WorkspaceAuditLogPage>`) that each own their own accumulating-pages `useState` + cursor-driven `useQuery` (deliberately not `useInfiniteQuery` — the project hasn't adopted it; the accumulator pattern matches existing pagination in the codebase). Reuses `qk` (added in Slice 1), `<Forbidden />` (added in Slice 1), and `lib/error-messages.ts` (also extended in Slice 1).

**Tech Stack:** FastAPI 0.117, SQLAlchemy 2 async, Pydantic v2, mypy --strict, pytest-asyncio (loop_scope="session"). Frontend: TypeScript (strict), React 19, TanStack Router (file-based), TanStack Query v5, Vitest 2, React Testing Library 16, Tailwind 4, shadcn/Radix primitives.

**Depends on:** Slice 1 (Roles CRUD) merged — Slice 2 imports `qk`, `<Forbidden />`, the new error-messages mappings, and the api-types re-export setup.

---

## File Structure

### Create

| Path | Purpose |
|---|---|
| `packages/api-types/src/audit-log.ts` | `AuditEventOut` + `AuditEventsPage` TS mirrors (with `actor_email`). |
| `apps/web/src/components/audit/audit-table.tsx` | Dense `[time, actor email, action, target]` table — click-row callback. |
| `apps/web/src/components/audit/audit-table.test.tsx` | Renders 4 columns, "—" for null actor_email, click fires onSelect, truncated target_id + tooltip. |
| `apps/web/src/components/audit/audit-detail-drawer.tsx` | shadcn `Sheet` showing pretty-printed before/after JSON. |
| `apps/web/src/components/audit/audit-detail-drawer.test.tsx` | Renders before/after, handles before-null (create) and after-null (delete), close fires. |
| `apps/web/src/components/audit/load-more-button.tsx` | Pending state, hidden when no next_cursor. |
| `apps/web/src/components/audit/load-more-button.test.tsx` | Renders, pending → "Loading…" + disabled, hidden when no next_cursor. |
| `apps/web/src/components/platform-audit-log-page.tsx` | Per-scope page composition. |
| `apps/web/src/components/platform-audit-log-page.test.tsx` | Gate, accumulating pages on load-more, row click opens drawer. |
| `apps/web/src/components/workspace-audit-log-page.tsx` | Per-scope page composition. |
| `apps/web/src/components/workspace-audit-log-page.test.tsx` | Gate, accumulating pages on load-more, row click opens drawer. |
| `apps/web/src/routes/_app.platform.audit-log.tsx` | 3-line file-route. |

### Modify

| Path | Lines | Change |
|---|---|---|
| `apps/api/src/xtrusio_api/schemas/audit_log.py` | 18-29 (the `AuditEventOut` body) | Add `actor_email: str \| None`. |
| `apps/api/src/xtrusio_api/services/platform_audit_log.py` | 53-69 (the `base` + `sql` strings inside `list_platform_audit_events`) | Replace the inline `SELECT id, actor_auth_user_id, ...` with one that `LEFT JOIN auth.users u ON u.id = r.actor_auth_user_id` and projects `u.email AS actor_email`. |
| `apps/api/src/xtrusio_api/services/workspace_audit_log.py` | 32-50 (mirror) | Same LEFT JOIN + actor_email projection. |
| `apps/api/tests/services/test_platform_audit_log.py` | append | New tests: actor_email populated when actor exists; None when actor_auth_user_id null; None when auth user hard-deleted. |
| `apps/api/tests/services/test_workspace_audit_log.py` | append | Same three assertions, workspace-scope. |
| `packages/api-types/src/index.ts` | end (already has `export * from "./role";` from Slice 1) | Add `export * from "./audit-log";`. |
| `apps/web/src/lib/api.ts` | end of file (after Slice-1 additions) | Add `fetchPlatformAuditLog(cursor?)` and `fetchWorkspaceAuditLog(workspaceId, cursor?)`. |
| `apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx` | 1-24 (full file) | Replace placeholder with file-route mounting `<WorkspaceAuditLogPage workspaceId={...} />`. |

### Notes

- The `LEFT JOIN auth.users` projection is read-only, no RLS bypass — the audit-log endpoint already runs as the FastAPI service role (the `require_permission` gate is what enforces who-can-read).
- `auth.users.id` is PK-indexed; the join is O(1) per audit row, no new index required.
- "Hard-deleted user" means `auth.users.id` no longer matches `actor_auth_user_id`. Soft-deleted (`deleted_at != NULL` in app tables) is irrelevant here because we look up by PK.
- `actor_auth_user_id` is nullable for events emitted by background tasks or system processes; we accept and surface that as `actor_email = null` end-to-end.
- Slice 2 must not regress the `_decode_audit_cursor`/`_encode_audit_cursor` wire format — these are reused across both endpoints and the cursor is exposed to the frontend.

---

## Slice 2A — Backend: actor_email LEFT JOIN

### Task 2A.1: Schema — add `actor_email` to `AuditEventOut`

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/src/xtrusio_api/schemas/audit_log.py` (lines 18-30, `AuditEventOut`)

- [ ] **Step 1: Read current contents**

Run: `cat apps/api/src/xtrusio_api/schemas/audit_log.py`
Note the existing `AuditEventOut` body.

- [ ] **Step 2: Add the field**

Replace the existing `AuditEventOut` class body (lines 18-30) with:

```python
class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_auth_user_id: UUID | None
    actor_email: str | None
    action: str
    target_type: str
    target_id: str
    scope: str
    workspace_id: UUID | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    created_at: datetime
```

- [ ] **Step 3: Confirm the schema imports remain valid**

Run: `uv run python -c "from xtrusio_api.schemas.audit_log import AuditEventOut, AuditEventsPage; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/xtrusio_api/schemas/audit_log.py
git commit -m "feat(api): AuditEventOut.actor_email"
```

### Task 2A.2: Service — platform audit log LEFT JOIN — TDD

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/tests/services/test_platform_audit_log.py` (append)
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/src/xtrusio_api/services/platform_audit_log.py` (lines 53-69)

- [ ] **Step 1: Append failing tests**

Open `apps/api/tests/services/test_platform_audit_log.py` and append at the end:

```python
async def test_actor_email_populated_when_actor_exists(
    db: AsyncSession,
) -> None:
    actor_id = uuid4()
    await _seed_actor(db, actor_id, "actor-with-email")
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.create",
        target_type="role",
        target_id=uuid4(),
        scope="platform",
        after={"key": "dispatcher"},
    )
    await db.commit()
    rows, _ = await list_platform_audit_events(db, limit=50)
    matching = [r for r in rows if r["actor_auth_user_id"] == actor_id]
    assert matching, "seeded audit row not returned"
    assert matching[0]["actor_email"] == "actor-with-email@example.com"


async def test_actor_email_none_when_actor_auth_user_id_is_null(
    db: AsyncSession,
) -> None:
    # Seed an audit row with actor_id=None to simulate a system-emitted event.
    await db.execute(
        text(
            "INSERT INTO rbac_audit_log "
            "(actor_auth_user_id, action, target_type, target_id, scope, before, after, created_at) "
            "VALUES (NULL, 'system_event', 'role', :tid, 'platform', NULL, '{}'::jsonb, NOW())"
        ),
        {"tid": str(uuid4())},
    )
    await db.commit()
    rows, _ = await list_platform_audit_events(db, limit=50)
    nulls = [r for r in rows if r["actor_auth_user_id"] is None]
    assert nulls, "system-emitted audit row not returned"
    assert nulls[0]["actor_email"] is None


async def test_actor_email_none_when_actor_hard_deleted(
    db: AsyncSession,
) -> None:
    actor_id = uuid4()
    await _seed_actor(db, actor_id, "actor-to-be-deleted")
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="platform_role.create",
        target_type="role",
        target_id=uuid4(),
        scope="platform",
        after={"key": "ephemeral"},
    )
    # Hard-delete the auth.users row but keep the audit row. This mirrors the
    # state we'd see if an account were purged manually.
    await db.execute(
        text("DELETE FROM auth.users WHERE id = :id"), {"id": str(actor_id)}
    )
    await db.commit()
    rows, _ = await list_platform_audit_events(db, limit=50)
    orphaned = [
        r
        for r in rows
        if r["actor_auth_user_id"] == actor_id and r["actor_email"] is None
    ]
    assert orphaned, "orphaned audit row missing or actor_email not None"
```

- [ ] **Step 2: Run to verify they fail**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_platform_audit_log.py -v -k actor_email`
Expected: all 3 new tests FAIL with `KeyError: 'actor_email'` (the row dicts from the service don't carry it yet).

- [ ] **Step 3: Update the service to add the LEFT JOIN**

Open `apps/api/src/xtrusio_api/services/platform_audit_log.py`. Replace the `base` string and the two `sql` strings (lines 53-68) with:

```python
    base = (
        "SELECT r.id, r.actor_auth_user_id, u.email AS actor_email, "
        "r.action, r.target_type, r.target_id, r.scope, r.workspace_id, "
        "r.before, r.after, r.created_at "
        "FROM rbac_audit_log r "
        "LEFT JOIN auth.users u ON u.id = r.actor_auth_user_id "
        "WHERE r.scope = 'platform' "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {"ts": ts, "rid": rid, "lim": limit + 1}
        sql = base + (
            "AND (r.created_at < :ts OR (r.created_at = :ts AND r.id < :rid)) "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
        )
    else:
        params = {"lim": limit + 1}
        sql = base + "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
```

The two cursor branches must use `r.created_at` / `r.id` (aliased) — the unprefixed form was unambiguous before the JOIN but isn't now.

- [ ] **Step 4: Run to verify the new tests pass + all old tests still pass**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_platform_audit_log.py -v`
Expected: all PASS (the new actor_email tests plus the original pagination/cursor tests).

- [ ] **Step 5: Mypy + ruff on touched file**

Run:
```bash
uv run mypy apps/api/src/xtrusio_api/services/platform_audit_log.py
uv run ruff check apps/api/src/xtrusio_api/services/platform_audit_log.py
uv run ruff format --check apps/api/src/xtrusio_api/services/platform_audit_log.py
```
Expected: exit 0 each.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/services/platform_audit_log.py apps/api/tests/services/test_platform_audit_log.py
git commit -m "feat(api): platform audit log returns actor_email via LEFT JOIN"
```

### Task 2A.3: Service — workspace audit log LEFT JOIN — TDD

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/tests/services/test_workspace_audit_log.py` (append)
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/api/src/xtrusio_api/services/workspace_audit_log.py` (the SELECT in `list_workspace_audit_events`)

- [ ] **Step 1: Append failing tests**

Open `apps/api/tests/services/test_workspace_audit_log.py`. Locate any existing `_seed_actor`-style helper (or copy the one from `test_platform_audit_log.py`). Append at the end:

```python
async def test_workspace_actor_email_populated_when_actor_exists(
    db: AsyncSession,
) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    await _seed_actor(db, actor_id, "ws-actor")
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.create",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=workspace_id,
        after={"key": "viewer"},
    )
    await db.commit()
    rows, _ = await list_workspace_audit_events(
        db, workspace_id=workspace_id, limit=50
    )
    assert rows and rows[0]["actor_email"] == "ws-actor@example.com"


async def test_workspace_actor_email_none_when_actor_null(
    db: AsyncSession,
) -> None:
    workspace_id = uuid4()
    await db.execute(
        text(
            "INSERT INTO rbac_audit_log "
            "(actor_auth_user_id, action, target_type, target_id, scope, workspace_id, before, after, created_at) "
            "VALUES (NULL, 'system_event', 'role', :tid, 'workspace', :wid, NULL, '{}'::jsonb, NOW())"
        ),
        {"tid": str(uuid4()), "wid": str(workspace_id)},
    )
    await db.commit()
    rows, _ = await list_workspace_audit_events(
        db, workspace_id=workspace_id, limit=50
    )
    assert rows and rows[0]["actor_email"] is None


async def test_workspace_actor_email_none_when_actor_hard_deleted(
    db: AsyncSession,
) -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    await _seed_actor(db, actor_id, "ws-actor-deleted")
    await write_audit_event(
        db,
        actor_id=actor_id,
        action="workspace_role.create",
        target_type="role",
        target_id=uuid4(),
        scope="workspace",
        workspace_id=workspace_id,
        after={"key": "ghost"},
    )
    await db.execute(
        text("DELETE FROM auth.users WHERE id = :id"), {"id": str(actor_id)}
    )
    await db.commit()
    rows, _ = await list_workspace_audit_events(
        db, workspace_id=workspace_id, limit=50
    )
    assert rows and rows[0]["actor_email"] is None
```

If a `_seed_actor` helper does not exist in this test file, port the one from `test_platform_audit_log.py` (see top of that file). The reasoning is identical: both files seed `auth.users` rows so the LEFT JOIN has something to find.

- [ ] **Step 2: Run to verify failing**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_audit_log.py -v -k actor_email`
Expected: FAIL with `KeyError: 'actor_email'`.

- [ ] **Step 3: Update the service**

Open `apps/api/src/xtrusio_api/services/workspace_audit_log.py`. The current `list_workspace_audit_events` has a similar SELECT — adjust it to:

```python
async def list_workspace_audit_events(
    db: AsyncSession,
    *,
    workspace_id: UUID,
    cursor: tuple[datetime, int] | None = None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], str | None]:
    """Paginated SELECT on rbac_audit_log filtered to this workspace.

    LEFT JOIN auth.users projects actor_email; NULL when the actor was a
    system process or has been hard-deleted.
    """
    base = (
        "SELECT r.id, r.actor_auth_user_id, u.email AS actor_email, "
        "r.action, r.target_type, r.target_id, r.scope, r.workspace_id, "
        "r.before, r.after, r.created_at "
        "FROM rbac_audit_log r "
        "LEFT JOIN auth.users u ON u.id = r.actor_auth_user_id "
        "WHERE r.scope = 'workspace' AND r.workspace_id = :wid "
    )
    params: dict[str, Any]
    if cursor is not None:
        ts, rid = cursor
        params = {
            "wid": str(workspace_id),
            "ts": ts,
            "rid": rid,
            "lim": limit + 1,
        }
        sql = base + (
            "AND (r.created_at < :ts OR (r.created_at = :ts AND r.id < :rid)) "
            "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
        )
    else:
        params = {"wid": str(workspace_id), "lim": limit + 1}
        sql = base + "ORDER BY r.created_at DESC, r.id DESC LIMIT :lim"
    rows = [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = _encode_audit_cursor(last["created_at"], int(last["id"]))
        rows = rows[:limit]
    return rows, next_cursor
```

- [ ] **Step 4: Run to verify passing**

Run: `STARTUP_RECONCILE_TOLERANT=false uv run pytest apps/api/tests/services/test_workspace_audit_log.py -v`
Expected: all PASS (new + existing).

- [ ] **Step 5: Mypy + ruff**

Run:
```bash
uv run mypy apps/api/src/xtrusio_api/services/workspace_audit_log.py
uv run ruff check apps/api/src/xtrusio_api/services/workspace_audit_log.py
uv run ruff format --check apps/api/src/xtrusio_api/services/workspace_audit_log.py
```
Expected: exit 0 each.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/xtrusio_api/services/workspace_audit_log.py apps/api/tests/services/test_workspace_audit_log.py
git commit -m "feat(api): workspace audit log returns actor_email via LEFT JOIN"
```

---

## Slice 2B — Frontend foundation (api-types + lib/api)

### Task 2B.1: api-types — AuditEventOut + AuditEventsPage

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/packages/api-types/src/audit-log.ts`
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/packages/api-types/src/index.ts`

- [ ] **Step 1: Write the type file**

```ts
// packages/api-types/src/audit-log.ts
// Mirror of apps/api/src/xtrusio_api/schemas/audit_log.py. Note `id` is a
// bigint server-side but JSON-serialises as a JS number — fine for cursor
// page sizes well under 2^53.

export type AuditEventOut = {
  id: number;
  actor_auth_user_id: string | null;
  actor_email: string | null;
  action: string;
  target_type: string;
  target_id: string;
  scope: "platform" | "workspace";
  workspace_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  created_at: string;
};

export type AuditEventsPage = {
  items: AuditEventOut[];
  next_cursor: string | null;
};
```

- [ ] **Step 2: Update the re-export**

Open `packages/api-types/src/index.ts`. After the existing `export * from "./role";` (added in Slice 1), append:

```ts
export * from "./audit-log";
```

- [ ] **Step 3: Typecheck**

Run: `pnpm --filter @xtrusio/api-types typecheck`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add packages/api-types/src/audit-log.ts packages/api-types/src/index.ts
git commit -m "feat(api-types): AuditEventOut + AuditEventsPage"
```

### Task 2B.2: lib/api — audit fetchers

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/lib/api.ts` (append after Slice-1 additions)

- [ ] **Step 1: Update the import at the top of the file**

Open `apps/web/src/lib/api.ts`. Extend the `@xtrusio/api-types` import (which Slice 1 already broadened) to also include the audit types:

```ts
import type {
  // ... existing imports from Slice 1 ...
  AuditEventsPage,
} from "@xtrusio/api-types";
```

- [ ] **Step 2: Append the fetchers**

At the bottom of the file:

```ts
// ----- Audit-log (P6c Slice 2) -----

export async function fetchPlatformAuditLog(
  cursor?: string,
): Promise<AuditEventsPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<AuditEventsPage>(`/api/platform/audit-log${qs}`);
}

export async function fetchWorkspaceAuditLog(
  workspaceId: string,
  cursor?: string,
): Promise<AuditEventsPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<AuditEventsPage>(
    `/api/workspaces/${workspaceId}/audit-log${qs}`,
  );
}
```

- [ ] **Step 3: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/lib/api.ts
git commit -m "feat(web): audit-log fetchers in lib/api"
```

---

## Slice 2C — Shared UI building blocks (TDD each)

### Task 2C.1: `<LoadMoreButton />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/audit/load-more-button.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/audit/load-more-button.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/audit/load-more-button.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LoadMoreButton } from "./load-more-button";

describe("<LoadMoreButton />", () => {
  it("renders 'Load more' when a next cursor exists", () => {
    render(
      <LoadMoreButton nextCursor="abc" pending={false} onClick={() => {}} />,
    );
    expect(
      screen.getByRole("button", { name: /load more/i }),
    ).toBeInTheDocument();
  });

  it("renders nothing when nextCursor is null", () => {
    const { container } = render(
      <LoadMoreButton nextCursor={null} pending={false} onClick={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows pending state and disables", () => {
    render(
      <LoadMoreButton nextCursor="abc" pending onClick={() => {}} />,
    );
    const btn = screen.getByRole("button", { name: /loading/i });
    expect(btn).toBeDisabled();
  });

  it("fires onClick", async () => {
    const onClick = vi.fn();
    render(
      <LoadMoreButton nextCursor="abc" pending={false} onClick={onClick} />,
    );
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/audit/load-more-button.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/src/components/audit/load-more-button.tsx
import { Button } from "@/components/ui/button";

type Props = {
  nextCursor: string | null;
  pending: boolean;
  onClick: () => void;
};

export function LoadMoreButton({ nextCursor, pending, onClick }: Props) {
  if (nextCursor === null) return null;
  return (
    <div className="mt-4 flex justify-center">
      <Button variant="outline" disabled={pending} onClick={onClick}>
        {pending ? "Loading…" : "Load more"}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/audit/load-more-button.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/audit/load-more-button.tsx apps/web/src/components/audit/load-more-button.test.tsx
git commit -m "feat(web): <LoadMoreButton />"
```

### Task 2C.2: `<AuditTable />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/audit/audit-table.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/audit/audit-table.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/audit/audit-table.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AuditEventOut } from "@xtrusio/api-types";
import { AuditTable } from "./audit-table";

const EVENTS: AuditEventOut[] = [
  {
    id: 1,
    actor_auth_user_id: "u-1",
    actor_email: "ana@acme.com",
    action: "platform_role.update",
    target_type: "role",
    target_id: "11111111-1111-1111-1111-111111111111",
    scope: "platform",
    workspace_id: null,
    before: null,
    after: { key: "dispatcher" },
    created_at: "2026-05-22T10:00:00Z",
  },
  {
    id: 2,
    actor_auth_user_id: null,
    actor_email: null,
    action: "system_event",
    target_type: "role",
    target_id: "22222222-2222-2222-2222-222222222222",
    scope: "platform",
    workspace_id: null,
    before: null,
    after: null,
    created_at: "2026-05-22T09:00:00Z",
  },
];

describe("<AuditTable />", () => {
  it("renders four columns and every row", () => {
    render(<AuditTable events={EVENTS} onSelect={() => {}} />);
    expect(screen.getByText("ana@acme.com")).toBeInTheDocument();
    expect(screen.getByText("platform_role.update")).toBeInTheDocument();
    expect(screen.getByText("system_event")).toBeInTheDocument();
  });

  it("renders '—' for null actor_email", () => {
    render(<AuditTable events={EVENTS} onSelect={() => {}} />);
    const dashes = screen.getAllByText("—");
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it("truncates target_id and exposes the full id as a title attribute", () => {
    render(<AuditTable events={EVENTS} onSelect={() => {}} />);
    const target = screen.getByTitle(
      "11111111-1111-1111-1111-111111111111",
    );
    expect(target.textContent).not.toEqual(
      "11111111-1111-1111-1111-111111111111",
    );
    expect(target.textContent?.length ?? 0).toBeLessThan(20);
  });

  it("fires onSelect with the clicked event", async () => {
    const onSelect = vi.fn();
    render(<AuditTable events={EVENTS} onSelect={onSelect} />);
    await userEvent.click(screen.getByText("platform_role.update"));
    expect(onSelect).toHaveBeenCalledWith(EVENTS[0]);
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/audit/audit-table.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/src/components/audit/audit-table.tsx
import type { AuditEventOut } from "@xtrusio/api-types";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Props = {
  events: AuditEventOut[];
  onSelect: (e: AuditEventOut) => void;
};

function formatTime(iso: string): string {
  // Use the user's locale; keep it short. Stable across SSR/CSR is irrelevant
  // here because this is a CSR-only app.
  return new Date(iso).toLocaleString();
}

function truncate(value: string, head = 8): string {
  return value.length <= head + 1 ? value : `${value.slice(0, head)}…`;
}

export function AuditTable({ events, onSelect }: Props) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-44">Time</TableHead>
          <TableHead className="w-60">Actor</TableHead>
          <TableHead>Action</TableHead>
          <TableHead className="w-56">Target</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((e) => (
          <TableRow
            key={e.id}
            className="cursor-pointer"
            onClick={() => onSelect(e)}
          >
            <TableCell className="text-xs text-muted-foreground">
              <time
                dateTime={e.created_at}
                title={new Date(e.created_at).toISOString()}
              >
                {formatTime(e.created_at)}
              </time>
            </TableCell>
            <TableCell className="text-sm">{e.actor_email ?? "—"}</TableCell>
            <TableCell className="font-mono text-xs">{e.action}</TableCell>
            <TableCell className="font-mono text-xs">
              <span title={e.target_id}>
                {e.target_type}:{truncate(e.target_id)}
              </span>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/audit/audit-table.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/audit/audit-table.tsx apps/web/src/components/audit/audit-table.test.tsx
git commit -m "feat(web): <AuditTable />"
```

### Task 2C.3: `<AuditDetailDrawer />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/audit/audit-detail-drawer.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/audit/audit-detail-drawer.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/audit/audit-detail-drawer.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { AuditEventOut } from "@xtrusio/api-types";
import { AuditDetailDrawer } from "./audit-detail-drawer";

const CREATE_EVENT: AuditEventOut = {
  id: 1,
  actor_auth_user_id: "u-1",
  actor_email: "ana@acme.com",
  action: "platform_role.create",
  target_type: "role",
  target_id: "tid",
  scope: "platform",
  workspace_id: null,
  before: null,
  after: { key: "dispatcher", permission_keys: ["platform.users.read"] },
  created_at: "2026-05-22T10:00:00Z",
};

const DELETE_EVENT: AuditEventOut = {
  ...CREATE_EVENT,
  id: 2,
  action: "platform_role.delete",
  before: { key: "old", permission_keys: [] },
  after: null,
};

describe("<AuditDetailDrawer />", () => {
  it("renders nothing when event is null", () => {
    const { container } = render(
      <AuditDetailDrawer event={null} onOpenChange={() => {}} />,
    );
    // shadcn Sheet portals to document.body; with open=false there should be no
    // visible drawer content.
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the 'after' JSON for a create event and shows 'before' as empty", () => {
    render(
      <AuditDetailDrawer event={CREATE_EVENT} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/dispatcher/i)).toBeInTheDocument();
    // 'before' should render with an explicit empty marker.
    expect(screen.getByText(/before/i)).toBeInTheDocument();
  });

  it("renders the 'before' JSON for a delete event and shows 'after' as empty", () => {
    render(
      <AuditDetailDrawer event={DELETE_EVENT} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/"key": "old"/)).toBeInTheDocument();
  });

  it("fires onOpenChange(false) when the close affordance is clicked", async () => {
    const onOpenChange = vi.fn();
    render(
      <AuditDetailDrawer
        event={CREATE_EVENT}
        onOpenChange={onOpenChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/audit/audit-detail-drawer.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the component**

```tsx
// apps/web/src/components/audit/audit-detail-drawer.tsx
import type { AuditEventOut } from "@xtrusio/api-types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

type Props = {
  event: AuditEventOut | null;
  onOpenChange: (open: boolean) => void;
};

function pretty(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

export function AuditDetailDrawer({ event, onOpenChange }: Props) {
  return (
    <Sheet open={event !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="font-mono">{event?.action}</SheetTitle>
          <SheetDescription>
            {event?.actor_email ?? "(system)"} —{" "}
            {event ? new Date(event.created_at).toLocaleString() : ""}
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-6">
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Target</h3>
            <p className="font-mono text-xs">
              {event?.target_type}:{event?.target_id}
            </p>
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">Before</h3>
            <pre className="max-h-64 overflow-auto rounded-md border bg-muted p-3 font-mono text-xs">
              {event?.before === null || event?.before === undefined
                ? "(none)"
                : pretty(event.before)}
            </pre>
          </section>
          <section className="space-y-2">
            <h3 className="text-sm font-medium">After</h3>
            <pre className="max-h-64 overflow-auto rounded-md border bg-muted p-3 font-mono text-xs">
              {event?.after === null || event?.after === undefined
                ? "(none)"
                : pretty(event.after)}
            </pre>
          </section>
        </div>
      </SheetContent>
    </Sheet>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/audit/audit-detail-drawer.test.tsx`
Expected: 4 PASS.

If the test fails the "empty container" assertion because the shadcn `Sheet` always renders an empty portal node even when closed, adjust the first test to query for the SheetContent visibility instead:

```ts
expect(screen.queryByRole("dialog")).toBeNull();
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/audit/audit-detail-drawer.tsx apps/web/src/components/audit/audit-detail-drawer.test.tsx
git commit -m "feat(web): <AuditDetailDrawer />"
```

---

## Slice 2D — Per-scope page components + routes

### Task 2D.1: `<PlatformAuditLogPage />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/platform-audit-log-page.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/platform-audit-log-page.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/platform-audit-log-page.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditEventOut, MeResponse } from "@xtrusio/api-types";
import { PlatformAuditLogPage } from "./platform-audit-log-page";

const ME_WITH: MeResponse = {
  user_id: "u-1",
  email: "super@xtrusio.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.audit.read"],
  tenants: [],
  pending_invite: null,
};
const ME_WITHOUT: MeResponse = { ...ME_WITH, platform_permissions: [] };

const EV1: AuditEventOut = {
  id: 1,
  actor_auth_user_id: "u-1",
  actor_email: "ana@acme.com",
  action: "platform_role.create",
  target_type: "role",
  target_id: "tid-1",
  scope: "platform",
  workspace_id: null,
  before: null,
  after: { key: "dispatcher" },
  created_at: "2026-05-22T10:00:00Z",
};
const EV2: AuditEventOut = { ...EV1, id: 2, action: "platform_role.update" };

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchPlatformAuditLog: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => vi.clearAllMocks());

function renderWith(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <PlatformAuditLogPage />
    </QueryClientProvider>,
  );
}

describe("<PlatformAuditLogPage />", () => {
  it("renders <Forbidden /> when me lacks platform.audit.read", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITHOUT);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      expect(
        screen.getByText(/don't have access|don't have permission/i),
      ).toBeInTheDocument(),
    );
  });

  it("renders the first page of events", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.fetchPlatformAuditLog).mockResolvedValue({
      items: [EV1, EV2],
      next_cursor: "next-1",
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => {
      expect(screen.getByText("platform_role.create")).toBeInTheDocument();
      expect(screen.getByText("platform_role.update")).toBeInTheDocument();
    });
  });

  it("accumulates pages when Load more is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.fetchPlatformAuditLog)
      .mockResolvedValueOnce({ items: [EV1], next_cursor: "next-1" })
      .mockResolvedValueOnce({
        items: [{ ...EV2, action: "platform_role.delete" }],
        next_cursor: null,
      });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("platform_role.create"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() => {
      expect(screen.getByText("platform_role.create")).toBeInTheDocument();
      expect(screen.getByText("platform_role.delete")).toBeInTheDocument();
    });
    expect(api.fetchPlatformAuditLog).toHaveBeenCalledTimes(2);
    expect(api.fetchPlatformAuditLog).toHaveBeenLastCalledWith("next-1");
  });

  it("opens the drawer with the clicked event", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_WITH);
    vi.mocked(api.fetchPlatformAuditLog).mockResolvedValue({
      items: [EV1],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("platform_role.create"));
    await userEvent.click(screen.getByText("platform_role.create"));
    await waitFor(() =>
      expect(screen.getByText(/"key": "dispatcher"/)).toBeInTheDocument(),
    );
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/platform-audit-log-page.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the page**

```tsx
// apps/web/src/components/platform-audit-log-page.tsx
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { AuditEventOut, AuditEventsPage } from "@xtrusio/api-types";
import { fetchPlatformAuditLog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import {
  getDefaultLandingPath,
  hasPlatformPerm,
  useMe,
} from "@/lib/me-adapter";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditDetailDrawer } from "@/components/audit/audit-detail-drawer";
import { LoadMoreButton } from "@/components/audit/load-more-button";

export function PlatformAuditLogPage() {
  const { me } = useMe();
  if (!hasPlatformPerm(me, "platform.audit.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body />;
}

function Body() {
  // Local accumulator: each click on Load more appends a page.
  const [cursor, setCursor] = useState<string | null>(null);
  const [pages, setPages] = useState<AuditEventsPage[]>([]);

  const query = useQuery({
    queryKey: [...qk.platformAudit(), cursor ?? "head"],
    queryFn: async () => {
      const page = await fetchPlatformAuditLog(cursor ?? undefined);
      setPages((prev) =>
        cursor === null ? [page] : [...prev, page],
      );
      return page;
    },
  });

  const events = useMemo<AuditEventOut[]>(
    () => pages.flatMap((p) => p.items),
    [pages],
  );
  const lastCursor =
    pages.length > 0 ? pages[pages.length - 1]!.next_cursor : null;

  const [selected, setSelected] = useState<AuditEventOut | null>(null);

  return (
    <>
      <PageHeader
        title="Platform audit log"
        description="Every platform-scope RBAC mutation in reverse-chronological order. Click a row to inspect before/after JSON."
      />
      <AuditTable events={events} onSelect={setSelected} />
      <LoadMoreButton
        nextCursor={lastCursor}
        pending={query.isFetching}
        onClick={() => setCursor(lastCursor)}
      />
      <AuditDetailDrawer
        event={selected}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
      />
    </>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/platform-audit-log-page.test.tsx`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/platform-audit-log-page.tsx apps/web/src/components/platform-audit-log-page.test.tsx
git commit -m "feat(web): <PlatformAuditLogPage />"
```

### Task 2D.2: `_app.platform.audit-log` file-route

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/routes/_app.platform.audit-log.tsx`

- [ ] **Step 1: Write the route file**

```tsx
import { createFileRoute } from "@tanstack/react-router";
import { PlatformAuditLogPage } from "@/components/platform-audit-log-page";

export const Route = createFileRoute("/_app/platform/audit-log")({
  component: PlatformAuditLogPage,
});
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/routes/_app.platform.audit-log.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /platform/audit-log file-route"
```

### Task 2D.3: `<WorkspaceAuditLogPage />` — TDD

**Files:**
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/workspace-audit-log-page.test.tsx`
- Create: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/components/workspace-audit-log-page.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/workspace-audit-log-page.test.tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuditEventOut, MeResponse } from "@xtrusio/api-types";
import { WorkspaceAuditLogPage } from "./workspace-audit-log-page";

const WID = "wid-1";

const ME_OWNER: MeResponse = {
  user_id: "u-1",
  email: "owner@acme.com",
  platform: null,
  platform_permissions: [],
  tenants: [
    {
      id: WID,
      slug: "acme",
      name: "Acme",
      role: "owner",
      permissions: ["workspace.audit.read"],
    },
  ],
  pending_invite: null,
};
const ME_NOT_OWNER: MeResponse = {
  ...ME_OWNER,
  tenants: [
    {
      ...ME_OWNER.tenants[0]!,
      role: "editor",
      permissions: ["workspace.members.read"],
    },
  ],
};

const EV1: AuditEventOut = {
  id: 1,
  actor_auth_user_id: "u-1",
  actor_email: "owner@acme.com",
  action: "workspace_role.create",
  target_type: "role",
  target_id: "tid-1",
  scope: "workspace",
  workspace_id: WID,
  before: null,
  after: { key: "viewer" },
  created_at: "2026-05-22T10:00:00Z",
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchMe: vi.fn(),
    fetchWorkspaceAuditLog: vi.fn(),
  };
});

import * as api from "@/lib/api";

beforeEach(() => vi.clearAllMocks());

function renderWith(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <WorkspaceAuditLogPage workspaceId={WID} />
    </QueryClientProvider>,
  );
}

describe("<WorkspaceAuditLogPage />", () => {
  it("renders <Forbidden /> when me lacks workspace.audit.read for this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_NOT_OWNER);
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() =>
      expect(
        screen.getByText(/don't have access|don't have permission/i),
      ).toBeInTheDocument(),
    );
  });

  it("renders the first page scoped to this workspace", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceAuditLog).mockResolvedValue({
      items: [EV1],
      next_cursor: null,
    });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("workspace_role.create"));
    expect(api.fetchWorkspaceAuditLog).toHaveBeenCalledWith(WID, undefined);
  });

  it("accumulates pages when Load more is clicked", async () => {
    vi.mocked(api.fetchMe).mockResolvedValue(ME_OWNER);
    vi.mocked(api.fetchWorkspaceAuditLog)
      .mockResolvedValueOnce({ items: [EV1], next_cursor: "next-1" })
      .mockResolvedValueOnce({
        items: [{ ...EV1, id: 2, action: "workspace_role.delete" }],
        next_cursor: null,
      });
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    renderWith(qc);
    await waitFor(() => screen.getByText("workspace_role.create"));
    await userEvent.click(screen.getByRole("button", { name: /load more/i }));
    await waitFor(() =>
      expect(screen.getByText("workspace_role.delete")).toBeInTheDocument(),
    );
    expect(api.fetchWorkspaceAuditLog).toHaveBeenLastCalledWith(
      WID,
      "next-1",
    );
  });
});
```

- [ ] **Step 2: Run to verify failing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/workspace-audit-log-page.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Write the page**

```tsx
// apps/web/src/components/workspace-audit-log-page.tsx
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import type { AuditEventOut, AuditEventsPage } from "@xtrusio/api-types";
import { fetchWorkspaceAuditLog } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import {
  getDefaultLandingPath,
  hasWorkspacePerm,
  useMe,
} from "@/lib/me-adapter";
import { PageHeader } from "@/components/page-header";
import { Forbidden } from "@/components/forbidden";
import { AuditTable } from "@/components/audit/audit-table";
import { AuditDetailDrawer } from "@/components/audit/audit-detail-drawer";
import { LoadMoreButton } from "@/components/audit/load-more-button";

export function WorkspaceAuditLogPage({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const { me } = useMe();
  if (!hasWorkspacePerm(me, workspaceId, "workspace.audit.read")) {
    return <Forbidden landingPath={getDefaultLandingPath(me)} />;
  }
  return <Body workspaceId={workspaceId} />;
}

function Body({ workspaceId }: { workspaceId: string }) {
  const [cursor, setCursor] = useState<string | null>(null);
  const [pages, setPages] = useState<AuditEventsPage[]>([]);

  const query = useQuery({
    queryKey: [...qk.workspaceAudit(workspaceId), cursor ?? "head"],
    queryFn: async () => {
      const page = await fetchWorkspaceAuditLog(
        workspaceId,
        cursor ?? undefined,
      );
      setPages((prev) =>
        cursor === null ? [page] : [...prev, page],
      );
      return page;
    },
  });

  const events = useMemo<AuditEventOut[]>(
    () => pages.flatMap((p) => p.items),
    [pages],
  );
  const lastCursor =
    pages.length > 0 ? pages[pages.length - 1]!.next_cursor : null;

  const [selected, setSelected] = useState<AuditEventOut | null>(null);

  return (
    <>
      <PageHeader
        title="Workspace audit log"
        description="Every RBAC mutation in this workspace, reverse-chronological."
      />
      <AuditTable events={events} onSelect={setSelected} />
      <LoadMoreButton
        nextCursor={lastCursor}
        pending={query.isFetching}
        onClick={() => setCursor(lastCursor)}
      />
      <AuditDetailDrawer
        event={selected}
        onOpenChange={(o) => {
          if (!o) setSelected(null);
        }}
      />
    </>
  );
}
```

- [ ] **Step 4: Run to verify passing**

Run: `pnpm --filter @xtrusio/web exec vitest run src/components/workspace-audit-log-page.test.tsx`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/workspace-audit-log-page.tsx apps/web/src/components/workspace-audit-log-page.test.tsx
git commit -m "feat(web): <WorkspaceAuditLogPage />"
```

### Task 2D.4: Replace the `_app.workspace.$workspaceId.audit-log` placeholder

**Files:**
- Modify: `/Users/jpsingh/Developer/Project/xtrusio/apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx` (full file rewrite)

- [ ] **Step 1: Write the new file**

```tsx
import { createFileRoute, useParams } from "@tanstack/react-router";
import { WorkspaceAuditLogPage } from "@/components/workspace-audit-log-page";

export const Route = createFileRoute(
  "/_app/workspace/$workspaceId/audit-log",
)({
  component: RouteComponent,
});

function RouteComponent() {
  const { workspaceId } = useParams({
    from: "/_app/workspace/$workspaceId/audit-log",
  });
  return <WorkspaceAuditLogPage workspaceId={workspaceId} />;
}
```

- [ ] **Step 2: Typecheck**

Run: `pnpm --filter @xtrusio/web typecheck`
Expected: exit 0.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/routes/_app.workspace.$workspaceId.audit-log.tsx apps/web/src/routeTree.gen.ts
git commit -m "feat(web): /workspace/\$id/audit-log now consumes <WorkspaceAuditLogPage />"
```

---

## Slice 2 Wrap — End-of-slice verification, review, PR, merge

### Task 2W.1: Controller-run end-of-slice gate

- [ ] **Step 1: Reset and run full backend tests**

Run: `STARTUP_RECONCILE_TOLERANT=false make test-clean`
Expected: exit 0, all backend tests PASS from a clean DB.

- [ ] **Step 2: Lint + typecheck + frontend test gate**

Run: `STARTUP_RECONCILE_TOLERANT=false make check`
Expected: exit 0 (ruff check + ruff format --check + mypy --strict + turbo typecheck + vitest).

- [ ] **Step 3: Smoke check manually (USER-DRIVEN)**

User logs in as super_admin, visits `/platform/audit-log` after creating/editing/deleting a role from Slice 1, confirms entries with `actor_email = own email`, clicks a row → drawer opens with before/after JSON. Repeats as workspace owner at `/workspace/<wid>/audit-log` for that workspace.

### Task 2W.2: Opus code-quality review

Controller-run via `/ultrareview`. Apply blocking findings.

### Task 2W.3: Open the PR

- [ ] **Step 1: Write the PR body**

Save to `docs/superpowers/PR-rbac-p6c-slice-2-body.md`:

```markdown
## Summary

- Extend `AuditEventOut` with `actor_email: str \| None`.
- Service-layer LEFT JOIN onto `auth.users` in both `list_platform_audit_events` and `list_workspace_audit_events`. `auth.users.id` is PK-indexed — no new index needed.
- New frontend shared blocks: `<AuditTable>`, `<AuditDetailDrawer>`, `<LoadMoreButton>`.
- `<PlatformAuditLogPage>` at `/platform/audit-log` and `<WorkspaceAuditLogPage>` at `/workspace/$id/audit-log`. Cursor-driven Load-more with a local accumulator (deliberately not `useInfiniteQuery`).
- Tests: 3 new backend assertions per scope (actor exists / actor_id null / actor hard-deleted); full frontend coverage of the new blocks and pages.

No migration. Alembic head stays at `0009`.

## Test plan

- [ ] `STARTUP_RECONCILE_TOLERANT=false make test-clean` green
- [ ] `STARTUP_RECONCILE_TOLERANT=false make check` green
- [ ] Manual: super_admin sees their email next to every RBAC mutation they performed in `/platform/audit-log`; clicking opens the drawer with before/after JSON
- [ ] Manual: workspace owner sees workspace-scope events only at `/workspace/<wid>/audit-log`
- [ ] Manual: Load more advances the cursor; trailing `next_cursor=null` hides the button
- [ ] Manual: a workspace `editor` is shown `<Forbidden />` at `/workspace/<their-wid>/audit-log`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "P6c Slice 2 — Audit log viewers (platform + workspace)" \
  --body "$(cat docs/superpowers/PR-rbac-p6c-slice-2-body.md)"
```

### Task 2W.4: Merge + HANDOFF update

- [ ] **Step 1: Merge**

```bash
gh pr merge <PR#> --squash
gh pr view <PR#> --json state  # confirm "MERGED"
```

- [ ] **Step 2: Update HANDOFF.md**

Move "P6c Slice 2" from NEXT into the Done & merged table; pivot NEXT to "P6c Slice 3 — Members port + nav + cleanup".

- [ ] **Step 3: Commit + push**

```bash
git add docs/superpowers/HANDOFF.md
git commit -m "docs(handoff): mark P6c Slice 2 merged; pivot NEXT to Slice 3"
git push
```

---

## Self-review checklist (run before declaring Slice 2 done)

- [ ] `actor_email` populated in every backend audit-log response from a clean DB (super_admin's email appears against their own mutations)
- [ ] `actor_email` is `null` for system-emitted (`actor_auth_user_id IS NULL`) rows and for hard-deleted actors (verified by test)
- [ ] No test relies on stable ordering across non-deterministic cursors — pagination tests assert presence of expected ids rather than positions
- [ ] `useInfiniteQuery` is NOT used (deliberate decision per the spec; the project hasn't adopted it)
- [ ] `<LoadMoreButton />` is hidden when `next_cursor === null`
- [ ] `<AuditDetailDrawer />` distinguishes "no before" (create) from "no after" (delete) with the `(none)` placeholder
- [ ] `make check` exits 0 from a CLEAN DB
- [ ] HANDOFF.md updated post-merge
