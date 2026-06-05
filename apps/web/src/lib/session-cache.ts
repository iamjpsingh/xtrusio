// apps/web/src/lib/session-cache.ts
//
// Session access for apiFetch, backed by the Zustand auth store (the single
// source of truth — lib/auth-store.ts). There is no separate onAuthStateChange
// subscription here anymore; the store owns it, so apiFetch always reads the
// same session the rest of the app sees.
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";
import { useAuthStore } from "./auth-store";

/**
 * Safety margin (seconds) before a token's real `expires_at` at which we treat
 * it as "about to expire" and proactively refresh BEFORE sending. auth-js
 * itself considers a token expired ~90s before real expiry and its auto-refresh
 * tick is visibility-gated (it pauses when the tab is backgrounded), so a token
 * in its final window — or one that went stale while the tab was hidden — would
 * otherwise be sent and 401 at the backend. 60s comfortably covers that window
 * while staying well inside the token's lifetime, so we don't refresh on every
 * request.
 */
const EXPIRY_MARGIN_SEC = 60;

/** Current session snapshot from the store (null when signed out / pre-init). */
export function getCachedSession(): Session | null {
  return useAuthStore.getState().session;
}

/**
 * True when `expires_at` (unix seconds) is missing, already past, or within the
 * safety margin of now — i.e. the access token is stale enough that we should
 * refresh before sending it. A missing `expires_at` is treated as stale (we
 * can't prove freshness, so prefer a refresh over a likely 401).
 */
function isNearExpiry(session: Session): boolean {
  const expiresAt = session.expires_at;
  if (expiresAt == null) return true;
  const nowSec = Math.floor(Date.now() / 1000);
  return expiresAt - nowSec <= EXPIRY_MARGIN_SEC;
}

/**
 * Resolve a session for apiFetch.
 *
 * - Pre-init ("loading") window: fall back to a one-shot getSession(), which
 *   auto-refreshes inside auth-js's margin and returns the current session.
 * - Authenticated, token fresh: return the store session as-is (the hot path —
 *   no network).
 * - Authenticated, token near/at expiry: proactively fetch a fresh session via
 *   getSession() (auth-js refreshes inside its own margin and persists+broadcasts
 *   the new tokens, so the store stays in sync via onAuthStateChange) and return
 *   the FRESH session so the token sent on the wire is current — NOT the stale
 *   store value. If the refresh yields nothing, fall back to the store session.
 *
 * This is the core fix for the "401 after login" storm: tokens in their final
 * ~90s window (or after a backgrounded tab refocuses) are refreshed before send
 * instead of being sent stale.
 */
export async function resolveSession(): Promise<Session | null> {
  const { session, status } = useAuthStore.getState();
  if (status === "loading") {
    const {
      data: { session: fresh },
    } = await supabase.auth.getSession();
    return fresh;
  }
  if (session && isNearExpiry(session)) {
    const {
      data: { session: refreshed },
    } = await supabase.auth.getSession();
    return refreshed ?? session;
  }
  return session;
}
