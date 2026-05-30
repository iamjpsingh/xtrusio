// packages/api-types/src/workspace-member-list.ts
//
// Thin re-exports of the generated OpenAPI workspace-members-list schemas (F.3,
// finding H13). `email` can be null when the auth.users row has been
// hard-deleted (the service uses a LEFT JOIN so the membership row still
// surfaces). The backend Pydantic model is `WorkspaceMemberListItemOut`; the
// public name is kept as `WorkspaceMemberListItem` for existing consumers.

import type { components } from "../generated/openapi";

export type WorkspaceMemberListItem = components["schemas"]["WorkspaceMemberListItemOut"];
export type WorkspaceMembersPage = components["schemas"]["WorkspaceMembersPage"];
