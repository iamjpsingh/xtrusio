// apps/web/src/lib/me-adapter.ts
// Legacy-compat adapter over the pinned MeResponse shape from
// @xtrusio/api-types. Exposes permission-key checks so call sites migrate off
// `me.platform.role === "super_admin"` style enum reads. Enum fields stay
// available on MeResponse until every consumer is converted (later phase).

import { useQuery } from "@tanstack/react-query";
import type { MeResponse, PermissionKey, TenantContext } from "@xtrusio/api-types";
import { fetchMe } from "./api";

export function hasPlatformPerm(me: MeResponse | null, key: PermissionKey): boolean {
  if (!me) return false;
  return me.platform_permissions.includes(key);
}

export function hasWorkspacePerm(
  me: MeResponse | null,
  workspaceId: string,
  key: PermissionKey,
): boolean {
  if (!me) return false;
  const t = me.tenants.find((x) => x.id === workspaceId);
  if (!t) return false;
  return t.permissions.includes(key);
}

export function findTenant(me: MeResponse | null, workspaceId: string): TenantContext | undefined {
  if (!me) return undefined;
  return me.tenants.find((t) => t.id === workspaceId);
}

/**
 * Pick the URL the user should land on when there's no last-selected scope.
 * Order: pending invite > onboarding > platform shell > first workspace.
 */
export function getDefaultLandingPath(me: MeResponse | null): string {
  if (!me) return "/sign-in";
  if (me.pending_invite) return "/accept-invite";
  if (me.platform) return "/platform";
  const first = me.tenants[0];
  if (first) return `/workspace/${first.id}`;
  return "/onboarding";
}

/** Shared `useQuery(['me'])` hook so every consumer reuses the same cache entry. */
export function useMe(): { me: MeResponse | null; isLoading: boolean } {
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    refetchOnWindowFocus: false,
  });
  return { me: data ?? null, isLoading };
}
