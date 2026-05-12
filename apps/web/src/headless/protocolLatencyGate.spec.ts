import { describe, expect, it } from "vitest";
import { evaluateProtocolLatencyGate, protocolCommandLatencyMs } from "./protocolLatencyGate";

describe("protocolLatencyGate", () => {
  it("fails when browser-observed command latency exceeds the configured threshold", () => {
    const result = evaluateProtocolLatencyGate({
      maxCommandLatencyMs: 5_000,
      commands: [
        {
          requestId: "req_fast",
          playerId: 1,
          requestType: "movement",
          promptToDecisionMs: 20,
          decisionToAckMs: 300,
          totalMs: 320,
          status: "accepted",
        },
        {
          requestId: "req_slow_ack",
          playerId: 2,
          requestType: "burden_exchange",
          promptToDecisionMs: 9,
          decisionToAckMs: 9_890,
          totalMs: 9_899,
          status: "accepted",
        },
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.maxCommandMs).toBe(9_899);
    expect(result.offenders).toHaveLength(1);
    expect(result.failures[0]).toContain("protocol command latency exceeded 5000ms");
    expect(result.failures[0]).toContain("request_id=req_slow_ack");
    expect(result.failures[0]).toContain("decision_to_ack_ms=9890");
  });

  it("uses the slowest available command phase when total latency is missing", () => {
    expect(
      protocolCommandLatencyMs({
        requestId: "req_ack_only",
        playerId: 3,
        requestType: "purchase_tile",
        promptToDecisionMs: null,
        decisionToAckMs: 5_400,
        totalMs: null,
        status: "accepted",
      }),
    ).toBe(5_400);
  });

  it("is disabled when no threshold is configured", () => {
    const result = evaluateProtocolLatencyGate({
      commands: [
        {
          requestId: "req_slow",
          playerId: 1,
          requestType: "movement",
          promptToDecisionMs: 0,
          decisionToAckMs: 10_000,
          totalMs: 10_000,
          status: "accepted",
        },
      ],
    });

    expect(result.ok).toBe(true);
    expect(result.offenders).toEqual([]);
    expect(result.failures).toEqual([]);
  });
});
