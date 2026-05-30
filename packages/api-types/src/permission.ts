// packages/api-types/src/permission.ts
//
// Thin re-exports of the generated OpenAPI permission-catalog schemas (F.3,
// finding H13). `PermissionScope` has no standalone OpenAPI schema (the backend
// inlines it as an enum on `PermissionDef.scope`), so it stays hand-written as
// a UI convenience alias derived from the generated `PermissionDef`.

import type { components } from "../generated/openapi";

export type PermissionDef = components["schemas"]["PermissionDef"];

/** Derived from the generated `PermissionDef.scope` enum so it never drifts. */
export type PermissionScope = PermissionDef["scope"];

export type PermissionsCatalog = components["schemas"]["PermissionsCatalog"];
