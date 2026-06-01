// Central registry for every TanStack Query key tuple. Every consumer must
// import keys from here (never inline strings) so cache invalidation never
// silently misses.

export const qk = {
  // Identity / global.
  me: () => ["me"] as const,
  tenants: () => ["tenants"] as const,
  acceptInvite: () => ["accept-invite"] as const,
  signupStatus: () => ["signup-status"] as const,
  platformSettings: () => ["platform", "settings"] as const,
  permissionsCatalog: () => ["permissions", "catalog"] as const,
  platformRoles: () => ["platform", "roles"] as const,
  workspaceRoles: (workspaceId: string) => ["workspace", workspaceId, "roles"] as const,
  platformAudit: () => ["platform", "audit-log"] as const,
  workspaceAudit: (workspaceId: string) => ["workspace", workspaceId, "audit-log"] as const,
  // Dashboard metrics (one round-trip per dashboard).
  platformStats: () => ["platform", "stats"] as const,
  workspaceStats: (workspaceId: string) => ["workspace", workspaceId, "stats"] as const,
  // Invite lists. `tenantInvites` (platform-clients view, keyed by tenant id)
  // and `workspaceInvites` (workspace-members view) target different backend
  // resources, so the tuples stay distinct — only the shape is unified.
  tenantInvites: (tenantId: string) => ["tenant", tenantId, "invites"] as const,
  workspaceInvites: (workspaceId: string) => ["workspace", workspaceId, "invites"] as const,
  // P6d list/settings keys. The infinite-query lists key on the base tuple;
  // pages live inside one cache entry (no per-cursor key).
  platformUsers: () => ["platform-users"] as const,
  workspaceMembers: (workspaceId: string) => ["workspace-members", workspaceId] as const,
  workspaceSettings: (workspaceId: string) => ["workspace-settings", workspaceId] as const,
  // Grant lists per (scope, user[, workspace]). Used by <GrantManagerDialog>.
  platformRoleGrants: (userId: string) => ["platform-role-grants", userId] as const,
  workspaceRoleGrants: (workspaceId: string, userId: string) =>
    ["workspace-role-grants", workspaceId, userId] as const,
};
