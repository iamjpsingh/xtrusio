import { supabase } from "./supabase";
import type {
  AuditEventsPage,
  MeResponse,
  PermissionsCatalog,
  PlatformRoleGrantOut,
  PlatformRoleGrantsPage,
  PlatformRoleIn,
  PlatformRoleOut,
  PlatformRolePatch,
  PlatformRolesPage,
  PlatformUsersPage,
  WorkspaceMembersPage,
  WorkspaceRoleGrantOut,
  WorkspaceRoleGrantsPage,
  WorkspaceRoleIn,
  WorkspaceRoleOut,
  WorkspaceRolePatch,
  WorkspaceRolesPage,
  WorkspaceSettingsOut,
} from "@xtrusio/api-types";

const baseUrl = import.meta.env.VITE_API_BASE_URL;
if (!baseUrl) {
  throw new Error("VITE_API_BASE_URL must be set in .env");
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: unknown,
  ) {
    super(`API ${status}: ${JSON.stringify(body)}`);
  }

  /** The backend error code from a FastAPI `{ "detail": "<code>" }` body, if present. */
  get code(): string | null {
    if (typeof this.body === "object" && this.body !== null && "detail" in this.body) {
      const d = (this.body as Record<string, unknown>).detail;
      return typeof d === "string" ? d : null;
    }
    return null;
  }
}

