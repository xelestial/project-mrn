import { afterEach, describe, expect, it, vi } from "vitest";
import { emptyHeadlessMetrics } from "./HeadlessGameClient";
import {
  buildProtocolProgressKey,
  buildProtocolPaceDiagnostic,
  buildHeadlessHumanSessionPayload,
  evaluateProtocolGate,
  fetchRuntimeStatus,
  policyForProtocolPlayer,
  shouldEmitProtocolProgress,
  summarizeProtocolClients,
  type ProtocolClientRuntime,
} from "./fullStackProtocolHarness";

function clientRuntime(
  label: string,
  overrides: Partial<ProtocolClientRuntime> = {},
): ProtocolClientRuntime {
  return {
    label,
    role: label === "spectator" ? "spectator" : "seat",
    playerId: label === "spectator" ? 0 : Number(label.replace("seat:", "")),
    status: "connected",
    lastCommitSeq: 12,
    metrics: emptyHeadlessMetrics(),
    traceCount: 0,
    ...overrides,
  };
}

type ProgressClient = Parameters<typeof buildProtocolProgressKey>[0][number];

function progressClient(
  playerId: number,
  overrides: Partial<ProgressClient> = {},
): ProgressClient {
  return {
    playerId,
    status: "connected",
    state: {
      lastCommitSeq: 20,
    } as ProgressClient["state"],
    metrics: emptyHeadlessMetrics(),
    ...overrides,
  };
}

