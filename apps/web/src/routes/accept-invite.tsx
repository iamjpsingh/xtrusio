import { createFileRoute, redirect } from "@tanstack/react-router";
import { errorCode, postAcceptInvite } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
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
 * Establish the invitee's session from the URL hash (if present) BEFORE the
 * accept POST. Returns an error code string when the link is expired/invalid
 * (caller short-circuits to the error surface) or `null` when a session is in
 * place (either freshly set from the hash, or already present from the
 * `pending_invite` redirect path with no hash).
 *
 * Mirrors reset-password-page's recovery-hash handling, but done in the loader
 * so it runs exactly once per route entry — preserving the M12 "accept fires
 * exactly once" property without a useEffect + useRef guard.
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
  // M12: the accept POST runs in a router loader — no useEffect + useRef guard +
  // eslint-disable. The loader runs once per route entry; TanStack Router caches
  // the result, so a re-render never re-fires the mutation.
  //
  // invite-flow fix: the loader FIRST consumes the GoTrue invite-link hash
  // (`#access_token&refresh_token&type=invite`) via setSession to establish the
  // invitee's session, THEN runs the accept POST against that session. Without
  // this, the sessionless invitee never had a session and the POST 401'd.
  loader: async (): Promise<{ code: string }> => {
    const sessionError = await establishInviteSession();
    if (sessionError !== null) {
      return { code: sessionError };
    }

    let errorCodeValue: string | null = null;
    try {
      await queryClient.fetchQuery({
        queryKey: qk.acceptInvite(),
        queryFn: postAcceptInvite,
        retry: false,
      });
    } catch (e) {
      const code = errorCode(e);
      // An already-provisioned account is a success from the user's POV.
      if (code !== "already_provisioned") {
        errorCodeValue = code;
      }
    }
    // Refresh `me` either way so the resolver sees the freshly-provisioned access.
    await queryClient.invalidateQueries({ queryKey: qk.me() });
    if (errorCodeValue !== null) {
      // fetchQuery caches the rejected result; remove it so a manual retry
      // (re-entering the route) re-runs the POST instead of replaying the error.
      queryClient.removeQueries({ queryKey: qk.acceptInvite() });
      return { code: errorCodeValue };
    }
    throw redirect({ to: "/" });
  },
  component: AcceptInvitePage,
});
