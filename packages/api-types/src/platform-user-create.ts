// packages/api-types/src/platform-user-create.ts
//
// Thin re-exports of the generated OpenAPI direct-create platform-user
// schemas. The backend Pydantic models are `PlatformUserCreate` (request) and
// `PlatformUserCreated` (response); the public TS names match.

import type { components } from "../generated/openapi";

export type PlatformUserCreate = components["schemas"]["PlatformUserCreate"];
export type PlatformUserCreated = components["schemas"]["PlatformUserCreated"];