describe("fullStackProtocolHarness", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates four human seats and public visibility for protocol RL sessions", () => {
    const payload = buildHeadlessHumanSessionPayload({
      seed: 20260508,
      seatCount: 4,
      config: { runtime: { policy_mode: "baseline" } },
    });

    expect(payload.seats).toEqual([
      { seat: 1, seat_type: "human" },
      { seat: 2, seat_type: "human" },
      { seat: 3, seat_type: "human" },
      { seat: 4, seat_type: "human" },
    ]);
    expect(payload.config).toMatchObject({
      seed: 20260508,
      visibility: "public",
      runtime: { seed: 20260508, policy_mode: "baseline" },
    });
  });

  it("keeps compact client summaries without raw stream payloads", () => {
    const summary = summarizeProtocolClients([
      clientRuntime("seat:1"),
      clientRuntime("spectator", {
        playerId: 0,
        lastCommitSeq: 11,
      }),
    ]);

    expect(summary).toEqual({
      "seat:1": expect.objectContaining({
        role: "seat",
        playerId: 1,
        lastCommitSeq: 12,
      }),
      spectator: expect.objectContaining({
        role: "spectator",
        playerId: 0,
        lastCommitSeq: 11,
      }),
    });
    expect(JSON.stringify(summary)).not.toContain("view_state");
    expect(JSON.stringify(summary)).not.toContain("messages");
  });

  it("selects per-player policies when profile maps are configured", () => {
    const defaultPolicy = vi.fn();
    const seatTwoPolicy = vi.fn();

    expect(policyForProtocolPlayer(1, defaultPolicy, { 2: seatTwoPolicy })).toBe(defaultPolicy);
    expect(policyForProtocolPlayer(2, defaultPolicy, { 2: seatTwoPolicy })).toBe(seatTwoPolicy);
  });

  it("fails the gate on protocol instability and passes a healthy completion", () => {
    const healthy = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: { ...emptyHeadlessMetrics(), acceptedAckCount: 3 },
        }),
        clientRuntime("spectator", {
          metrics: { ...emptyHeadlessMetrics(), runtimeCompletedCount: 1 },
        }),
      ],
    });
    expect(healthy.ok).toBe(true);
    expect(healthy.failures).toEqual([]);

    const recoveredStale = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            acceptedAckCount: 3,
            staleAckCount: 1,
            staleDecisionRetryCount: 1,
          },
        }),
        clientRuntime("spectator", {
          metrics: { ...emptyHeadlessMetrics(), runtimeCompletedCount: 1 },
        }),
      ],
    });
    expect(recoveredStale.ok).toBe(true);

    const unstable = evaluateProtocolGate({
      timedOut: false,
      completed: false,
      clients: [
        clientRuntime("seat:2", {
          metrics: {
            ...emptyHeadlessMetrics(),
            nonMonotonicCommitCount: 1,
            semanticCommitRegressionCount: 1,
            rejectedAckCount: 1,
            staleAckCount: 1,
          },
        }),
      ],
    });
    expect(unstable.ok).toBe(false);
    expect(unstable.failures).toEqual(
      expect.arrayContaining([
        "game did not reach completed runtime status",
        "seat:2 did not complete any accepted decision through websocket",
        "seat:2 saw non-monotonic commit seq 1 time(s)",
        "seat:2 saw runtime position regression 1 time(s)",
        "seat:2 received rejected decision ack 1 time(s)",
        "seat:2 has unrecovered stale decision ack 1/1 time(s)",
      ]),
    );
  });

  it("does not accept server-only completion without a completed websocket commit", () => {
    const result = evaluateProtocolGate({
      timedOut: false,
      completed: false,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: { ...emptyHeadlessMetrics(), acceptedAckCount: 1 },
        }),
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toContain("no websocket client received completed view_commit");
  });

  it("fails the gate when a client answers a raw prompt before the active view_commit", () => {
    const result = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            acceptedAckCount: 1,
            rawPromptFallbackWithoutActiveCommitCount: 1,
          },
        }),
        clientRuntime("spectator", {
          metrics: { ...emptyHeadlessMetrics(), runtimeCompletedCount: 1 },
        }),
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toContain("seat:1 answered raw prompt before active view_commit 1 time(s)");
  });

  it("fails the gate when spectator receives private prompt or decision ack messages", () => {
    const result = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: { ...emptyHeadlessMetrics(), acceptedAckCount: 1 },
        }),
        clientRuntime("spectator", {
          metrics: {
            ...emptyHeadlessMetrics(),
            runtimeCompletedCount: 1,
            spectatorPromptLeakCount: 1,
            spectatorDecisionAckLeakCount: 1,
          },
        }),
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toEqual(
      expect.arrayContaining([
        "spectator received private prompt 1 time(s)",
        "spectator received private decision ack 1 time(s)",
      ]),
    );
  });

  it("fails the gate when the protocol stops making observable progress", () => {
    const result = evaluateProtocolGate({
      timedOut: false,
      idleTimedOut: true,
      completed: false,
      runtimeStatus: "waiting_input",
      clients: [
        clientRuntime("seat:1", {
          metrics: { ...emptyHeadlessMetrics(), acceptedAckCount: 1 },
        }),
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toContain("protocol run made no websocket/runtime progress before completion");
  });

  it("fails the gate when a forced reconnect never receives a recovery view_commit", () => {
    const result = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            acceptedAckCount: 1,
            reconnectCount: 2,
            forcedReconnectCount: 2,
            reconnectRecoveryCount: 1,
            reconnectRecoveryPendingCount: 1,
          },
        }),
        clientRuntime("spectator", {
          metrics: { ...emptyHeadlessMetrics(), runtimeCompletedCount: 1 },
        }),
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toEqual(
      expect.arrayContaining([
        "seat:1 has unresolved reconnect recovery 1 time(s)",
        "seat:1 recovered 1/2 forced reconnect(s)",
      ]),
    );
  });

  it("treats prompt delivery and reconnect recovery as protocol progress", () => {
    const base = buildProtocolProgressKey([progressClient(1)], "waiting_input");

    expect(
      buildProtocolProgressKey([
        progressClient(1, {
          metrics: { ...emptyHeadlessMetrics(), promptMessageCount: 1 },
        }),
      ], "waiting_input"),
    ).not.toBe(base);
    expect(
      buildProtocolProgressKey([
        progressClient(1, {
          metrics: { ...emptyHeadlessMetrics(), reconnectRecoveryCount: 1 },
        }),
      ], "waiting_input"),
    ).not.toBe(base);
  });

  it("summarizes protocol pace and the active prompt in progress diagnostics", () => {
    const pace = buildProtocolPaceDiagnostic({
      runtimeStatus: "waiting_input",
      elapsedMs: 30_000,
      clients: [
        clientRuntime("seat:1", {
          lastCommitSeq: 12,
          metrics: {
            ...emptyHeadlessMetrics(),
            outboundDecisionCount: 2,
            acceptedAckCount: 1,
          },
        }),
        clientRuntime("seat:2", {
          lastCommitSeq: 14,
          metrics: {
            ...emptyHeadlessMetrics(),
            outboundDecisionCount: 1,
            acceptedAckCount: 1,
          },
        }),
      ],
      traces: [
        {
          event: "view_commit_seen",
          session_id: "sess_1",
          player_id: 1,
          commit_seq: 14,
          payload: {
            runtime_status: "waiting_input",
            round_index: 2,
            turn_index: 5,
            active_prompt_request_id: "req_purchase",
            active_prompt_player_id: 2,
            active_prompt_request_type: "purchase_tile",
          },
        },
        {
          event: "decision_sent",
          session_id: "sess_1",
          player_id: 1,
          request_id: "req_roll",
        },
        {
          event: "decision_ack",
          session_id: "sess_1",
          player_id: 1,
          request_id: "req_roll",
          status: "accepted",
        },
      ],
    });

    expect(pace).toMatchObject({
      maxCommitSeq: 14,
      latestRoundIndex: 2,
      latestTurnIndex: 5,
      activePromptRequestId: "req_purchase",
      activePromptPlayerId: 2,
      activePromptRequestType: "purchase_tile",
      waitingOnActivePrompt: true,
      latestTraceEvent: "decision_ack",
      latestDecisionRequestId: "req_roll",
      latestAckRequestId: "req_roll",
      latestAckStatus: "accepted",
      commitSeqPerMinute: 28,
      decisionsPerMinute: 6,
      acceptedAcksPerMinute: 4,
    });
  });

  it("keeps missing active prompt fields null in progress diagnostics", () => {
    const pace = buildProtocolPaceDiagnostic({
      runtimeStatus: "running",
      elapsedMs: 15_000,
      clients: [clientRuntime("seat:1", { lastCommitSeq: 3 })],
      traces: [
        {
          event: "view_commit_seen",
          session_id: "sess_1",
          player_id: 1,
          commit_seq: 3,
          payload: {
            runtime_status: "running",
            round_index: null,
            turn_index: undefined,
            active_prompt_request_id: null,
            active_prompt_player_id: null,
            active_prompt_request_type: "",
          },
        },
      ],
    });

    expect(pace).toMatchObject({
      latestRoundIndex: null,
      latestTurnIndex: null,
      activePromptRequestId: null,
      activePromptPlayerId: null,
      activePromptRequestType: null,
      waitingOnActivePrompt: false,
    });
  });

  it("fails the gate when the server used decision timeout fallback", () => {
    const result = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            acceptedAckCount: 2,
            decisionTimeoutFallbackCount: 1,
          },
        }),
        clientRuntime("spectator", {
          metrics: { ...emptyHeadlessMetrics(), runtimeCompletedCount: 1 },
        }),
      ],
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toContain("seat:1 saw server decision timeout fallback 1 time(s)");
  });

  it("does not treat heartbeat, repeated snapshots, resume requests, or reconnects as game progress", () => {
    const before = progressClient(1);
    const after = progressClient(1, {
      metrics: {
        ...emptyHeadlessMetrics(),
        inboundMessageCount: 18,
        viewCommitCount: 7,
        snapshotPulseCount: 5,
        heartbeatCount: 4,
        resumeRequestCount: 3,
        reconnectCount: 2,
      },
    });

    expect(buildProtocolProgressKey([after], "waiting_input")).toBe(
      buildProtocolProgressKey([before], "waiting_input"),
    );
  });

  it("does treat new commits, decisions, acknowledgements, and protocol errors as game progress", () => {
    const base = buildProtocolProgressKey([progressClient(1)], "waiting_input");

    expect(
      buildProtocolProgressKey([
        progressClient(1, {
          state: { lastCommitSeq: 21 } as ProgressClient["state"],
        }),
      ], "waiting_input"),
    ).not.toBe(base);
    expect(
      buildProtocolProgressKey([
        progressClient(1, {
          metrics: { ...emptyHeadlessMetrics(), outboundDecisionCount: 1 },
        }),
      ], "waiting_input"),
    ).not.toBe(base);
    expect(
      buildProtocolProgressKey([
        progressClient(1, {
          metrics: { ...emptyHeadlessMetrics(), acceptedAckCount: 1 },
        }),
      ], "waiting_input"),
    ).not.toBe(base);
    expect(
      buildProtocolProgressKey([
        progressClient(1, {
          metrics: { ...emptyHeadlessMetrics(), errorMessageCount: 1 },
        }),
      ], "waiting_input"),
    ).not.toBe(base);
  });

  it("emits progress logs immediately on startup, periodically, and on observable progress changes", () => {
    expect(
      shouldEmitProtocolProgress({
        enabled: false,
        nowMs: 1_000,
        lastCallbackAtMs: 0,
        progressIntervalMs: 5_000,
        progressKeyChanged: true,
      }),
    ).toBe(false);

    expect(
      shouldEmitProtocolProgress({
        enabled: true,
        nowMs: 1_000,
        lastCallbackAtMs: 0,
        progressIntervalMs: 5_000,
        progressKeyChanged: false,
      }),
    ).toBe(true);

    expect(
      shouldEmitProtocolProgress({
        enabled: true,
        nowMs: 1_500,
        lastCallbackAtMs: 1_000,
        progressIntervalMs: 5_000,
        progressKeyChanged: true,
      }),
    ).toBe(false);

    expect(
      shouldEmitProtocolProgress({
        enabled: true,
        nowMs: 2_000,
        lastCallbackAtMs: 1_000,
        progressIntervalMs: 5_000,
        progressKeyChanged: true,
      }),
    ).toBe(true);

    expect(
      shouldEmitProtocolProgress({
        enabled: true,
        nowMs: 5_999,
        lastCallbackAtMs: 1_000,
        progressIntervalMs: 5_000,
        progressKeyChanged: false,
      }),
    ).toBe(false);

    expect(
      shouldEmitProtocolProgress({
        enabled: true,
        nowMs: 6_000,
        lastCallbackAtMs: 1_000,
        progressIntervalMs: 5_000,
        progressKeyChanged: false,
      }),
    ).toBe(true);
  });

  it("reports a missing runtime session as not_found instead of throwing", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          ok: false,
          error: { code: "SESSION_NOT_FOUND", message: "Session not found" },
        }),
        { status: 404, headers: { "content-type": "application/json" } },
      ),
    );

    await expect(fetchRuntimeStatus("http://127.0.0.1:9091", "sess_missing", "token")).resolves.toBe("not_found");
  });

  it("retries transient runtime status fetch failures", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    fetchMock
      .mockRejectedValueOnce(new TypeError("fetch failed"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            ok: true,
            data: { runtime: { status: "waiting_input" } },
          }),
          { status: 200, headers: { "content-type": "application/json" } },
        ),
      );

    await expect(fetchRuntimeStatus("http://127.0.0.1:9091", "sess_retry", "token")).resolves.toBe("waiting_input");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
