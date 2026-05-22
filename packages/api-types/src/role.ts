// packages/api-types/src/role.ts
// Mirror of apps/api/src/xtrusio_api/schemas/platform_role.py and
// apps/api/src/xtrusio_api/schemas/workspace_role.py. The Grant types are
// included now so future P6d code (grant-management UIs) can import them
// without another api-types release.

import type { PermissionKey } from "./me";

export type PlatformRoleIn = {
  key: string;
  name: string;
  description: string | null;
  permission_keys: PermissionKey[];
};

export type PlatformRolePatch = {
  name?: string | null;
  description?: string | null;
  permission_keys?: PermissionKey[] | null;
};

export type PlatformRoleOut = {
  id: string;
  key: string;
  name: string;
  description: string | null;
  is_system: boolean;
  permission_keys: PermissionKey[];
  created_at: string;
  updated_at: string;
};

export type PlatformRolesPage = {
  items: PlatformRoleOut[];
  next_cursor: string | null;
};

export type PlatformRoleGrantIn = { role_id: string };

export type PlatformRoleGrantOut = {
  id: string;
  auth_user_id: string;
  role_id: string;
  role_key: string;
  granted_at: string;
  granted_by: string | null;
};

export type PlatformRoleGrantsPage = {
  items: PlatformRoleGrantOut[];
  next_cursor: string | null;
};

export type WorkspaceRoleIn = PlatformRoleIn;
export type WorkspaceRolePatch = PlatformRolePatch;

export type WorkspaceRoleOut = PlatformRoleOut & { workspace_id: string };

export type WorkspaceRolesPage = {
  items: WorkspaceRoleOut[];
  next_cursor: string | null;
};

export type WorkspaceRoleGrantIn = { role_id: string };

export type WorkspaceRoleGrantOut = {
  id: string;
  auth_user_id: string;
  workspace_id: string;
  role_id: string;
  role_key: string;
  granted_at: string;
  granted_by: string | null;
};

export type WorkspaceRoleGrantsPage = {
  items: WorkspaceRoleGrantOut[];
  next_cursor: string | null;
};
