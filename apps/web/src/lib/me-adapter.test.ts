// apps/web/src/lib/me-adapter.test.ts
import { describe, expect, it } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import { hasPlatformPerm, hasWorkspacePerm, findTenant, getDefaultLandingPath } from "./me-adapter";

const empty: MeResponse = {
  user_id: "u",
  email: "x@x.com",
  platform: null,
  platform_permissions: [],
  tenants: [],
  pending_invite: null,
};

const platformAdmin: MeResponse = {
  ...empty,
  platform: { role: "admin", is_active: true },
  platform_permissions: ["platform.users.read", "platform.clients.read"],
};

const tenantOwner: MeResponse = {
  ...empty,
  tenants: [
    {
      id: "t1",
      slug: "acme",
      name: "Acme",
      role: "owner",
      permissions: ["workspace.members.read", "workspace.members.invite"],
    },
  ],
};

describe("hasPlatformPerm", () => {
  it("returns false when `me` is null", () => {
    expect(hasPlatformPerm(null, "platform.users.read")).toBe(false);
  });

  it("returns false when the key is not granted", () => {
    expect(hasPlatformPerm(platformAdmin, "platform.settings.manage")).toBe(false);
  });

  it("returns true when the key is granted", () => {
    expect(hasPlatformPerm(platformAdmin, "platform.users.read")).toBe(true);
  });
});

describe("hasWorkspacePerm", () => {
  it("returns false when `me` is null", () => {
    expect(hasWorkspacePerm(null, "t1", "workspace.members.read")).toBe(false);
  });

  it("returns false for an unknown workspace id", () => {
    expect(hasWorkspacePerm(tenantOwner, "missing", "workspace.members.read")).toBe(false);
  });

  it("returns true when the workspace grants the key", () => {
    expect(hasWorkspacePerm(tenantOwner, "t1", "workspace.members.invite")).toBe(true);
  });

  it("returns false when the workspace exists but does not grant the key", () => {
    expect(hasWorkspacePerm(tenantOwner, "t1", "workspace.audit.read")).toBe(false);
  });
});

describe("findTenant", () => {
  it("returns the tenant by id", () => {
    expect(findTenant(tenantOwner, "t1")?.slug).toBe("acme");
  });

  it("returns undefined for an unknown id", () => {
    expect(findTenant(tenantOwner, "nope")).toBeUndefined();
  });

  it("returns undefined when `me` is null", () => {
    expect(findTenant(null, "t1")).toBeUndefined();
  });
});

describe("getDefaultLandingPath", () => {
  it("sends platform users to /platform", () => {
    expect(getDefaultLandingPath(platformAdmin)).toBe("/platform");
  });

  it("sends tenant-only users to their first workspace", () => {
    expect(getDefaultLandingPath(tenantOwner)).toBe("/workspace/t1");
  });

  it("sends unprovisioned users to /onboarding", () => {
    expect(getDefaultLandingPath(empty)).toBe("/onboarding");
  });

  it("returns /sign-in when `me` is null", () => {
    expect(getDefaultLandingPath(null)).toBe("/sign-in");
  });
});
