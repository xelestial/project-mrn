import { describe, expect, it } from "vitest";
import {
  buildDecisionMessage,
  buildGameStreamKey,
  createDecisionRequestLedger,
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

  it("records a decision request id exactly once per stream key", () => {
    const ledger = createDecisionRequestLedger();
    const streamKey = buildGameStreamKey("sess_a", "seat-1");

    expect(ledger.shouldSend(streamKey, "req_burden_3")).toBe(true);
    ledger.recordSent(streamKey, "req_burden_3");

    expect(ledger.shouldSend(streamKey, "req_burden_3")).toBe(false);
    expect(ledger.shouldSend(streamKey, "req_burden_4")).toBe(true);
  });

  it("clears sent decision ids when the stream key changes", () => {
    const ledger = createDecisionRequestLedger();
    const firstStream = buildGameStreamKey("sess_a", "seat-1");
    const secondStream = buildGameStreamKey("sess_a", "seat-2");

    ledger.recordSent(firstStream, "req_1");

    expect(ledger.shouldSend(firstStream, "req_1")).toBe(false);
    expect(ledger.shouldSend(secondStream, "req_1")).toBe(true);
  });

  it("keeps sent decision ids across fresh hook ledgers for the same stream key", () => {
    const streamKey = buildGameStreamKey("sess_recovered_ledgers", "seat-1");
    const firstLedger = createDecisionRequestLedger();
    const secondLedger = createDecisionRequestLedger();

    firstLedger.recordSent(streamKey, "req_burden_3");

    expect(secondLedger.shouldSend(streamKey, "req_burden_3")).toBe(false);
    expect(secondLedger.shouldSend(streamKey, "req_burden_4")).toBe(true);
  });

  it("builds decision messages with the backend-issued module continuation", () => {
    expect(
      buildDecisionMessage({
        requestId: "req_move_1",
        playerId: 1,
        choiceId: "roll",
        choicePayload: { dice: 4 },
        continuation: {
          resumeToken: "resume-token-1",
          frameId: "turn:1:p1",
          moduleId: "mod:turn:1:p1:dice",
          moduleType: "DiceRollModule",
          moduleCursor: "dice:await_choice",
          batchId: null,
        },
        clientSeq: 42,
      }),
    ).toEqual({
      type: "decision",
      request_id: "req_move_1",
      player_id: 1,
      choice_id: "roll",
      choice_payload: { dice: 4 },
      resume_token: "resume-token-1",
      frame_id: "turn:1:p1",
      module_id: "mod:turn:1:p1:dice",
      module_type: "DiceRollModule",
      module_cursor: "dice:await_choice",
      client_seq: 42,
    });
  });
});
