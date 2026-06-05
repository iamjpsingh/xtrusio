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
    expect(resolveRoute({ session: null, me: null }, "/", null)).toEqual({
      kind: "redirect",
      to: "/sign-in",
    });
  });

  it("allows /sign-up when unauth", () => {
    expect(resolveRoute({ session: null, me: null }, "/sign-up", null)).toEqual({ kind: "render" });
  });

  it("allows /forgot-password and /reset-password when unauth", () => {
    expect(resolveRoute({ session: null, me: null }, "/forgot-password", null)).toEqual({
      kind: "render",
    });
    expect(resolveRoute({ session: null, me: null }, "/reset-password", null)).toEqual({
      kind: "render",
    });
  });

  it("renders /reset-password even with a (recovery) session so the form survives setSession", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/reset-password", null)).toEqual({
      kind: "render",
    });
  });

  it("renders /accept-invite when unauth so the loader can consume the invite-link hash", () => {
    // A sessionless invitee arrives from a GoTrue invite link with the session
    // in the URL hash. The route must NOT bounce to /sign-in before the loader
    // calls setSession.
    expect(resolveRoute({ session: null, me: null }, "/accept-invite", null)).toEqual({
      kind: "render",
    });
  });

  it("pending invite forces /accept-invite", () => {
    expect(resolveRoute({ session: "s", me: pending }, "/platform", null)).toEqual({
      kind: "redirect",
      to: "/accept-invite",
    });
  });

  it("super_admin lands on /platform from /", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/", null)).toEqual({
      kind: "redirect",
      to: "/platform",
    });
  });

  it("super_admin can navigate /platform/settings", () => {
    expect(resolveRoute({ session: "s", me: sa }, "/platform/settings", null)).toEqual({
      kind: "render",
    });
  });

  it("tenant member redirected away from /platform/*", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/platform/settings", null)).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("tenant member can navigate to their own /workspace/$id", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/t1", null)).toEqual({
      kind: "render",
    });
  });

  it("tenant member can navigate to a nested /workspace/$id/members", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/t1/members", null)).toEqual({
      kind: "render",
    });
  });

  it("tenant member redirected away from a workspace they don't belong to", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/workspace/other", null)).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("tenant member lands on their first workspace from /", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/", null)).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("unprovisioned forced to /onboarding from /platform", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/platform", null)).toEqual({
      kind: "redirect",
      to: "/onboarding",
    });
  });

  it("unprovisioned on /onboarding renders", () => {
    expect(resolveRoute({ session: "s", me: unprov }, "/onboarding", null)).toEqual({
      kind: "render",
    });
  });

  it("honours the passed last-selected workspace on / (L9: no localStorage read)", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/", "t1")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });

  it("falls back to default landing when the passed last-selected workspace is unknown", () => {
    expect(resolveRoute({ session: "s", me: tenant }, "/", "missing")).toEqual({
      kind: "redirect",
      to: "/workspace/t1",
    });
  });
});
