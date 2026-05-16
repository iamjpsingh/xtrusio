import { useEffect, useRef } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError, postAcceptInvite } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

function errorCode(e: unknown): string {
  if (e instanceof ApiError) return e.code ?? "";
  if (e instanceof Error) return e.message;
  return "";
}

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
      <main className="grid min-h-screen place-items-center px-6">
        <div className="max-w-md space-y-4 text-center">
          <h1 className="text-2xl font-semibold text-foreground">
            Couldn&rsquo;t accept invitation
          </h1>
          <p className="text-muted-foreground">{errorMessage(code ?? "")}</p>
          <Button
            onClick={() => void supabase.auth.signOut().then(() => navigate({ to: "/sign-in" }))}
          >
            Sign out
          </Button>
        </div>
      </main>
    );
  }
  return (
    <main className="grid min-h-screen place-items-center text-muted-foreground">
      Completing your invitation…
    </main>
  );
}
