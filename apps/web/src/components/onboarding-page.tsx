import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { errorCode, postOnboarding } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { errorMessage } from "@/lib/error-messages";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

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
        <div>
          <Label htmlFor="ws">Workspace name</Label>
          <Input
            id="ws"
            value={workspaceName}
            onChange={(e) => setWorkspaceName(e.target.value)}
            required
            minLength={2}
            maxLength={200}
          />
        </div>
        {m.error ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(errorCode(m.error))}
          </p>
        ) : null}
        <Button type="submit" className="w-full" disabled={m.isPending}>
          {m.isPending ? "Creating…" : "Continue"}
        </Button>
      </form>
    </AuthLayout>
  );
}
