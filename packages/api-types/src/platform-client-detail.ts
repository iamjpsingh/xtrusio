// packages/api-types/src/platform-client-detail.ts
//
// Thin re-exports of the generated OpenAPI client-detail schemas for
// `GET /api/platform/clients/{slug}` (platform-scope view of one client tenant
// + its members). `members` is an INLINE list (no pagination) — see the backend
// `PlatformClientDetail` docstring for the bounded-membership rationale.
// `email`/`owner_email` can be null when the auth.users row was hard-deleted.

import type { components } from "../generated/openapi";

export type PlatformClientDetail = components["schemas"]["PlatformClientDetail"];
export type PlatformClientMember = components["schemas"]["PlatformClientMember"];
