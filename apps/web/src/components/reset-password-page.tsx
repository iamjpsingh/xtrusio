import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { Eye, EyeOff, LockKeyhole } from "lucide-react";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { authErrorMessage } from "@/lib/error-messages";
import { supabase } from "@/lib/supabase";

type Phase = "verifying" | "ready" | "expired" | "done";

const MIN_PASSWORD_LENGTH = 8;

/**
 * Parse the recovery hash GoTrue appends after the redirect. The client uses
 * the implicit flow (no `flowType` set, `detectSessionInUrl:false`), so a
 * successful recovery returns `#access_token=...&refresh_token=...&type=recovery`
 * and a failure returns `#error=...&error_code=...&error_description=...`.
 */
function parseRecoveryHash(hash: string): {
  accessToken: string | null;
  refreshToken: string | null;
  type: string | null;
  errorCode: string | null;
} {
  const params = new URLSearchParams(hash.replace(/^#/, ""));
  return {
    accessToken: params.get("access_token"),
    refreshToken: params.get("refresh_token"),
    type: params.get("type"),
    errorCode: params.get("error_code") ?? params.get("error"),
  };
}

export function ResetPasswordPage() {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<Phase>("verifying");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Handle the recovery token LOCALLY on this route only — we do NOT flip the
  // global `detectSessionInUrl`. We read the hash once on mount, establish the
  // recovery session via setSession, then clear the hash from the URL.
  useEffect(() => {
    const { accessToken, refreshToken, type, errorCode } = parseRecoveryHash(window.location.hash);
    if (errorCode) {
      setPhase("expired");
      return;
    }
    if (type === "recovery" && accessToken && refreshToken) {
      void supabase.auth
        .setSession({ access_token: accessToken, refresh_token: refreshToken })
        .then(({ error: sessionError }) => {
          if (sessionError) {
            setPhase("expired");
            return;
          }
          // Scrub the tokens from the address bar once consumed.
          window.history.replaceState(null, "", window.location.pathname);
          setPhase("ready");
        })
        .catch(() => setPhase("expired"));
      return;
    }
    // No recovery payload at all → treat as an invalid/expired entry.
    setPhase("expired");
  }, []);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setSaving(true);
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setSaving(false);
    if (updateError) {
      setError(authErrorMessage(updateError));
      return;
    }
    setPhase("done");
    // Sign out the temporary recovery session, then send them to sign in fresh.
    await supabase.auth.signOut();
    void navigate({ to: "/sign-in" });
  };

  if (phase === "verifying") {
    return (
      <AuthLayout title="Reset password" subtitle="Verifying your link…">
        <p className="text-center text-sm text-muted-foreground">One moment…</p>
      </AuthLayout>
    );
  }

  if (phase === "expired") {
    return (
      <AuthLayout
        title="Link expired"
        subtitle="This password-reset link is no longer valid"
        footer={
          <span>
            <Link
              to="/forgot-password"
              className="font-medium text-foreground underline-offset-4 hover:underline"
            >
              Request a new link
            </Link>
          </span>
        }
      >
        <p role="alert" className="text-center text-sm text-destructive">
          {authErrorMessage({ code: "otp_expired" })}
        </p>
      </AuthLayout>
    );
  }

  if (phase === "done") {
    return (
      <AuthLayout title="Password updated" subtitle="Signing you in…">
        <p className="text-center text-sm text-muted-foreground">
          Your password has been changed. Redirecting to sign in…
        </p>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle="Enter a new password for your account"
      footer={
        <span>
          <Link
            to="/sign-in"
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            Back to sign in
          </Link>
        </span>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1.5">
          <label
            htmlFor="password"
            className="text-xs font-medium tracking-wide text-muted-foreground"
          >
            New password
          </label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              minLength={MIN_PASSWORD_LENGTH}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="At least 8 characters"
              disabled={saving}
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

        <div className="space-y-1.5">
          <label
            htmlFor="confirm"
            className="text-xs font-medium tracking-wide text-muted-foreground"
          >
            Confirm new password
          </label>
          <div className="relative">
            <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              id="confirm"
              type={showPassword ? "text" : "password"}
              minLength={MIN_PASSWORD_LENGTH}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="Re-enter your new password"
              disabled={saving}
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
          disabled={saving}
        >
          {saving ? "Saving…" : "Update password"}
        </Button>
      </form>
    </AuthLayout>
  );
}
