import { describe, expect, it } from "vitest";
import type { InboundMessage } from "../../core/contracts/stream";
import { selectLastMove, selectLatestSnapshot, selectSituation, selectTimeline } from "./streamSelectors";

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
          character: "교리 연구관",
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
            zone_color: "빨간색",
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
    expect(snapshot?.players[0].character).toBe("교리 연구관");
    expect(snapshot?.tiles[0].tileKind).toBe("T3");
  });

  it("builds localized timeline labels from recent messages", () => {
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

  it("extracts basic situation from latest message", () => {
    const situation = selectSituation([snapshotEvent]);
    expect(situation.round).toBe("2");
    expect(situation.turn).toBe("5");
    expect(situation.actor).toBe("3");
    expect(situation.eventType).toBe("턴 종료 스냅샷");
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
    expect(timeline[0].detail).toContain("drop 7");
    expect(timeline[1].detail).toContain("[징표]");
    expect(timeline[2].detail).toContain("주사위 카드 1, 4 사용");
  });
});
