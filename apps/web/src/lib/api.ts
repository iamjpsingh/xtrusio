import { supabase } from "./supabase";
import type { MeResponse } from "./route-resolver";

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
  return apiFetch("/api/platform/signup-status");
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
