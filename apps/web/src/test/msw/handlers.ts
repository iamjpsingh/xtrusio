// apps/web/src/test/msw/handlers.ts
//
// Default MSW handlers (F.2, finding H13). These intercept the real `fetch`
// calls that `lib/api.ts` issues, so converted component tests exercise the
// genuine `apiFetch` → network → JSON-parse path instead of stubbing
// `lib/api`. Return bodies are the typed fixtures, so the api-fetch ↔ schema
// alignment is checked by the type system.
//
// The base URL matches the hermetic `VITE_API_BASE_URL` set in vitest.config.ts.
// Per-test overrides go through `server.use(...)` in the individual specs.

import { HttpResponse, http } from "msw";
import type {
  AuditCatalog,
  AuditEventsPage,
  JobRunsPage,
  PermissionsCatalog,
  PlatformRoleGrantsPage,
  PlatformRoleOut,
  PlatformRolesPage,
  PlatformUsersPage,
  TenantsPage,
} from "@xtrusio/api-types";
import {
  auditEventCreate,
  meSuperAdmin,
  permissionsCatalog,
  platformRoleAuditor,
  platformRoleGrantAuditor,
  platformUserAna,
  platformUserBen,
  tenantAcme,
  tenantGlobex,
} from "./fixtures";

const API = "http://api.test.invalid";

export const handlers = [
  http.get(`${API}/api/me`, () => HttpResponse.json(meSuperAdmin)),

  http.get(`${API}/api/permissions/catalog`, () =>
    HttpResponse.json<PermissionsCatalog>(permissionsCatalog),
  ),

  // Worker/system job-run log (default empty page).
  http.get(`${API}/api/platform/job-runs`, () =>
    HttpResponse.json<JobRunsPage>({ items: [], next_cursor: null }),
  ),

  // Audit event catalog (activity-feed filter dropdown + action labels).
  http.get(`${API}/api/audit/catalog`, () =>
    HttpResponse.json<AuditCatalog>({
      categories: [
        { key: "roles", label: "Roles" },
        { key: "grants", label: "Grants" },
        { key: "invites", label: "Invites" },
      ],
      actions: [
        { action: "platform_role.create", label: "Created platform role", category: "roles" },
      ],
    }),
  ),

  // ----- Platform roles -----
  http.get(`${API}/api/platform/roles`, () =>
    HttpResponse.json<PlatformRolesPage>({ items: [platformRoleAuditor], next_cursor: null }),
  ),
  http.post(`${API}/api/platform/roles`, async ({ request }) => {
    const body = (await request.json()) as Partial<PlatformRoleOut>;
    const created: PlatformRoleOut = {
      ...platformRoleAuditor,
      id: "10000000-0000-0000-0000-0000000000ff",
      key: body.key ?? platformRoleAuditor.key,
      name: body.name ?? platformRoleAuditor.name,
      description: body.description ?? null,
      permission_keys: body.permission_keys ?? [],
    };
    return HttpResponse.json<PlatformRoleOut>(created, { status: 201 });
  }),
  http.patch(`${API}/api/platform/roles/:id`, async ({ request, params }) => {
    const body = (await request.json()) as Partial<PlatformRoleOut>;
    return HttpResponse.json<PlatformRoleOut>({
      ...platformRoleAuditor,
      id: String(params.id),
      name: body.name ?? platformRoleAuditor.name,
      description: body.description ?? platformRoleAuditor.description,
      permission_keys: body.permission_keys ?? platformRoleAuditor.permission_keys,
    });
  }),
  http.delete(`${API}/api/platform/roles/:id`, () => new HttpResponse(null, { status: 204 })),

  // ----- Platform users + grants -----
  http.get(`${API}/api/platform/users`, () =>
    HttpResponse.json<PlatformUsersPage>({
      items: [platformUserAna, platformUserBen],
      next_cursor: null,
    }),
  ),
  http.get(`${API}/api/platform/users/:userId/roles`, () =>
    HttpResponse.json<PlatformRoleGrantsPage>({
      items: [platformRoleGrantAuditor],
      next_cursor: null,
    }),
  ),

  // ----- Client tenants (platform Clients page) -----
  // `GET /api/tenants` returns the `TenantsPage` envelope, NOT a bare array.
  http.get(`${API}/api/tenants`, () =>
    HttpResponse.json<TenantsPage>({ items: [tenantAcme, tenantGlobex], next_cursor: null }),
  ),

  // ----- Platform audit log -----
  http.get(`${API}/api/platform/audit-log`, () =>
    HttpResponse.json<AuditEventsPage>({ items: [auditEventCreate], next_cursor: null }),
  ),
];
