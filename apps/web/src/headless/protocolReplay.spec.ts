import { describe, expect, it } from "vitest";
import type { HeadlessTraceEvent } from "./HeadlessGameClient";
import { protocolTraceEventsToReplayRows, serializeProtocolReplayRows } from "./protocolReplay";

describe("protocolReplay", () => {
  it("converts compact full-stack decision trace events into replay rows", () => {
    const events: HeadlessTraceEvent[] = [
      {
        event: "view_commit_seen",
        session_id: "sess_protocol",
        player_id: 1,
        commit_seq: 7,
        payload: {
          runtime_status: "waiting_input",
          round_index: 1,
          turn_index: 2,
          active_prompt_request_id: "req_1",
        },
      },
      {
        event: "decision_sent",
        session_id: "sess_protocol",
        player_id: 2,
        commit_seq: 7,
        request_id: "req_1",
        choice_id: "buy",
        payload: {
          request_type: "purchase_tile",
          legal_choice_ids: ["buy", "pass"],
          round_index: 1,
          turn_index: 2,
        },
      },
      {
        event: "view_commit_seen",
        session_id: "sess_protocol",
        player_id: 1,
        commit_seq: 99,
        payload: {
          runtime_status: "completed",
        },
      },
    ];

    const rows = protocolTraceEventsToReplayRows(events, {
      seed: 20260508,
      policyMode: "baseline",
    });

    expect(rows).toEqual([
      expect.objectContaining({
        game_id: "sess_protocol",
        step: 0,
        seed: 20260508,
        policy_mode: "baseline",
        player_id: 2,
        primary_player_id: 2,
        primary_player_id_source: "legacy",
        legacy_player_id: 2,
        public_player_id: null,
        seat_id: null,
        viewer_id: null,
        decision_key: "purchase_tile",
        chosen_action_id: "buy",
        action_space_source: "full_stack_protocol_trace",
        done: true,
        outcome: expect.objectContaining({ runtime_status: "completed" }),
      }),
    ]);
    expect(rows[0].legal_actions).toEqual([
      { action_id: "buy", legal: true, label: "buy" },
      { action_id: "pass", legal: true, label: "pass" },
    ]);
    expect(rows[0].observation).toEqual({
      commit_seq: 7,
      request_id: "req_1",
      round_index: 1,
      turn_index: 2,
      player_id: 2,
      primary_player_id: 2,
      primary_player_id_source: "legacy",
      legacy_player_id: 2,
      public_player_id: null,
      seat_id: null,
      viewer_id: null,
      cash: null,
      score: null,
      total_score: null,
      shards: null,
      owned_tile_count: null,
      position: null,
      alive: null,
      character: null,
    });
  });

  it("computes reward and final outcome from authoritative compact player summaries", () => {
    const events: HeadlessTraceEvent[] = [
      {
        event: "view_commit_seen",
        session_id: "sess_protocol_reward",
        player_id: 1,
        commit_seq: 7,
        payload: {
          runtime_status: "waiting_input",
          player_summaries: [
            {
              player_id: 1,
              legacy_player_id: 1,
              public_player_id: "player_public_1",
              seat_id: "seat_public_1",
              viewer_id: "viewer_public_1",
              cash: 20,
              score: 2,
              total_score: 2,
              shards: 1,
              owned_tile_count: 1,
              alive: true,
            },
            { player_id: 2, cash: 18, score: 3, total_score: 3, shards: 1, owned_tile_count: 2, alive: true },
          ],
        },
      },
      {
        event: "decision_sent",
        session_id: "sess_protocol_reward",
        player_id: 1,
        commit_seq: 7,
        request_id: "req_lap",
        choice_id: "cash",
        payload: {
          request_type: "lap_reward",
          legacy_player_id: 1,
          public_player_id: "player_public_1",
          seat_id: "seat_public_1",
          viewer_id: "viewer_public_1",
          legal_choice_ids: ["cash", "shard"],
        },
      },
      {
        event: "view_commit_seen",
        session_id: "sess_protocol_reward",
        player_id: 1,
        commit_seq: 8,
        payload: {
          runtime_status: "completed",
          player_summaries: [
            {
              player_id: 1,
              legacy_player_id: 1,
              public_player_id: "player_public_1",
              seat_id: "seat_public_1",
              viewer_id: "viewer_public_1",
              cash: 25,
              score: 3,
              total_score: 3,
              shards: 2,
              owned_tile_count: 1,
              alive: true,
            },
            { player_id: 2, cash: 18, score: 3, total_score: 3, shards: 1, owned_tile_count: 2, alive: true },
          ],
        },
      },
    ];

    const rows = protocolTraceEventsToReplayRows(events);

    expect(rows[0].reward.components).toMatchObject({
      cash_delta: 5,
      score_delta: 1,
      shard_delta: 1,
      tile_delta: 0,
    });
    expect(rows[0].reward.total).toBeGreaterThan(0);
    expect(rows[0].observation).toEqual(
      expect.objectContaining({
        player_id: 1,
        legacy_player_id: 1,
        public_player_id: "player_public_1",
        seat_id: "seat_public_1",
        viewer_id: "viewer_public_1",
        cash: 20,
        score: 2,
        total_score: 2,
        shards: 1,
        owned_tile_count: 1,
        alive: true,
      }),
    );
    expect(rows[0].outcome).toEqual({
      runtime_status: "completed",
      final_rank: 1,
      final_player_summary: expect.objectContaining({
        player_id: 1,
        public_player_id: "player_public_1",
        seat_id: "seat_public_1",
        viewer_id: "viewer_public_1",
        cash: 25,
        score: 3,
        shards: 2,
      }),
    });
  });

  it("exports primary player identity while preserving numeric legacy aliases", () => {
    const events: HeadlessTraceEvent[] = [
      {
        event: "view_commit_seen",
        session_id: "sess_protocol_identity",
        player_id: 1,
        commit_seq: 7,
        payload: {
          runtime_status: "waiting_input",
          player_summaries: [
            {
              player_id: 2,
              legacy_player_id: 2,
              primary_player_id: "player_public_2",
              primary_player_id_source: "public",
              public_player_id: "player_public_2",
              seat_id: "seat_public_2",
              viewer_id: "viewer_public_2",
              cash: 18,
              total_score: 3,
              alive: true,
            },
          ],
        },
      },
      {
        event: "decision_sent",
        session_id: "sess_protocol_identity",
        player_id: 2,
        commit_seq: 7,
        request_id: "req_identity",
        choice_id: "pass",
        payload: {
          request_type: "identity_check",
          primary_player_id: "player_public_2",
          primary_player_id_source: "public",
          legacy_player_id: 2,
          public_player_id: "player_public_2",
          seat_id: "seat_public_2",
          viewer_id: "viewer_public_2",
          legal_choice_ids: ["pass"],
        },
      },
    ];

    const [row] = protocolTraceEventsToReplayRows(events);

    expect(row).toEqual(
      expect.objectContaining({
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        player_id: 2,
        legacy_player_id: 2,
        public_player_id: "player_public_2",
      }),
    );
    expect(row.observation).toEqual(
      expect.objectContaining({
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        player_id: 2,
        legacy_player_id: 2,
        public_player_id: "player_public_2",
      }),
    );
    expect(row.outcome.final_player_summary).toEqual(
      expect.objectContaining({
        primary_player_id: "player_public_2",
        primary_player_id_source: "public",
        player_id: 2,
        legacy_player_id: 2,
      }),
    );
  });

  it("does not serialize raw view_state or stream messages into replay rows", () => {
    const rows = protocolTraceEventsToReplayRows([
      {
        event: "decision_sent",
        session_id: "sess_protocol",
        player_id: 1,
        commit_seq: 3,
        request_id: "req_secret",
        choice_id: "pass",
        payload: {
          request_type: "hand_choice",
          legal_choice_ids: ["pass"],
          view_state: { hidden: true },
          messages: [{ type: "prompt" }],
        },
      },
    ]);
    const serialized = serializeProtocolReplayRows(rows);

    expect(serialized).not.toContain("view_state");
    expect(serialized).not.toContain("messages");
    expect(serialized).not.toContain("hidden");
  });
});
