import { describe, expect, it } from "vitest";
import { errorMessage } from "./error-messages";

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
