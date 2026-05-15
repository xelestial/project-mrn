import { describe, expect, it, vi } from "vitest";
import type { InboundMessage } from "../core/contracts/stream";
import {
  baselineDecisionPolicy,
  conservativeDecisionPolicy,
  createResourceFocusedDecisionPolicy,
  HeadlessGameClient,
} from "./HeadlessGameClient";

function viewCommitMessage(args: {
  commitSeq: number;
  requestId: string;
  playerId: number;
  requestType?: string;
  choiceId?: string;
  choicePayload?: Record<string, unknown>;
  publicPlayerId?: string;
  primaryPlayerId?: string | number;
  primaryPlayerIdSource?: "public" | "protocol" | "legacy";
  legacyPlayerId?: number;
  seatId?: string;
  viewerId?: string;
  publicPromptInstanceId?: string;
  publicContext?: Record<string, unknown>;
  viewState?: Record<string, unknown>;
  choices?: Array<{
    choice_id: string;
    title?: string;
    value?: Record<string, unknown> | null;
    secondary?: boolean;
  }>;
}): InboundMessage {
  return {
    type: "view_commit",
    seq: args.commitSeq,
    session_id: "sess_headless",
    server_time_ms: 1000 + args.commitSeq,
    payload: {
      schema_version: 1,
      commit_seq: args.commitSeq,
      source_event_seq: args.commitSeq,
      round_index: 1,
      turn_index: args.playerId,
      turn_label: `R1-T${args.playerId}`,
      viewer: {
        role: "seat",
        player_id: args.publicPlayerId ?? args.playerId,
        ...(args.legacyPlayerId !== undefined ? { legacy_player_id: args.legacyPlayerId } : {}),
        ...(args.publicPlayerId ? { public_player_id: args.publicPlayerId } : {}),
        ...(args.seatId ? { seat_id: args.seatId } : {}),
        ...(args.viewerId ? { viewer_id: args.viewerId } : {}),
        seat: args.playerId,
      },
      runtime: {
        status: "waiting_input",
        round_index: 1,
        turn_index: args.playerId,
        turn_label: `R1-T${args.playerId}`,
        active_frame_id: `frame:${args.playerId}`,
        active_module_id: `module:${args.playerId}`,
        active_module_type: "PromptModule",
        module_path: [`frame:${args.playerId}`, `module:${args.playerId}`],
      },
      view_state: {
        prompt: {
          active: {
            request_id: args.requestId,
            request_type: args.requestType ?? "purchase_tile",
            player_id: args.publicPlayerId ?? args.playerId,
            ...(args.primaryPlayerId !== undefined ? { primary_player_id: args.primaryPlayerId } : {}),
            ...(args.primaryPlayerIdSource ? { primary_player_id_source: args.primaryPlayerIdSource } : {}),
            ...(args.legacyPlayerId !== undefined ? { legacy_player_id: args.legacyPlayerId } : {}),
            ...(args.publicPlayerId ? { public_player_id: args.publicPlayerId } : {}),
            ...(args.seatId ? { seat_id: args.seatId } : {}),
            ...(args.viewerId ? { viewer_id: args.viewerId } : {}),
            timeout_ms: 30000,
            runner_kind: "module",
            prompt_instance_id: 17,
            ...(args.publicPromptInstanceId ? { public_prompt_instance_id: args.publicPromptInstanceId } : {}),
            resume_token: `resume:${args.requestId}`,
            frame_id: `frame:${args.playerId}`,
            module_id: `module:${args.playerId}`,
            module_type: "PromptModule",
            module_cursor: "await_choice",
            public_context: args.publicContext ?? {},
            choices: args.choices ?? [
              {
                choice_id: args.choiceId ?? "buy",
                title: "구매",
                value: args.choicePayload ?? { buy: true },
              },
              {
                choice_id: "pass",
                title: "넘김",
                secondary: true,
              },
            ],
          },
        },
        ...(args.viewState ?? {}),
      },
    },
  };
}

function viewCommitWithoutPromptMessage(args: {
  commitSeq: number;
  playerId: number;
  roundIndex?: number;
  turnIndex?: number;
  viewState?: Record<string, unknown>;
}): InboundMessage {
  return {
    type: "view_commit",
    seq: args.commitSeq,
    session_id: "sess_headless",
    server_time_ms: 1000 + args.commitSeq,
    payload: {
      schema_version: 1,
      commit_seq: args.commitSeq,
      source_event_seq: args.commitSeq,
      round_index: args.roundIndex ?? 1,
      turn_index: args.turnIndex ?? args.playerId,
      turn_label: `R${args.roundIndex ?? 1}-T${args.turnIndex ?? args.playerId}`,
      viewer: {
        role: "seat",
        player_id: args.playerId,
        seat: args.playerId,
      },
      runtime: {
        status: "running",
        round_index: args.roundIndex ?? 1,
        turn_index: args.turnIndex ?? args.playerId,
        turn_label: `R${args.roundIndex ?? 1}-T${args.turnIndex ?? args.playerId}`,
        active_frame_id: `frame:${args.playerId}`,
        active_module_id: `module:${args.playerId}`,
        active_module_type: "PromptModule",
        module_path: [`frame:${args.playerId}`, `module:${args.playerId}`],
      },
      view_state: args.viewState ?? {},
    },
  };
}

function ackMessage(args: {
  seq: number;
  requestId: string;
  status: "accepted" | "rejected" | "stale";
  reason?: string;
}): InboundMessage {
  return {
    type: "decision_ack",
    seq: args.seq,
    session_id: "sess_headless",
    server_time_ms: 2000 + args.seq,
    payload: {
      request_id: args.requestId,
      status: args.status,
      reason: args.reason ?? "",
    },
  };
}

