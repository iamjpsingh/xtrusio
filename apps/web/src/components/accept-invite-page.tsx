import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { TriangleAlert } from "lucide-react";
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
    <AuthLayout
      title="We couldn't accept your invite"
      subtitle="This invitation can't be used right now"
    >
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="rounded-full bg-foreground/5 p-3">
          <TriangleAlert className="h-6 w-6 text-muted-foreground" />
        </div>
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(code)}
        </p>
        <Button
          className="bg-foreground text-background hover:bg-foreground/90 h-11 w-full font-medium shadow-lg"
          onClick={() => void supabase.auth.signOut().then(() => navigate({ to: "/sign-in" }))}
        >
          Sign out
        </Button>
      </div>
    </AuthLayout>
  );
}
