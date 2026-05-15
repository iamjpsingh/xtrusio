const MESSAGES: Record<string, string> = {
  signups_disabled: "Signups are currently disabled.",
  email_taken: "An account with that email already exists.",
  invalid_email: "That email address doesn't look valid.",
  weak_password: "Password must be at least 8 characters.",
  already_has_membership: "You're already in a workspace.",
  workspace_name_invalid: "Workspace name must be 2-200 characters.",
  email_provider_unavailable:
    "Couldn't send the email. Please try again in a moment.",
  no_invite: "We couldn't find an invitation for your account.",
  invite_expired: "This invitation has expired.",
  invite_revoked: "This invitation was revoked.",
  invite_already_accepted: "This invitation has already been accepted.",
  email_mismatch: "This invitation was for a different email address.",
};

export function errorMessage(code: string): string {
  return MESSAGES[code] ?? "Something went wrong. Please try again.";
}
