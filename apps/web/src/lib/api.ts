import { supabase } from "./supabase";
import { resolveSession } from "./session-cache";
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
  PlatformStats,
  PlatformUserCreate,
  PlatformUserCreated,
  PlatformUsersPage,
  TenantsPage,
  WorkspaceMembersPage,
  WorkspaceRoleGrantOut,
  WorkspaceRoleGrantsPage,
  WorkspaceRoleIn,
  WorkspaceRoleOut,
  WorkspaceRolePatch,
  WorkspaceRolesPage,
  WorkspaceSettingsOut,
  WorkspaceStats,
} from "@xtrusio/api-types";

const baseUrl = import.meta.env.VITE_API_BASE_URL;
if (!baseUrl) {
  throw new Error("VITE_API_BASE_URL must be set in .env");
}

/** Default per-request timeout. Overridable via apiFetch's 4th argument. */
const DEFAULT_TIMEOUT_MS = 20_000;

export class ApiError extends Error {
  /**
   * Structured backend error code (the top-level body key, e.g. `detail`),
   * NOT a stringification of the whole body. `.message` is the code or
   * `API <status>` — never raw JSON (L8/H2).
   */
  readonly code: string | null;

  constructor(
    public status: number,
    public body: unknown,
  ) {
    const code = ApiError.codeFromBody(body);
    super(code ?? `API ${status}`);
    this.name = "ApiError";
    this.code = code;
  }

  private static codeFromBody(body: unknown): string | null {
    if (typeof body === "object" && body !== null && "detail" in body) {
      const d = (body as Record<string, unknown>).detail;
      return typeof d === "string" ? d : null;
    }
    return null;
  }
}

/**
 * Thrown when a 401 could not be recovered by a token refresh. The
 * AuthProvider's SIGNED_OUT branch handles the redirect (cleared cache +
 * auth-state); callers generally don't need to special-case this.
 */
export class SessionExpiredError extends Error {
  constructor() {
    super("session_expired");
    this.name = "SessionExpiredError";
  }
}

/** Extract a backend error code from a thrown value (ApiError.code, else Error.message). */
export function errorCode(e: unknown): string {
  if (e instanceof ApiError) return e.code ?? "";
  if (e instanceof Error) return e.message;
  return "";
}

/**
 * Build request headers with a bearer token. When `token` is supplied (the
 * refresh-and-retry path) it is used verbatim — no store read — so the retry
 * carries the freshly refreshed token rather than re-deriving a possibly stale
 * one. Otherwise the token is resolved from the session cache (which itself
 * refreshes near-expiry tokens before returning them).
 */
async function authHeaders(init?: RequestInit, token?: string | null): Promise<Headers> {
  const accessToken =
    token !== undefined ? token : ((await resolveSession())?.access_token ?? null);
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type") && init?.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return headers;
}

/**
 * Issue a single request with an AbortController-backed timeout. Returns the
 * raw Response (caller decides how to parse). `signal` is honoured separately
 * from the timeout so external aborts still propagate.
 */
async function rawRequest(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${baseUrl}${path}`, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Core fetch wrapper (H2/L8/L10):
 * - AbortController-backed timeout (default 20s, override via 4th arg).
 * - On 401: refresh the session once and retry, building the retry's bearer
 *   header from the token `refreshSession()` returned (NOT a fresh store read),
 *   so the retry can't pick up a stale token. If refresh fails, sign out and
 *   throw SessionExpiredError. The `retried` guard prevents infinite loops.
 * - Initial request reads the access token from the session cache (which itself
 *   refreshes near-expiry tokens before returning them).
 */
async function performFetch(
  path: string,
  init: RequestInit | undefined,
  timeoutMs: number,
  retried: boolean,
  token?: string,
): Promise<Response> {
  const headers = await authHeaders(init, retried ? (token ?? null) : undefined);
  const res = await rawRequest(path, { ...init, headers }, timeoutMs);

  if (res.status === 401 && !retried) {
    const { data, error } = await supabase.auth.refreshSession();
    if (error || !data.session?.access_token) {
      await supabase.auth.signOut();
      throw new SessionExpiredError();
    }
    return performFetch(path, init, timeoutMs, true, data.session.access_token);
  }
  return res;
}

/**
 * Fetch a JSON body. Use `apiFetchVoid` for 204/DELETE endpoints — this overload
 * always parses a JSON response and never returns `undefined` (L8 fix).
 */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const res = await performFetch(path, init, timeoutMs, false);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

/**
 * Fetch an endpoint that returns no body (204 / DELETE). Returns `Promise<void>`
 * with an honest type — never `undefined as T` (L8).
 */
export async function apiFetchVoid(
  path: string,
  init?: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<void> {
  const res = await performFetch(path, init, timeoutMs, false);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }
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

/**
 * Resend the signup-confirmation email (POST /api/signup/resend → 202).
 * The backend is gated by `signups_enabled` and never reveals whether the
 * email exists (non-enumeration), so the resolved value is always void.
 */
export async function postSignupResend(email: string): Promise<void> {
  await apiFetch("/api/signup/resend", {
    method: "POST",
    body: JSON.stringify({ email }),
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

/**
 * Direct-create a platform user (super_admin only — the backend gates the
 * endpoint by role). Body is the generated `PlatformUserCreate` shape
 * (email + password + role); returns the provisioned `PlatformUserCreated`.
 */
export async function postPlatformUser(body: PlatformUserCreate): Promise<PlatformUserCreated> {
  return apiFetch("/api/platform/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deletePlatformInvite(id: string): Promise<void> {
  await apiFetchVoid(`/api/platform/users/invites/${id}`, { method: "DELETE" });
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
  await apiFetchVoid(`/api/tenants/${tenantId}/invites/${id}`, { method: "DELETE" });
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
  await apiFetchVoid(`/api/platform/roles/${id}`, { method: "DELETE" });
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
  await apiFetchVoid(`/api/workspaces/${workspaceId}/roles/${id}`, {
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

// ----- Dashboard stats (dashboard-metrics) -----

export async function fetchPlatformStats(): Promise<PlatformStats> {
  return apiFetch<PlatformStats>("/api/platform/stats");
}

export async function fetchWorkspaceStats(workspaceId: string): Promise<WorkspaceStats> {
  return apiFetch<WorkspaceStats>(`/api/workspaces/${workspaceId}/stats`);
}

// ----- Client tenants list (platform clients view) -----
//
// `GET /api/tenants` returns the cursor-paginated `TenantsPage` envelope
// (`items` + `next_cursor`), NOT a bare array — mirrors `fetchPlatformUsers`.

export async function fetchTenants(cursor: string | null): Promise<TenantsPage> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return apiFetch<TenantsPage>(`/api/tenants${qs}`);
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
  await apiFetchVoid(`/api/platform/users/${userId}/roles/${grantId}`, { method: "DELETE" });
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
  await apiFetchVoid(`/api/workspaces/${workspaceId}/members/${userId}/roles/${grantId}`, {
    method: "DELETE",
  });
}
