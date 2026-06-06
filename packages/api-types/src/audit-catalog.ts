// packages/api-types/src/audit-catalog.ts
//
// Thin re-exports of the generated OpenAPI audit-catalog schemas (mirrors the
// permissions-catalog re-export). The catalog (action -> label + category) is
// non-secret metadata consumed by the activity-feed filter dropdown + the
// human-readable action labels.

import type { components } from "../generated/openapi";

export type AuditCatalog = components["schemas"]["AuditCatalog"];
export type AuditCategoryDef = components["schemas"]["AuditCategoryDef"];
export type AuditActionDef = components["schemas"]["AuditActionDef"];
