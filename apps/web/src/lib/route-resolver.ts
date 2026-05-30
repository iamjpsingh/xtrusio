// apps/web/src/lib/route-resolver.ts
import type { MeResponse } from "@xtrusio/api-types";
import { getDefaultLandingPath } from "./me-adapter";
import { PLATFORM_SENTINEL } from "./last-workspace";

export type { MeResponse };
export type AuthState = { session: string | null; me: MeResponse | null };
export type RouteDecision = { kind: "render" } | { kind: "redirect"; to: string };

const PUBLIC = new Set(["/sign-in", "/sign-up"]);
const UNGATED_AUTHED = new Set(["/onboarding", "/accept-invite"]);

function isPlatformPath(path: string): boolean {
  return path === "/platform" || path.startsWith("/platform/");
}

function workspaceIdFromPath(path: string): string | null {
  // Matches /workspace/<id> and /workspace/<id>/...
  const m = /^\/workspace\/([^/]+)(?:\/.*)?$/.exec(path);
  return m ? (m[1] ?? null) : null;
}

/**
 * Pure route decision. `lastWorkspace` is passed in by the caller (read once
 * via `readLastWorkspace()`) rather than read from localStorage here, so the
 * resolver has no side effects and stays trivially testable (L9).
 */
export function resolveRoute(
  state: AuthState,
  path: string,
  lastWorkspace: string | null,
): RouteDecision {
  if (!state.session) {
    return PUBLIC.has(path) ? { kind: "render" } : { kind: "redirect", to: "/sign-in" };
  }
  if (!state.me) return { kind: "render" }; // spinner rendered by caller while /me loads

  const me = state.me;

  // Pending invite takes precedence over every authed path.
  if (me.pending_invite) {
    return path === "/accept-invite"
      ? { kind: "render" }
      : { kind: "redirect", to: "/accept-invite" };
  }

  // Ungated authed pages (onboarding, accept-invite when no pending invite).
  if (UNGATED_AUTHED.has(path)) {
    if (path === "/onboarding" && (me.platform || me.tenants.length > 0)) {
      return { kind: "redirect", to: getDefaultLandingPath(me) };
    }
    return { kind: "render" };
  }

  // Platform shell — only when user has a platform context.
  if (isPlatformPath(path)) {
    return me.platform ? { kind: "render" } : { kind: "redirect", to: getDefaultLandingPath(me) };
  }

  // Workspace shell — only when the workspace id matches one of the user's tenants.
  const wid = workspaceIdFromPath(path);
  if (wid !== null) {
    const belongs = me.tenants.some((t) => t.id === wid);
    return belongs ? { kind: "render" } : { kind: "redirect", to: getDefaultLandingPath(me) };
  }

  // Anything else (notably "/") → honour last-selected scope if it's still valid,
  // otherwise fall back to the default landing.
  if (path === "/") {
    const last = lastWorkspace;
    if (last === PLATFORM_SENTINEL && me.platform) {
      return { kind: "redirect", to: "/platform" };
    }
    if (last && last !== PLATFORM_SENTINEL && me.tenants.some((t) => t.id === last)) {
      return { kind: "redirect", to: `/workspace/${last}` };
    }
  }
  return { kind: "redirect", to: getDefaultLandingPath(me) };
}
