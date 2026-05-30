import { createFileRoute, redirect } from "@tanstack/react-router";
import { errorCode, postAcceptInvite } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { AcceptInvitePage } from "@/components/accept-invite-page";

export const Route = createFileRoute("/accept-invite")({
  // M12: the accept POST runs in a router loader — no useEffect + useRef guard +
  // eslint-disable. The loader runs once per route entry; TanStack Router caches
  // the result, so a re-render never re-fires the mutation.
  loader: async (): Promise<{ code: string }> => {
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
