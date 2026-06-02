import { describe, expect, it } from "vitest";
import { authErrorMessage, errorMessage } from "./error-messages";
import { ApiError } from "./api";

describe("errorMessage", () => {
  it("returns the mapped string for known codes", () => {
    expect(errorMessage("signups_disabled")).toMatch(/disabled/i);
    expect(errorMessage("email_taken")).toMatch(/already/i);
    expect(errorMessage("already_has_membership")).toMatch(/workspace/i);
  });

  it("falls back to a generic string for unknown codes", () => {
    expect(errorMessage("not_a_real_code")).toMatch(/something/i);
  });
});

describe("errorMessage — P6c Slice 1 codes", () => {
  it("maps role_key_taken", () => {
    expect(errorMessage("role_key_taken")).toBe("A role with this key already exists.");
  });
  it("maps system_role_immutable", () => {
    expect(errorMessage("system_role_immutable")).toBe("System roles can't be modified.");
  });
  it("maps role_scope_mismatch", () => {
    expect(errorMessage("role_scope_mismatch")).toBe("That role belongs to a different scope.");
  });
  it("maps scope_mismatch", () => {
    expect(errorMessage("scope_mismatch")).toBe("That permission belongs to a different scope.");
  });
  it("maps an unknown_permission key with the offending key surfaced", () => {
    expect(errorMessage("unknown_permission: workspace.unknown")).toBe(
      "Unknown permission: workspace.unknown. Refresh the page.",
    );
  });
  it("maps single_super_admin_invariant", () => {
    expect(errorMessage("single_super_admin_invariant")).toBe(
      "You can't remove the last super admin.",
    );
  });
  it("maps owner_floor", () => {
    expect(errorMessage("owner_floor")).toBe("You can't revoke the last workspace owner.");
  });
  it("maps a privilege_escalation key with the offending perm surfaced", () => {
    expect(errorMessage("privilege_escalation: platform.roles.manage")).toBe(
      "You can't grant a role with a permission you lack: platform.roles.manage.",
    );
  });
  it("maps membership_not_found", () => {
    expect(errorMessage("membership_not_found")).toBe(
      "That user isn't a member of this workspace.",
    );
  });
  it("maps platform_user_not_found", () => {
    expect(errorMessage("platform_user_not_found")).toBe("That user isn't a platform user.");
  });
  it("falls through to the existing default for unknown codes", () => {
    const result = errorMessage("definitely-not-a-real-code");
    expect(result).toBeTruthy();
  });
});

describe("errorMessage — auth-pages codes (2026-06-02)", () => {
  it("maps email_not_confirmed", () => {
    expect(errorMessage("email_not_confirmed")).toMatch(/verif/i);
  });
  it("maps invalid_credentials", () => {
    expect(errorMessage("invalid_credentials")).toBe("Email or password is incorrect.");
  });
  it("maps rate_limited and over_request_rate_limit", () => {
    expect(errorMessage("rate_limited")).toMatch(/too many/i);
    expect(errorMessage("over_request_rate_limit")).toMatch(/too many/i);
  });
  it("maps otp_expired", () => {
    expect(errorMessage("otp_expired")).toMatch(/expired/i);
  });
});

describe("authErrorMessage", () => {
  it("maps a 429 ApiError to the rate-limited message regardless of code", () => {
    expect(authErrorMessage(new ApiError(429, { detail: "whatever" }))).toMatch(/too many/i);
  });
  it("maps an ApiError code (502 email_provider_unavailable)", () => {
    expect(authErrorMessage(new ApiError(502, { detail: "email_provider_unavailable" }))).toMatch(
      /couldn't send/i,
    );
  });
  it("maps a supabase-shaped AuthError by code", () => {
    expect(authErrorMessage({ code: "email_not_confirmed", status: 400 })).toMatch(/verif/i);
  });
  it("maps a supabase-shaped AuthError by 429 status", () => {
    expect(authErrorMessage({ code: "over_email_send_rate_limit", status: 429 })).toMatch(
      /too many/i,
    );
  });
  it("maps a fetch network failure (TypeError) to the connectivity message", () => {
    expect(authErrorMessage(new TypeError("Failed to fetch"))).toMatch(/connection/i);
  });
  it("falls back to the generic message for an unrecognised value", () => {
    expect(authErrorMessage({})).toMatch(/something went wrong/i);
  });
});
