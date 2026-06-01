import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Building2 } from "lucide-react";
import { errorCode, postOnboarding } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { errorMessage } from "@/lib/error-messages";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";

export function OnboardingPage() {
  const [workspaceName, setWorkspaceName] = useState("");
  const navigate = useNavigate();
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: () => postOnboarding(workspaceName),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: qk.me() });
      navigate({ to: "/" });
    },
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  return (
    <AuthLayout title="Create your workspace" subtitle="Name your organization to get started">
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="ws" className="text-xs font-medium tracking-wide text-muted-foreground">
            Workspace name
          </label>
          <div className="relative">
            <Building2 className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id="ws"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              required
              minLength={2}
              maxLength={200}
              autoComplete="organization"
              placeholder="Acme Inc."
              disabled={m.isPending}
              className="bg-foreground/5 hover:bg-foreground/[0.07] focus:bg-foreground/[0.08] h-11 w-full rounded-md border border-foreground/10 pl-10 pr-3 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-foreground/25 focus:outline-none focus:ring-2 focus:ring-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        </div>
        {m.error ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(errorCode(m.error))}
          </p>
        ) : null}
        <Button
          type="submit"
          className="bg-foreground text-background hover:bg-foreground/90 h-11 w-full font-medium shadow-lg"
          disabled={m.isPending}
        >
          {m.isPending ? "Creating…" : "Continue"}
        </Button>
      </form>
    </AuthLayout>
  );
}
