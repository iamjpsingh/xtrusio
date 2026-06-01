// packages/api-types/src/workspace-stats.ts
//
// Thin re-export of the generated OpenAPI WorkspaceStats schema (GET
// /api/workspaces/{workspace_id}/stats). Each field is `number | null`:
// `null` means the caller lacks that metric's permission, and the frontend
// omits its card.

import type { components } from "../generated/openapi";

export type WorkspaceStats = components["schemas"]["WorkspaceStats"];
