import type { MeResponse } from "@xtrusio/api-types";

export type { MeResponse };
export type AuthState = { session: string | null; me: MeResponse | null };
export type RouteDecision = { kind: "render" } | { kind: "redirect"; to: string };

const PLATFORM_ONLY = new Set(["/settings", "/users"]);
const PUBLIC = new Set(["/sign-in", "/sign-up"]);

export function resolveRoute(state: AuthState, path: string): RouteDecision {
  if (!state.session) {
    return PUBLIC.has(path) ? { kind: "render" } : { kind: "redirect", to: "/sign-in" };
  }
  if (!state.me) return { kind: "render" }; // spinner is rendered by the caller while /me loads

  const { platform, tenants, pending_invite } = state.me;

  if (pending_invite) {
    return path === "/accept-invite"
      ? { kind: "render" }
      : { kind: "redirect", to: "/accept-invite" };
  }

  if (platform) return { kind: "render" };

  if (tenants.length > 0) {
    return PLATFORM_ONLY.has(path) ? { kind: "redirect", to: "/" } : { kind: "render" };
  }

  // Unprovisioned.
  return path === "/onboarding" ? { kind: "render" } : { kind: "redirect", to: "/onboarding" };
}
