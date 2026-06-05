import { useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { fetchSignupStatus, postSignupResend } from "@/lib/api";
import { qk } from "@/lib/query-keys";
import { authErrorMessage, errorMessage } from "@/lib/error-messages";
import { Eye, EyeOff, LockKeyhole, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";
import { AuthLayout } from "@/components/auth-layout";

export function SignInPage() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const { data: signupStatus, isLoading: signupStatusLoading } = useQuery({
    queryKey: qk.signupStatus(),
    queryFn: fetchSignupStatus,
  });
  const signupsEnabled = signupStatus?.signups_enabled === true;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsConfirm, setNeedsConfirm] = useState(false);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent">("idle");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setNeedsConfirm(false);
    setResendState("idle");
    setLoading(true);
    const result = await signIn(email, password);
    setLoading(false);
    if (result.error) {
      if (result.code === "email_not_confirmed") {
        setNeedsConfirm(true);
        setError(errorMessage("email_not_confirmed"));
        return;
      }
      if (result.status === 429 || result.code === "over_request_rate_limit") {
        setError(errorMessage("rate_limited"));
        return;
      }
      // invalid_credentials (and any other auth error) → generic, non-enumerating.
      setError(errorMessage("invalid_credentials"));
      return;
    }
    void navigate({ to: "/" });
  };

  const onResend = async () => {
    setResendState("sending");
    try {
      await postSignupResend(email);
      setResendState("sent");
    } catch (err) {
      setResendState("idle");
      setError(authErrorMessage(err));
    }
  };

  return (
    <AuthLayout
      title="Welcome back"
      subtitle="Sign in to your dashboard"
      footer={
        // Reserve the footer space (non-breaking space) until signup-status
        // resolves so the copy doesn't flicker from the invite line to the
        // "Create an account" line on first load — and the card height stays
        // stable. AuthLayout only renders the footer block when `footer` is
        // truthy, so the &nbsp; keeps the slot occupied without showing text.
        signupStatusLoading ? (
          <span aria-hidden>&nbsp;</span>
        ) : signupsEnabled ? (
          <span>
            Don't have an account?{" "}
            <Link
              to="/sign-up"
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              Create an account
            </Link>
          </span>
        ) : (
          <span>Have an invite? Open the link in your invitation email to get started.</span>
        )
      }
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
            <User className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
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

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label
              htmlFor="password"
              className="text-xs font-medium tracking-wide text-muted-foreground"
            >
              Password
            </label>
            <Link
              to="/forgot-password"
              className="text-xs font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
            >
              Forgot password?
            </Link>
          </div>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="Enter your password"
              disabled={loading}
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

        {error && (
          <div className="space-y-2">
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
            {needsConfirm &&
              (resendState === "sent" ? (
                <p className="text-sm text-muted-foreground">
                  Verification email sent. Check your inbox.
                </p>
              ) : (
                <button
                  type="button"
                  onClick={() => void onResend()}
                  disabled={resendState === "sending"}
                  className="text-sm font-medium text-foreground underline-offset-4 hover:underline disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {resendState === "sending" ? "Sending…" : "Resend verification email"}
                </button>
              ))}
          </div>
        )}

        <Button
          type="submit"
          className="bg-foreground text-background hover:bg-foreground/90 h-11 w-full font-medium shadow-lg"
          disabled={loading}
        >
          {loading ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </AuthLayout>
  );
}
