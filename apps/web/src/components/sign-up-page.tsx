import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { errorCode, fetchSignupStatus, postSignup } from "@/lib/api";
import { errorMessage } from "@/lib/error-messages";
import { AuthLayout } from "@/components/auth-layout";
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
      <AuthLayout title="Sign-up unavailable" subtitle="Public client signup is currently turned off">
        <p className="text-center text-sm text-muted-foreground">
          Contact your administrator for an invitation.
        </p>
      </AuthLayout>
    );
  }
  if (submitted) {
    return (
      <AuthLayout title="Check your email" subtitle={`We've sent a confirmation link to ${email}`}>
        <p className="text-center text-sm text-muted-foreground">
          Check your inbox and click the link to complete sign-up.
        </p>
      </AuthLayout>
    );
  }
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    m.mutate();
  };
  return (
    <AuthLayout title="Create your account" subtitle="Start a new client workspace">
      <form onSubmit={onSubmit} className="space-y-4">
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
          <p role="alert" className="text-sm text-destructive">
            {errorMessage(errorCode(m.error))}
          </p>
        ) : null}
        <Button type="submit" className="w-full" disabled={m.isPending}>
          {m.isPending ? "Submitting…" : "Sign up"}
        </Button>
      </form>
    </AuthLayout>
  );
}
