import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { errorCode, fetchSignupStatus, postSignup } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { errorMessage } from "@/lib/error-messages";
import { Eye, EyeOff, LockKeyhole, User } from "lucide-react";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";

export function SignUpPage() {
  const { data: status, isLoading } = useQuery({
    queryKey: qk.signupStatus(),
    queryFn: fetchSignupStatus,
  });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const m = useMutation({
    mutationFn: () => postSignup(email, password),
    onSuccess: () => setSubmitted(true),
  });

  if (isLoading) return null;
  if (status && !status.signups_enabled) {
    return (
      <AuthLayout
        title="Sign-up unavailable"
        subtitle="Public client signup is currently turned off"
      >
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
        <div className="space-y-1.5">
          <label
            htmlFor="email"
            className="text-xs font-medium tracking-wide text-muted-foreground"
          >
            Email
          </label>
          <div className="relative">
            <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="Enter your email"
              disabled={m.isPending}
              className="bg-foreground/5 hover:bg-foreground/[0.07] focus:bg-foreground/[0.08] h-11 w-full rounded-md border border-foreground/10 pl-10 pr-3 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-foreground/25 focus:outline-none focus:ring-2 focus:ring-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label
            htmlFor="password"
            className="text-xs font-medium tracking-wide text-muted-foreground"
          >
            Password
          </label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="At least 8 characters"
              disabled={m.isPending}
              className="bg-foreground/5 hover:bg-foreground/[0.07] focus:bg-foreground/[0.08] h-11 w-full rounded-md border border-foreground/10 pl-10 pr-10 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-foreground/25 focus:outline-none focus:ring-2 focus:ring-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground focus:outline-none focus-visible:text-foreground"
              aria-label={showPassword ? "Hide password" : "Show password"}
              tabIndex={-1}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
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
          {m.isPending ? "Submitting…" : "Sign up"}
        </Button>
      </form>
    </AuthLayout>
  );
}
