const MESSAGES: Record<string, string> = {
  signups_disabled: "Signups are currently disabled.",
  email_taken: "An account with that email already exists.",
  user_exists: "A user with that email already exists.",
  invalid_email: "That email address doesn't look valid.",
  weak_password: "Password must be at least 8 characters.",
  already_has_membership: "You're already in a workspace.",
  workspace_name_invalid: "Workspace name must be 2-200 characters.",
  email_provider_unavailable: "Couldn't send the email. Please try again in a moment.",
  no_invite: "We couldn't find an invitation for your account.",
  invite_expired: "This invitation has expired.",
  invite_revoked: "This invitation was revoked.",
  invite_already_accepted: "This invitation has already been accepted.",
  email_mismatch: "This invitation was for a different email address.",
  already_provisioned: "Your account is already set up.",
  role_key_taken: "A role with this key already exists.",
  system_role_immutable: "System roles can't be modified.",
  role_scope_mismatch: "That role belongs to a different scope.",
  scope_mismatch: "That permission belongs to a different scope.",
  single_super_admin_invariant: "You can't remove the last super admin.",
  owner_floor: "You can't revoke the last workspace owner.",
  membership_not_found: "That user isn't a member of this workspace.",
  platform_user_not_found: "That user isn't a platform user.",
  "invalid cursor": "Couldn't load more events. Try refreshing.",
  // P6d additions.
  workspace_not_found: "We couldn't find that workspace.",
  role_not_found: "That role no longer exists. Refresh the page.",
  grant_not_found: "That grant has already been removed.",
};

export function errorMessage(code: string): string {
  if (code.startsWith("unknown_permission: ")) {
    const key = code.slice("unknown_permission: ".length);
    return `Unknown permission: ${key}. Refresh the page.`;
  }
  if (code.startsWith("privilege_escalation: ")) {
    const perm = code.slice("privilege_escalation: ".length);
    return `You can't grant a role with a permission you lack: ${perm}.`;
  }
  return MESSAGES[code] ?? "Something went wrong. Please try again.";
}
