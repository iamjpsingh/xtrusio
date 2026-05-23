// packages/api-types/src/workspace-member-list.ts
// Mirror of apps/api/src/xtrusio_api/schemas/workspace_member_list.py.
// email can be null when the auth.users row has been hard-deleted (the
// service uses a LEFT JOIN so the membership row still surfaces).

import type { TenantRole } from "./me";

export type WorkspaceMemberListItem = {
  user_id: string;
  email: string | null;
  role: TenantRole;
  joined_at: string;
  granted_role_count: number;
};

export type WorkspaceMembersPage = {
  items: WorkspaceMemberListItem[];
  next_cursor: string | null;
};
