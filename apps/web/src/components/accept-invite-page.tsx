import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { errorMessage } from "@/lib/error-messages";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

// getRouteApi avoids a circular import between this component and the route
// file (the route imports this component for `component:`).
const routeApi = getRouteApi("/accept-invite");

export function AcceptInvitePage() {
  const navigate = useNavigate();
  // On the success path the loader throws `redirect({ to: "/" })`, so this
  // component only ever renders for the error path — `code` is always present.
  const { code } = routeApi.useLoaderData();

  return (
    <AuthLayout title="Accepting your invite" subtitle="One moment while we set up your access">
      <div className="space-y-4 text-center">
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(code)}
        </p>
        <Button
          onClick={() => void supabase.auth.signOut().then(() => navigate({ to: "/sign-in" }))}
        >
          Sign out
        </Button>
      </div>
    </AuthLayout>
  );
}
