import { describe, expect, it } from "vitest";
import {
  buildDecisionFlightKey,
  buildGameStreamKey,
  createDecisionRequestLedger,
} from "./decisionProtocol";

describe("decisionProtocol lifecycle handling", () => {
  it("blocks duplicate decisions until the accepted or stale ack releases the active flight", () => {
    const ledger = createDecisionRequestLedger();
    const streamKey = buildGameStreamKey("sess_decision_lifecycle", "seat-1");
    const flightKey = buildDecisionFlightKey({
      requestId: "req_prompt_1",
      playerId: 1,
      requestType: "purchase",
      continuation: {
        promptFingerprint: "sha256:prompt-1",
        promptFingerprintVersion: "prompt-fingerprint-v1",
        promptInstanceId: 1,
        resumeToken: "resume-token-1",
        frameId: "frame-1",
        moduleId: "module-1",
        moduleType: "PurchaseModule",
        moduleCursor: "cursor-1",
        batchId: "batch-1",
      },
    });

    expect(ledger.beginFlight(streamKey, flightKey, "req_prompt_1")).toEqual({
      status: "started",
      requestId: "req_prompt_1",
    });
    ledger.recordSent(streamKey, "req_prompt_1");

    expect(ledger.beginFlight(streamKey, flightKey, "req_prompt_1")).toEqual({
      status: "duplicate",
      requestId: "req_prompt_1",
    });
    expect(ledger.shouldSend(streamKey, "req_prompt_1")).toBe(false);

    expect(ledger.releaseFlight(streamKey, flightKey, "req_prompt_1")).toBe(true);
  });

  it("allows a controlled retry after stale feedback forgets the old request id", () => {
    const ledger = createDecisionRequestLedger();
    const streamKey = buildGameStreamKey("sess_decision_retry", "seat-1");
    const flightKey = "player:1\nprompt:sha256:prompt-2\naction:purchase";

    expect(ledger.beginFlight(streamKey, flightKey, "req_stale")).toEqual({
      status: "started",
      requestId: "req_stale",
    });
    ledger.recordSent(streamKey, "req_stale");

    ledger.releaseFlight(streamKey, flightKey, "req_stale");
    ledger.forget(streamKey, "req_stale");

    expect(ledger.shouldSend(streamKey, "req_stale")).toBe(true);
    expect(ledger.beginFlight(streamKey, flightKey, "req_stale")).toEqual({
      status: "started",
      requestId: "req_stale",
    });
  });
});
