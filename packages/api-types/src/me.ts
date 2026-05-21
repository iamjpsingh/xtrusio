// packages/api-types/src/me.ts
// Mirror of apps/api/src/xtrusio_api/schemas/me.py:MeResponse. The enum
// fields (`platform.role`, `tenants[].role`) are kept ADDITIVELY alongside
// the resolver-derived permission arrays so frontend consumers can migrate
// component-by-component. The enum fields will be removed in a later phase
// once every consumer reads permissions instead.

export type PlatformRole = "super_admin" | "admin" | "editor";
export type TenantRole = "owner" | "admin" | "editor" | "read_only";

/** Permission key as defined in apps/api/src/xtrusio_api/rbac/catalog.py. */
export type PermissionKey = string;

export type PlatformContext = {
  role: PlatformRole;
  is_active: boolean;
};

export type TenantContext = {
  id: string;
  slug: string;
  name: string;
  role: TenantRole;
  /** Resolver-derived effective workspace permission keys. */
  permissions: PermissionKey[];
};

export type PendingInvite = {
  kind: "platform" | "tenant";
  id: string;
  tenant_id: string | null;
  role: string;
};

export type MeResponse = {
  user_id: string;
  email: string;
  platform: PlatformContext | null;
  /** Resolver-derived effective platform permission keys (empty if none). */
  platform_permissions: PermissionKey[];
  tenants: TenantContext[];
  pending_invite: PendingInvite | null;
};
