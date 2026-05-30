// packages/api-types/src/role.ts
//
// Thin re-exports of the generated OpenAPI role + grant schemas (F.3, finding
// H13). The platform and workspace variants are distinct backend Pydantic
// models (workspace adds `workspace_id`), so each re-exports its own generated
// schema rather than aliasing across scopes.

import type { components } from "../generated/openapi";

export type PlatformRoleIn = components["schemas"]["PlatformRoleIn"];
export type PlatformRolePatch = components["schemas"]["PlatformRolePatch"];
export type PlatformRoleOut = components["schemas"]["PlatformRoleOut"];
export type PlatformRolesPage = components["schemas"]["PlatformRolesPage"];

export type PlatformRoleGrantIn = components["schemas"]["PlatformRoleGrantIn"];
export type PlatformRoleGrantOut = components["schemas"]["PlatformRoleGrantOut"];
export type PlatformRoleGrantsPage = components["schemas"]["PlatformRoleGrantsPage"];

export type WorkspaceRoleIn = components["schemas"]["WorkspaceRoleIn"];
export type WorkspaceRolePatch = components["schemas"]["WorkspaceRolePatch"];
export type WorkspaceRoleOut = components["schemas"]["WorkspaceRoleOut"];
export type WorkspaceRolesPage = components["schemas"]["WorkspaceRolesPage"];

export type WorkspaceRoleGrantIn = components["schemas"]["WorkspaceRoleGrantIn"];
export type WorkspaceRoleGrantOut = components["schemas"]["WorkspaceRoleGrantOut"];
export type WorkspaceRoleGrantsPage = components["schemas"]["WorkspaceRoleGrantsPage"];
