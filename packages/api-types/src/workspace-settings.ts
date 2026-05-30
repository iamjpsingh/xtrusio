// packages/api-types/src/workspace-settings.ts
//
// Thin re-exports of the generated OpenAPI workspace-settings schemas (F.3,
// finding H13). P6d MVP only exposes `name` as mutable; slug/timestamps are
// read-only.

import type { components } from "../generated/openapi";

export type WorkspaceSettingsOut = components["schemas"]["WorkspaceSettingsOut"];
export type WorkspaceSettingsUpdate = components["schemas"]["WorkspaceSettingsUpdate"];
