import { describe, expect, it } from "vitest";
import { formatDuration, jobStatusVariant } from "./job-run-format";

describe("formatDuration", () => {
  it("renders sub-second as ms", () => {
    expect(formatDuration(0)).toBe("0ms");
    expect(formatDuration(850)).toBe("850ms");
  });

  it("renders seconds with one decimal", () => {
    expect(formatDuration(1200)).toBe("1.2s");
    expect(formatDuration(59000)).toBe("59.0s");
  });

  it("renders minutes and seconds past a minute", () => {
    expect(formatDuration(65000)).toBe("1m 5s");
    expect(formatDuration(125000)).toBe("2m 5s");
  });
});

describe("jobStatusVariant", () => {
  it("maps known statuses", () => {
    expect(jobStatusVariant("success")).toBe("secondary");
    expect(jobStatusVariant("partial")).toBe("outline");
    expect(jobStatusVariant("error")).toBe("destructive");
  });

  it("falls back to outline for unknown status", () => {
    expect(jobStatusVariant("weird")).toBe("outline");
  });
});
