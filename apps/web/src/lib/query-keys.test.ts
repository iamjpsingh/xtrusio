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

  it("returns a stable tuple for platformAudit, with the category in the key", () => {
    expect(qk.platformAudit()).toEqual(["platform", "audit-log", null]);
    expect(qk.platformAudit("invites")).toEqual(["platform", "audit-log", "invites"]);
  });

  it("namespaces workspaceAudit by workspaceId, with the category in the key", () => {
    expect(qk.workspaceAudit("wid-1")).toEqual(["workspace", "wid-1", "audit-log", null]);
    expect(qk.workspaceAudit("wid-1", "grants")).toEqual([
      "workspace",
      "wid-1",
      "audit-log",
      "grants",
    ]);
  });

  it("namespaces workspaceInvites by workspaceId", () => {
    expect(qk.workspaceInvites("wid-1")).toEqual(["workspace", "wid-1", "invites"]);
  });

  it("does not collide platform vs workspace namespaces", () => {
    expect(qk.platformRoles()[0]).not.toEqual(qk.workspaceRoles("any")[0]);
    expect(qk.platformAudit()[0]).not.toEqual(qk.workspaceAudit("any")[0]);
  });

  it("exposes the E.4 identity/global factories", () => {
    expect(qk.me()).toEqual(["me"]);
    expect(qk.tenants()).toEqual(["tenants"]);
    expect(qk.signupStatus()).toEqual(["signup-status"]);
    expect(qk.platformSettings()).toEqual(["platform", "settings"]);
  });

  it("namespaces tenantInvites by tenantId, parallel to workspaceInvites", () => {
    expect(qk.tenantInvites("t-1")).toEqual(["tenant", "t-1", "invites"]);
    // Distinct resources → distinct first segment.
    expect(qk.tenantInvites("x")[0]).not.toEqual(qk.workspaceInvites("x")[0]);
  });
});
