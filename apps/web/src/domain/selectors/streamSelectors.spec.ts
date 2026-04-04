import { describe, expect, it } from "vitest";
import type { InboundMessage } from "../../core/contracts/stream";
import {
  selectCoreActionFeed,
  selectCriticalAlerts,
  selectLastMove,
  selectLatestManifest,
  selectLatestSnapshot,
  selectSituation,
  selectTheaterFeed,
  selectTimeline,
} from "./streamSelectors";

const snapshotEvent: InboundMessage = {
  type: "event",
  seq: 9,
  session_id: "s1",
  payload: {
    event_type: "turn_end_snapshot",
    round_index: 2,
    turn_index: 5,
    acting_player_id: 3,
    snapshot: {
      players: [
        {
          player_id: 1,
          display_name: "Player 1",
          character: "Scholar",
          alive: true,
          position: 5,
          cash: 12,
          shards: 4,
          hidden_trick_count: 1,
          owned_tile_count: 2,
        },
      ],
      board: {
        marker_owner_player_id: 2,
        f_value: 3,
        tiles: [
          {
            tile_index: 5,
            tile_kind: "T3",
            zone_color: "red",
            purchase_cost: 4,
            rent_cost: 4,
            owner_player_id: 1,
            pawn_player_ids: [1, 3],
          },
        ],
      },
    },
  },
};

