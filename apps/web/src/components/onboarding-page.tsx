import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { postOnboarding } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
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
      await qc.invalidateQueries({ queryKey: ["me"] });
      navigate({ to: "/" });
    },
  });
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="text-2xl font-semibold">Create your workspace</h1>
        <p className="text-sm text-muted-foreground">
          A workspace is where you and your team will work. You can rename it later.
        </p>
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
          <p className="text-sm text-destructive">
            {errorMessage((m.error as Error).message)}
          </p>
        ) : null}
        <Button type="submit" className="w-full" disabled={m.isPending}>
          {m.isPending ? "Creating…" : "Continue"}
        </Button>
      </form>
    </main>
  );
}
