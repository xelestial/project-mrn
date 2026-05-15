import { afterEach, describe, expect, it, vi } from "vitest";
import { emptyHeadlessMetrics } from "./HeadlessGameClient";
import {
  buildProtocolProgressKey,
  buildProtocolPaceDiagnostic,
  buildHeadlessHumanSessionPayload,
  collectProtocolPromptRepetitionFailures,
  collectProtocolSuspicionFailures,
  evaluateProtocolGate,
  evaluateProtocolBackendTimingGate,
  fetchRuntimeStatus,
  joinProtocolSeats,
  parseProtocolBackendTimingEvents,
  policyForProtocolPlayer,
  resolveProtocolTimeoutPolicy,
  shouldEmitProtocolProgress,
  summarizeProtocolBackendTiming,
  summarizeProtocolClients,
  summarizeProtocolGateEvidence,
  summarizeProtocolPromptRepetitions,
  summarizeProtocolThroughput,
  type ProtocolClientRuntime,
} from "./fullStackProtocolHarness";
import type { FrontendTransportAdapter } from "./frontendTransportAdapter";

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
      runtime: { seed: 20260508, policy_mode: "baseline", ai_decision_delay_ms: 0 },
    });
  });

  it("preserves an explicit protocol server AI decision delay override", () => {
    const payload = buildHeadlessHumanSessionPayload({
      seed: 20260508,
      config: { runtime: { ai_decision_delay_ms: 250 } },
    });

    expect(payload.config).toMatchObject({
      runtime: { seed: 20260508, ai_decision_delay_ms: 250 },
    });
  });

  it("uses explicit legacy join companions instead of coercing public player ids", async () => {
    const transport = {
      joinSession: vi.fn(async ({ seat }: { seat: number }) => ({
        seat,
        player_id: `player_public_${seat}`,
        legacy_player_id: seat,
        public_player_id: `player_public_${seat}`,
        seat_id: `seat_public_${seat}`,
        viewer_id: `viewer_public_${seat}`,
        session_token: `session_p${seat}_token`,
      })),
    } as unknown as FrontendTransportAdapter;

    const joins = await joinProtocolSeats(
      "http://127.0.0.1:9091",
      {
        sessionId: "session_test",
        joinTokens: {
          2: "join_two",
          1: "join_one",
        },
      },
      transport,
    );

    expect(joins).toEqual([
      { seat: 1, playerId: 1, token: "session_p1_token" },
      { seat: 2, playerId: 2, token: "session_p2_token" },
    ]);
    expect(joins.some((join) => Number.isNaN(join.playerId))).toBe(false);
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

  it("summarizes protocol gate evidence for topology, prompt lifecycle, reconnects, and privacy", () => {
    const evidence = summarizeProtocolGateEvidence({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      expectedSeatCount: 4,
      requireSpectator: true,
      requireProtocolEvidence: true,
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            viewCommitCount: 5,
            promptMessageCount: 1,
            outboundDecisionCount: 1,
            acceptedAckCount: 1,
            forcedReconnectCount: 1,
            reconnectRecoveryCount: 1,
          },
        }),
        clientRuntime("seat:2", {
          metrics: { ...emptyHeadlessMetrics(), viewCommitCount: 4, acceptedAckCount: 1 },
        }),
        clientRuntime("seat:3", {
          metrics: { ...emptyHeadlessMetrics(), viewCommitCount: 4, acceptedAckCount: 1 },
        }),
        clientRuntime("seat:4", {
          metrics: { ...emptyHeadlessMetrics(), viewCommitCount: 4, acceptedAckCount: 1 },
        }),
        clientRuntime("spectator", {
          metrics: { ...emptyHeadlessMetrics(), viewCommitCount: 4, runtimeCompletedCount: 1 },
        }),
      ],
      traces: [
        {
          event: "view_commit_seen",
          session_id: "sess_1",
          player_id: 1,
          commit_seq: 9,
          payload: {
            active_prompt_request_id: "req_roll",
            active_prompt_player_id: 1,
            active_prompt_request_type: "movement",
          },
        },
        { event: "decision_sent", session_id: "sess_1", player_id: 1, request_id: "req_roll" },
        {
          event: "decision_ack",
          session_id: "sess_1",
          player_id: 1,
          request_id: "req_roll",
          status: "accepted",
        },
      ],
    });

    expect(evidence).toMatchObject({
      expectedSeatCount: 4,
      spectatorRequired: true,
      seatClientCount: 4,
      spectatorClientCount: 1,
      completedViewCommitClientCount: 1,
      viewCommitCount: 21,
      maxCommitSeq: 12,
      promptMessageCount: 1,
      activePromptViewCommitTraceCount: 1,
      outboundDecisionCount: 1,
      decisionSentTraceCount: 1,
      acceptedAckCount: 4,
      acceptedDecisionAckTraceCount: 1,
      forcedReconnectCount: 1,
      reconnectRecoveryCount: 1,
      spectatorPromptLeakCount: 0,
      spectatorDecisionAckLeakCount: 0,
      identityViolationCount: 0,
      traceCount: 3,
    });
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

    const recoveredUnackedRetryStale = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            acceptedAckCount: 3,
            runtimeCompletedCount: 1,
            staleAckCount: 2,
            unackedDecisionRetryCount: 2,
          },
        }),
      ],
    });
    expect(recoveredUnackedRetryStale.ok).toBe(true);

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

    const unrecoveredUnackedRetryStale = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            acceptedAckCount: 3,
            staleAckCount: 3,
            unackedDecisionRetryCount: 2,
          },
        }),
      ],
    });
    expect(unrecoveredUnackedRetryStale.ok).toBe(false);
    expect(unrecoveredUnackedRetryStale.failures).toContain("seat:1 has unrecovered stale decision ack 1/3 time(s)");
  });

  it("fails the gate when required protocol topology or lifecycle evidence is missing", () => {
    const result = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      expectedSeatCount: 4,
      requireSpectator: true,
      requireProtocolEvidence: true,
      clients: [
        clientRuntime("seat:1", {
          metrics: {
            ...emptyHeadlessMetrics(),
            runtimeCompletedCount: 1,
            viewCommitCount: 1,
            outboundDecisionCount: 1,
            acceptedAckCount: 1,
          },
        }),
      ],
      traces: [{ event: "view_commit_seen", session_id: "sess_1", player_id: 1, commit_seq: 1 }],
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toEqual(
      expect.arrayContaining([
        "protocol gate expected 4 seat client(s), saw 1",
        "protocol gate expected a spectator websocket client",
        "protocol evidence did not include accepted decision_ack trace",
        "protocol evidence did not include decision_sent trace",
        "protocol evidence did not include active prompt view_commit trace",
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
          ts_ms: 1_000,
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
          ts_ms: 1_750,
          session_id: "sess_1",
          player_id: 1,
          request_id: "req_roll",
          payload: {
            request_type: "movement",
          },
        },
        {
          event: "decision_ack",
          ts_ms: 2_250,
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
      slowestCommandLatencies: [
        {
          requestId: "req_roll",
          playerId: 1,
          requestType: "movement",
          promptToDecisionMs: null,
          decisionToAckMs: 500,
          totalMs: null,
          status: "accepted",
        },
      ],
      pendingDecisionAges: [],
    });
  });

  it("reports prompt-to-decision and pending decision command latencies", () => {
    const pace = buildProtocolPaceDiagnostic({
      runtimeStatus: "waiting_input",
      elapsedMs: 10_000,
      clients: [clientRuntime("seat:2", { lastCommitSeq: 9 })],
      traces: [
        {
          event: "view_commit_seen",
          ts_ms: 10_000,
          session_id: "sess_1",
          player_id: 2,
          commit_seq: 9,
          payload: {
            active_prompt_request_id: "req_slow",
            active_prompt_player_id: 2,
            active_prompt_request_type: "purchase_tile",
          },
        },
        {
          event: "decision_sent",
          ts_ms: 23_500,
          session_id: "sess_1",
          player_id: 2,
          request_id: "req_slow",
        },
        {
          event: "decision_ack",
          ts_ms: 24_100,
          session_id: "sess_1",
          player_id: 2,
          request_id: "req_slow",
          status: "accepted",
        },
        {
          event: "decision_sent",
          ts_ms: 26_000,
          session_id: "sess_1",
          player_id: 2,
          request_id: "req_pending",
          payload: {
            request_type: "movement",
          },
        },
        {
          event: "view_commit_seen",
          ts_ms: 31_000,
          session_id: "sess_1",
          player_id: 2,
          commit_seq: 10,
          payload: {},
        },
      ],
    });

    expect(pace.slowestCommandLatencies[0]).toMatchObject({
      requestId: "req_slow",
      promptToDecisionMs: 13_500,
      decisionToAckMs: 600,
      totalMs: 14_100,
    });
    expect(pace.pendingDecisionAges[0]).toMatchObject({
      requestId: "req_pending",
      playerId: 2,
      requestType: "movement",
      ageMs: 5_000,
    });
  });

  it("keeps public active prompt identity in pace and repetition diagnostics", () => {
    const traces = [
      {
        event: "view_commit_seen",
        ts_ms: 10_000,
        session_id: "sess_public",
        player_id: 2,
        commit_seq: 9,
        payload: {
          runtime_status: "waiting_input",
          round_index: 1,
          turn_index: 2,
          active_module_id: "module:public:prompt",
          active_module_type: "PurchaseModule",
          active_prompt_request_id: "req_public_1",
          active_prompt_primary_player_id: "player_public_2",
          active_prompt_primary_player_id_source: "public",
          active_prompt_player_id: 2,
          active_prompt_legacy_player_id: 2,
          active_prompt_public_player_id: "player_public_2",
          active_prompt_seat_id: "seat_public_2",
          active_prompt_viewer_id: "viewer_public_2",
          active_prompt_request_type: "purchase_tile",
        },
      },
      {
        event: "decision_sent",
        ts_ms: 12_000,
        session_id: "sess_public",
        player_id: 2,
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        protocol_player_id: "player_public_2",
        legacy_player_id: 2,
        public_player_id: "player_public_2",
        seat_id: "seat_public_2",
        viewer_id: "viewer_public_2",
        request_id: "req_public_1",
        payload: {
          request_type: "purchase_tile",
        },
      },
      {
        event: "decision_ack",
        ts_ms: 12_500,
        session_id: "sess_public",
        player_id: 2,
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        protocol_player_id: "player_public_2",
        legacy_player_id: 2,
        public_player_id: "player_public_2",
        seat_id: "seat_public_2",
        viewer_id: "viewer_public_2",
        request_id: "req_public_1",
        status: "accepted",
      },
      {
        event: "view_commit_seen",
        ts_ms: 13_000,
        session_id: "sess_public",
        player_id: 2,
        commit_seq: 10,
        payload: {
          runtime_status: "waiting_input",
          round_index: 1,
          turn_index: 2,
          active_module_id: "module:public:prompt",
          active_module_type: "PurchaseModule",
          active_prompt_request_id: "req_public_2",
          active_prompt_primary_player_id: "player_public_2",
          active_prompt_primary_player_id_source: "public",
          active_prompt_player_id: 2,
          active_prompt_legacy_player_id: 2,
          active_prompt_public_player_id: "player_public_2",
          active_prompt_seat_id: "seat_public_2",
          active_prompt_viewer_id: "viewer_public_2",
          active_prompt_request_type: "purchase_tile",
        },
      },
    ] as const;

    const pace = buildProtocolPaceDiagnostic({
      runtimeStatus: "waiting_input",
      elapsedMs: 10_000,
      clients: [clientRuntime("seat:2", { lastCommitSeq: 10 })],
      traces: [...traces],
    });
    const repeated = summarizeProtocolPromptRepetitions([...traces], 1);

    expect(pace).toMatchObject({
      activePromptRequestId: "req_public_2",
      activePromptPrimaryPlayerId: "player_public_2",
      activePromptPrimaryPlayerIdSource: "public",
      activePromptPlayerId: 2,
    });
    expect(pace.slowestCommandLatencies[0]).toMatchObject({
      requestId: "req_public_1",
      primaryPlayerId: "player_public_2",
      primaryPlayerIdSource: "public",
      playerId: 2,
      requestType: "purchase_tile",
    });
    expect(repeated[0]).toMatchObject({
      primaryPlayerId: "player_public_2",
      primaryPlayerIdSource: "public",
      playerId: 2,
      count: 2,
    });
    expect(repeated[0].signature).toContain("player=player_public_2");
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

  it("classifies timeout fallback as a fail-fast protocol suspicion", () => {
    const failures = collectProtocolSuspicionFailures([
      clientRuntime("seat:1", {
        metrics: {
          ...emptyHeadlessMetrics(),
          acceptedAckCount: 2,
          decisionTimeoutFallbackCount: 1,
        },
      }),
    ]);

    expect(failures).toContain("seat:1 saw server decision timeout fallback 1 time(s)");
  });

  it("fails fast when the same module keeps issuing new prompt ids for the same request type", () => {
    const traces = Array.from({ length: 9 }, (_, index) => ({
      event: "view_commit_seen",
      ts_ms: 1_000 + index,
      session_id: "sess_loop",
      player_id: index % 2 === 0 ? 3 : 0,
      commit_seq: 50 + index,
      payload: {
        runtime_status: "waiting_input",
        round_index: 1,
        turn_index: 1,
        active_module_id: "mod:seq:action:1:p2:53:fortuneresolve",
        active_module_type: "FortuneResolveModule",
        active_prompt_request_id: `trick_tile_target:${index + 1}`,
        active_prompt_player_id: 3,
        active_prompt_request_type: "trick_tile_target",
      },
    }));

    const repeated = summarizeProtocolPromptRepetitions(traces);
    const failures = collectProtocolPromptRepetitionFailures(traces);
    const gate = evaluateProtocolGate({
      timedOut: false,
      completed: true,
      runtimeStatus: "completed",
      clients: [
        clientRuntime("seat:3", {
          metrics: {
            ...emptyHeadlessMetrics(),
            acceptedAckCount: 9,
            runtimeCompletedCount: 1,
          },
        }),
      ],
      traces,
    });

    expect(repeated).toHaveLength(1);
    expect(repeated[0]).toMatchObject({
      count: 9,
      playerId: 3,
      requestType: "trick_tile_target",
      activeModuleId: "mod:seq:action:1:p2:53:fortuneresolve",
    });
    expect(failures[0]).toContain("repeated active prompt signature exceeded 8");
    expect(gate.ok).toBe(false);
    expect(gate.failures[0]).toContain("FortuneResolveModule");
  });

  it("fails backend timing gate when server timing logs are missing", () => {
    const result = evaluateProtocolBackendTimingGate({
      events: [],
      required: true,
    });

    expect(result.ok).toBe(false);
    expect(result.failures).toEqual([
      "backend timing gate did not find runtime_command_process_timing events",
      "backend timing gate did not find runtime_transition_phase_timing events",
    ]);
  });

  it("parses docker server timing logs and applies the 5s default backend timing gate", () => {
    const logText = [
      'server-1  | {"event":"runtime_command_process_timing","session_id":"sess_a","command_seq":7,"total_ms":4010,"redis_commit_count":2,"view_commit_count":1,"request_type":"movement"}',
      'server-1  | {"event":"runtime_transition_phase_timing","session_id":"sess_a","processed_command_seq":7,"total_ms":5001,"module_type":"DraftModule","request_type":"draft_card","request_id":"req-1","reason":"prompt_required"}',
      'server-1  | {"event":"decision_route_timing","session_id":"sess_a","request_id":"req-1","total_ms":33,"submit_decision_ms":18,"ack_publish_ms":7}',
      'server-1  | {"event":"runtime_decision_gateway_prompt_timing","session_id":"sess_a","request_id":"req-1","total_ms":21,"create_prompt_ms":8}',
      'server-1  | {"event":"runtime_command_process_timing","session_id":"sess_b","command_seq":1,"total_ms":1,"redis_commit_count":1,"view_commit_count":1}',
    ].join("\n");

    const events = parseProtocolBackendTimingEvents(logText, { sessionId: "sess_a" });
    const summary = summarizeProtocolBackendTiming(events);
    const result = evaluateProtocolBackendTimingGate({ events, required: true });

    expect(events).toHaveLength(4);
    expect(summary).toMatchObject({
      eventCount: 4,
      commandTimingCount: 1,
      transitionTimingCount: 1,
      decisionRouteTimingCount: 1,
      promptTimingCount: 1,
      maxCommandMs: 4010,
      maxTransitionMs: 5001,
      maxDecisionRouteMs: 33,
      maxPromptMs: 21,
      maxRedisCommitCount: 2,
      maxViewCommitCount: 1,
      slowCommandCount: 0,
      slowTransitionCount: 1,
    });
    expect(result.ok).toBe(false);
    expect(result.failures).toEqual(
      expect.arrayContaining([
        expect.stringContaining("backend command redis_commit_count exceeded 1"),
        expect.stringContaining("backend transition exceeded 5000ms"),
      ]),
    );
    expect(result.failures).not.toEqual(
      expect.arrayContaining([expect.stringContaining("backend command exceeded")]),
    );
  });

  it("summarizes protocol throughput from frontend traces and backend timing phases", () => {
    const summary = summarizeProtocolThroughput({
      durationMs: 60_000,
      traces: [
        { event: "decision_sent", ts_ms: 100, session_id: "sess", player_id: 1, request_id: "r1" },
        { event: "decision_ack", ts_ms: 160, session_id: "sess", player_id: 1, request_id: "r1", status: "accepted" },
        { event: "decision_sent", ts_ms: 300, session_id: "sess", player_id: 2, request_id: "r2" },
        { event: "view_commit_seen", ts_ms: 50, session_id: "sess", player_id: 1, commit_seq: 1 },
        { event: "view_commit_seen", ts_ms: 250, session_id: "sess", player_id: 1, commit_seq: 2 },
        { event: "view_commit_seen", ts_ms: 250, session_id: "sess", player_id: 2, commit_seq: 2 },
        { event: "view_commit_seen", ts_ms: 550, session_id: "sess", player_id: 1, commit_seq: 3 },
      ],
      backendEvents: [
        {
          event: "decision_route_timing",
          total_ms: 40,
          submit_decision_ms: 22,
          ack_publish_ms: 8,
        },
        {
          event: "runtime_command_process_timing",
          total_ms: 120,
          command_boundary_finalization_ms: 30,
          authoritative_commit_ms: 45,
        },
      ],
    });

    expect(summary).toMatchObject({
      decisionCount: 2,
      acceptedAckCount: 1,
      missingAckCount: 1,
      uniqueViewCommitCount: 3,
      decisionsPerMinute: 2,
      ackLatencyMs: { count: 1, p50: 60, p95: 60, max: 60 },
      commitGapMs: { count: 2, p50: 200, p95: 300, max: 300 },
      backend: {
        decisionRoute: {
          count: 1,
          phases: {
            submit_decision_ms: { count: 1, p50: 22, p95: 22, max: 22 },
          },
        },
        command: {
          count: 1,
          phases: {
            authoritative_commit_ms: { count: 1, p50: 45, p95: 45, max: 45 },
          },
        },
      },
    });
  });

  it("keeps timeout hard by default but can continue while observable progress is flowing", () => {
    expect(resolveProtocolTimeoutPolicy({ profile: "live", timeoutMs: 600_000 })).toEqual({
      timeoutMs: 600_000,
      hardTimeoutMs: 600_000,
      continueWhileProgressing: false,
    });

    expect(
      resolveProtocolTimeoutPolicy({
        profile: "live",
        timeoutMs: 600_000,
        continueWhileProgressing: true,
      }),
    ).toEqual({
      timeoutMs: 600_000,
      hardTimeoutMs: 1_200_000,
      continueWhileProgressing: true,
    });

    expect(
      resolveProtocolTimeoutPolicy({
        profile: "live",
        timeoutMs: 600_000,
        hardTimeoutMs: 900_000,
        continueWhileProgressing: true,
      }).hardTimeoutMs,
    ).toBe(900_000);
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
