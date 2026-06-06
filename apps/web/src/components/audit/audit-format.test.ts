import { describe, expect, it } from "vitest";
import type { AuditEventOut } from "@xtrusio/api-types";
import { diffSnapshots, humanizeField, roleLabel } from "./audit-format";

function ev(partial: Partial<AuditEventOut>): AuditEventOut {
  return {
    id: 1,
    actor_auth_user_id: "u-1",
    actor_email: "a@example.com",
    action: "platform_role.grant",
    target_type: "user_role",
    target_id: "t-1",
    scope: "platform",
    workspace_id: null,
    before: null,
    after: null,
    action_label: "Granted platform role",
    category: "grants",
    created_at: "2026-06-06T00:00:00Z",
    ...partial,
  };
}

describe("roleLabel", () => {
  it("prefers the human role_name over the machine key", () => {
    expect(roleLabel(ev({ after: { role_name: "Auditor", role_key: "auditor" } }))).toBe("Auditor");
  });

  it("falls back to name / key / role in priority order", () => {
    expect(roleLabel(ev({ after: { name: "Owner" } }))).toBe("Owner");
    expect(roleLabel(ev({ after: { role_key: "viewer" } }))).toBe("viewer");
    expect(roleLabel(ev({ after: { key: "editor" } }))).toBe("editor");
    expect(roleLabel(ev({ after: null, before: { role: "admin" } }))).toBe("admin");
  });

  it("returns null when no role-ish field is present", () => {
    expect(roleLabel(ev({ after: { signups_enabled: true }, before: null }))).toBeNull();
    expect(roleLabel(ev({ after: null, before: null }))).toBeNull();
  });
});

describe("diffSnapshots", () => {
  it("treats a null before (create) as all-empty before, real after", () => {
    const rows = diffSnapshots(null, { key: "x", name: "X" });
    expect(rows.map((r) => r.field)).toEqual(["key", "name"]);
    expect(rows.every((r) => r.before === null)).toBe(true);
    expect(rows.find((r) => r.field === "key")?.after).toBe("x");
    expect(rows.every((r) => r.changed)).toBe(true);
  });

  it("marks unchanged fields as not changed", () => {
    const rows = diffSnapshots({ name: "same", key: "a" }, { name: "same", key: "b" });
    expect(rows.find((r) => r.field === "name")?.changed).toBe(false);
    expect(rows.find((r) => r.field === "key")?.changed).toBe(true);
  });

  it("renders arrays/objects as compact JSON leaves", () => {
    const rows = diffSnapshots(null, { perms: ["a", "b"] });
    expect(rows[0]?.after).toBe('["a","b"]');
  });

  it("returns [] when both snapshots are null", () => {
    expect(diffSnapshots(null, null)).toEqual([]);
  });
});

describe("humanizeField", () => {
  it("title-cases a snake_case key", () => {
    expect(humanizeField("role_name")).toBe("Role name");
    expect(humanizeField("signups_enabled")).toBe("Signups enabled");
  });
});
