import { describe, expect, it } from "vitest";
import type { InboundMessage } from "../../core/contracts/stream";
import { selectLatestSnapshot, selectSituation, selectTimeline } from "./streamSelectors";

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
    expect(timeline[0].label).toBe("decision_ack");
  });

  it("extracts basic situation from latest message", () => {
    const situation = selectSituation([snapshotEvent]);
    expect(situation.round).toBe("2");
    expect(situation.turn).toBe("5");
    expect(situation.actor).toBe("3");
    expect(situation.eventType).toBe("turn_end_snapshot");
  });
});

