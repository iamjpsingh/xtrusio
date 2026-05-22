// apps/web/src/lib/last-workspace.test.ts
import { beforeEach, describe, expect, it } from "vitest";
import { readLastWorkspace, writeLastWorkspace, clearLastWorkspace } from "./last-workspace";

describe("last-workspace", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("reads null when no value is stored", () => {
    expect(readLastWorkspace()).toBeNull();
  });

  it("round-trips a workspace id", () => {
    writeLastWorkspace("t-123");
    expect(readLastWorkspace()).toBe("t-123");
  });

  it("round-trips the sentinel for the platform shell", () => {
    writeLastWorkspace("__platform__");
    expect(readLastWorkspace()).toBe("__platform__");
  });

  it("clears the stored value", () => {
    writeLastWorkspace("t-1");
    clearLastWorkspace();
    expect(readLastWorkspace()).toBeNull();
  });
});
