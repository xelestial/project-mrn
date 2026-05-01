import { describe, expect, it } from "vitest";
import {
  buildGameStreamKey,
  shouldApplyReplayResponse,
} from "./useGameStream";

describe("useGameStream replay recovery guards", () => {
  it("builds the active stream key from the normalized session and token", () => {
    expect(buildGameStreamKey(" sess_a ", "seat-token")).toBe("sess_a\nseat-token");
    expect(buildGameStreamKey("sess_a")).toBe("sess_a\n");
  });

  it("rejects replay responses captured for a previous stream key", () => {
    const captured = buildGameStreamKey("sess_a", "seat-1");
    const active = buildGameStreamKey("sess_a", "seat-2");

    expect(shouldApplyReplayResponse(captured, active)).toBe(false);
  });

  it("rejects replay responses after the request is aborted", () => {
    const controller = new AbortController();
    const streamKey = buildGameStreamKey("sess_a", "seat-1");

    controller.abort();

    expect(shouldApplyReplayResponse(streamKey, streamKey, controller.signal)).toBe(false);
  });
});