describe("streamSelectors", () => {
  it("extracts latest snapshot from event payload", () => {
    const snapshot = selectLatestSnapshot([snapshotEvent]);
    expect(snapshot).not.toBeNull();
    expect(snapshot?.round).toBe(2);
    expect(snapshot?.turn).toBe(5);
    expect(snapshot?.markerOwnerPlayerId).toBe(2);
    expect(snapshot?.players[0].character).toBe("Scholar");
    expect(snapshot?.tiles[0].tileKind).toBe("T3");
  });

  it("builds timeline labels from recent messages", () => {
    const timeline = selectTimeline([
      snapshotEvent,
      {
        type: "decision_ack",
        seq: 10,
        session_id: "s1",
        payload: { status: "accepted" },
      },
    ]);
    expect(timeline[0].seq).toBe(10);
    expect(timeline[0].label).toBe("선택 응답");
  });

  it("extracts situation and keeps weather persistence", () => {
    const situation = selectSituation([
      {
        type: "event",
        seq: 7,
        session_id: "s1",
        payload: {
          event_type: "weather_reveal",
          weather_name: "긴급 피난",
        },
      },
      snapshotEvent,
    ]);
    expect(situation.round).toBe("2");
    expect(situation.turn).toBe("5");
    expect(situation.actor).toBe("P3");
    expect(situation.weather).toBe("긴급 피난");
    expect(situation.weatherEffect).not.toBe("-");
  });

  it("ignores runtime stalled warnings in situation headline", () => {
    const situation = selectSituation([
      {
        type: "event",
        seq: 100,
        session_id: "s1",
        payload: { event_type: "dice_roll", total_move: 6 },
      },
      {
        type: "error",
        seq: 101,
        session_id: "s1",
        payload: { code: "RUNTIME_STALLED_WARN", message: "stalled" },
      },
    ]);
    expect(situation.eventType).toBe("이동값 결정");
  });

  it("keeps prompt and decision events out of situation headline", () => {
    const situation = selectSituation([
      {
        type: "event",
        seq: 110,
        session_id: "s1",
        payload: { event_type: "turn_start", round_index: 2, turn_index: 3, acting_player_id: 2 },
      },
      {
        type: "prompt",
        seq: 111,
        session_id: "s1",
        payload: { request_id: "req_2", request_type: "purchase_tile", player_id: 2 },
      },
      {
        type: "event",
        seq: 112,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          request_id: "req_2",
          player_id: 2,
          resolution: "accepted",
          choice_id: "yes",
        },
      },
    ]);
    expect(situation.eventType).toBe("턴 시작");
    expect(situation.actor).toBe("P2");
    expect(situation.round).toBe("2");
    expect(situation.turn).toBe("3");
  });

  it("extracts recent move summary from player_move event", () => {
    const move = selectLastMove([
      snapshotEvent,
      {
        type: "event",
        seq: 12,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          acting_player_id: 2,
          from_tile_index: 5,
          to_tile_index: 8,
        },
      },
    ]);
    expect(move).not.toBeNull();
    expect(move?.playerId).toBe(2);
    expect(move?.fromTileIndex).toBe(5);
    expect(move?.toTileIndex).toBe(8);
  });

  it("formats less-common event details for timeline", () => {
    const timeline = selectTimeline(
      [
        {
          type: "event",
          seq: 30,
          session_id: "s1",
          payload: {
            event_type: "dice_roll",
            cards_used: [1, 4],
            total_move: 5,
          },
        },
        {
          type: "event",
          seq: 31,
          session_id: "s1",
          payload: {
            event_type: "marker_transferred",
            from_player_id: 2,
            to_player_id: 1,
          },
        },
        {
          type: "heartbeat",
          seq: 32,
          session_id: "s1",
          payload: {
            interval_ms: 5000,
            backpressure: {
              subscriber_count: 1,
              drop_count: 7,
              queue_size: 256,
            },
          },
        },
      ],
      3
    );
    expect(timeline[0].detail).toContain("유실 7");
    expect(timeline[1].detail).toContain("[징표] P2 -> P1");
    expect(timeline[2].detail).toContain("카드 1+4");
  });

  it("extracts latest manifest from stream events", () => {
    const manifest = selectLatestManifest([
      {
        type: "event",
        seq: 40,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          parameter_manifest: {
            manifest_version: 2,
            manifest_hash: "hash_123",
            version: "v2",
            source_fingerprints: { ruleset: "abc" },
            board: {
              topology: "line",
              tiles: [{ tile_index: 0, tile_kind: "F1", zone_color: "", purchase_cost: null, rent_cost: null }],
            },
            seats: {
              allowed: [1, 2, 3],
            },
            labels: {
              tile_kind_labels: {
                S: "Fortune",
                F1: "End - 1",
              },
            },
            dice: {
              values: [1, 2, 3],
              max_cards_per_turn: 2,
              use_one_card_plus_one_die: true,
            },
          },
        },
      },
    ]);
    expect(manifest).not.toBeNull();
    expect(manifest?.manifestHash).toBe("hash_123");
    expect(manifest?.manifestVersion).toBe(2);
    expect(manifest?.version).toBe("v2");
    expect(manifest?.sourceFingerprints).toEqual({ ruleset: "abc" });
    expect(manifest?.boardTopology).toBe("line");
    expect(manifest?.boardTiles.length).toBe(1);
    expect(manifest?.seatAllowed).toEqual([1, 2, 3]);
    expect(manifest?.dice).toEqual({
      values: [1, 2, 3],
      maxCardsPerTurn: 2,
      useOneCardPlusOneDie: true,
    });
  });

  it("keeps unknown event codes visible as timeline labels", () => {
    const timeline = selectTimeline([
      {
        type: "event",
        seq: 70,
        session_id: "s1",
        payload: {
          event_type: "custom_new_event",
          summary: "new event summary",
        },
      },
    ]);
    expect(timeline[0].label).toBe("custom_new_event");
    expect(timeline[0].detail).toBe("new event summary");
  });

  it("builds theater feed with event and non-event continuity", () => {
    const theater = selectTheaterFeed([
      {
        type: "event",
        seq: 80,
        session_id: "s1",
        payload: { event_type: "player_move", acting_player_id: 2, from_tile_index: 0, to_tile_index: 3 },
      },
      {
        type: "prompt",
        seq: 81,
        session_id: "s1",
        payload: { request_type: "purchase_tile", player_id: 2 },
      },
      {
        type: "decision_ack",
        seq: 82,
        session_id: "s1",
        payload: { request_id: "r1", status: "accepted", player_id: 2 },
      },
      {
        type: "event",
        seq: 83,
        session_id: "s1",
        payload: { event_type: "bankruptcy", player_id: 4 },
      },
    ]);
    expect(theater).toHaveLength(4);
    expect(theater[0].eventCode).toBe("bankruptcy");
    expect(theater[0].tone).toBe("critical");
    expect(theater[0].lane).toBe("core");
    expect(theater[1].eventCode).toBe("decision_ack");
    expect(theater[1].lane).toBe("prompt");
    expect(theater[3].lane).toBe("core");
    expect(theater[3].actor).toBe("P2");
  });

  it("extracts critical alerts from bankruptcy/game_end/timeout/runtime failures", () => {
    const alerts = selectCriticalAlerts([
      {
        type: "event",
        seq: 90,
        session_id: "s1",
        payload: { event_type: "round_start", round_index: 1 },
      },
      {
        type: "event",
        seq: 91,
        session_id: "s1",
        payload: { event_type: "decision_timeout_fallback", player_id: 2, summary: "timeout fallback" },
      },
      {
        type: "error",
        seq: 92,
        session_id: "s1",
        payload: { code: "RUNTIME_STALLED_WARN", message: "watchdog warning" },
      },
      {
        type: "event",
        seq: 93,
        session_id: "s1",
        payload: { event_type: "bankruptcy", player_id: 3 },
      },
      {
        type: "event",
        seq: 94,
        session_id: "s1",
        payload: { event_type: "game_end", summary: "finished" },
      },
    ]);
    expect(alerts.map((a) => a.seq)).toEqual([94, 93, 91]);
    expect(alerts[0].severity).toBe("critical");
    expect(alerts[2].severity).toBe("warning");
  });

  it("builds core action feed and marks local actor entries", () => {
    const feed = selectCoreActionFeed(
      [
        {
          type: "event",
          seq: 510,
          session_id: "s1",
          payload: {
            event_type: "player_move",
            acting_player_id: 1,
            from_tile_index: 0,
            to_tile_index: 5,
          },
        },
        {
          type: "event",
          seq: 511,
          session_id: "s1",
          payload: {
            event_type: "tile_purchased",
            acting_player_id: 2,
            player_id: 2,
            tile_index: 5,
            cost: 4,
          },
        },
      ],
      1,
      8
    );
    expect(feed).toHaveLength(2);
    expect(feed[0].seq).toBe(511);
    expect(feed[0].isLocalActor).toBe(false);
    expect(feed[1].seq).toBe(510);
    expect(feed[1].isLocalActor).toBe(true);
  });
});
