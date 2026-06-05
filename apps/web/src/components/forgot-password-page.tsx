import { useState, type FormEvent } from "react";
import { Link } from "@tanstack/react-router";
import { Mail } from "lucide-react";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { authErrorMessage } from "@/lib/error-messages";
import { supabase } from "@/lib/supabase";

function BackToSignIn() {
  return (
    <span>
      Remembered it?{" "}
      <Link
        to="/sign-in"
        className="font-medium text-foreground underline-offset-4 hover:underline"
      >
        Back to sign in
      </Link>
    </span>
  );
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    // Always show the same "check your email" result regardless of whether the
    // email exists — no enumeration oracle. We still surface transport/rate-limit
    // failures so the user knows to retry, but never reveal account existence.
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    });
    setLoading(false);
    if (resetError) {
      setError(authErrorMessage(resetError));
      return;
    }
    setSent(true);
  };

  if (sent) {
    return (
      <AuthLayout
        title="Check your email"
        subtitle={`If an account exists for ${email}, we've sent a reset link`}
        footer={<BackToSignIn />}
      >
        <p className="text-center text-sm text-muted-foreground">
          Click the link in the email to choose a new password. The link expires shortly, so use it
          soon.
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Forgot your password?"
      subtitle="Enter your email and we'll send a reset link"
      footer={<BackToSignIn />}
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label
            htmlFor="email"
            className="text-xs font-medium tracking-wide text-muted-foreground"
          >
            Email
          </label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="Enter your email"
              disabled={loading}
              className="bg-foreground/5 hover:bg-foreground/[0.07] focus:bg-foreground/[0.08] h-11 w-full rounded-md border border-foreground/10 pl-10 pr-3 text-sm text-foreground transition-colors placeholder:text-muted-foreground/60 focus:border-foreground/25 focus:outline-none focus:ring-2 focus:ring-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>
        </div>

        {error ? (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}

        <Button
          type="submit"
          className="bg-foreground text-background hover:bg-foreground/90 h-11 w-full font-medium shadow-lg"
          disabled={loading}
        >
          {loading ? "Sending…" : "Send reset link"}
        </Button>
      </form>
    </AuthLayout>
  );
}
