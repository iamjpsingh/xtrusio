// apps/web/src/test/msw/fixtures.ts
//
// Real-shape JSON fixtures for the MSW handlers (F.2, finding H13). Every value
// is typed with the `@xtrusio/api-types` re-exports of the OpenAPI schema, so a
// drift between what the backend returns and what the frontend expects shows up
// as a TYPE error here — the api-fetch ↔ schema alignment is exercised in test
// code, not just asserted in prose.
//
// No real users / no real secrets — these are deterministic @example.com test
// fixtures only.

import type {
  AuditEventOut,
  MeResponse,
  PermissionsCatalog,
  PlatformRoleGrantOut,
  PlatformRoleOut,
  PlatformUserListItem,
  TenantOut,
} from "@xtrusio/api-types";

export const meSuperAdmin: MeResponse = {
  user_id: "00000000-0000-0000-0000-000000000001",
  email: "super@example.com",
  platform: { role: "super_admin", is_active: true },
  platform_permissions: [
    "platform.roles.manage",
    "platform.users.read",
    "platform.users.manage",
    "platform.audit.read",
  ],
  tenants: [],
  pending_invite: null,
};

// A platform *admin* (not super_admin). Holds `platform.users.manage` — so the
// per-row Manage roles affordance still shows — but must NOT see the
// super_admin-only "Add platform user" provisioning entry point.
export const mePlatformAdmin: MeResponse = {
  ...meSuperAdmin,
  user_id: "00000000-0000-0000-0000-000000000002",
  email: "admin@example.com",
  platform: { role: "admin", is_active: true },
};

export const permissionsCatalog: PermissionsCatalog = {
  items: [
    {
      scope: "platform",
      key: "platform.users.read",
      category: "Platform users",
      description: "View platform users",
    },
    {
      scope: "platform",
      key: "platform.users.manage",
      category: "Platform users",
      description: "Manage platform users",
    },
  ],
};

export const platformRoleAuditor: PlatformRoleOut = {
  id: "10000000-0000-0000-0000-000000000001",
  key: "auditor",
  name: "Auditor",
  description: "Read-only auditor",
  is_system: false,
  permission_keys: ["platform.users.read"],
  created_at: "2026-05-22T00:00:00Z",
  updated_at: "2026-05-22T00:00:00Z",
};

export const platformUserAna: PlatformUserListItem = {
  id: "20000000-0000-0000-0000-000000000001",
  email: "ana@example.com",
  role: "admin",
  is_active: true,
  created_at: "2026-05-01T00:00:00Z",
  last_sign_in_at: "2026-05-20T08:00:00Z",
  granted_role_count: 2,
};

export const platformUserBen: PlatformUserListItem = {
  id: "20000000-0000-0000-0000-000000000002",
  email: "ben@example.com",
  role: "editor",
  is_active: false,
  created_at: "2026-05-02T00:00:00Z",
  last_sign_in_at: null,
  granted_role_count: 0,
};

// Client tenants surfaced by the platform Clients page (`GET /api/tenants`).
export const tenantAcme: TenantOut = {
  id: "50000000-0000-0000-0000-000000000001",
  slug: "acme-corp",
  name: "Acme Corp",
  created_at: "2026-05-10T00:00:00Z",
  updated_at: "2026-05-10T00:00:00Z",
  created_by: meSuperAdmin.user_id,
};

export const tenantGlobex: TenantOut = {
  id: "50000000-0000-0000-0000-000000000002",
  slug: "globex",
  name: "Globex",
  created_at: "2026-05-11T00:00:00Z",
  updated_at: "2026-05-11T00:00:00Z",
  created_by: meSuperAdmin.user_id,
};

export const platformRoleGrantAuditor: PlatformRoleGrantOut = {
  id: "30000000-0000-0000-0000-000000000001",
  auth_user_id: platformUserAna.id,
  role_id: platformRoleAuditor.id,
  role_key: "auditor",
  granted_at: "2026-05-21T00:00:00Z",
  granted_by: meSuperAdmin.user_id,
};

export const auditEventCreate: AuditEventOut = {
  id: 1001,
  actor_auth_user_id: meSuperAdmin.user_id,
  actor_email: "super@example.com",
  action: "platform_role.create",
  target_type: "platform_role",
  target_id: platformRoleAuditor.id,
  scope: "platform",
  workspace_id: null,
  before: null,
  after: { key: "auditor", name: "Auditor" },
  created_at: "2026-05-22T00:00:01Z",
};

export const auditEventDelete: AuditEventOut = {
  id: 1002,
  actor_auth_user_id: meSuperAdmin.user_id,
  actor_email: "super@example.com",
  action: "platform_role.delete",
  target_type: "platform_role",
  target_id: platformRoleAuditor.id,
  scope: "platform",
  workspace_id: null,
  before: { key: "auditor", name: "Auditor" },
  after: null,
  created_at: "2026-05-22T00:00:02Z",
};
