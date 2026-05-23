// Central registry for every TanStack Query key tuple. Every consumer must
// import keys from here (never inline strings) so cache invalidation never
// silently misses.

export const qk = {
  permissionsCatalog: () => ["permissions", "catalog"] as const,
  platformRoles: () => ["platform", "roles"] as const,
  workspaceRoles: (workspaceId: string) => ["workspace", workspaceId, "roles"] as const,
  platformAudit: () => ["platform", "audit-log"] as const,
  workspaceAudit: (workspaceId: string) => ["workspace", workspaceId, "audit-log"] as const,
  workspaceInvites: (workspaceId: string) => ["workspace", workspaceId, "invites"] as const,
  // P6d list/settings keys.
  platformUsers: () => ["platform-users"] as const,
  platformUsersWithCursor: (cursor: string | null) => ["platform-users", cursor] as const,
  workspaceMembers: (workspaceId: string) => ["workspace-members", workspaceId] as const,
  workspaceMembersWithCursor: (workspaceId: string, cursor: string | null) =>
    ["workspace-members", workspaceId, cursor] as const,
  workspaceSettings: (workspaceId: string) => ["workspace-settings", workspaceId] as const,
  // Grant lists per (scope, user[, workspace]). Used by <GrantManagerDialog>.
  platformRoleGrants: (userId: string) => ["platform-role-grants", userId] as const,
  workspaceRoleGrants: (workspaceId: string, userId: string) =>
    ["workspace-role-grants", workspaceId, userId] as const,
};
