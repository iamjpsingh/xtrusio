// packages/api-types/src/platform-user-list.ts
//
// Thin re-exports of the generated OpenAPI platform-users-list schemas (F.3,
// finding H13). The backend Pydantic model is named `PlatformUserListItemOut`;
// the existing frontend consumers import `PlatformUserListItem`, so the
// public name is kept as an alias over the generated schema.

import type { components } from "../generated/openapi";

export type PlatformUserListItem = components["schemas"]["PlatformUserListItemOut"];
export type PlatformUsersPage = components["schemas"]["PlatformUsersPage"];
