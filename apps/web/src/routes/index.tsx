// apps/web/src/routes/index.tsx
// Root index route. `/` is never a content page — it exists only to send the
// user to their real landing (platform / workspace / onboarding) or to sign-in.
//
// Making `/` a REAL route (with a redirecting beforeLoad) is what fixes the
// "Not Found after login" bug: the app navigates to `/` after sign-in, and
// previously there was no `/` route, so the router raised a notFound that the
// AuthGuard had to race to hide. Now `/` always resolves to a redirect.
import { createFileRoute, redirect } from "@tanstack/react-router";
import { supabase } from "@/lib/supabase";
import { queryClient } from "@/lib/query-client";
import { qk } from "@/lib/query-keys";
import { fetchMe } from "@/lib/api";
import { getDefaultLandingPath } from "@/lib/me-adapter";

export const Route = createFileRoute("/")({
  beforeLoad: async () => {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) {
      throw redirect({ to: "/sign-in" });
    }
    let landing: string;
    try {
      const me = await queryClient.ensureQueryData({ queryKey: qk.me(), queryFn: fetchMe });
      landing = getDefaultLandingPath(me);
    } catch {
      // A valid session but /me failed (expired/unusable token) — send to
      // sign-in rather than loop on a broken landing.
      landing = "/sign-in";
    }
    throw redirect({ to: landing });
  },
  component: () => null,
});
