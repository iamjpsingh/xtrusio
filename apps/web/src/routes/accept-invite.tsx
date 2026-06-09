import { createFileRoute } from "@tanstack/react-router";
import { supabase } from "@/lib/supabase";
import { AcceptInvitePage } from "@/components/accept-invite-page";

/**
 * Parse the invite hash GoTrue appends after the redirect. The client uses the
 * implicit flow (`detectSessionInUrl:false`), so a freshly-clicked invite link
 * returns `#access_token=...&refresh_token=...&type=invite` (GoTrue uses
 * `type=signup` for some templates) and an expired/used link returns
 * `#error=...&error_code=...&error_description=...`. We consume this LOCALLY on
 * this route — we do NOT flip the global `detectSessionInUrl`.
 */
function parseInviteHash(hash: string): {
  accessToken: string | null;
  refreshToken: string | null;
  type: string | null;
  errorCode: string | null;
} {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  return {
    accessToken: params.get("access_token"),
    refreshToken: params.get("refresh_token"),
    type: params.get("type"),
    errorCode: params.get("error_code") ?? params.get("error"),
  };
}

const INVITE_HASH_TYPES = new Set(["invite", "signup"]);

/**
 * Outcome of consuming the invite link. `ready` means a session is in place and
 * the invitee should be shown the set-password form; `error` carries a code for
 * the "couldn't accept your invite" surface (expired/used/invalid link).
 */
export type LoaderResult = { status: "ready" } | { status: "error"; code: string };

/**
 * Establish the invitee's session from the URL hash (if present). Returns an
 * error code when the link is expired/invalid (caller short-circuits to the
 * error surface) or `null` when a session is in place (either freshly set from
 * the hash, or already present from the `pending_invite` redirect path with no
 * hash).
 *
 * Mirrors reset-password-page's recovery-hash handling, but done in the loader
 * so it runs exactly once per route entry.
 */
async function establishInviteSession(): Promise<string | null> {
  const {
    accessToken,
    refreshToken,
    type,
    errorCode: hashError,
  } = parseInviteHash(window.location.hash);
  if (hashError) {
    // Expired/used invite link → existing "couldn't accept your invite" surface.
    return "invite_expired";
  }
  if (accessToken && refreshToken && (type === null || INVITE_HASH_TYPES.has(type))) {
    let sessionFailed = false;
    try {
      const { error } = await supabase.auth.setSession({
        access_token: accessToken,
        refresh_token: refreshToken,
      });
      sessionFailed = error != null;
    } catch {
      sessionFailed = true;
    }
    if (sessionFailed) return "invite_expired";
    // Scrub the tokens from the address bar once consumed.
    window.history.replaceState(null, "", window.location.pathname);
    return null;
  }
  // No hash tokens at all → the `pending_invite` redirect path: the user is
  // already authenticated and the accept POST runs against the existing session.
  return null;
}

export const Route = createFileRoute("/accept-invite")({
  // invite-to-signup: the loader ONLY consumes the GoTrue invite-link hash
  // (`#access_token&refresh_token&type=invite`) via setSession to establish the
  // invitee's session. It does NOT auto-accept — the invitee must set a
  // password first. The accept POST now runs from <AcceptInvitePage> after the
  // password is set, so the link alone no longer joins them.
  loader: async (): Promise<LoaderResult> => {
    const sessionError = await establishInviteSession();
    if (sessionError !== null) {
      return { status: "error", code: sessionError };
    }
    return { status: "ready" };
  },
  component: AcceptInvitePage,
});
