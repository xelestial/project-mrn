import { describe, expect, it } from "vitest";
import {
  buildDecisionFlightKey,
  buildDecisionMessage,
  buildGameStreamKey,
  createDecisionRequestLedger,
} from "../domain/stream/decisionProtocol";
import { resolveDecisionFlightIdentity } from "./useGameStream";

describe("useGameStream authoritative commit helpers", () => {
  it("builds the active stream key from the normalized session and token", () => {
    expect(buildGameStreamKey(" sess_a ", "seat-token")).toBe("sess_a\nseat-token");
    expect(buildGameStreamKey("sess_a")).toBe("sess_a\n");
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

  it("can release one request id for a controlled stale-prompt retry", () => {
    const ledger = createDecisionRequestLedger();
    const streamKey = buildGameStreamKey("sess_retry", "seat-1");

    ledger.recordSent(streamKey, "req_retry_1");
    expect(ledger.shouldSend(streamKey, "req_retry_1")).toBe(false);

    ledger.forget(streamKey, "req_retry_1");

    expect(ledger.shouldSend(streamKey, "req_retry_1")).toBe(true);
  });

  it("groups decision flights by active prompt, player, and request type instead of request id alone", () => {
    const first = buildDecisionFlightKey({
      requestId: "req_original",
      playerId: 1,
      requestType: "purchase",
      continuation: {
        promptInstanceId: 91,
        promptFingerprint: "sha256:prompt-91",
        promptFingerprintVersion: "prompt-fingerprint-v1",
        resumeToken: "resume-91",
        frameId: "turn:2:p1",
        moduleId: "mod:purchase:91",
        moduleType: "PurchaseModule",
        moduleCursor: "purchase:await_choice",
        batchId: null,
      },
    });
    const duplicateWithNewRequestId = buildDecisionFlightKey({
      requestId: "req_accidental_second",
      playerId: 1,
      requestType: "purchase",
      continuation: {
        promptInstanceId: 91,
        promptFingerprint: "sha256:prompt-91",
        promptFingerprintVersion: "prompt-fingerprint-v1",
        resumeToken: "resume-91",
        frameId: "turn:2:p1",
        moduleId: "mod:purchase:91",
        moduleType: "PurchaseModule",
        moduleCursor: "purchase:await_choice",
        batchId: null,
      },
    });
    const nextPrompt = buildDecisionFlightKey({
      requestId: "req_next_prompt",
      playerId: 1,
      requestType: "purchase",
      continuation: {
        promptInstanceId: 92,
        promptFingerprint: "sha256:prompt-92",
        promptFingerprintVersion: "prompt-fingerprint-v1",
        resumeToken: "resume-92",
        frameId: "turn:2:p1",
        moduleId: "mod:purchase:92",
        moduleType: "PurchaseModule",
        moduleCursor: "purchase:await_choice",
        batchId: null,
      },
    });

    expect(duplicateWithNewRequestId).toBe(first);
    expect(nextPrompt).not.toBe(first);
  });

  it("uses public protocol identity for decision flights without requiring a legacy numeric bridge", () => {
    const flightIdentity = resolveDecisionFlightIdentity({
      playerId: "player_public_2",
      publicPlayerId: "player_public_2",
      legacyPlayerId: null,
    });

    expect(flightIdentity).toEqual({
      playerId: "player_public_2",
      source: "public",
      legacyPlayerId: null,
      publicPlayerId: "player_public_2",
    });
    if (flightIdentity === null) {
      throw new Error("expected public decision flight identity");
    }
    expect(
      buildDecisionFlightKey({
        requestId: "req_public_prompt",
        playerId: flightIdentity.playerId,
        requestType: "purchase",
        continuation: {
          promptInstanceId: 93,
          promptFingerprint: "sha256:prompt-93",
          promptFingerprintVersion: "prompt-fingerprint-v1",
          resumeToken: "resume-93",
          frameId: "turn:3:p2",
          moduleId: "mod:purchase:93",
          moduleType: "PurchaseModule",
          moduleCursor: "purchase:await_choice",
          batchId: null,
        },
      }),
    ).toBe("player:player_public_2\nprompt:sha256:prompt-93\naction:purchase");
  });

  it("prefers public protocol identity over a numeric top-level legacy alias for decision flights", () => {
    const flightIdentity = resolveDecisionFlightIdentity({
      playerId: 2,
      publicPlayerId: "player_public_2",
      legacyPlayerId: 2,
    });

    expect(flightIdentity).toEqual({
      playerId: "player_public_2",
      source: "public",
      legacyPlayerId: 2,
      publicPlayerId: "player_public_2",
    });
    if (flightIdentity === null) {
      throw new Error("expected public decision flight identity");
    }
    expect(
      buildDecisionFlightKey({
        requestId: "req_public_prompt",
        playerId: flightIdentity.playerId,
        requestType: "purchase",
        continuation: {
          promptInstanceId: 93,
          promptFingerprint: "sha256:prompt-93",
          promptFingerprintVersion: "prompt-fingerprint-v1",
          resumeToken: "resume-93",
          frameId: "turn:3:p2",
          moduleId: "mod:purchase:93",
          moduleType: "PurchaseModule",
          moduleCursor: "purchase:await_choice",
          batchId: null,
        },
      }),
    ).toBe("player:player_public_2\nprompt:sha256:prompt-93\naction:purchase");
  });

  it("blocks a different request id while the same prompt flight is still active", () => {
    const ledger = createDecisionRequestLedger();
    const streamKey = buildGameStreamKey("sess_single_flight", "seat-1");
    const flightKey = "player:1\nprompt:sha256:prompt-9\naction:purchase";

    expect(ledger.beginFlight(streamKey, flightKey, "req_first")).toEqual({
      status: "started",
      requestId: "req_first",
    });
    expect(ledger.beginFlight(streamKey, flightKey, "req_first")).toEqual({
      status: "duplicate",
      requestId: "req_first",
    });
    expect(ledger.beginFlight(streamKey, flightKey, "req_second")).toEqual({
      status: "busy",
      requestId: "req_first",
    });

    ledger.releaseFlight(streamKey, flightKey, "req_first");

    expect(ledger.beginFlight(streamKey, flightKey, "req_second")).toEqual({
      status: "started",
      requestId: "req_second",
    });
  });

  it("builds decision messages with the backend-issued module continuation", () => {
    expect(
      buildDecisionMessage({
        requestId: "req_move_1",
        playerId: 1,
        choiceId: "roll",
        choicePayload: { dice: 4 },
        continuation: {
          promptInstanceId: 31,
          promptFingerprint: "sha256:prompt-31",
          promptFingerprintVersion: "prompt-fingerprint-v1",
          resumeToken: "resume-token-1",
          frameId: "turn:1:p1",
          moduleId: "mod:turn:1:p1:dice",
          moduleType: "DiceRollModule",
          moduleCursor: "dice:await_choice",
          batchId: null,
        },
        viewCommitSeqSeen: 42,
        clientSeq: 42,
      }),
    ).toEqual({
      type: "decision",
      request_id: "req_move_1",
      player_id: 1,
      player_id_alias_role: "legacy_compatibility_alias",
      primary_player_id: 1,
      primary_player_id_source: "legacy",
      choice_id: "roll",
      choice_payload: { dice: 4 },
      resume_token: "resume-token-1",
      prompt_fingerprint: "sha256:prompt-31",
      prompt_fingerprint_version: "prompt-fingerprint-v1",
      frame_id: "turn:1:p1",
      module_id: "mod:turn:1:p1:dice",
      module_type: "DiceRollModule",
      module_cursor: "dice:await_choice",
      prompt_instance_id: 31,
      view_commit_seq_seen: 42,
      client_seq: 42,
    });
  });

  it("keeps prompt instance zero in decision messages", () => {
    expect(
      buildDecisionMessage({
        requestId: "req_batch_1",
        playerId: 1,
        choiceId: "confirm",
        continuation: {
          promptInstanceId: 0,
          promptFingerprint: null,
          promptFingerprintVersion: null,
          resumeToken: "resume-token-0",
          frameId: "turn:1:p1",
          moduleId: "mod:turn:1:p1:burden",
          moduleType: "BurdenExchangeModule",
          moduleCursor: "burden:await_choice",
          batchId: "batch:1",
          missingPlayerIds: [1, 3],
          resumeTokensByPlayerId: {
            "1": "resume-token-0",
            "3": "resume-token-3",
          },
        },
        viewCommitSeqSeen: 7,
        clientSeq: 8,
      }),
    ).toMatchObject({
      prompt_instance_id: 0,
      batch_id: "batch:1",
      missing_player_ids: [1, 3],
      resume_tokens_by_player_id: {
        "1": "resume-token-0",
        "3": "resume-token-3",
      },
    });
  });
});
