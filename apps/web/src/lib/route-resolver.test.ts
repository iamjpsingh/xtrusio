import { describe, expect, it } from "vitest";
import { resolveRoute, type MeResponse } from "./route-resolver";

const unprov: MeResponse = {
  user_id: "u",
  email: "x@x.com",
  platform: null,
  tenants: [],
  pending_invite: null,
};
const sa: MeResponse = { ...unprov, platform: { role: "super_admin", is_active: true } };
const tenant: MeResponse = {
  ...unprov,
  tenants: [{ id: "t", slug: "acme", name: "Acme", role: "owner" }],
};
const pending: MeResponse = {
  ...unprov,
  pending_invite: { kind: "tenant", id: "i", tenant_id: "t", role: "admin" },
};

describe("resolveRoute", () => {
  it("redirects unauth to /sign-in", () => {
    expect(resolveRoute({ session: null, me: null }, "/")).toEqual({ kind: "redirect", to: "/sign-in" });
  });
  it("allows /sign-up when unauth", () => {
    expect(resolveRoute({ session: null, me: null }, "/sign-up")).toEqual({ kind: "render" });
  });
  it("pending invite forces /accept-invite", () => {
    expect(resolveRoute({ session: "s", me: pending }, "/")).toEqual({
      kind: "redirect",
      to: "/accept-invite",
    });
  });
  it("super_admin can navigate platform routes", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/settings")).toEqual({ kind: "render" });
  });
  it("tenant_member redirected away from /settings", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/settings")).toEqual({
      kind: "redirect",
      to: "/",
    });
  });
  it("unprovisioned forced to /onboarding", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/")).toEqual({
      kind: "redirect",
      to: "/onboarding",
    });
  });
  it("unprovisioned on /onboarding renders", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/onboarding")).toEqual({
      kind: "render",
    });
  });
});
