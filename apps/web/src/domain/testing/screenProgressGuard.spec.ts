import { describe, expect, it } from "vitest";

import { createScreenProgressGuard } from "../../../scripts/screenProgressGuard.mjs";

describe("screen progress guard", () => {
  it("fails when the visible screen signature does not change for the stall window", () => {
    const guard = createScreenProgressGuard({ stallMs: 60_000, startTimeMs: 0 });

    expect(guard.observe({ nowMs: 0, commitSeq: 12, screenSignature: "round-1" }).status).toBe(
      "progress",
    );
    expect(guard.observe({ nowMs: 59_999, commitSeq: 12, screenSignature: "round-1" }).status).toBe(
      "idle",
    );

    const stalled = guard.observe({ nowMs: 60_000, commitSeq: 12, screenSignature: "round-1" });

    expect(stalled).toMatchObject({
      status: "stalled",
      stalledMs: 60_000,
      lastCommitSeq: 12,
    });
  });

  it("does not reset the visible screen stall timer when only commit_seq advances", () => {
    const guard = createScreenProgressGuard({ stallMs: 60_000, startTimeMs: 0 });

    guard.observe({ nowMs: 0, commitSeq: 1, screenSignature: "round-1" });
    guard.observe({ nowMs: 30_000, commitSeq: 2, screenSignature: "round-1" });

    const stalled = guard.observe({ nowMs: 60_000, commitSeq: 3, screenSignature: "round-1" });

    expect(stalled).toMatchObject({
      status: "stalled",
      stalledMs: 60_000,
      lastCommitSeq: 3,
    });
  });

  it("resets the stall timer when the screen changes even if commit_seq is unchanged", () => {
    const guard = createScreenProgressGuard({ stallMs: 60_000, startTimeMs: 0 });

    guard.observe({ nowMs: 0, commitSeq: 3, screenSignature: "prompt-a" });
    guard.observe({ nowMs: 59_000, commitSeq: 3, screenSignature: "prompt-b" });

    expect(guard.observe({ nowMs: 118_999, commitSeq: 3, screenSignature: "prompt-b" }).status).toBe(
      "idle",
    );
    expect(guard.observe({ nowMs: 119_000, commitSeq: 3, screenSignature: "prompt-b" }).status).toBe(
      "stalled",
    );
  });
});
