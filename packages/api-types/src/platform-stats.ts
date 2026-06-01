// packages/api-types/src/platform-stats.ts
//
// Thin re-export of the generated OpenAPI PlatformStats schema (GET
// /api/platform/stats). Each field is `number | null`: `null` means the
// caller is not authorized for that metric, and the frontend omits its card.

import type { components } from "../generated/openapi";

export type PlatformStats = components["schemas"]["PlatformStats"];
