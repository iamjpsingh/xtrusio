// apps/web/src/lib/me-adapter.ts
// Legacy-compat adapter over the pinned MeResponse shape from
// @xtrusio/api-types. Exposes permission-key checks so call sites migrate off
// `me.platform.role === "super_admin"` style enum reads. Enum fields stay
// available on MeResponse until every consumer is converted (later phase).

import { useQuery } from "@tanstack/react-query";
import type { MeResponse, PermissionKey, TenantContext } from "@xtrusio/api-types";
import { fetchMe } from "./api";
import { qk } from "./query-keys";

export function hasPlatformPerm(me: MeResponse | null, key: PermissionKey): boolean {
  if (!me) return false;
  return me.platform_permissions.includes(key);
}

/**
 * Super-admin gate for platform-user *provisioning* (direct-create + invite).
 * This is a ROLE check, not a permission check: a platform `admin` holds
 * `platform.users.manage` (so they may grant/revoke roles) but must NOT be
 * able to mint new platform users. The backend enforces the same super_admin
 * gate on the POST endpoints; this is the matching UI guard.
 */
export function isSuperAdmin(me: MeResponse | null): boolean {
  return me?.platform?.role === "super_admin";
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
    queryKey: qk.me(),
    queryFn: fetchMe,
    refetchOnWindowFocus: false,
  });
  return { me: data ?? null, isLoading };
}
