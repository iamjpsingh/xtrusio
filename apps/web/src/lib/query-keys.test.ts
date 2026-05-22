import { describe, expect, it } from "vitest";
import { qk } from "./query-keys";

describe("qk — TanStack Query key registry", () => {
  it("returns a stable tuple for permissionsCatalog", () => {
    expect(qk.permissionsCatalog()).toEqual(["permissions", "catalog"]);
  });

  it("returns a stable tuple for platformRoles", () => {
    expect(qk.platformRoles()).toEqual(["platform", "roles"]);
  });

  it("namespaces workspaceRoles by workspaceId", () => {
    expect(qk.workspaceRoles("wid-1")).toEqual(["workspace", "wid-1", "roles"]);
    expect(qk.workspaceRoles("wid-2")).not.toEqual(qk.workspaceRoles("wid-1"));
  });

  it("returns a stable tuple for platformAudit", () => {
    expect(qk.platformAudit()).toEqual(["platform", "audit-log"]);
  });

  it("namespaces workspaceAudit by workspaceId", () => {
    expect(qk.workspaceAudit("wid-1")).toEqual([
      "workspace",
      "wid-1",
      "audit-log",
    ]);
  });

  it("namespaces workspaceInvites by workspaceId", () => {
    expect(qk.workspaceInvites("wid-1")).toEqual([
      "workspace",
      "wid-1",
      "invites",
    ]);
  });

  it("does not collide platform vs workspace namespaces", () => {
    expect(qk.platformRoles()[0]).not.toEqual(qk.workspaceRoles("any")[0]);
    expect(qk.platformAudit()[0]).not.toEqual(qk.workspaceAudit("any")[0]);
  });
});
