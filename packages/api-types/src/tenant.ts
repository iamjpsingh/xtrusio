// packages/api-types/src/tenant.ts
//
// Thin re-exports of the generated OpenAPI tenant schemas. `GET /api/tenants`
// returns the cursor-paginated `TenantsPage` envelope (`items` + `next_cursor`),
// NOT a bare `TenantOut[]`. The public names match the backend Pydantic models
// (`TenantOut` / `TenantsPage`) so a drift between backend and frontend shows
// up as a TYPE error in the consumers.

import type { components } from "../generated/openapi";

export type TenantOut = components["schemas"]["TenantOut"];
export type TenantsPage = components["schemas"]["TenantsPage"];
