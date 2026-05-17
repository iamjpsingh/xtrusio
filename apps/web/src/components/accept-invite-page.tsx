import { useEffect, useRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { errorCode, postAcceptInvite } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

export function AcceptInvitePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: postAcceptInvite,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate({ to: "/" });
    },
    onError: async (e) => {
      if (errorCode(e) === "already_provisioned") {
        await qc.invalidateQueries({ queryKey: ["me"] });
        navigate({ to: "/" });
      }
    },
  });
  const fired = useRef(false);
  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    m.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const code = m.error ? errorCode(m.error) : null;
  if (m.error && code !== "already_provisioned") {
    return (
      <AuthLayout title="Accepting your invite" subtitle="One moment while we set up your access">
        <div className="space-y-4 text-center">
          <p role="alert" className="text-sm text-destructive">{errorMessage(code ?? "")}</p>
          <Button
            onClick={() => void supabase.auth.signOut().then(() => navigate({ to: "/sign-in" }))}
          >
            Sign out
          </Button>
        </div>
      </AuthLayout>
    );
  }
  return (
    <AuthLayout title="Accepting your invite" subtitle="One moment while we set up your access">
      <p className="text-center text-muted-foreground">Completing your invitation…</p>
    </AuthLayout>
  );
}
