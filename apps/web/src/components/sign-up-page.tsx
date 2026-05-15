import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { fetchSignupStatus, postSignup } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function SignUpPage() {
  const { data: status, isLoading } = useQuery({
    queryKey: ["signup-status"],
    queryFn: fetchSignupStatus,
  });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const m = useMutation({
    mutationFn: () => postSignup(email, password),
    onSuccess: () => setSubmitted(true),
  });

  if (isLoading) return null;
  if (status && !status.signups_enabled) {
    return (
      <main className="grid min-h-screen place-items-center px-6">
        <div className="max-w-md text-center text-muted-foreground">
          Signups are currently disabled. Contact your administrator for an invitation.
        </div>
      </main>
    );
  }
  if (submitted) {
    return (
      <main className="grid min-h-screen place-items-center px-6">
        <div className="max-w-md text-center">
          <h1 className="text-2xl font-semibold">Check your email</h1>
          <p className="mt-2 text-muted-foreground">
            We&rsquo;ve sent a confirmation link to <strong>{email}</strong>.
          </p>
        </div>
      </main>
    );
  }
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  return (
    <main className="grid min-h-screen place-items-center px-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="text-2xl font-semibold">Create your account</h1>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div>
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        {m.error ? (
          <p className="text-sm text-destructive">
            {errorMessage((m.error as Error).message)}
          </p>
        ) : null}
        <Button type="submit" className="w-full" disabled={m.isPending}>
          {m.isPending ? "Submitting…" : "Sign up"}
        </Button>
      </form>
    </main>
  );
}
