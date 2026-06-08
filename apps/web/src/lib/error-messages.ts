import { ApiError } from "./api";

const MESSAGES: Record<string, string> = {
  signups_disabled: "Signups are disabled.",
  email_exists: "This email already has an account.",
  email_taken: "An account with that email already exists.",
  user_exists: "A user with that email already exists.",
  invalid_email: "That email address doesn't look valid.",
  weak_password: "Password must be at least 8 characters.",
  already_has_membership: "You're already in a workspace.",
  workspace_name_invalid: "Workspace name must be 2-200 characters.",
  email_provider_unavailable: "Couldn't send the email. Please try again in a moment.",
  no_invite: "We couldn't find an invitation for your account.",
  invite_expired: "This invitation has expired.",
  invite_revoked: "This invitation was revoked.",
  invite_already_accepted: "This invitation has already been accepted.",
  email_mismatch: "This invitation was for a different email address.",
  already_provisioned: "Your account is already set up.",
  role_key_taken: "A role with this key already exists.",
  // Role save (slice #65) returns a sanitized bare `privilege_escalation`
  // (no perm key, to avoid leaking the RBAC graph). Grants still use the
  // `privilege_escalation: <perm>` prefixed form handled in errorMessage().
  privilege_escalation: "You can only include permissions you currently hold.",
  system_role_immutable: "System roles can't be modified.",
  role_scope_mismatch: "That role belongs to a different scope.",
  scope_mismatch: "That permission belongs to a different scope.",
  single_super_admin_invariant: "You can't remove the last super admin.",
  owner_floor: "You can't revoke the last workspace owner.",
  membership_not_found: "That user isn't a member of this workspace.",
  platform_user_not_found: "That user isn't a platform user.",
  "invalid cursor": "Couldn't load more events. Try refreshing.",
  // P6d additions.
  workspace_not_found: "We couldn't find that workspace.",
  role_not_found: "That role no longer exists. Refresh the page.",
  grant_not_found: "That grant has already been removed.",
  // Auth-pages additions (2026-06-02). Some are backend codes, others are the
  // GoTrue `AuthError.code` strings surfaced by supabase-js on the client.
  rate_limited: "Too many attempts. Please wait a minute and try again.",
  over_request_rate_limit: "Too many attempts. Please wait a minute and try again.",
  over_email_send_rate_limit: "Too many emails sent. Please wait a minute and try again.",
  email_not_confirmed: "Your email isn't verified yet.",
  invalid_credentials: "Wrong email or password.",
  otp_expired: "This link has expired. Request a new one.",
  same_password: "Your new password must be different from your current one.",
  network_error: "Couldn't reach the server. Check your connection and try again.",
};

export function errorMessage(code: string): string {
  if (code.startsWith("unknown_permission: ")) {
    const key = code.slice("unknown_permission: ".length);
    return `Unknown permission: ${key}. Refresh the page.`;
  }
  if (code.startsWith("privilege_escalation: ")) {
    const perm = code.slice("privilege_escalation: ".length);
    return `You can't grant a role with a permission you lack: ${perm}.`;
  }
  return MESSAGES[code] ?? "Something went wrong. Please try again.";
}

/**
 * Friendly copy for an arbitrary thrown auth error. Handles, in order:
 * - `ApiError` (backend): 429 → rate-limited, then the structured `.code`.
 * - supabase-js `AuthError`-shaped objects: HTTP `status` 429 then `.code`.
 * - AbortError / timeouts / network failures → a connectivity message.
 * - Anything else → the generic registry fallback.
 *
 * Returning a string (never null) keeps callers simple — they render it
 * directly. The mapping never reveals whether an email exists.
 */
export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 429) return errorMessage("rate_limited");
    return errorMessage(error.code ?? "");
  }
  if (isAbortLike(error)) return errorMessage("network_error");
  const supa = asSupabaseError(error);
  if (supa) {
    if (supa.status === 429) return errorMessage("rate_limited");
    if (supa.code) return errorMessage(supa.code);
  }
  if (error instanceof TypeError) {
    // fetch() rejects with a TypeError on a network-level failure.
    return errorMessage("network_error");
  }
  return errorMessage("");
}

function isAbortLike(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function asSupabaseError(error: unknown): { code?: string; status?: number } | null {
  if (typeof error !== "object" || error === null) return null;
  const e = error as Record<string, unknown>;
  const code = typeof e.code === "string" ? e.code : undefined;
  const status = typeof e.status === "number" ? e.status : undefined;
  if (code === undefined && status === undefined) return null;
  return { code, status };
}
