// Central registry for every TanStack Query key tuple. Every consumer must
// import keys from here (never inline strings) so cache invalidation never
// silently misses.

export const qk = {
  permissionsCatalog: () => ["permissions", "catalog"] as const,
  platformRoles: () => ["platform", "roles"] as const,
  workspaceRoles: (workspaceId: string) =>
    ["workspace", workspaceId, "roles"] as const,
  platformAudit: () => ["platform", "audit-log"] as const,
  workspaceAudit: (workspaceId: string) =>
    ["workspace", workspaceId, "audit-log"] as const,
  workspaceInvites: (workspaceId: string) =>
    ["workspace", workspaceId, "invites"] as const,
};
