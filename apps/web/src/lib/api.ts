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
