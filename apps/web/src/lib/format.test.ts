import { describe, expect, it } from "vitest";
import { formatDateTime } from "./format";

describe("formatDateTime", () => {
  it("formats a valid ISO timestamp deterministically (UTC, en-US)", () => {
    // 14:30 UTC — fixed timezone means the output never drifts with the host.
    expect(formatDateTime("2026-06-05T14:30:00Z")).toBe("Jun 5, 2026, 02:30 PM");
  });

  it("formats midnight UTC", () => {
    expect(formatDateTime("2026-01-01T00:00:00Z")).toBe("Jan 1, 2026, 12:00 AM");
  });

  it("returns the default em-dash fallback for null", () => {
    expect(formatDateTime(null)).toBe("—");
  });

  it("returns the default fallback for undefined / empty string", () => {
    expect(formatDateTime(undefined)).toBe("—");
    expect(formatDateTime("")).toBe("—");
  });

  it("honours a custom fallback (the platform-users 'Never' case)", () => {
    expect(formatDateTime(null, { fallback: "Never" })).toBe("Never");
  });

  it("returns the fallback (not 'Invalid Date') for an unparseable string", () => {
    expect(formatDateTime("not-a-date")).toBe("—");
    expect(formatDateTime("not-a-date", { fallback: "Never" })).toBe("Never");
  });
});
