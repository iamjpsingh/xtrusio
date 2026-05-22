// apps/web/src/lib/route-resolver.test.ts
import { describe, expect, it } from "vitest";
import type { MeResponse } from "@xtrusio/api-types";
import { resolveRoute } from "./route-resolver";

const unprov: MeResponse = {
  user_id: "u",
  email: "x@x.com",
  platform: null,
  platform_permissions: [],
  tenants: [],
  pending_invite: null,
};
const sa: MeResponse = {
  ...unprov,
  platform: { role: "super_admin", is_active: true },
  platform_permissions: ["platform.users.read", "platform.settings.manage"],
};
const tenant: MeResponse = {
  ...unprov,
  tenants: [
    {
      id: "t1",
      slug: "acme",
      name: "Acme",
      role: "owner",
      permissions: ["workspace.members.read"],
    },
  ],
};
const pending: MeResponse = {
  ...unprov,
  pending_invite: { kind: "tenant", id: "i", tenant_id: "t", role: "admin" },
};

describe("resolveRoute", () => {
  it("redirects unauth to /sign-in", () => {
    expect(resolveRoute({ session: null, me: null }, "/")).toEqual({
      kind: "redirect",
      to: "/sign-in",
    });
  });

  it("allows /sign-up when unauth", () => {
    expect(resolveRoute({ session: null, me: null }, "/sign-up")).toEqual({ kind: "render" });
  });

  it("pending invite forces /accept-invite", () => {
    expect(resolveRoute({ session: "s", me: pending }, "/platform")).toEqual({
      kind: "redirect",
      to: "/accept-invite",
    });
  });

  it("super_admin lands on /platform from /", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/")).toEqual({
      kind: "redirect",
      to: "/platform",
    });
  });

  it("super_admin can navigate /platform/settings", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/platform/settings")).toEqual({
      kind: "render",
    });
  });

  it("tenant member redirected away from /platform/*", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/platform/settings")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("tenant member can navigate to their own /workspace/$id", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/t1")).toEqual({
      kind: "render",
    });
  });

  it("tenant member can navigate to a nested /workspace/$id/members", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/t1/members")).toEqual({
      kind: "render",
    });
  });

  it("tenant member redirected away from a workspace they don't belong to", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/other")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("tenant member lands on their first workspace from /", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("unprovisioned forced to /onboarding from /platform", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/platform")).toEqual({
      kind: "redirect",
      to: "/onboarding",
    });
  });

  it("unprovisioned on /onboarding renders", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/onboarding")).toEqual({
      kind: "render",
    });
  });

  it("honours last-selected workspace from localStorage on /", () => {
    window.localStorage.setItem("xtrusio.last-workspace", "t1");
    expect(resolveRoute({ session: "s", me: tenant }, "/")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
    window.localStorage.clear();
  });

  it("falls back to default landing when last-selected workspace is unknown", () => {
    window.localStorage.setItem("xtrusio.last-workspace", "missing");
    expect(resolveRoute({ session: "s", me: tenant }, "/")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
    window.localStorage.clear();
  });
});
