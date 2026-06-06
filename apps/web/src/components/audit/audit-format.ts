// Activity-feed presentation helpers shared by <AuditTable> + <AuditDetailDrawer>.
// The backend enriches every event with `action_label` + `category` (computed
// from the action catalog); these helpers turn the free-form `before`/`after`
// JSON snapshots into a readable role label and a structured field diff.

import type { AuditEventOut } from "@xtrusio/api-types";

type Snapshot = Record<string, unknown>;

function asSnapshot(value: AuditEventOut["before"]): Snapshot | null {
  return value && typeof value === "object" ? (value as Snapshot) : null;
}

/**
 * Best-effort human role label for an event. Grants/role mutations carry the
 * role under different keys depending on the source service (grants use
 * `role_name`/`role_key`, role CRUD uses `name`/`key`, invites use `role`).
 * Prefers the human name over the machine key. Returns null when no role-ish
 * field is present (the table renders an em-dash).
 */
export function roleLabel(e: AuditEventOut): string | null {
  const src = asSnapshot(e.after) ?? asSnapshot(e.before);
  if (!src) return null;
  for (const key of ["role_name", "name", "role_key", "key", "role"]) {
    const v = src[key];
    if (typeof v === "string" && v.length > 0) return v;
  }
  return null;
}

export type DiffRow = {
  field: string;
  before: string | null;
  after: string | null;
  changed: boolean;
};

function renderLeaf(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  // arrays / nested objects → compact JSON, monospace-rendered by the drawer.
  return JSON.stringify(value);
}

/**
 * Build a unified before→after diff over the union of keys in both snapshots,
 * sorted alphabetically. A row is `changed` when its before/after leaves
 * differ. Handles the create case (before=null → all additions) and delete
 * case (after=null → all removals) cleanly.
 */
export function diffSnapshots(
  before: AuditEventOut["before"],
  after: AuditEventOut["after"],
): DiffRow[] {
  const b = asSnapshot(before) ?? {};
  const a = asSnapshot(after) ?? {};
  const keys = Array.from(new Set([...Object.keys(b), ...Object.keys(a)])).sort();
  return keys.map((field) => {
    const beforeLeaf = renderLeaf(b[field]);
    const afterLeaf = renderLeaf(a[field]);
    return { field, before: beforeLeaf, after: afterLeaf, changed: beforeLeaf !== afterLeaf };
  });
}

/** Title-case a snake_case payload key for display: `role_name` → `Role name`. */
export function humanizeField(field: string): string {
  const spaced = field.replace(/_/g, " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
