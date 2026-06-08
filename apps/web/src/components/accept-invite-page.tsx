import { useState, type FormEvent } from "react";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { Eye, EyeOff, LockKeyhole, TriangleAlert } from "lucide-react";
import { errorCode, fetchMe, postAcceptInvite } from "@/lib/api";
import { getDefaultLandingPath } from "@/lib/me-adapter";
import { qk } from "@/lib/query-keys";
import { queryClient } from "@/lib/query-client";
import { authErrorMessage, errorMessage } from "@/lib/error-messages";
import { AuthLayout } from "@/components/auth-layout";
import { Button } from "@/components/ui/button";
import { supabase } from "@/lib/supabase";

// getRouteApi avoids a circular import between this component and the route
// file (the route imports this component for `component:`).
const routeApi = getRouteApi("/accept-invite");

const MIN_PASSWORD_LENGTH = 8;

// Accept-side codes that mean "already joined" — a success from the invitee's
// point of view, so we land them rather than show an error.
const ALREADY_JOINED = new Set(["already_provisioned", "invite_already_accepted"]);

/** The "couldn't accept your invite" surface for an expired/invalid link. */
function InviteErrorView({ code }: { code: string }) {
  const navigate = useNavigate();
  return (
    <AuthLayout
      title="We couldn't accept your invite"
      subtitle="This invitation can't be used right now"
    >
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="rounded-full bg-foreground/5 p-3">
          <TriangleAlert className="h-6 w-6 text-muted-foreground" />
        </div>
        <p role="alert" className="text-sm text-destructive">
          {errorMessage(code)}
        </p>
        <Button
          className="bg-foreground text-background hover:bg-foreground/90 h-11 w-full font-medium shadow-lg"
          onClick={() => void supabase.auth.signOut().then(() => navigate({ to: "/sign-in" }))}
        >
          Sign out
        </Button>
      </div>
    </AuthLayout>
  );
}

/**
 * Set-password form. The invitee's session is already established (loader ran
 * setSession); they set account credentials here. Only AFTER the password is
 * saved do we POST the accept to provision membership, then land them.
 */
function SetPasswordView() {
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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

    // 1) Complete account creation — set the credential before joining.
    const { error: updateError } = await supabase.auth.updateUser({ password });
    if (updateError) {
      setSaving(false);
      setError(authErrorMessage(updateError));
      return;
    }

    // 2) Provision membership against the now-credentialed session.
    try {
      await postAcceptInvite();
    } catch (err) {
      const code = errorCode(err);
      // Already joined (idempotent re-submit) → treat as success and land them.
      if (!ALREADY_JOINED.has(code)) {
        setSaving(false);
        setError(errorMessage(code));
        return;
      }
    }

    // 3) Refresh `me` so the resolver sees the freshly-provisioned access, then
    //    land them on their default scope (workspace / platform / onboarding).
    const me = await queryClient.fetchQuery({ queryKey: qk.me(), queryFn: fetchMe });
    void navigate({ to: getDefaultLandingPath(me) });
  };

  return (
    <AuthLayout
      title="Set a password to join"
      subtitle="Choose a password to finish setting up your account"
    >
      <form onSubmit={onSubmit} className="space-y-4">
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
            Confirm password
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
              placeholder="Re-enter your password"
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
          {saving ? "Joining…" : "Set password & join"}
        </Button>
      </form>
    </AuthLayout>
  );
}

export function AcceptInvitePage() {
  const result = routeApi.useLoaderData();
  if (result.status === "error") {
    return <InviteErrorView code={result.code} />;
  }
  return <SetPasswordView />;
}
