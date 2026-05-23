// packages/api-types/src/platform-user-list.ts
// Mirror of apps/api/src/xtrusio_api/schemas/platform_user_list.py.

import type { PlatformRole } from "./me";

export type PlatformUserListItem = {
  id: string;
  email: string;
  role: PlatformRole;
  is_active: boolean;
  created_at: string;
  last_sign_in_at: string | null;
  granted_role_count: number;
};

export type PlatformUsersPage = {
  items: PlatformUserListItem[];
  next_cursor: string | null;
};