describe("HeadlessGameClient", () => {
  it("uses the shared frontend decision protocol for an active prompt", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_decision",
      token: "seat-2",
      playerId: 2,
      policy: baselineDecisionPolicy,
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 10,
        requestId: "req_purchase_10",
        playerId: 2,
        publicPromptInstanceId: "prompt_public_purchase_17",
        choicePayload: { tile_index: 5, buy: true },
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toEqual({
      type: "decision",
      request_id: "req_purchase_10",
      player_id: 2,
      player_id_alias_role: "legacy_compatibility_alias",
      primary_player_id: 2,
      primary_player_id_source: "legacy",
      choice_id: "buy",
      choice_payload: { tile_index: 5, buy: true },
      prompt_instance_id: 17,
      public_prompt_instance_id: "prompt_public_purchase_17",
      resume_token: "resume:req_purchase_10",
      frame_id: "frame:2",
      module_id: "module:2",
      module_type: "PromptModule",
      module_cursor: "await_choice",
      view_commit_seq_seen: 10,
      client_seq: 10,
    });
    expect(client.trace.find((event) => event.event === "decision_sent")?.payload).toMatchObject({
      prompt_instance_id: 17,
      public_prompt_instance_id: "prompt_public_purchase_17",
    });
    expect(client.trace.find((event) => event.event === "decision_sent")).toMatchObject({
      player_id: 2,
      primary_player_id: 2,
      primary_player_id_source: "legacy",
      protocol_player_id: 2,
      legacy_player_id: 2,
      public_player_id: null,
      seat_id: null,
      viewer_id: null,
    });
    expect(client.metrics.outboundDecisionCount).toBe(1);
    expect(client.metrics.illegalActionCount).toBe(0);
  });

  it("sends active prompt public player identity while preserving the legacy numeric alias", async () => {
    let observedPolicyIdentity: unknown = null;
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_public_player",
      token: "seat-2",
      playerId: 2,
      policy: (context) => {
        observedPolicyIdentity = (context as unknown as Record<string, unknown>)["identity"];
        return baselineDecisionPolicy(context);
      },
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 12,
        requestId: "req_public_player_12",
        playerId: 2,
        legacyPlayerId: 2,
        publicPlayerId: "player_public_2",
        seatId: "seat_public_2",
        viewerId: "viewer_public_2",
        choicePayload: { tile_index: 7, buy: true },
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_public_player_12",
      primary_player_id: "player_public_2",
      primary_player_id_source: "public",
      legacy_player_id: 2,
      public_player_id: "player_public_2",
      seat_id: "seat_public_2",
      viewer_id: "viewer_public_2",
      choice_id: "buy",
      choice_payload: { tile_index: 7, buy: true },
    });
    expect(outbound[0]).not.toHaveProperty("player_id");
    expect(client.trace.find((event) => event.event === "view_commit_seen")?.payload).toMatchObject({
      active_prompt_identity: {
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        protocol_player_id: "player_public_2",
        legacy_player_id: 2,
        public_player_id: "player_public_2",
        seat_id: "seat_public_2",
        viewer_id: "viewer_public_2",
      },
      active_prompt_primary_player_id: "player_public_2",
      active_prompt_primary_player_id_source: "public",
      active_prompt_player_id: 2,
    });
    expect(client.trace.find((event) => event.event === "decision_sent")?.payload).toMatchObject({
      identity: {
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        protocol_player_id: "player_public_2",
        legacy_player_id: 2,
        public_player_id: "player_public_2",
        seat_id: "seat_public_2",
        viewer_id: "viewer_public_2",
      },
      primary_player_id: "player_public_2",
      primary_player_id_source: "public",
      protocol_player_id: "player_public_2",
      legacy_player_id: 2,
      public_player_id: "player_public_2",
      seat_id: "seat_public_2",
      viewer_id: "viewer_public_2",
    });
    expect(client.trace.find((event) => event.event === "decision_sent")).toMatchObject({
      player_id: 2,
      player_id_alias_role: "legacy_debug_alias",
      primary_player_id: "player_public_2",
      primary_player_id_source: "public",
      protocol_player_id: "player_public_2",
      legacy_player_id: 2,
      public_player_id: "player_public_2",
      seat_id: "seat_public_2",
      viewer_id: "viewer_public_2",
    });
    expect(observedPolicyIdentity).toEqual({
      primaryPlayerId: "player_public_2",
      primaryPlayerIdSource: "public",
      protocolPlayerId: "player_public_2",
      legacyPlayerId: 2,
      publicPlayerId: "player_public_2",
      seatId: "seat_public_2",
      viewerId: "viewer_public_2",
    });
  });

  it("routes an active public player prompt without a legacy player bridge", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_public_only_player",
      token: "seat-2",
      playerId: 2,
      policy: baselineDecisionPolicy,
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 13,
        requestId: "req_public_only_player_13",
        playerId: 2,
        publicPlayerId: "player_public_2",
        seatId: "seat_public_2",
        viewerId: "viewer_public_2",
        choicePayload: { tile_index: 8, buy: true },
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_public_only_player_13",
      primary_player_id: "player_public_2",
      primary_player_id_source: "public",
      legacy_player_id: 2,
      public_player_id: "player_public_2",
      seat_id: "seat_public_2",
      viewer_id: "viewer_public_2",
      choice_id: "buy",
      choice_payload: { tile_index: 8, buy: true },
    });
    expect(outbound[0]).not.toHaveProperty("player_id");
  });

  it("prefers explicit prompt primary identity over a numeric active prompt alias", async () => {
    let observedPolicyIdentity: unknown = null;
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_explicit_primary",
      token: "seat-2",
      playerId: 2,
      policy: (context) => {
        observedPolicyIdentity = context.identity;
        return baselineDecisionPolicy(context);
      },
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 15,
        requestId: "req_explicit_primary_15",
        playerId: 2,
        legacyPlayerId: 2,
        primaryPlayerId: "player_public_2",
        primaryPlayerIdSource: "public",
        choicePayload: { tile_index: 10, buy: true },
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_explicit_primary_15",
      primary_player_id: "player_public_2",
      primary_player_id_source: "public",
      legacy_player_id: 2,
      choice_id: "buy",
      choice_payload: { tile_index: 10, buy: true },
    });
    expect(outbound[0]).not.toHaveProperty("player_id");
    expect(outbound[0]).not.toHaveProperty("player_id_alias_role");
    expect(client.trace.find((event) => event.event === "view_commit_seen")?.payload).toMatchObject({
      active_prompt_identity: {
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        protocol_player_id: 2,
        legacy_player_id: 2,
        public_player_id: null,
      },
      active_prompt_primary_player_id: "player_public_2",
      active_prompt_primary_player_id_source: "public",
      active_prompt_player_id: 2,
      active_prompt_protocol_player_id: 2,
      active_prompt_legacy_player_id: 2,
      active_prompt_public_player_id: null,
    });
    expect(client.trace.find((event) => event.event === "decision_sent")).toMatchObject({
      player_id: 2,
      primary_player_id: "player_public_2",
      primary_player_id_source: "public",
      protocol_player_id: 2,
      legacy_player_id: 2,
    });
    expect(observedPolicyIdentity).toMatchObject({
      primaryPlayerId: "player_public_2",
      primaryPlayerIdSource: "public",
      protocolPlayerId: 2,
      legacyPlayerId: 2,
    });
  });

  it("repairs malformed numeric public primary identity in compact traces", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_malformed_trace_primary",
      token: "seat-2",
      playerId: 2,
      policy: baselineDecisionPolicy,
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 16,
        requestId: "req_malformed_trace_primary_16",
        playerId: 2,
        primaryPlayerId: 2,
        primaryPlayerIdSource: "public",
        legacyPlayerId: 2,
        publicPlayerId: "player_public_2",
        seatId: "seat_public_2",
        viewerId: "viewer_public_2",
        choicePayload: { tile_index: 11, buy: true },
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(client.trace.find((event) => event.event === "view_commit_seen")?.payload).toMatchObject({
      active_prompt_identity: {
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        protocol_player_id: "player_public_2",
        legacy_player_id: 2,
        public_player_id: "player_public_2",
        seat_id: "seat_public_2",
        viewer_id: "viewer_public_2",
      },
      active_prompt_primary_player_id: "player_public_2",
      active_prompt_primary_player_id_source: "public",
      active_prompt_player_id: 2,
      active_prompt_protocol_player_id: "player_public_2",
      active_prompt_legacy_player_id: 2,
      active_prompt_public_player_id: "player_public_2",
    });
  });

  it("keeps routing legacy prompts when the viewer also exposes public identity", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_mixed_viewer_legacy_prompt",
      token: "seat-2",
      playerId: 2,
      policy: baselineDecisionPolicy,
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 14,
        requestId: "req_legacy_prompt_public_viewer_14",
        playerId: 2,
        legacyPlayerId: 2,
        publicPlayerId: "player_public_2",
        seatId: "seat_public_2",
        viewerId: "viewer_public_2",
        viewState: {
          prompt: {
            active: {
              request_id: "req_legacy_prompt_public_viewer_14",
              request_type: "purchase_tile",
              player_id: 2,
              legacy_player_id: 2,
              timeout_ms: 30000,
              runner_kind: "module",
              prompt_instance_id: 18,
              resume_token: "resume:req_legacy_prompt_public_viewer_14",
              frame_id: "frame:2",
              module_id: "module:2",
              module_type: "PromptModule",
              module_cursor: "await_choice",
              public_context: {},
              choices: [
                {
                  choice_id: "buy",
                  title: "구매",
                  value: { tile_index: 9, buy: true },
                },
                {
                  choice_id: "pass",
                  title: "넘김",
                  secondary: true,
                },
              ],
            },
          },
        },
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_legacy_prompt_public_viewer_14",
      player_id: 2,
      choice_id: "buy",
      choice_payload: { tile_index: 9, buy: true },
    });
  });

  it("routes protocol-string prompts when viewer player_id is a numeric compatibility alias", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_numeric_viewer_public_prompt",
      token: "seat-2",
      playerId: 2,
      policy: baselineDecisionPolicy,
    });
    const message = viewCommitMessage({
      commitSeq: 17,
      requestId: "req_numeric_viewer_public_prompt_17",
      playerId: 2,
      legacyPlayerId: 2,
      publicPlayerId: "player_public_2",
      seatId: "seat_public_2",
      viewerId: "viewer_public_2",
      choicePayload: { tile_index: 12, buy: true },
    });
    const payload = message.payload as {
      viewer: Record<string, unknown>;
      view_state: { prompt: { active: Record<string, unknown> } };
    };
    payload.viewer.player_id = 2;
    const active = payload.view_state.prompt.active;
    active.player_id = "player_public_2";
    delete active.public_player_id;

    const outbound = await client.ingestMessage(message);

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_numeric_viewer_public_prompt_17",
      primary_player_id: "player_public_2",
      primary_player_id_source: "protocol",
      legacy_player_id: 2,
      choice_id: "buy",
      choice_payload: { tile_index: 12, buy: true },
    });
    expect(outbound[0]).not.toHaveProperty("player_id");
  });

  it("declines repeatable burden exchange by default to keep protocol playtests bounded", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_burden_default",
      token: "seat-2",
      playerId: 2,
      policy: baselineDecisionPolicy,
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 11,
        requestId: "req_burden_11",
        playerId: 2,
        requestType: "burden_exchange",
        choices: [
          {
            choice_id: "yes",
            title: "Pay 1 to remove",
            value: { burden_cost: 1, card_name: "Burden" },
          },
          {
            choice_id: "no",
            title: "Keep burden",
            value: { burden_cost: 1, card_name: "Burden" },
            secondary: true,
          },
        ],
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_burden_11",
      player_id: 2,
      choice_id: "no",
      choice_payload: { burden_cost: 1, card_name: "Burden" },
    });
  });

  it("tracks forced reconnect recovery only after a view_commit is observed", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_reconnect",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });
    (client as unknown as { socket: { close: () => void } | null }).socket = { close: vi.fn() };

    client.forceReconnect("after_first_prompt");

    expect(client.metrics.forcedReconnectCount).toBe(1);
    expect(client.metrics.reconnectCount).toBe(0);
    expect(client.metrics.reconnectRecoveryCount).toBe(0);
    expect(client.metrics.reconnectRecoveryPendingCount).toBe(1);

    await client.ingestMessage(
      viewCommitWithoutPromptMessage({
        commitSeq: 4,
        playerId: 1,
      }),
    );

    expect(client.metrics.reconnectRecoveryCount).toBe(1);
    expect(client.metrics.reconnectRecoveryPendingCount).toBe(0);
    expect(client.trace.some((item) => item.event === "forced_reconnect_recovered")).toBe(true);
  });

  it("supports deterministic resource profile policies for headless seats", async () => {
    const cash = createResourceFocusedDecisionPolicy("cash");
    const shard = createResourceFocusedDecisionPolicy("shard");
    const score = createResourceFocusedDecisionPolicy("score");
    const context = {
      sessionId: "sess_profile",
      playerId: 1,
      latestCommit: null,
      lastCommitSeq: 0,
      messages: [],
      legalChoices: [],
      prompt: {
        requestId: "req_profile",
        requestType: "lap_reward",
        playerId: 1,
        timeoutMs: 30000,
        publicContext: {},
        continuation: {
          promptInstanceId: null,
          promptFingerprint: null,
          promptFingerprintVersion: null,
          resumeToken: null,
          frameId: null,
          moduleId: null,
          moduleType: null,
          moduleCursor: null,
          batchId: null,
        },
        effectContext: null,
        behavior: {
          normalizedRequestType: "lap_reward",
          singleSurface: false,
          autoContinue: false,
          chainKey: null,
          chainItemCount: null,
          currentItemDeckIndex: null,
        },
        surface: {
          kind: "lap_reward",
          blocksPublicEvents: false,
          movement: null,
          lapReward: null,
          burdenExchangeBatch: null,
          markTarget: null,
          characterPick: null,
          handChoice: null,
          purchaseTile: null,
          trickTileTarget: null,
        },
        choices: [
          { choiceId: "cash", title: "돈", description: "현금 +20냥", value: { cash_units: 20 }, secondary: false },
          { choiceId: "shards", title: "조각", description: "조각 +2", value: { shard_units: 2 }, secondary: false },
          { choiceId: "score", title: "승점", description: "승점 +3", value: { score: 3 }, secondary: false },
        ],
      },
    };

    await expect(Promise.resolve(cash(context as never))).resolves.toMatchObject({ choiceId: "cash" });
    await expect(Promise.resolve(shard(context as never))).resolves.toMatchObject({ choiceId: "shards" });
    await expect(Promise.resolve(score(context as never))).resolves.toMatchObject({ choiceId: "score" });
  });

  it("uses conservative policy to choose pass-like choices", async () => {
    const decision = await conservativeDecisionPolicy({
      sessionId: "sess_profile",
      playerId: 1,
      latestCommit: null,
      lastCommitSeq: 0,
      messages: [],
      legalChoices: [],
      prompt: {
        requestId: "req_pass",
        requestType: "purchase_tile",
        playerId: 1,
        timeoutMs: 30000,
        publicContext: {},
        continuation: {
          promptInstanceId: null,
          promptFingerprint: null,
          promptFingerprintVersion: null,
          resumeToken: null,
          frameId: null,
          moduleId: null,
          moduleType: null,
          moduleCursor: null,
          batchId: null,
        },
        effectContext: null,
        behavior: {
          normalizedRequestType: "purchase_tile",
          singleSurface: false,
          autoContinue: false,
          chainKey: null,
          chainItemCount: null,
          currentItemDeckIndex: null,
        },
        surface: {
          kind: "purchase_tile",
          blocksPublicEvents: false,
          movement: null,
          lapReward: null,
          burdenExchangeBatch: null,
          markTarget: null,
          characterPick: null,
          handChoice: null,
          purchaseTile: null,
          trickTileTarget: null,
        },
        choices: [
          { choiceId: "buy", title: "구매", description: "", value: { buy: true }, secondary: false },
          { choiceId: "pass", title: "넘김", description: "", value: null, secondary: true },
        ],
      },
    } as never);

    expect(decision.choiceId).toBe("pass");
  });

  it("fails the gate when a policy selects a non-legal choice", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_illegal",
      token: "seat-2",
      playerId: 2,
      policy: () => ({ choiceId: "not_legal" }),
    });

    await expect(
      client.ingestMessage(
        viewCommitMessage({
          commitSeq: 11,
          requestId: "req_purchase_11",
          playerId: 2,
        }),
      ),
    ).rejects.toThrow("Illegal headless decision");

    expect(client.metrics.illegalActionCount).toBe(1);
    expect(client.metrics.outboundDecisionCount).toBe(0);
  });

  it("suppresses duplicate decisions while policy resolution is still in flight", async () => {
    let resolveDecision!: (decision: { choiceId: string }) => void;
    const policy = vi.fn(
      () =>
        new Promise<{ choiceId: string }>((resolve) => {
          resolveDecision = resolve;
        }),
    );
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_inflight",
      token: "seat-2",
      playerId: 2,
      policy,
    });
    const prompt = viewCommitMessage({
      commitSeq: 10,
      requestId: "req_inflight",
      playerId: 2,
    });

    const first = client.ingestMessage(prompt);
    const second = await client.ingestMessage(prompt);

    expect(second).toEqual([]);
    expect(client.metrics.duplicateDecisionSuppressionCount).toBe(1);
    expect(policy).toHaveBeenCalledTimes(1);

    resolveDecision({ choiceId: "buy" });
    const firstOutbound = await first;

    expect(firstOutbound).toHaveLength(1);
    expect(firstOutbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_inflight",
      choice_id: "buy",
    });
    expect(client.metrics.outboundDecisionCount).toBe(1);
  });

  it("records a semantic runtime regression even when commit_seq increases", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_regression",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    await client.ingestMessage(
      viewCommitWithoutPromptMessage({
        commitSeq: 20,
        playerId: 1,
        roundIndex: 3,
        turnIndex: 8,
      }),
    );
    await client.ingestMessage(
      viewCommitWithoutPromptMessage({
        commitSeq: 21,
        playerId: 1,
        roundIndex: 2,
        turnIndex: 9,
      }),
    );

    expect(client.metrics.nonMonotonicCommitCount).toBe(0);
    expect(client.metrics.semanticCommitRegressionCount).toBe(1);
    expect(client.trace.some((event) => event.event === "runtime_position_regressed")).toBe(true);
  });

  it("records compact public player summaries for authoritative replay rewards", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_summaries",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    await client.ingestMessage(
      viewCommitWithoutPromptMessage({
        commitSeq: 22,
        playerId: 1,
        viewState: {
          players: {
            items: [
              {
                player_id: 1,
                seat: 1,
                cash: 20,
                score: 2,
                total_score: 2,
                shards: 3,
                owned_tile_count: 1,
                position: 5,
                alive: true,
                current_character_face: "박수",
                hidden_trick_count: 2,
              },
            ],
          },
        },
      }),
    );

    expect(client.trace[0].payload?.["player_summaries"]).toEqual([
      {
        player_id: 1,
        legacy_player_id: 1,
        public_player_id: null,
        seat_id: null,
        viewer_id: null,
        seat: 1,
        character: "박수",
        cash: 20,
        score: 2,
        total_score: 2,
        shards: 3,
        owned_tile_count: 1,
        position: 5,
        alive: true,
      },
    ]);
    expect(JSON.stringify(client.trace[0])).not.toContain("hidden_trick_count");
  });

  it("batches active flip choices like the rendered frontend prompt", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_active_flip",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 12,
        requestId: "req_active_flip_12",
        playerId: 1,
        requestType: "active_flip",
        choices: [
          { choice_id: "none", title: "뒤집기 종료", value: null },
          { choice_id: "2", title: "A -> B", value: { card_index: 2 } },
          { choice_id: "4", title: "C -> D", value: { card_index: 4 } },
        ],
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_active_flip_12",
      player_id: 1,
      choice_id: "none",
      choice_payload: {
        selected_choice_ids: ["2", "4"],
        finish_after_selection: true,
      },
    });
  });

  it("finishes an active flip phase after the policy already selected a card", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_active_flip_guard",
      token: "seat-1",
      playerId: 1,
      policy: () => ({ choiceId: "2" }),
    });
    const choices = [
      { choice_id: "none", title: "뒤집기 종료", value: null },
      { choice_id: "2", title: "A -> B", value: { card_index: 2 } },
      { choice_id: "4", title: "C -> D", value: { card_index: 4 } },
    ];

    const firstOutbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 14,
        requestId: "req_active_flip_14",
        playerId: 1,
        requestType: "active_flip",
        choices,
      }),
    );

    expect(firstOutbound).toHaveLength(1);
    expect(firstOutbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_active_flip_14",
      choice_id: "2",
    });
    await client.ingestMessage(ackMessage({ seq: 15, requestId: "req_active_flip_14", status: "accepted" }));

    const secondOutbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 16,
        requestId: "req_active_flip_16",
        playerId: 1,
        requestType: "active_flip",
        publicContext: { already_flipped_count: 1, already_flipped_cards: [2] },
        choices,
      }),
    );

    expect(secondOutbound).toHaveLength(1);
    expect(secondOutbound[0]).toMatchObject({
      type: "decision",
      request_id: "req_active_flip_16",
      choice_id: "none",
    });
    expect(secondOutbound[0].type === "decision" ? secondOutbound[0].choice_payload : null).toBeUndefined();
    expect(client.trace.some((event) => event.event === "active_flip_guard_applied")).toBe(true);
  });

  it("sends simultaneous batch continuation from an authoritative view_commit prompt", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_batch_commit",
      token: "seat-2",
      playerId: 2,
      policy: baselineDecisionPolicy,
    });

    const outbound = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 13,
        requestId: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p1",
        playerId: 2,
        requestType: "burden_exchange",
        choices: [
          {
            choice_id: "no",
            title: "교환 안 함",
            value: { selected_card_indices: [] },
            secondary: true,
          },
        ],
        viewState: {
          prompt: {
            active: {
              request_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p1",
              request_type: "burden_exchange",
              player_id: 2,
              timeout_ms: 30000,
              runner_kind: "module",
              prompt_instance_id: 0,
              resume_token: "resume:p2",
              frame_id: "simul:resupply:1:95",
              module_id: "mod:simul:resupply:1:95",
              module_type: "ResupplyModule",
              module_cursor: "await_resupply_batch:4",
              batch_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1",
              missing_player_ids: [1, 2, 3, 4],
              resume_tokens_by_player_id: {
                "1": "resume:p1",
                "2": "resume:p2",
                "3": "resume:p3",
                "4": "resume:p4",
              },
              choices: [
                {
                  choice_id: "no",
                  title: "교환 안 함",
                  value: { selected_card_indices: [] },
                  secondary: true,
                },
              ],
            },
          },
        },
      }),
    );

    expect(outbound).toHaveLength(1);
    expect(outbound[0]).toMatchObject({
      type: "decision",
      request_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p1",
      player_id: 2,
      choice_id: "no",
      prompt_instance_id: 0,
      batch_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1",
      missing_player_ids: [1, 2, 3, 4],
      resume_tokens_by_player_id: {
        "1": "resume:p1",
        "2": "resume:p2",
        "3": "resume:p3",
        "4": "resume:p4",
      },
      view_commit_seq_seen: 13,
    });
  });

  it("treats a raw prompt as a wake-up hint until an active view_commit prompt exists", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_raw_prompt",
      token: "seat-3",
      playerId: 3,
      policy: baselineDecisionPolicy,
    });

    const rawPrompt: InboundMessage = {
      type: "prompt",
      seq: 77,
      session_id: "sess_headless_raw_prompt",
      payload: {
        request_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p2",
        request_type: "burden_exchange",
        player_id: 3,
        runner_kind: "module",
        prompt_instance_id: 0,
        resume_token: "resume:p3",
        frame_id: "simul:resupply:1:95",
        module_id: "mod:simul:resupply:1:95",
        module_type: "ResupplyModule",
        module_cursor: "await_resupply_batch:4",
        batch_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1",
        missing_player_ids: [1, 2, 3, 4],
        resume_tokens_by_player_id: {
          "1": "resume:p1",
          "2": "resume:p2",
          "3": "resume:p3",
          "4": "resume:p4",
        },
        legal_choices: [
          {
            choice_id: "no",
            title: "교환 안 함",
            value: { selected_card_indices: [] },
            secondary: true,
          },
        ],
      },
    };

    expect(
      await client.ingestMessage(
        viewCommitWithoutPromptMessage({
          commitSeq: 77,
          playerId: 3,
        }),
      ),
    ).toEqual([]);

    const outbound = await client.ingestMessage(rawPrompt);

    expect(outbound).toEqual([]);
    expect(client.trace.some((event) => event.event === "prompt_deferred_until_view_commit")).toBe(true);

    const committedDecision = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 78,
        requestId: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p2",
        playerId: 3,
        requestType: "burden_exchange",
        choices: [
          {
            choice_id: "no",
            title: "교환 안 함",
            value: { selected_card_indices: [] },
            secondary: true,
          },
        ],
        viewState: {
          prompt: {
            active: {
              request_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p2",
              request_type: "burden_exchange",
              player_id: 3,
              timeout_ms: 30000,
              runner_kind: "module",
              prompt_instance_id: 0,
              resume_token: "resume:p3",
              frame_id: "simul:resupply:1:95",
              module_id: "mod:simul:resupply:1:95",
              module_type: "ResupplyModule",
              module_cursor: "await_resupply_batch:4",
              batch_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1",
              missing_player_ids: [1, 2, 3, 4],
              resume_tokens_by_player_id: {
                "1": "resume:p1",
                "2": "resume:p2",
                "3": "resume:p3",
                "4": "resume:p4",
              },
              choices: [
                {
                  choice_id: "no",
                  title: "교환 안 함",
                  value: { selected_card_indices: [] },
                  secondary: true,
                },
              ],
            },
          },
        },
      }),
    );

    expect(committedDecision).toHaveLength(1);
    expect(committedDecision[0]).toMatchObject({
      type: "decision",
      request_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p2",
      player_id: 3,
      choice_id: "no",
      prompt_instance_id: 0,
      batch_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1",
      missing_player_ids: [1, 2, 3, 4],
      resume_tokens_by_player_id: {
        "1": "resume:p1",
        "2": "resume:p2",
        "3": "resume:p3",
        "4": "resume:p4",
      },
      view_commit_seq_seen: 78,
    });

    expect(
      await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 79,
          requestId: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p2",
          playerId: 3,
          requestType: "burden_exchange",
          choices: [
            {
              choice_id: "no",
              title: "교환 안 함",
              value: { selected_card_indices: [] },
              secondary: true,
            },
          ],
          viewState: {
            prompt: {
              active: {
                request_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1:p2",
                request_type: "burden_exchange",
                player_id: 3,
                timeout_ms: 30000,
                runner_kind: "module",
                prompt_instance_id: 0,
                resume_token: "resume:p3",
                frame_id: "simul:resupply:1:95",
                module_id: "mod:simul:resupply:1:95",
                module_type: "ResupplyModule",
                module_cursor: "await_resupply_batch:4",
                batch_id: "batch:simul:resupply:1:95:mod:simul:resupply:1:95:resupply:1",
                missing_player_ids: [1, 2, 3, 4],
                resume_tokens_by_player_id: {
                  "1": "resume:p1",
                  "2": "resume:p2",
                  "3": "resume:p3",
                  "4": "resume:p4",
                },
                choices: [
                  {
                    choice_id: "no",
                    title: "교환 안 함",
                    value: { selected_card_indices: [] },
                    secondary: true,
                  },
                ],
              },
            },
          },
        }),
      ),
    ).toEqual([]);
  });

  it("decides from active view_commit prompt data instead of raw prompt choices", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_raw_prompt_hint",
      token: "seat-3",
      playerId: 3,
      policy: baselineDecisionPolicy,
    });

    expect(
      await client.ingestMessage({
        type: "prompt",
        seq: 78,
        session_id: "sess_headless_raw_prompt_hint",
        payload: {
          request_id: "req_hint_only",
          request_type: "purchase_tile",
          player_id: 3,
          runner_kind: "module",
          prompt_instance_id: 7,
          resume_token: "resume:raw",
          frame_id: "frame:3",
          module_id: "module:3",
          module_type: "PromptModule",
          module_cursor: "await_choice",
          legal_choices: [{ choice_id: "raw_only", title: "raw", value: { raw: true } }],
        },
      }),
    ).toEqual([]);

    const decisions = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 79,
        requestId: "req_hint_only",
        playerId: 3,
        choices: [
          {
            choice_id: "commit_only",
            title: "commit",
            value: { commit: true },
          },
        ],
      }),
    );

    expect(decisions).toHaveLength(1);
    expect(decisions[0]).toMatchObject({
      request_id: "req_hint_only",
      choice_id: "commit_only",
      choice_payload: { commit: true },
      view_commit_seq_seen: 79,
    });
  });

  it("does not answer a raw prompt if no authoritative view_commit arrives", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_raw_prompt_fallback",
      token: "seat-3",
      playerId: 3,
      policy: baselineDecisionPolicy,
      rawPromptFallbackDelayMs: 1,
    });
    const sendSpy = vi.spyOn(client, "send").mockReturnValue(true);

    expect(
      await client.ingestMessage(
        viewCommitWithoutPromptMessage({
          commitSeq: 77,
          playerId: 3,
        }),
      ),
    ).toEqual([]);

    await client.ingestMessage({
      type: "prompt",
      seq: 78,
      session_id: "sess_headless_raw_prompt_fallback",
      payload: {
        request_id: "req_raw_fallback",
        request_type: "purchase_tile",
        player_id: 3,
        runner_kind: "module",
        prompt_instance_id: 7,
        resume_token: "resume:raw",
        frame_id: "frame:3",
        module_id: "module:3",
        module_type: "PromptModule",
        module_cursor: "await_choice",
        legal_choices: [{ choice_id: "pass", title: "넘김", secondary: true }],
      },
    });

    await new Promise((resolve) => setTimeout(resolve, 10));

    const decisions = sendSpy.mock.calls
      .map(([message]) => message)
      .filter((message) => message && message.type === "decision");
    expect(decisions).toEqual([]);
    expect(client.metrics.rawPromptFallbackWithoutActiveCommitCount).toBe(0);
    expect(client.trace.some((event) => event.event === "prompt_fallback_skipped_missing_view_commit")).toBe(true);
    sendSpy.mockRestore();
  });

  it("does not answer a raw prompt while a different authoritative prompt is active", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_raw_prompt_mismatch",
      token: "seat-3",
      playerId: 3,
      policy: baselineDecisionPolicy,
    });

    const first = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 77,
        requestId: "req_authoritative",
        playerId: 3,
      }),
    );
    expect(first).toHaveLength(1);

    const rawPrompt: InboundMessage = {
      type: "prompt",
      seq: 78,
      session_id: "sess_headless_raw_prompt_mismatch",
      payload: {
        request_id: "req_other",
        request_type: "purchase_tile",
        player_id: 3,
        runner_kind: "module",
        prompt_instance_id: 1,
        resume_token: "resume:other",
        frame_id: "frame:3",
        module_id: "module:3",
        module_type: "PromptModule",
        module_cursor: "await_choice",
        legal_choices: [{ choice_id: "pass", title: "넘김", secondary: true }],
      },
    };

    expect(await client.ingestMessage(rawPrompt)).toEqual([]);
    expect(client.trace.some((event) => event.event === "prompt_deferred_due_active_mismatch")).toBe(true);
  });

  it("retries a stale decision once after a newer view_commit keeps the same prompt active", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_retry",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    const first = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 4,
        requestId: "req_retry",
        playerId: 1,
      }),
    );
    expect(first).toHaveLength(1);
    expect(first[0]).toMatchObject({ request_id: "req_retry", view_commit_seq_seen: 4 });

    expect(
      await client.ingestMessage(
        ackMessage({
          seq: 5,
          requestId: "req_retry",
          status: "stale",
          reason: "stale_prompt",
        }),
      ),
    ).toEqual([]);

    const retry = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 5,
        requestId: "req_retry",
        playerId: 1,
      }),
    );
    expect(retry).toHaveLength(1);
    expect(retry[0]).toMatchObject({ request_id: "req_retry", view_commit_seq_seen: 5 });
    expect(client.metrics.staleDecisionRetryCount).toBe(1);

    expect(
      await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 6,
          requestId: "req_retry",
          playerId: 1,
        }),
      ),
    ).toEqual([]);
  });

  it("retries request_not_pending once when the latest view_commit still exposes the same prompt", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_request_not_pending_retry",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    const first = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 10,
        requestId: "req_request_not_pending",
        playerId: 1,
      }),
    );
    expect(first).toHaveLength(1);
    expect(first[0]).toMatchObject({ request_id: "req_request_not_pending", view_commit_seq_seen: 10 });

    expect(
      await client.ingestMessage(
        ackMessage({
          seq: 11,
          requestId: "req_request_not_pending",
          status: "stale",
          reason: "request_not_pending",
        }),
      ),
    ).toEqual([]);

    const retry = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 11,
        requestId: "req_request_not_pending",
        playerId: 1,
      }),
    );
    expect(retry).toHaveLength(1);
    expect(retry[0]).toMatchObject({ request_id: "req_request_not_pending", view_commit_seq_seen: 11 });
    expect(client.metrics.staleDecisionRetryCount).toBe(1);

    expect(
      await client.ingestMessage(
        ackMessage({
          seq: 12,
          requestId: "req_request_not_pending",
          status: "stale",
          reason: "request_not_pending",
        }),
      ),
    ).toEqual([]);
    expect(
      await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 12,
          requestId: "req_request_not_pending",
          playerId: 1,
        }),
      ),
    ).toEqual([]);
    expect(client.metrics.staleDecisionRetryCount).toBe(1);
  });

  it("does not retry a stale decision when the server already resolved the prompt", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_already_resolved",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    const first = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 4,
        requestId: "req_already_resolved",
        playerId: 1,
      }),
    );
    expect(first).toHaveLength(1);

    expect(
      await client.ingestMessage(
        ackMessage({
          seq: 5,
          requestId: "req_already_resolved",
          status: "stale",
          reason: "already_resolved",
        }),
      ),
    ).toEqual([]);

    expect(
      await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 5,
          requestId: "req_already_resolved",
          playerId: 1,
        }),
      ),
    ).toEqual([]);
    expect(client.metrics.staleDecisionRetryCount).toBe(0);
  });

  it("releases the decision ledger when transport send fails", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_send_fail",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    const first = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 7,
        requestId: "req_send_fail",
        playerId: 1,
      }),
    );
    expect(first).toHaveLength(1);
    expect(first[0]).toMatchObject({ request_id: "req_send_fail", view_commit_seq_seen: 7 });

    client.markDecisionSendFailed(first[0]);
    expect(client.metrics.decisionSendFailureCount).toBe(1);

    const retry = await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 8,
        requestId: "req_send_fail",
        playerId: 1,
      }),
    );
    expect(retry).toHaveLength(1);
    expect(retry[0]).toMatchObject({ request_id: "req_send_fail", view_commit_seq_seen: 8 });
  });

  it("does not time-retry an unacked decision when the same active prompt remains visible", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(10_000);
    try {
      const client = new HeadlessGameClient({
        sessionId: "sess_headless_unacked_retry",
        token: "seat-1",
        playerId: 1,
        policy: baselineDecisionPolicy,
      });

      const first = await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 30,
          requestId: "req_unacked_retry",
          playerId: 1,
        }),
      );
      expect(first).toHaveLength(1);

      nowSpy.mockReturnValue(14_999);
      expect(
        await client.ingestMessage(
          viewCommitMessage({
            commitSeq: 31,
            requestId: "req_unacked_retry",
            playerId: 1,
          }),
        ),
      ).toEqual([]);
      expect(client.metrics.duplicateDecisionSuppressionCount).toBe(1);

      nowSpy.mockReturnValue(60_000);
      const retry = await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 32,
          requestId: "req_unacked_retry",
          playerId: 1,
        }),
      );

      expect(retry).toEqual([]);
      expect(client.metrics.unackedDecisionRetryCount).toBe(0);
      expect(client.metrics.outboundDecisionCount).toBe(1);
      expect(client.metrics.duplicateDecisionSuppressionCount).toBe(2);
      expect(client.trace.some((event) => event.event === "decision_unacked_retry_sent")).toBe(false);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("resends an unacked decision immediately after reconnect exposes the same active prompt", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(30_000);
    try {
      const client = new HeadlessGameClient({
        sessionId: "sess_headless_reconnect_unacked_retry",
        token: "seat-1",
        playerId: 1,
        policy: baselineDecisionPolicy,
      });
      (client as unknown as { socket: { close: () => void } | null }).socket = { close: vi.fn() };

      const first = await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 50,
          requestId: "req_reconnect_unacked_retry",
          playerId: 1,
        }),
      );
      expect(first).toHaveLength(1);

      client.forceReconnect("after_first_decision");

      nowSpy.mockReturnValue(30_100);
      const retry = await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 51,
          requestId: "req_reconnect_unacked_retry",
          playerId: 1,
        }),
      );

      expect(retry).toHaveLength(1);
      expect(retry[0]).toMatchObject({
        request_id: "req_reconnect_unacked_retry",
        choice_id: "buy",
        view_commit_seq_seen: 51,
        client_seq: 51,
      });
      expect(client.metrics.unackedDecisionRetryCount).toBe(1);
      expect(client.metrics.duplicateDecisionSuppressionCount).toBe(0);
      expect(client.trace.some((event) => event.event === "pending_decision_reconnect_retry_armed")).toBe(true);
      expect(
        client.trace.some(
          (event) =>
            event.event === "decision_unacked_retry_sent" &&
            event.payload?.["retry_after_reconnect"] === true,
        ),
      ).toBe(true);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("does not resend after a decision ack resolves the request", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(20_000);
    try {
      const client = new HeadlessGameClient({
        sessionId: "sess_headless_unacked_ack",
        token: "seat-1",
        playerId: 1,
        policy: baselineDecisionPolicy,
      });

      const first = await client.ingestMessage(
        viewCommitMessage({
          commitSeq: 40,
          requestId: "req_unacked_ack",
          playerId: 1,
        }),
      );
      expect(first).toHaveLength(1);

      await client.ingestMessage(ackMessage({ seq: 41, requestId: "req_unacked_ack", status: "accepted" }));

      nowSpy.mockReturnValue(25_000);
      expect(
        await client.ingestMessage(
          viewCommitMessage({
            commitSeq: 42,
            requestId: "req_unacked_ack",
            playerId: 1,
          }),
        ),
      ).toEqual([]);
      expect(client.metrics.unackedDecisionRetryCount).toBe(0);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("records server timeout fallback events as protocol failures", async () => {
    const client = new HeadlessGameClient({
      sessionId: "sess_headless_timeout_fallback",
      token: "seat-1",
      playerId: 1,
      policy: baselineDecisionPolicy,
    });

    await client.ingestMessage(
      viewCommitMessage({
        commitSeq: 20,
        requestId: "req_timeout_fallback",
        playerId: 2,
        viewState: {
          scene: {
            core_action_feed: [
              {
                seq: 44,
                event_code: "decision_timeout_fallback",
                payload: {
                  request_id: "req_timeout_fallback",
                },
              },
            ],
          },
        },
      }),
    );

    expect(client.metrics.decisionTimeoutFallbackCount).toBe(1);
    expect(client.trace.some((event) => event.event === "decision_timeout_fallback_seen")).toBe(true);
  });
});