/** Extract a backend error code from a thrown value (ApiError.detail, else Error.message). */
export function errorCode(e: unknown): string {
  if (e instanceof ApiError) return e.code ?? "";
  if (e instanceof Error) return e.message;
  return "";
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type") && init?.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }
  const res = await fetch(`${baseUrl}${path}`, { ...init, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function fetchMe(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/api/me");
}

export async function fetchSignupStatus(): Promise<{ signups_enabled: boolean }> {
  return apiFetch("/api/signup-status");
}

export async function postSignup(email: string, password: string): Promise<void> {
  await apiFetch("/api/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function postOnboarding(workspace_name: string): Promise<{
  tenant: { id: string; slug: string; name: string; role: string };
}> {
  return apiFetch("/api/onboarding/tenants", {
    method: "POST",
    body: JSON.stringify({ workspace_name }),
  });
}

export async function fetchPlatformSettings(): Promise<{
  signups_enabled: boolean;
  updated_at: string;
  updated_by_email: string | null;
}> {
  return apiFetch("/api/platform/settings");
}

export async function putPlatformSettings(signups_enabled: boolean): Promise<{
  signups_enabled: boolean;
}> {
  return apiFetch("/api/platform/settings", {
    method: "PUT",
    body: JSON.stringify({ signups_enabled }),
  });
}

export type PlatformInvite = {
  id: string;
  email: string;
  role: "admin" | "editor";
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export type TenantInvite = {
  id: string;
  tenant_id: string;
  email: string;
  role: "admin" | "editor" | "read_only";
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

export async function postPlatformInvite(
  email: string,
  role: "admin" | "editor",
): Promise<PlatformInvite> {
  return apiFetch("/api/platform/users/invites", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function fetchPlatformInvites(): Promise<{ items: PlatformInvite[] }> {
  return apiFetch("/api/platform/users/invites");
}

export async function deletePlatformInvite(id: string): Promise<void> {
  await apiFetch(`/api/platform/users/invites/${id}`, { method: "DELETE" });
}

export async function postTenantInvite(
  tenantId: string,
  email: string,
  role: "admin" | "editor" | "read_only",
): Promise<TenantInvite> {
  return apiFetch(`/api/tenants/${tenantId}/invites`, {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function fetchTenantInvites(tenantId: string): Promise<{ items: TenantInvite[] }> {
  return apiFetch(`/api/tenants/${tenantId}/invites`);
}

export async function deleteTenantInvite(tenantId: string, id: string): Promise<void> {
  await apiFetch(`/api/tenants/${tenantId}/invites/${id}`, { method: "DELETE" });
}

export async function postAcceptInvite(): Promise<{
  kind: "platform" | "tenant";
  role: string;
  tenant_id: string | null;
}> {
  return apiFetch("/api/invites/accept", { method: "POST" });
}

// ----- Permissions catalog (P6c Slice 1A) -----

export async function fetchPermissionsCatalog(): Promise<PermissionsCatalog> {
  return apiFetch<PermissionsCatalog>("/api/permissions/catalog");
}

// ----- Platform role CRUD (consumes P4 routes) -----

export async function fetchPlatformRoles(cursor?: string): Promise<PlatformRolesPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<PlatformRolesPage>(`/api/platform/roles${qs}`);
}

export async function postPlatformRole(body: PlatformRoleIn): Promise<PlatformRoleOut> {
  return apiFetch<PlatformRoleOut>("/api/platform/roles", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function patchPlatformRole(
  id: string,
  body: PlatformRolePatch,
): Promise<PlatformRoleOut> {
  return apiFetch<PlatformRoleOut>(`/api/platform/roles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deletePlatformRole(id: string): Promise<void> {
  await apiFetch(`/api/platform/roles/${id}`, { method: "DELETE" });
}

// ----- Workspace role CRUD (consumes P5 routes) -----

export async function fetchWorkspaceRoles(
  workspaceId: string,
  cursor?: string,
): Promise<WorkspaceRolesPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<WorkspaceRolesPage>(`/api/workspaces/${workspaceId}/roles${qs}`);
}

export async function postWorkspaceRole(
  workspaceId: string,
  body: WorkspaceRoleIn,
): Promise<WorkspaceRoleOut> {
  return apiFetch<WorkspaceRoleOut>(`/api/workspaces/${workspaceId}/roles`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function patchWorkspaceRole(
  workspaceId: string,
  id: string,
  body: WorkspaceRolePatch,
): Promise<WorkspaceRoleOut> {
  return apiFetch<WorkspaceRoleOut>(`/api/workspaces/${workspaceId}/roles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function deleteWorkspaceRole(workspaceId: string, id: string): Promise<void> {
  await apiFetch(`/api/workspaces/${workspaceId}/roles/${id}`, {
    method: "DELETE",
  });
}

// ----- Audit-log (P6c Slice 2) -----

export async function fetchPlatformAuditLog(cursor?: string): Promise<AuditEventsPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<AuditEventsPage>(`/api/platform/audit-log${qs}`);
}

export async function fetchWorkspaceAuditLog(
  workspaceId: string,
  cursor?: string,
): Promise<AuditEventsPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<AuditEventsPage>(`/api/workspaces/${workspaceId}/audit-log${qs}`);
}

// ----- Platform users list (P6d) -----

export async function fetchPlatformUsers(cursor: string | null): Promise<PlatformUsersPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<PlatformUsersPage>(`/api/platform/users${qs}`);
}

// ----- Workspace members list (P6d) -----

export async function fetchWorkspaceMembers(
  workspaceId: string,
  cursor: string | null,
): Promise<WorkspaceMembersPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<WorkspaceMembersPage>(`/api/workspaces/${workspaceId}/members${qs}`);
}

// ----- Workspace settings (P6d) -----

export async function fetchWorkspaceSettings(workspaceId: string): Promise<WorkspaceSettingsOut> {
  return apiFetch<WorkspaceSettingsOut>(`/api/workspaces/${workspaceId}/settings`);
}

export async function updateWorkspaceSettings(
  workspaceId: string,
  body: { name: string },
): Promise<WorkspaceSettingsOut> {
  return apiFetch<WorkspaceSettingsOut>(`/api/workspaces/${workspaceId}/settings`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

// ----- Platform role grants (P4) -----

export async function fetchPlatformRoleGrants(
  userId: string,
  cursor?: string,
): Promise<PlatformRoleGrantsPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<PlatformRoleGrantsPage>(`/api/platform/users/${userId}/roles${qs}`);
}

export async function postPlatformRoleGrant(
  userId: string,
  roleId: string,
): Promise<PlatformRoleGrantOut> {
  return apiFetch<PlatformRoleGrantOut>(`/api/platform/users/${userId}/roles`, {
    method: "POST",
    body: JSON.stringify({ role_id: roleId }),
  });
}

export async function deletePlatformRoleGrant(userId: string, grantId: string): Promise<void> {
  await apiFetch(`/api/platform/users/${userId}/roles/${grantId}`, { method: "DELETE" });
}

// ----- Workspace role grants (P5) -----

export async function fetchWorkspaceRoleGrants(
  workspaceId: string,
  userId: string,
  cursor?: string,
): Promise<WorkspaceRoleGrantsPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<WorkspaceRoleGrantsPage>(
    `/api/workspaces/${workspaceId}/members/${userId}/roles${qs}`,
  );
}

export async function postWorkspaceRoleGrant(
  workspaceId: string,
  userId: string,
  roleId: string,
): Promise<WorkspaceRoleGrantOut> {
  return apiFetch<WorkspaceRoleGrantOut>(`/api/workspaces/${workspaceId}/members/${userId}/roles`, {
    method: "POST",
    body: JSON.stringify({ role_id: roleId }),
  });
}

export async function deleteWorkspaceRoleGrant(
  workspaceId: string,
  userId: string,
  grantId: string,
): Promise<void> {
  await apiFetch(`/api/workspaces/${workspaceId}/members/${userId}/roles/${grantId}`, {
    method: "DELETE",
  });
}
