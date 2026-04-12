import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { InboundMessage } from "../../core/contracts/stream";
import {
  selectActiveCharacterSlots,
  selectCoreActionFeed,
  selectCriticalAlerts,
  selectCurrentActorPlayerId,
  selectCurrentTurnRevealItems,
  selectDerivedPlayers,
  selectLastMove,
  selectLatestManifest,
  selectLiveSnapshot,
  selectLatestSnapshot,
  selectLivePlayers,
  selectMarkTargetCharacterSlots,
  selectMarkerOrderedPlayers,
  selectSituation,
  selectTheaterFeed,
  selectTimeline,
  selectTurnStage,
} from "./streamSelectors";

function loadSharedSceneFixture(): {
  messages: InboundMessage[];
  expected: {
    scene: {
      situation: {
        actor_player_id: number | null;
        round_index: number | null;
        turn_index: number | null;
        weather_name: string;
        weather_effect: string;
      };
      theater_feed: Array<{ seq: number; event_code: string; lane: string }>;
      core_action_feed: Array<{ seq: number; event_code: string }>;
      timeline: Array<{ seq: number; event_code: string }>;
      critical_alerts: Array<{ seq: number; event_code: string; severity: "warning" | "critical" }>;
    };
  };
} {
  const path = resolve(process.cwd(), "../../packages/runtime-contracts/ws/examples/selector.scene.turn_resolution.json");
  return JSON.parse(readFileSync(path, "utf-8"));
}

function loadSharedPlayerMarkTargetFixture(): {
  messages: InboundMessage[];
  expected: {
    players: {
      items: Array<{
        player_id: number;
        display_name: string;
        cash: number;
        shards: number;
        owned_tile_count: number;
        trick_count: number;
        hand_coins: number;
        placed_coins: number;
        total_score: number;
        priority_slot: number | null;
        current_character_face: string;
        is_marker_owner: boolean;
        is_current_actor: boolean;
      }>;
    };
    active_slots: {
      items: Array<{
        slot: number;
        player_id: number | null;
        label: string | null;
        character: string | null;
        inactive_character: string | null;
        is_current_actor: boolean;
      }>;
    };
    mark_target: {
      candidates: Array<{
        slot: number;
        player_id: number | null;
        label: string | null;
        character: string;
      }>;
    };
  };
} {
  const path = resolve(process.cwd(), "../../packages/runtime-contracts/ws/examples/selector.player.mark_target_visibility.json");
  return JSON.parse(readFileSync(path, "utf-8"));
}

function loadSharedBoardFixture(): {
  messages: InboundMessage[];
  expected: {
    board: {
      last_move: {
        player_id: number | null;
        from_tile_index: number | null;
        to_tile_index: number | null;
        path_tile_indices: number[];
      };
      tiles: Array<{
        tile_index: number;
        score_coin_count: number;
        owner_player_id: number | null;
        pawn_player_ids: number[];
      }>;
    };
  };
} {
  const path = resolve(process.cwd(), "../../packages/runtime-contracts/ws/examples/selector.board.live_tiles.json");
  return JSON.parse(readFileSync(path, "utf-8"));
}

function fixtureMessageCodeBySeq(messages: InboundMessage[], seq: number): string {
  const message = messages.find((item) => item.seq === seq);
  if (!message) {
    return "";
  }
  if (message.type === "event") {
    return typeof message.payload.event_type === "string" ? message.payload.event_type : "";
  }
  return message.type;
}

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
            score_coin_count: 2,
            owner_player_id: 1,
            pawn_player_ids: [1, 3],
          },
          {
            tile_index: 8,
            tile_kind: "T3",
            zone_color: "blue",
            purchase_cost: 5,
            rent_cost: 5,
            score_coin_count: 0,
            owner_player_id: null,
            pawn_player_ids: [],
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
    expect(snapshot?.markerDraftDirection).toBeNull();
    expect(snapshot?.players[0].character).toBe("Scholar");
    expect(snapshot?.tiles[0].tileKind).toBe("T3");
    expect(snapshot?.tiles[0].scoreCoinCount).toBe(2);
  });

  it("orders player cards from the marker owner using marker draft direction", () => {
    const clockwiseMessages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [1, 2, 3, 4].map((playerId) => ({
              player_id: playerId,
              display_name: `Player ${playerId}`,
              character: "-",
              alive: true,
              position: playerId - 1,
              cash: 10,
              shards: 4,
              hidden_trick_count: 0,
              owned_tile_count: 0,
            })),
            board: {
              marker_owner_player_id: 2,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "round_start",
          round_index: 2,
          turn_index: 1,
          marker_owner_player_id: 2,
          marker_draft_direction: "clockwise",
        },
      },
    ];

    const counterclockwiseMessages: InboundMessage[] = [
      ...clockwiseMessages.slice(0, 1),
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "marker_transferred",
          round_index: 2,
          turn_index: 1,
          to_player_id: 2,
          draft_direction: "counterclockwise",
        },
      },
    ];

    expect(selectMarkerOrderedPlayers(clockwiseMessages).map((player) => player.playerId)).toEqual([2, 3, 4, 1]);
    expect(selectMarkerOrderedPlayers(counterclockwiseMessages).map((player) => player.playerId)).toEqual([2, 1, 4, 3]);
  });

  it("prefers backend-projected marker order when view_state players are present", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [1, 2, 3, 4].map((playerId) => ({
              player_id: playerId,
              display_name: `Player ${playerId}`,
              character: "-",
              alive: true,
              position: playerId - 1,
              cash: 10,
              shards: 4,
              hidden_trick_count: 0,
              owned_tile_count: 0,
            })),
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
          view_state: {
            players: {
              ordered_player_ids: [3, 4, 1, 2],
              marker_owner_player_id: 3,
              marker_draft_direction: "clockwise",
            },
          },
        },
      },
    ];

    expect(selectMarkerOrderedPlayers(messages).map((player) => player.playerId)).toEqual([3, 4, 1, 2]);
  });

  it("prefers backend-projected active slots and mark target candidates when present", () => {
    const messages: InboundMessage[] = [
      {
        type: "prompt",
        seq: 1,
        session_id: "s1",
        payload: {
          request_id: "req_mark_backend",
          request_type: "mark_target",
          player_id: 1,
          view_state: {
            players: {
              ordered_player_ids: [1, 2, 3, 4],
              marker_owner_player_id: 1,
              marker_draft_direction: "clockwise",
              items: [
                {
                  player_id: 1,
                  display_name: "Player 1",
                  cash: 20,
                  shards: 4,
                  owned_tile_count: 0,
                  trick_count: 5,
                  hand_coins: 0,
                  placed_coins: 0,
                  total_score: 0,
                  priority_slot: 2,
                  current_character_face: "산적",
                  is_marker_owner: true,
                  is_current_actor: true,
                },
              ],
            },
            active_slots: {
              items: [
                { slot: 1, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 2, player_id: 1, label: "P1", character: "산적", inactive_character: "자객", is_current_actor: true },
                { slot: 3, player_id: null, label: null, character: "탈출 노비", inactive_character: "추노꾼", is_current_actor: false },
                { slot: 4, player_id: null, label: null, character: "아전", inactive_character: "파발꾼", is_current_actor: false },
                { slot: 5, player_id: 2, label: "P2", character: "교리 연구관", inactive_character: "교리 감독관", is_current_actor: false },
                { slot: 6, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 7, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 8, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
              ],
            },
            mark_target: {
              actor_slot: 2,
              candidates: [
                { slot: 3, player_id: null, label: null, character: "탈출 노비" },
                { slot: 4, player_id: null, label: null, character: "아전" },
                { slot: 5, player_id: 2, label: "P2", character: "교리 연구관" },
              ],
            },
          },
        },
      },
    ];

    expect(selectActiveCharacterSlots(messages, 1).slice(0, 5)).toMatchObject([
      { slot: 1, character: null },
      { slot: 2, character: "산적", playerId: 1, isCurrentActor: true, isLocalPlayer: true },
      { slot: 3, character: "탈출 노비" },
      { slot: 4, character: "아전" },
      { slot: 5, character: "교리 연구관", playerId: 2 },
    ]);
    expect(selectMarkTargetCharacterSlots(messages, "산적", 1)).toEqual([
      { slot: 3, playerId: null, label: null, character: "탈출 노비" },
      { slot: 4, playerId: null, label: null, character: "아전" },
      { slot: 5, playerId: 2, label: "P2", character: "교리 연구관" },
    ]);
  });

  it("prefers backend-projected reveal ordering and interrupt flags when present", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 10,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 2,
          acting_player_id: 2,
          character: "산적",
          view_state: {
            reveals: {
              round_index: 4,
              turn_index: 2,
              items: [
                {
                  seq: 11,
                  event_code: "weather_reveal",
                  event_order: 10,
                  tone: "effect",
                  focus_tile_index: null,
                  is_interrupt: true,
                },
                {
                  seq: 12,
                  event_code: "dice_roll",
                  event_order: 20,
                  tone: "move",
                  focus_tile_index: null,
                  is_interrupt: false,
                },
                {
                  seq: 13,
                  event_code: "player_move",
                  event_order: 30,
                  tone: "move",
                  focus_tile_index: 9,
                  is_interrupt: false,
                },
              ],
            },
          },
        },
      },
      {
        type: "event",
        seq: 11,
        session_id: "s1",
        payload: {
          event_type: "weather_reveal",
          round_index: 4,
          turn_index: 2,
          weather_name: "Cold Front",
          effect_text: "No lap cash.",
        },
      },
      {
        type: "event",
        seq: 12,
        session_id: "s1",
        payload: {
          event_type: "dice_roll",
          round_index: 4,
          turn_index: 2,
          acting_player_id: 2,
          total_move: 6,
        },
      },
      {
        type: "event",
        seq: 13,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          round_index: 4,
          turn_index: 2,
          acting_player_id: 2,
          from_tile_index: 3,
          to_tile_index: 9,
          path: [4, 5, 6, 7, 8, 9],
        },
      },
    ];

    const items = selectCurrentTurnRevealItems(messages, 6);

    expect(items.map((item) => item.eventCode)).toEqual(["weather_reveal", "dice_roll", "player_move"]);
    expect(items[0].isInterrupt).toBe(true);
    expect(items[2]).toMatchObject({
      detail: expect.stringContaining("10"),
      focusTileIndex: 9,
      tone: "move",
    });
  });

  it("prefers backend-projected board last move when present", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          snapshot: { players: [], board: { tiles: [] } },
          view_state: {
            board: {
              last_move: {
                player_id: 3,
                from_tile_index: 17,
                to_tile_index: 30,
                path_tile_indices: [18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
              },
            },
          },
        },
      },
    ];

    expect(selectLastMove(messages)).toEqual({
      playerId: 3,
      fromTileIndex: 17,
      toTileIndex: 30,
      pathTileIndices: [18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30],
    });
  });

  it("overlays current actor live deltas on top of the latest snapshot players", () => {
    const players = selectLivePlayers([
      snapshotEvent,
      {
        type: "event",
        seq: 210,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 2,
          turn_index: 6,
          acting_player_id: 1,
          character: "Builder",
        },
      },
      {
        type: "event",
        seq: 211,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          round_index: 2,
          turn_index: 6,
          player_id: 1,
          resolution: "accepted",
          choice_id: "huge_fire",
          public_context: {
            player_cash: 18,
            player_shards: 7,
            player_hand_coins: 2,
            player_placed_coins: 3,
            player_total_score: 5,
            player_owned_tile_count: 4,
          },
        },
      },
    ]);

    expect(players).toHaveLength(1);
    expect(players[0].character).toBe("Builder");
    expect(players[0].cash).toBe(18);
    expect(players[0].shards).toBe(7);
    expect(players[0].handCoins).toBe(2);
    expect(players[0].placedCoins).toBe(3);
    expect(players[0].totalScore).toBe(5);
    expect(players[0].ownedTileCount).toBe(4);
  });

  it("derives visible player faces and shared status from the live selector path", () => {
    const derivedPlayers = selectDerivedPlayers(
      [
        {
          ...snapshotEvent,
          payload: {
            ...snapshotEvent.payload,
            snapshot: {
              ...((snapshotEvent.payload.snapshot as Record<string, unknown>) ?? {}),
              current_round_order: [7, 1],
              active_by_card: { "7": "중매꾼" },
              players: [
                {
                  player_id: 1,
                  display_name: "Player 1",
                  character: "객주",
                  alive: true,
                  position: 5,
                  cash: 12,
                  shards: 4,
                  hidden_trick_count: 1,
                  owned_tile_count: 2,
                  public_tricks: ["건강 검진", "마당발"],
                },
              ],
            },
          },
        },
        {
          type: "event",
          seq: 210,
          session_id: "s1",
          payload: {
            event_type: "turn_start",
            round_index: 2,
            turn_index: 6,
            acting_player_id: 1,
            character: "중매꾼",
          },
        },
      ],
      1
    );

    expect(selectCurrentActorPlayerId([snapshotEvent])).toBe(3);
    expect(derivedPlayers).toHaveLength(1);
    expect(derivedPlayers[0].prioritySlot).toBe(7);
    expect(derivedPlayers[0].currentCharacterFace).toBe("중매꾼");
    expect(derivedPlayers[0].isCurrentActor).toBe(true);
    expect(derivedPlayers[0].isLocalPlayer).toBe(true);
    expect(derivedPlayers[0].trickCount).toBe(3);
  });

  it("builds active character slots from the same derived player path", () => {
    const slots = selectActiveCharacterSlots(
      [
        {
          type: "event",
          seq: 9,
          session_id: "s1",
          payload: {
            event_type: "turn_end_snapshot",
            round_index: 2,
            turn_index: 5,
            acting_player_id: 3,
            snapshot: {
              current_round_order: [7, 8],
              active_by_card: { "7": "중매꾼", "8": "사기꾼" },
              players: [
                {
                  player_id: 1,
                  display_name: "Player 1",
                  character: "객주",
                  alive: true,
                  position: 5,
                  cash: 12,
                  shards: 4,
                  hidden_trick_count: 1,
                  owned_tile_count: 2,
                },
                {
                  player_id: 2,
                  display_name: "Player 2",
                  character: "건설업자",
                  alive: true,
                  position: 8,
                  cash: 10,
                  shards: 1,
                  hidden_trick_count: 0,
                  owned_tile_count: 1,
                },
              ],
              board: {
                marker_owner_player_id: 2,
                f_value: 3,
                tiles: [],
              },
            },
          },
        },
        {
          type: "event",
          seq: 10,
          session_id: "s1",
          payload: {
            event_type: "turn_start",
            round_index: 2,
            turn_index: 6,
            acting_player_id: 2,
            character: "사기꾼",
          },
        },
      ],
      1
    );

    expect(slots[6]).toMatchObject({
      slot: 7,
      playerId: null,
      character: "중매꾼",
      inactiveCharacter: "객주",
      isCurrentActor: false,
      isLocalPlayer: false,
    });
    expect(slots[7]).toMatchObject({
      slot: 8,
      playerId: 2,
      character: "사기꾼",
      inactiveCharacter: "건설업자",
      isCurrentActor: true,
      isLocalPlayer: false,
    });
  });

  it("keeps earlier randomized faces visible across turn starts until the round changes", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "round_order",
          round_index: 1,
          turn_index: 1,
          order: [7, 8],
          active_by_card: {
            "1": "탐관오리",
            "7": "중매꾼",
            "8": "사기꾼",
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "객주",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
              {
                player_id: 2,
                display_name: "Player 2",
                character: "건설업자",
                alive: true,
                position: 1,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "중매꾼",
        },
      },
    ];

    const derivedPlayers = selectDerivedPlayers(messages, 1);
    const slots = selectActiveCharacterSlots(messages, 1);

    expect(derivedPlayers[0]).toMatchObject({
      playerId: 1,
      currentCharacterFace: "중매꾼",
    });
    expect(derivedPlayers[1]).toMatchObject({
      playerId: 2,
      currentCharacterFace: "-",
    });
    expect(slots[0]).toMatchObject({
      slot: 1,
      character: "탐관오리",
      inactiveCharacter: "어사",
      playerId: null,
    });
    expect(slots[6]).toMatchObject({
      slot: 7,
      playerId: 1,
      character: "중매꾼",
      inactiveCharacter: "객주",
      isCurrentActor: true,
      isLocalPlayer: true,
    });
    expect(slots[7]).toMatchObject({
      slot: 8,
      playerId: null,
      character: "사기꾼",
      inactiveCharacter: "건설업자",
    });
  });

  it("keeps round faces at turn boundaries and rehydrates mark targets from the prompt", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "round_order",
          round_index: 1,
          turn_index: 1,
          order: [2, 5, 6],
          active_by_card: {
            "1": "탐관오리",
            "2": "산적",
            "5": "교리 감독관",
            "6": "박수",
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "자객",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
              {
                player_id: 2,
                display_name: "Player 2",
                character: "교리 연구관",
                alive: true,
                position: 1,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
              {
                player_id: 3,
                display_name: "Player 3",
                character: "만신",
                alive: true,
                position: 2,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "산적",
        },
      },
      {
        type: "prompt",
        seq: 4,
        session_id: "s1",
        payload: {
          request_id: "req_mark_1",
          request_type: "mark_target",
          player_id: 1,
          legal_choices: [
            {
              choice_id: "교리 감독관",
              title: "교리 감독관",
              value: { target_character: "교리 감독관", target_card_no: 5 },
            },
            {
              choice_id: "박수",
              title: "박수",
              value: { target_character: "박수", target_card_no: 6 },
            },
            {
              choice_id: "none",
              title: "지목 안 함",
            },
          ],
          public_context: {
            actor_name: "산적",
            target_pairs: [
              { target_card_no: 5, target_character: "교리 감독관" },
              { target_card_no: 6, target_character: "박수" },
            ],
          },
        },
      },
    ];

    const derivedPlayers = selectDerivedPlayers(messages, 1);
    expect(derivedPlayers[1]).toMatchObject({ playerId: 2, currentCharacterFace: "-" });
    expect(derivedPlayers[2]).toMatchObject({ playerId: 3, currentCharacterFace: "-" });

    const slots = selectActiveCharacterSlots(messages, 1);
    expect(slots[1]).toMatchObject({ slot: 2, character: "산적" });
    expect(slots[4]).toMatchObject({ slot: 5, character: "교리 감독관" });
    expect(slots[5]).toMatchObject({ slot: 6, character: "박수" });
    expect(selectMarkTargetCharacterSlots(messages, "산적", 1)).toEqual([
      { slot: 5, playerId: null, label: null, character: "교리 감독관" },
      { slot: 6, playerId: null, label: null, character: "박수" },
    ]);
  });

  it("prefers fresher raw prompt active faces over a sparse backend active slot projection", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "박수",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "만신",
        },
      },
      {
        type: "prompt",
        seq: 3,
        session_id: "s1",
        payload: {
          request_id: "req_hidden_live",
          request_type: "hidden_trick_card",
          player_id: 1,
          public_context: {
            actor_name: "만신",
            active_by_card: {
              1: "탐관오리",
              2: "산적",
              3: "추노꾼",
              4: "파발꾼",
              5: "교리 감독관",
              6: "만신",
              7: "중매꾼",
              8: "사기꾼",
            },
          },
          view_state: {
            active_slots: {
              items: [
                { slot: 1, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 2, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 3, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 4, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 5, player_id: null, label: null, character: null, inactive_character: null, is_current_actor: false },
                { slot: 6, player_id: 1, label: "P1", character: "만신", inactive_character: "박수", is_current_actor: true },
                { slot: 7, player_id: null, label: null, character: "중매꾼", inactive_character: "객주", is_current_actor: false },
                { slot: 8, player_id: null, label: null, character: "사기꾼", inactive_character: "건설업자", is_current_actor: false },
              ],
            },
          },
        },
      },
    ];

    expect(selectActiveCharacterSlots(messages, 1).map((slot) => slot.character)).toEqual([
      "탐관오리",
      "산적",
      "추노꾼",
      "파발꾼",
      "교리 감독관",
      "만신",
      "중매꾼",
      "사기꾼",
    ]);
  });

  it("prefers fresher raw mark target candidates over a sparser backend projection", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "박수",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "만신",
        },
      },
      {
        type: "prompt",
        seq: 3,
        session_id: "s1",
        payload: {
          request_id: "req_mark_backend_sparse",
          request_type: "mark_target",
          player_id: 1,
          legal_choices: [
            {
              choice_id: "중매꾼",
              title: "중매꾼",
              value: { target_character: "중매꾼", target_card_no: 7 },
            },
            {
              choice_id: "사기꾼",
              title: "사기꾼",
              value: { target_character: "사기꾼", target_card_no: 8 },
            },
            {
              choice_id: "none",
              title: "지목 안 함",
            },
          ],
          public_context: {
            actor_name: "만신",
            active_by_card: {
              1: "탐관오리",
              2: "산적",
              3: "추노꾼",
              4: "파발꾼",
              5: "교리 감독관",
              6: "만신",
              7: "중매꾼",
              8: "사기꾼",
            },
          },
          view_state: {
            mark_target: {
              actor_slot: 6,
              candidates: [{ slot: 7, player_id: null, label: null, character: "중매꾼" }],
            },
          },
        },
      },
    ];

    expect(selectMarkTargetCharacterSlots(messages, "만신", 1)).toEqual([
      { slot: 7, playerId: null, label: null, character: "중매꾼" },
      { slot: 8, playerId: null, label: null, character: "사기꾼" },
    ]);
  });

  it("clears previous-turn public faces from non-actors at turn start", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "round_order",
          round_index: 1,
          turn_index: 1,
          active_by_card: {
            "2": "자객",
            "5": "교리 감독관",
            "6": "자객",
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 4,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "자객",
                alive: true,
                position: 0,
                cash: 15,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 1,
              },
              {
                player_id: 2,
                display_name: "Player 2",
                character: "교리 연구관",
                alive: true,
                position: 1,
                cash: 17,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
              {
                player_id: 4,
                display_name: "Player 4",
                character: "자객",
                alive: true,
                position: 3,
                cash: 17,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 1,
              },
            ],
            board: {
              marker_owner_player_id: 2,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "산적",
        },
      },
    ];

    const derivedPlayers = selectDerivedPlayers(messages, 1);
    expect(derivedPlayers[0]).toMatchObject({ playerId: 1, currentCharacterFace: "산적" });
    expect(derivedPlayers[1]).toMatchObject({ playerId: 2, currentCharacterFace: "-" });
    expect(derivedPlayers[2]).toMatchObject({ playerId: 4, currentCharacterFace: "-" });
  });

  it("hydrates active slots from mark-target prompt context when snapshots omit active faces", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "산적",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_mark_1",
          request_type: "mark_target",
          player_id: 1,
          public_context: {
            actor_name: "산적",
            target_pairs: [
              { target_card_no: 5, target_character: "교리 감독관" },
              { target_card_no: 6, target_character: "만신" },
              { target_card_no: 7, target_character: "객주" },
            ],
          },
        },
      },
    ];

    const slots = selectActiveCharacterSlots(messages, 1);
    expect(slots[1]).toMatchObject({ slot: 2, character: "산적" });
    expect(slots[4]).toMatchObject({ slot: 5, character: "교리 감독관" });
    expect(slots[5]).toMatchObject({ slot: 6, character: "만신" });
    expect(slots[6]).toMatchObject({ slot: 7, character: "객주" });
    expect(selectMarkTargetCharacterSlots(messages, "산적", 1)).toEqual([
      { slot: 5, playerId: null, label: null, character: "교리 감독관" },
      { slot: 6, playerId: null, label: null, character: "만신" },
      { slot: 7, playerId: null, label: null, character: "객주" },
    ]);
  });

  it("hydrates mark target slots from legal choices when target_pairs are omitted", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "산적",
          players: [
            {
              player_id: 1,
              display_name: "Player 1",
              character: "산적",
              alive: true,
              position: 0,
              cash: 20,
              shards: 4,
              hidden_trick_count: 0,
              owned_tile_count: 0,
            },
          ],
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_mark_2",
          request_type: "mark_target",
          player_id: 1,
          legal_choices: [
            {
              choice_id: "교리 감독관",
              title: "교리 감독관",
              value: { target_character: "교리 감독관" },
            },
            {
              choice_id: "만신",
              title: "만신",
              value: { target_character: "만신" },
            },
            {
              choice_id: "객주",
              title: "객주",
              value: { target_character: "객주" },
            },
            { choice_id: "none", title: "지목 안 함" },
          ],
          public_context: {
            actor_name: "산적",
          },
        },
      },
    ];

    const slots = selectActiveCharacterSlots(messages, 1);
    expect(slots[1]).toMatchObject({ slot: 2, character: "산적" });
    expect(slots[4]).toMatchObject({ slot: 5, character: "교리 감독관" });
    expect(slots[5]).toMatchObject({ slot: 6, character: "만신" });
    expect(slots[6]).toMatchObject({ slot: 7, character: "객주" });
    expect(selectMarkTargetCharacterSlots(messages, "산적", 1)).toEqual([
      { slot: 5, playerId: null, label: null, character: "교리 감독관" },
      { slot: 6, playerId: null, label: null, character: "만신" },
      { slot: 7, playerId: null, label: null, character: "객주" },
    ]);
  });

  it("preserves active slots when round-order arrives without active-by-card payload", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "round_start",
          marker_owner_player_id: 1,
          marker_draft_direction: "clockwise",
          active_by_card: {
            1: "탐관오리",
            2: "산적",
            3: "탈출 노비",
            4: "아전",
            5: "교리 감독관",
            6: "만신",
            7: "중매꾼",
            8: "사기꾼",
          },
          players: [
            { player_id: 1, display_name: "Player 1", character: "자객", alive: true, position: 0, cash: 20, shards: 4, hidden_trick_count: 0, owned_tile_count: 0 },
            { player_id: 2, display_name: "Player 2", character: "교리 연구관", alive: true, position: 0, cash: 20, shards: 4, hidden_trick_count: 0, owned_tile_count: 0 },
            { player_id: 3, display_name: "Player 3", character: "만신", alive: true, position: 0, cash: 20, shards: 4, hidden_trick_count: 0, owned_tile_count: 0 },
            { player_id: 4, display_name: "Player 4", character: "탐관오리", alive: true, position: 0, cash: 20, shards: 4, hidden_trick_count: 0, owned_tile_count: 0 },
          ],
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "round_order",
          order: [3, 2, 4, 1],
        },
      },
      {
        type: "prompt",
        seq: 3,
        session_id: "s1",
        payload: {
          request_id: "req_draft_live",
          request_type: "draft_card",
          player_id: 3,
          public_context: {
            actor_name: "만신",
          },
        },
      },
    ];

    expect(selectActiveCharacterSlots(messages, 3).map((slot) => slot.character)).toEqual([
      "탐관오리",
      "산적",
      "탈출 노비",
      "아전",
      "교리 감독관",
      "만신",
      "중매꾼",
      "사기꾼",
    ]);
  });

  it("matches shared player mark-target fixture contract", () => {
    const fixture = loadSharedPlayerMarkTargetFixture();
    const lastMessage = fixture.messages.at(-1);
    expect(lastMessage).toBeTruthy();
    const projectedMessages = fixture.messages.map((message, index) =>
      index === fixture.messages.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                players: fixture.expected.players,
                active_slots: fixture.expected.active_slots,
                mark_target: fixture.expected.mark_target,
              },
            },
          }
        : message
    );

    const expectedPlayers = fixture.expected.players.items.map((item) => ({
      playerId: item["player_id"],
      displayName: item["display_name"],
      character: item["current_character_face"],
      alive: true,
      position: 0,
      cash: item["cash"],
      shards: item["shards"],
      handCoins: item["hand_coins"],
      placedCoins: item["placed_coins"],
      totalScore: item["total_score"],
      hiddenTrickCount: 0,
      ownedTileCount: item["owned_tile_count"],
      publicTricks: [] as string[],
      trickCount: item["trick_count"],
      prioritySlot: item["priority_slot"],
      currentCharacterFace: item["current_character_face"],
      isMarkerOwner: item["is_marker_owner"],
      isCurrentActor: item["is_current_actor"],
      isLocalPlayer: item["player_id"] === 1,
    }));
    const expectedActiveSlots = fixture.expected.active_slots.items.map((item) => ({
      slot: item["slot"],
      playerId: item["player_id"],
      label: item["label"],
      character: item["character"],
      inactiveCharacter: item["inactive_character"],
      isCurrentActor: item["is_current_actor"],
      isLocalPlayer: item["player_id"] === 1,
    }));
    const expectedMarkTargets = fixture.expected.mark_target.candidates.map((item) => ({
      slot: item["slot"],
      playerId: item["player_id"],
      label: item["label"],
      character: item["character"],
    }));

    expect(selectDerivedPlayers(projectedMessages, 1)).toEqual(expectedPlayers);
    expect(selectActiveCharacterSlots(projectedMessages, 1)).toEqual(expectedActiveSlots);
    expect(selectMarkTargetCharacterSlots(projectedMessages, "산적", 1)).toEqual(expectedMarkTargets);
  });

  it("keeps mark-target active slots hydrated from the live prompt even if later events become the latest snapshot source", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "자객",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
        },
      },
      {
        type: "prompt",
        seq: 2,
        session_id: "s1",
        payload: {
          request_id: "req_mark_live",
          request_type: "mark_target",
          player_id: 1,
          legal_choices: [
            {
              choice_id: "탈출 노비",
              title: "탈출 노비",
              value: { target_character: "탈출 노비", target_card_no: 3 },
            },
            {
              choice_id: "아전",
              title: "아전",
              value: { target_character: "아전", target_card_no: 4 },
            },
            {
              choice_id: "교리 연구관",
              title: "교리 연구관",
              value: { target_character: "교리 연구관", target_card_no: 5 },
            },
            { choice_id: "none", title: "지목 안 함" },
          ],
          public_context: {
            actor_name: "산적",
          },
        },
      },
      {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "산적",
          players: [
            {
              player_id: 1,
              display_name: "Player 1",
              character: "산적",
              alive: true,
              position: 0,
              cash: 20,
              shards: 4,
              hidden_trick_count: 0,
              owned_tile_count: 0,
            },
          ],
        },
      },
    ];

    const slots = selectActiveCharacterSlots(messages, 1);
    expect(slots[1]).toMatchObject({ slot: 2, character: "산적" });
    expect(slots[2]).toMatchObject({ slot: 3, character: "탈출 노비" });
    expect(slots[3]).toMatchObject({ slot: 4, character: "아전" });
    expect(slots[4]).toMatchObject({ slot: 5, character: "교리 연구관" });
    expect(selectMarkTargetCharacterSlots(messages, "산적", 1)).toEqual([
      { slot: 3, playerId: null, label: null, character: "탈출 노비" },
      { slot: 4, playerId: null, label: null, character: "아전" },
      { slot: 5, playerId: null, label: null, character: "교리 연구관" },
    ]);
  });

  it("ignores stale backend active-slot projections when newer raw round state exists", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "자객",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
          view_state: {
            active_slots: {
              items: Array.from({ length: 8 }, (_, index) => ({
                slot: index + 1,
                player_id: null,
                label: null,
                character: null,
                inactive_character: null,
                is_current_actor: false,
              })),
            },
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "round_order",
          round_index: 1,
          turn_index: 1,
          active_by_card: {
            "2": "산적",
            "5": "교리 감독관",
            "6": "박수",
          },
        },
      },
      {
        type: "event",
        seq: 3,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 1,
          turn_index: 2,
          acting_player_id: 1,
          character: "산적",
        },
      },
    ];

    const slots = selectActiveCharacterSlots(messages, 1);
    expect(slots[1]).toMatchObject({ slot: 2, character: "산적", playerId: 1 });
    expect(slots[4]).toMatchObject({ slot: 5, character: "교리 감독관" });
    expect(slots[5]).toMatchObject({ slot: 6, character: "박수" });
  });

  it("builds active slots from manifest-carried active faces before any snapshot exists", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "parameter_manifest",
          manifest_hash: "hash_a",
          active_by_card: {
            "1": "어사",
            "2": "산적",
            "3": "탈출 노비",
            "4": "아전",
            "5": "교리 감독관",
            "6": "만신",
            "7": "중매꾼",
            "8": "사기꾼",
          },
        },
      },
    ];

    expect(selectActiveCharacterSlots(messages, 1).map((slot) => slot.character)).toEqual([
      "어사",
      "산적",
      "탈출 노비",
      "아전",
      "교리 감독관",
      "만신",
      "중매꾼",
      "사기꾼",
    ]);
  });

  it("falls back to session-provided initial active faces before stream events arrive", () => {
    expect(
      selectActiveCharacterSlots([], 1, undefined, {
        "1": "어사",
        "2": "산적",
        "3": "탈출 노비",
        "4": "아전",
        "5": "교리 감독관",
        "6": "만신",
        "7": "중매꾼",
        "8": "사기꾼",
      }).map((slot) => slot.character)
    ).toEqual(["어사", "산적", "탈출 노비", "아전", "교리 감독관", "만신", "중매꾼", "사기꾼"]);
  });

  it("ignores stale backend mark-target projections when a newer raw prompt arrives", () => {
    const messages: InboundMessage[] = [
      {
        type: "event",
        seq: 1,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 1,
          turn_index: 1,
          acting_player_id: 1,
          snapshot: {
            players: [
              {
                player_id: 1,
                display_name: "Player 1",
                character: "자객",
                alive: true,
                position: 0,
                cash: 20,
                shards: 4,
                hidden_trick_count: 0,
                owned_tile_count: 0,
              },
            ],
            board: {
              marker_owner_player_id: 1,
              f_value: 0,
              tiles: [],
            },
          },
          view_state: {
            mark_target: {
              actor_slot: 2,
              candidates: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 2,
        session_id: "s1",
        payload: {
          event_type: "round_order",
          round_index: 1,
          turn_index: 1,
          active_by_card: {
            "2": "산적",
            "3": "탈출 노비",
            "4": "아전",
            "5": "교리 감독관",
          },
        },
      },
      {
        type: "prompt",
        seq: 3,
        session_id: "s1",
        payload: {
          request_id: "req_mark_live",
          request_type: "mark_target",
          player_id: 1,
          legal_choices: [
            { choice_id: "탈출 노비", title: "탈출 노비", value: { target_character: "탈출 노비", target_card_no: 3 } },
            { choice_id: "아전", title: "아전", value: { target_character: "아전", target_card_no: 4 } },
            { choice_id: "교리 감독관", title: "교리 감독관", value: { target_character: "교리 감독관", target_card_no: 5 } },
            { choice_id: "none", title: "지목 안 함" },
          ],
          public_context: {
            actor_name: "산적",
          },
        },
      },
    ];

    expect(selectMarkTargetCharacterSlots(messages, "산적", 1)).toEqual([
      { slot: 3, playerId: null, label: null, character: "탈출 노비" },
      { slot: 4, playerId: null, label: null, character: "아전" },
      { slot: 5, playerId: null, label: null, character: "교리 감독관" },
    ]);
  });

  it("builds a live snapshot with updated pawns and tile ownership after current-turn events", () => {
    const snapshot = selectLiveSnapshot([
      snapshotEvent,
      {
        type: "event",
        seq: 220,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 2,
          turn_index: 6,
          acting_player_id: 1,
          character: "Builder",
        },
      },
      {
        type: "event",
        seq: 221,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          round_index: 2,
          turn_index: 6,
          acting_player_id: 1,
          from_tile_index: 5,
          to_tile_index: 8,
        },
      },
      {
        type: "event",
        seq: 222,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          round_index: 2,
          turn_index: 6,
          player_id: 1,
          resolution: "accepted",
          choice_id: "buy",
          public_context: {
            player_position: 8,
            player_owned_tile_count: 3,
          },
        },
      },
      {
        type: "event",
        seq: 223,
        session_id: "s1",
        payload: {
          event_type: "tile_purchased",
          round_index: 2,
          turn_index: 6,
          acting_player_id: 1,
          player_id: 1,
          tile_index: 8,
          cost: 5,
          score_coin_count: 1,
        },
      },
    ]);

    expect(snapshot).not.toBeNull();
    expect(snapshot?.players[0].position).toBe(8);
    expect(snapshot?.players[0].ownedTileCount).toBe(3);
    expect(snapshot?.tiles.find((tile) => tile.tileIndex === 8)?.ownerPlayerId).toBe(1);
    expect(snapshot?.tiles.find((tile) => tile.tileIndex === 8)?.scoreCoinCount).toBe(1);
    expect(snapshot?.tiles.find((tile) => tile.tileIndex === 8)?.pawnPlayerIds).toEqual([1]);
  });

  it("updates tile score coins from event public context on the live selector path", () => {
    const snapshot = selectLiveSnapshot([
      snapshotEvent,
      {
        type: "event",
        seq: 224,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          round_index: 2,
          turn_index: 6,
          player_id: 1,
          resolution: "accepted",
          choice_id: "place_score",
          public_context: {
            tile_index: 5,
            tile_score_coins: 3,
          },
        },
      },
    ]);

    expect(snapshot?.tiles.find((tile) => tile.tileIndex === 5)?.scoreCoinCount).toBe(3);
  });

  it("matches shared board live-tiles fixture contract", () => {
    const fixture = loadSharedBoardFixture();
    const projectedMessages = fixture.messages.map((message, index) =>
      index === fixture.messages.length - 1
        ? {
            ...message,
            payload: {
              ...message.payload,
              view_state: {
                board: fixture.expected.board,
              },
            },
          }
        : message
    );

    const snapshot = selectLiveSnapshot(projectedMessages);
    expect(snapshot?.tiles.find((tile) => tile.tileIndex === 5)).toMatchObject({
      tileIndex: 5,
      scoreCoinCount: 3,
      ownerPlayerId: 2,
      pawnPlayerIds: [2],
    });
    expect(snapshot?.tiles.find((tile) => tile.tileIndex === 8)).toMatchObject({
      tileIndex: 8,
      scoreCoinCount: 1,
      ownerPlayerId: 1,
      pawnPlayerIds: [1],
    });
    expect(selectLastMove(projectedMessages)).toEqual({
      playerId: fixture.expected.board.last_move.player_id,
      fromTileIndex: fixture.expected.board.last_move.from_tile_index,
      toTileIndex: fixture.expected.board.last_move.to_tile_index,
      pathTileIndices: fixture.expected.board.last_move.path_tile_indices,
    });
  });

  it("collects current-turn reveal events in public order for the board HUD", () => {
    const items = selectCurrentTurnRevealItems([
      {
        type: "event",
        seq: 700,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 8,
          turn_index: 2,
          acting_player_id: 2,
          character: "Bandit",
        },
      },
      {
        type: "event",
        seq: 701,
        session_id: "s1",
        payload: {
          event_type: "weather_reveal",
          round_index: 8,
          turn_index: 2,
          weather_name: "Cold Front",
          effect_text: "No lap cash. Pay 2 cash to bank.",
        },
      },
      {
        type: "event",
        seq: 702,
        session_id: "s1",
        payload: {
          event_type: "dice_roll",
          round_index: 8,
          turn_index: 2,
          acting_player_id: 2,
          total_move: 6,
        },
      },
      {
        type: "event",
        seq: 703,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          round_index: 8,
          turn_index: 2,
          acting_player_id: 2,
          from_tile_index: 3,
          to_tile_index: 9,
          path: [4, 5, 6, 7, 8, 9],
        },
      },
      {
        type: "event",
        seq: 704,
        session_id: "s1",
        payload: {
          event_type: "landing_resolved",
          round_index: 8,
          turn_index: 2,
          acting_player_id: 2,
          tile_index: 9,
          result: "PURCHASE",
        },
      },
      {
        type: "event",
        seq: 705,
        session_id: "s1",
        payload: {
          event_type: "tile_purchased",
          round_index: 8,
          turn_index: 2,
          player_id: 2,
          tile_index: 9,
          cost: 3,
        },
      },
      {
        type: "event",
        seq: 706,
        session_id: "s1",
        payload: {
          event_type: "fortune_drawn",
          round_index: 8,
          turn_index: 2,
          player_id: 2,
          card_name: "Lucky Wind",
          tile_index: 9,
        },
      },
      {
        type: "event",
        seq: 707,
        session_id: "s1",
        payload: {
          event_type: "fortune_resolved",
          round_index: 8,
          turn_index: 2,
          player_id: 2,
          summary: "Gain 2 cash.",
          tile_index: 9,
        },
      },
      {
        type: "prompt",
        seq: 708,
        session_id: "s1",
        payload: {
          request_id: "req_buy_1",
          request_type: "purchase_tile",
          player_id: 2,
          public_context: { tile_index: 9 },
        },
      },
    ], 7);

    expect(items.map((item) => item.eventCode)).toEqual([
      "weather_reveal",
      "dice_roll",
      "player_move",
      "landing_resolved",
      "tile_purchased",
      "fortune_drawn",
      "fortune_resolved",
    ]);
    expect(items[0]).toMatchObject({ tone: "effect", seq: 701 });
    expect(items[1]).toMatchObject({ tone: "move", seq: 702 });
    expect(items[2].focusTileIndex).toBe(9);
    expect(items[3].detail).toContain("구매");
    expect(items[4]).toMatchObject({ tone: "economy", seq: 705 });
    expect(items[6].detail).toContain("Gain 2 cash");
  });

  it("includes same-turn rent results in the board reveal stack", () => {
    const items = selectCurrentTurnRevealItems([
      {
        type: "event",
        seq: 900,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 9,
          turn_index: 4,
          acting_player_id: 3,
          character: "Surveyor",
        },
      },
      {
        type: "event",
        seq: 901,
        session_id: "s1",
        payload: {
          event_type: "rent_paid",
          round_index: 9,
          turn_index: 4,
          player_id: 3,
          payer_player_id: 3,
          owner_player_id: 1,
          tile_index: 12,
          final_amount: 5,
        },
      },
      {
        type: "event",
        seq: 902,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 9,
          turn_index: 4,
          player_id: 3,
          summary: "P3 rent turn closed",
        },
      },
    ]);

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      eventCode: "rent_paid",
      tone: "economy",
      seq: 901,
      focusTileIndex: 12,
    });
    expect(items[0].detail).toContain("P3");
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

  it("formats decision ack and runtime errors through locale helpers", () => {
    const timeline = selectTimeline([
      {
        type: "decision_ack",
        seq: 10,
        session_id: "s1",
        payload: { status: "accepted", reason: "worker ok" },
      },
      {
        type: "error",
        seq: 11,
        session_id: "s1",
        payload: { code: "EXTERNAL_AI_TIMEOUT", message: "worker timeout" },
      },
    ]);

    expect(timeline[0].detail).toBe("EXTERNAL_AI_TIMEOUT: worker timeout");
    expect(timeline[1].detail).toBe("accepted (worker ok)");
  });

  it("formats canonical decision events with prompt context and worker status", () => {
    const timeline = selectTimeline([
      {
        type: "event",
        seq: 12,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          request_id: "req_buy_1",
          request_type: "purchase_tile",
          player_id: 2,
          legal_choices: [{ choice_id: "yes" }, { choice_id: "no" }],
          public_context: {
            tile_index: 9,
            external_ai_worker_id: "prod-bot-1",
            external_ai_resolution_status: "resolved_by_worker",
            external_ai_ready_state: "ready",
            external_ai_policy_mode: "heuristic_v3_gpt",
            external_ai_worker_adapter: "reference_heuristic_v1",
            external_ai_policy_class: "HeuristicPolicy",
            external_ai_decision_style: "contract_heuristic",
          },
        },
      },
      {
        type: "event",
        seq: 13,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          request_id: "req_buy_1",
          player_id: 2,
          resolution: "accepted",
          choice_id: "yes",
          public_context: {
            external_ai_worker_id: "prod-bot-1",
            external_ai_resolution_status: "resolved_by_worker",
            external_ai_ready_state: "ready",
            external_ai_policy_mode: "heuristic_v3_gpt",
            external_ai_worker_adapter: "reference_heuristic_v1",
            external_ai_policy_class: "HeuristicPolicy",
            external_ai_decision_style: "contract_heuristic",
          },
        },
      },
    ]);

    expect(timeline[0].detail).toContain("외부 worker 처리 완료");
    expect(timeline[0].detail).toContain("상태 준비됨");
    expect(timeline[0].detail).toContain("모드 heuristic_v3_gpt");
    expect(timeline[0].detail).toContain("어댑터 reference_heuristic_v1");
    expect(timeline[0].detail).toContain("클래스 HeuristicPolicy");
    expect(timeline[1].detail).toContain("10번 칸");
    expect(timeline[1].detail).toContain("선택지 2개");
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
    expect(situation.weatherEffect).toContain("2배");
  });

  it("prefers backend scene projection for situation headline", () => {
    const situation = selectSituation([
      {
        type: "event",
        seq: 120,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 5,
          turn_index: 9,
          acting_player_id: 2,
          view_state: {
            scene: {
              situation: {
                actor_player_id: 2,
                round_index: 5,
                turn_index: 9,
                headline_seq: 121,
                headline_message_type: "event",
                headline_event_code: "player_move",
                weather_name: "긴급 피난",
                weather_effect: "모든 짐 제거 비용이 2배가 됩니다.",
              },
              theater_feed: [],
              core_action_feed: [],
            },
          },
        },
      },
      {
        type: "event",
        seq: 121,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          acting_player_id: 2,
          from_tile_index: 2,
          to_tile_index: 9,
        },
      },
    ]);

    expect(situation.actor).toBe("P2");
    expect(situation.round).toBe("5");
    expect(situation.turn).toBe("9");
    expect(situation.eventType).toBe("말 이동");
    expect(situation.weather).toBe("긴급 피난");
  });

  it("matches shared selector scene fixture contract", () => {
    const fixture = loadSharedSceneFixture();
    const situation = selectSituation(fixture.messages);
    const theater = selectTheaterFeed(fixture.messages);
    const core = selectCoreActionFeed(fixture.messages);
    const timeline = selectTimeline(fixture.messages);
    const alerts = selectCriticalAlerts(fixture.messages);

    expect(situation.actor).toBe("P4");
    expect(situation.round).toBe(String(fixture.expected.scene.situation.round_index));
    expect(situation.turn).toBe(String(fixture.expected.scene.situation.turn_index));
    expect(situation.weather).toBe(fixture.expected.scene.situation.weather_name);
    expect(situation.weatherEffect).toBe(fixture.expected.scene.situation.weather_effect);

    expect(theater.map((item) => ({ seq: item.seq, event_code: item.eventCode, lane: item.lane }))).toEqual(
      fixture.expected.scene.theater_feed.map((item) => ({
        seq: item.seq,
        event_code: item.event_code,
        lane: item.lane,
      })),
    );
    expect(core.map((item) => ({ seq: item.seq, event_code: item.eventCode }))).toEqual(
      fixture.expected.scene.core_action_feed.map((item) => ({
        seq: item.seq,
        event_code: item.event_code,
      })),
    );
    expect(timeline.map((item) => ({ seq: item.seq, event_code: fixtureMessageCodeBySeq(fixture.messages, item.seq) }))).toEqual(
      fixture.expected.scene.timeline.map((item) => ({
        seq: item.seq,
        event_code: item.event_code,
      })),
    );
    expect(alerts.map((item) => ({ seq: item.seq, severity: item.severity }))).toEqual(
      fixture.expected.scene.critical_alerts.map((item) => ({
        seq: item.seq,
        severity: item.severity,
      })),
    );
  });

  it("uses weather effect text when the payload provides effect_text", () => {
    const situation = selectSituation([
      {
        type: "event",
        seq: 8,
        session_id: "s1",
        payload: {
          event_type: "weather_reveal",
          weather_name: "Cold Front",
          effect_text: "No lap cash. Pay 2 cash to bank.",
        },
      },
      snapshotEvent,
    ]);
    expect(situation.weather).toBe("Cold Front");
    expect(situation.weatherEffect).toBe("No lap cash. Pay 2 cash to bank.");
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
          path: [6, 7, 8],
        },
      },
    ]);
    expect(move).not.toBeNull();
    expect(move?.playerId).toBe(2);
    expect(move?.fromTileIndex).toBe(5);
    expect(move?.toTileIndex).toBe(8);
    expect(move?.pathTileIndices).toEqual([6, 7, 8]);
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
      3,
    );
    expect(timeline[0].detail).toContain("누락 7");
    expect(timeline[1].detail).toContain("[징표] P2 -> P1");
    expect(timeline[2].detail).toContain("카드 1+4");
  });

  it("prefers backend scene projection for timeline ordering", () => {
    const timeline = selectTimeline([
      {
        type: "event",
        seq: 70,
        session_id: "s1",
        payload: {
          event_type: "dice_roll",
          cards_used: [1, 4],
          total_move: 5,
        },
      },
      {
        type: "decision_ack",
        seq: 71,
        session_id: "s1",
        payload: {
          request_id: "r1",
          status: "accepted",
          player_id: 2,
          view_state: {
            scene: {
              situation: {
                actor_player_id: 2,
                round_index: 2,
                turn_index: 5,
                headline_seq: 70,
                headline_message_type: "event",
                headline_event_code: "dice_roll",
                weather_name: "-",
                weather_effect: "-",
              },
              theater_feed: [],
              core_action_feed: [],
              timeline: [
                { seq: 71, message_type: "decision_ack", event_code: "decision_ack" },
                { seq: 70, message_type: "event", event_code: "dice_roll" },
              ],
              critical_alerts: [],
            },
          },
        },
      },
    ]);

    expect(timeline[0].seq).toBe(71);
    expect(timeline[0].label).toBe("선택 응답");
    expect(timeline[1].seq).toBe(70);
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
                S: "운수",
                F1: "종료 - 1",
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

  it("prefers backend scene projection for theater feed order and lanes", () => {
    const theater = selectTheaterFeed([
      {
        type: "prompt",
        seq: 181,
        session_id: "s1",
        payload: { request_type: "purchase_tile", player_id: 2 },
      },
      {
        type: "decision_ack",
        seq: 182,
        session_id: "s1",
        payload: { request_id: "r1", status: "accepted", player_id: 2 },
      },
      {
        type: "event",
        seq: 183,
        session_id: "s1",
        payload: {
          event_type: "bankruptcy",
          player_id: 4,
          view_state: {
            scene: {
              situation: {
                actor_player_id: 4,
                round_index: 4,
                turn_index: 6,
                headline_seq: 183,
                headline_message_type: "event",
                headline_event_code: "bankruptcy",
                weather_name: "-",
                weather_effect: "-",
              },
              theater_feed: [
                {
                  seq: 183,
                  message_type: "event",
                  event_code: "bankruptcy",
                  tone: "critical",
                  lane: "core",
                  actor_player_id: 4,
                  round_index: 4,
                  turn_index: 6,
                },
                {
                  seq: 182,
                  message_type: "decision_ack",
                  event_code: "decision_ack",
                  tone: "system",
                  lane: "prompt",
                  actor_player_id: 2,
                  round_index: null,
                  turn_index: null,
                },
                {
                  seq: 181,
                  message_type: "prompt",
                  event_code: "prompt",
                  tone: "system",
                  lane: "system",
                  actor_player_id: 2,
                  round_index: null,
                  turn_index: null,
                },
              ],
              core_action_feed: [],
            },
          },
        },
      },
    ]);

    expect(theater).toHaveLength(3);
    expect(theater[0].seq).toBe(183);
    expect(theater[0].lane).toBe("core");
    expect(theater[1].eventCode).toBe("decision_ack");
    expect(theater[1].lane).toBe("prompt");
    expect(theater[2].eventCode).toBe("prompt");
    expect(theater[2].lane).toBe("system");
  });

  it("routes ai decision lifecycle events to the system lane instead of the prompt lane", () => {
    const theater = selectTheaterFeed([
      {
        type: "event",
        seq: 84,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          request_type: "purchase_tile",
          player_id: 2,
          provider: "ai",
        },
      },
      {
        type: "event",
        seq: 85,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          player_id: 2,
          provider: "ai",
          resolution: "accepted",
          choice_id: "no",
        },
      },
    ]);

    expect(theater[0].eventCode).toBe("decision_resolved");
    expect(theater[0].lane).toBe("system");
    expect(theater[1].eventCode).toBe("decision_requested");
    expect(theater[1].lane).toBe("system");
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

  it("prefers backend scene projection for critical alerts", () => {
    const alerts = selectCriticalAlerts([
      {
        type: "event",
        seq: 94,
        session_id: "s1",
        payload: {
          event_type: "game_end",
          summary: "finished",
          view_state: {
            scene: {
              situation: {
                actor_player_id: null,
                round_index: 2,
                turn_index: 3,
                headline_seq: 94,
                headline_message_type: "event",
                headline_event_code: "game_end",
                weather_name: "-",
                weather_effect: "-",
              },
              theater_feed: [],
              core_action_feed: [],
              timeline: [],
              critical_alerts: [
                {
                  seq: 94,
                  message_type: "event",
                  event_code: "game_end",
                  severity: "critical",
                },
              ],
            },
          },
        },
      },
    ]);

    expect(alerts).toHaveLength(1);
    expect(alerts[0].seq).toBe(94);
    expect(alerts[0].severity).toBe("critical");
    expect(alerts[0].title).toBe("게임 종료");
  });

  it("formats timeout fallback details through locale resources", () => {
    const timeline = selectTimeline([
      {
        type: "event",
        seq: 95,
        session_id: "s1",
        payload: {
          event_type: "decision_timeout_fallback",
          player_id: 2,
          summary: "defaulted to local AI",
          public_context: {
            external_ai_worker_id: "prod-bot-1",
            external_ai_failure_code: "external_ai_timeout",
            external_ai_fallback_mode: "local_ai",
            external_ai_attempt_count: 3,
            external_ai_attempt_limit: 4,
          },
        },
      },
    ]);

    expect(timeline[0].detail).toContain("시간 초과 기본 처리");
    expect(timeline[0].detail).toContain("defaulted to local AI");
    expect(timeline[0].detail).toContain("prod-bot-1");
    expect(timeline[0].detail).toContain("external_ai_timeout");
    expect(timeline[0].detail).toContain("시도 3/4");
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
      8,
    );
    expect(feed).toHaveLength(2);
    expect(feed[0].seq).toBe(511);
    expect(feed[0].isLocalActor).toBe(false);
    expect(feed[1].seq).toBe(510);
    expect(feed[1].isLocalActor).toBe(true);
  });

  it("prefers backend scene projection for core action feed", () => {
    const feed = selectCoreActionFeed(
      [
        {
          type: "event",
          seq: 610,
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
          seq: 611,
          session_id: "s1",
          payload: {
            event_type: "tile_purchased",
            acting_player_id: 2,
            player_id: 2,
            tile_index: 5,
            cost: 4,
            view_state: {
              scene: {
                situation: {
                  actor_player_id: 2,
                  round_index: 7,
                  turn_index: 2,
                  headline_seq: 611,
                  headline_message_type: "event",
                  headline_event_code: "tile_purchased",
                  weather_name: "-",
                  weather_effect: "-",
                },
                theater_feed: [],
                core_action_feed: [
                  {
                    seq: 611,
                    event_code: "tile_purchased",
                    actor_player_id: 2,
                    round_index: 7,
                    turn_index: 2,
                  },
                  {
                    seq: 610,
                    event_code: "player_move",
                    actor_player_id: 1,
                    round_index: 7,
                    turn_index: 2,
                  },
                ],
              },
            },
          },
        },
      ],
      1,
      8,
    );

    expect(feed).toHaveLength(2);
    expect(feed[0].seq).toBe(611);
    expect(feed[0].isLocalActor).toBe(false);
    expect(feed[1].seq).toBe(610);
    expect(feed[1].isLocalActor).toBe(true);
  });

  it("keeps timeout fallback visible in the core action feed", () => {
    const feed = selectCoreActionFeed([
      {
        type: "event",
        seq: 520,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 3,
          acting_player_id: 3,
          character: "Surveyor",
        },
      },
      {
        type: "event",
        seq: 521,
        session_id: "s1",
        payload: {
          event_type: "decision_timeout_fallback",
          round_index: 4,
          turn_index: 3,
          player_id: 3,
          summary: "worker reported not ready",
          public_context: {
            external_ai_failure_code: "external_ai_worker_not_ready",
            external_ai_attempt_count: 1,
            external_ai_attempt_limit: 3,
          },
        },
      },
      {
        type: "event",
        seq: 522,
        session_id: "s1",
        payload: {
          event_type: "rent_paid",
          round_index: 4,
          turn_index: 3,
          player_id: 3,
          payer_player_id: 3,
          owner_player_id: 1,
          tile_index: 12,
          final_amount: 5,
        },
      },
    ]);

    expect(feed.map((item) => item.eventCode)).toEqual(["rent_paid", "decision_timeout_fallback", "turn_start"]);
    expect(feed[1].detail).toContain("external_ai_worker_not_ready");
    expect(feed[1].detail).toContain("시도 1/3");
  });

  it("builds a turn-stage beat and progress trail from the current turn", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 200,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          character: "교리 연구관",
        },
      },
      {
        type: "event",
        seq: 201,
        session_id: "s1",
        payload: {
          event_type: "dice_roll",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          cards_used: [1, 4],
          total_move: 5,
        },
      },
      {
        type: "event",
        seq: 202,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          from_tile_index: 3,
          to_tile_index: 8,
        },
      },
      {
        type: "event",
        seq: 203,
        session_id: "s1",
        payload: {
          event_type: "landing_resolved",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          result_type: "PURCHASE",
        },
      },
      {
        type: "event",
        seq: 204,
        session_id: "s1",
        payload: {
          event_type: "tile_purchased",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          tile_index: 8,
          cost: 5,
        },
      },
    ]);

    expect(stage.actor).toBe("P2");
    expect(stage.character).toBe("교리 연구관");
    expect(stage.currentBeatLabel).toBe("토지 구매");
    expect(stage.currentBeatDetail).toContain("9번 칸");
    expect(stage.progressTrail).toEqual(["턴 시작", "이동값 결정", "말 이동", "도착 결과", "토지 구매"]);
  });

  it("tracks beat kind and focus tile for purchase, rent, and prompt flows", () => {
    const purchaseStage = selectTurnStage([
      {
        type: "event",
        seq: 200,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          character: "Scholar",
        },
      },
      {
        type: "event",
        seq: 201,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          from_tile_index: 3,
          to_tile_index: 8,
        },
      },
      {
        type: "event",
        seq: 202,
        session_id: "s1",
        payload: {
          event_type: "tile_purchased",
          round_index: 3,
          turn_index: 8,
          acting_player_id: 2,
          tile_index: 8,
          cost: 5,
        },
      },
    ]);

    expect(purchaseStage.currentBeatKind).toBe("economy");
    expect(purchaseStage.focusTileIndex).toBe(8);

    const rentStage = selectTurnStage([
      {
        type: "event",
        seq: 300,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 9,
          acting_player_id: 4,
          character: "Courier",
        },
      },
      {
        type: "event",
        seq: 301,
        session_id: "s1",
        payload: {
          event_type: "rent_paid",
          round_index: 4,
          turn_index: 9,
          acting_player_id: 4,
          payer_player_id: 4,
          owner_player_id: 2,
          tile_index: 14,
          final_amount: 6,
        },
      },
      {
        type: "prompt",
        seq: 302,
        session_id: "s1",
        payload: {
          request_id: "req_9",
          request_type: "lap_reward",
          player_id: 4,
          public_context: {
            tile_index: 14,
          },
        },
      },
    ]);

    expect(rentStage.rentSummary).toContain("P4");
    expect(rentStage.currentBeatKind).toBe("decision");
    expect(rentStage.focusTileIndex).toBe(14);
    expect(rentStage.promptSummary).not.toBe("-");
  });

  it("captures lap reward, mark, and flip summaries in the current turn stage", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 700,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 8,
          turn_index: 2,
          acting_player_id: 2,
          character: "Bandit",
        },
      },
      {
        type: "event",
        seq: 701,
        session_id: "s1",
        payload: {
          event_type: "weather_reveal",
          round_index: 8,
          turn_index: 2,
          weather_name: "Cold Front",
          effect_text: "No lap cash. Pay 2 cash to bank.",
        },
      },
      {
        type: "event",
        seq: 702,
        session_id: "s1",
        payload: {
          event_type: "lap_reward_chosen",
          round_index: 8,
          turn_index: 2,
          acting_player_id: 2,
          amount: { cash: 6 },
        },
      },
      {
        type: "event",
        seq: 703,
        session_id: "s1",
        payload: {
          event_type: "mark_resolved",
          round_index: 8,
          turn_index: 2,
          source_player_id: 2,
          target_player_id: 4,
        },
      },
      {
        type: "event",
        seq: 704,
        session_id: "s1",
        payload: {
          event_type: "marker_flip",
          round_index: 8,
          turn_index: 2,
          from_character: "Courier",
          to_character: "Bandit",
        },
      },
    ]);

    expect(stage.weatherSummary).toContain("Cold Front");
    expect(stage.lapRewardSummary).toContain("P2");
    expect(stage.markSummary).toContain("P2");
    expect(stage.flipSummary).toContain("Courier");
    expect(stage.effectSummary).toContain("Courier");
  });

  it("surfaces queued and failed mark visibility events in the current turn stage", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 800,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 9,
          turn_index: 3,
          acting_player_id: 1,
          character: "Manshin",
        },
      },
      {
        type: "event",
        seq: 801,
        session_id: "s1",
        payload: {
          event_type: "mark_queued",
          round_index: 9,
          turn_index: 3,
          acting_player_id: 1,
          source_player_id: 1,
          target_player_id: 3,
          target_character: "Builder",
          effect_type: "manshin_remove_burdens",
        },
      },
      {
        type: "event",
        seq: 802,
        session_id: "s1",
        payload: {
          event_type: "mark_target_none",
          round_index: 9,
          turn_index: 3,
          acting_player_id: 1,
          source_player_id: 1,
          actor_name: "Manshin",
        },
      },
    ]);

    expect(stage.markSummary).toContain("기본 처리");
    expect(stage.effectSummary).toContain("기본 처리");
    expect(stage.progressTrail).toContain("지목 예약");
    expect(stage.progressTrail).toContain("지목 대상 없음");
  });

  it("uses prompt actor and hides stale character during draft and final-character phases", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 900,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 5,
          turn_index: 3,
          acting_player_id: 1,
          character: "건설업자",
        },
      },
      {
        type: "prompt",
        seq: 901,
        session_id: "s1",
        payload: {
          request_id: "req_draft_1",
          request_type: "draft_card",
          player_id: 2,
          round_index: 6,
          turn_index: 1,
          public_context: {
            round_index: 6,
            turn_index: 1,
            draft_phase: 2,
          },
        },
      },
    ]);

    expect(stage.actorPlayerId).toBe(2);
    expect(stage.actor).toBe("P2");
    expect(stage.round).toBe(6);
    expect(stage.turn).toBe(1);
    expect(stage.character).toBe("-");
    expect(stage.promptRequestType).toBe("draft_card");
  });

  it("also hides stale character for final_character_choice compatibility prompts", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 910,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 5,
          turn_index: 3,
          acting_player_id: 1,
          character: "건설업자",
        },
      },
      {
        type: "prompt",
        seq: 911,
        session_id: "s1",
        payload: {
          request_id: "req_final_1",
          request_type: "final_character_choice",
          player_id: 3,
          public_context: {
            round_index: 6,
            turn_index: 1,
          },
        },
      },
    ]);

    expect(stage.actorPlayerId).toBe(3);
    expect(stage.character).toBe("-");
    expect(stage.promptRequestType).toBe("final_character_choice");
  });

  it("derives prompt focus tile from canonical legal_choices when public_context omits tile_index", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 320,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 10,
          acting_player_id: 2,
          character: "Scholar",
        },
      },
      {
        type: "prompt",
        seq: 321,
        session_id: "s1",
        payload: {
          request_id: "req_coin_1",
          request_type: "coin_placement",
          player_id: 2,
          legal_choices: [
            {
              choice_id: "11",
              label: "11번 칸",
              value: { tile_index: 11 },
            },
            {
              choice_id: "17",
              label: "17번 칸",
              value: { tile_index: 17 },
            },
          ],
          public_context: {
            owned_tile_indices: [11, 17],
          },
        },
      },
    ]);

    expect(stage.currentBeatKind).toBe("decision");
    expect(stage.focusTileIndex).toBe(11);
    expect(stage.focusTileIndices).toEqual([11, 17]);
    expect(stage.promptSummary).toContain("승점 배치");
  });

  it("anchors matchmaker follow-up purchase prompts to the landing tile before legal targets", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 319,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 10,
          acting_player_id: 2,
          character: "중매꾼",
        },
      },
      {
        type: "event",
        seq: 320,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          round_index: 4,
          turn_index: 10,
          player_id: 2,
          request_type: "purchase_tile",
          legal_choices: [{ choice_id: "yes" }, { choice_id: "no" }],
          public_context: {
            tile_index: 7,
            landing_tile_index: 4,
            candidate_tiles: [7, 8],
          },
        },
      },
    ]);

    expect(stage.currentBeatKind).toBe("decision");
    expect(stage.focusTileIndex).toBe(4);
    expect(stage.focusTileIndices).toEqual([4, 7, 8]);
  });

  it("keeps timeout fallback visible in the current turn stage", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 330,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 11,
          acting_player_id: 2,
          character: "Scholar",
        },
      },
      {
        type: "event",
        seq: 331,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          round_index: 4,
          turn_index: 11,
          player_id: 2,
          request_type: "purchase_tile",
          public_context: { tile_index: 9 },
        },
      },
      {
        type: "event",
        seq: 332,
        session_id: "s1",
        payload: {
          event_type: "decision_timeout_fallback",
          round_index: 4,
          turn_index: 11,
          player_id: 2,
          summary: "defaulted to local AI",
          public_context: {
            tile_index: 9,
            external_ai_worker_id: "prod-bot-1",
            external_ai_failure_code: "external_ai_timeout",
            external_ai_fallback_mode: "local_ai",
            external_ai_attempt_count: 3,
            external_ai_attempt_limit: 4,
            external_ai_ready_state: "not_ready",
            external_ai_policy_mode: "heuristic_v3_gpt",
            external_ai_worker_adapter: "reference_heuristic_v1",
            external_ai_policy_class: "HeuristicPolicy",
            external_ai_decision_style: "contract_heuristic",
          },
        },
      },
    ]);

    expect(stage.promptSummary).toContain("시간 초과 기본 처리");
    expect(stage.promptSummary).toContain("prod-bot-1");
    expect(stage.currentBeatKind).toBe("system");
    expect(stage.focusTileIndex).toBe(9);
    expect(stage.externalAiWorkerId).toBe("prod-bot-1");
    expect(stage.externalAiFailureCode).toBe("external_ai_timeout");
    expect(stage.externalAiFallbackMode).toBe("local_ai");
    expect(stage.externalAiAttemptCount).toBe(3);
    expect(stage.externalAiAttemptLimit).toBe(4);
    expect(stage.externalAiReadyState).toBe("not_ready");
    expect(stage.externalAiPolicyMode).toBe("heuristic_v3_gpt");
    expect(stage.externalAiWorkerAdapter).toBe("reference_heuristic_v1");
    expect(stage.externalAiPolicyClass).toBe("HeuristicPolicy");
    expect(stage.externalAiDecisionStyle).toBe("contract_heuristic");
    expect(stage.externalAiResolutionStatus).toBe("-");
    expect(stage.progressTrail).toContain("시간 초과 기본 처리");
    expect(stage.promptSummary).toContain("시도 3/4");
  });

  it("captures external worker success status from decision_resolved events", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 330,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 10,
          acting_player_id: 2,
          character: "Scholar",
        },
      },
      {
        type: "event",
        seq: 331,
        session_id: "s1",
        payload: {
          event_type: "decision_resolved",
          round_index: 4,
          turn_index: 10,
          player_id: 2,
          resolution: "accepted",
          choice_id: "coins",
          public_context: {
            external_ai_worker_id: "prod-bot-1",
            external_ai_resolution_status: "resolved_by_worker",
            external_ai_attempt_count: 1,
            external_ai_attempt_limit: 2,
            external_ai_ready_state: "ready",
            external_ai_policy_mode: "heuristic_v3_gpt",
            external_ai_worker_adapter: "priority_score_v1",
            external_ai_policy_class: "PriorityScoredPolicy",
            external_ai_decision_style: "priority_scored_contract",
          },
        },
      },
    ]);

    expect(stage.externalAiWorkerId).toBe("prod-bot-1");
    expect(stage.externalAiResolutionStatus).toBe("resolved_by_worker");
    expect(stage.externalAiAttemptCount).toBe(1);
    expect(stage.externalAiAttemptLimit).toBe(2);
    expect(stage.externalAiReadyState).toBe("ready");
    expect(stage.externalAiPolicyMode).toBe("heuristic_v3_gpt");
    expect(stage.externalAiWorkerAdapter).toBe("priority_score_v1");
    expect(stage.externalAiPolicyClass).toBe("PriorityScoredPolicy");
    expect(stage.externalAiDecisionStyle).toBe("priority_scored_contract");
    expect(stage.promptSummary).toContain("외부 worker 처리 완료");
    expect(stage.promptSummary).toContain("상태 준비됨");
    expect(stage.promptSummary).toContain("어댑터 priority_score_v1");
    expect(stage.promptSummary).toContain("클래스 PriorityScoredPolicy");
  });

  it("keeps canonical request context visible inside the current turn stage decision beat", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 340,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 12,
          acting_player_id: 2,
          character: "Scholar",
        },
      },
      {
        type: "event",
        seq: 341,
        session_id: "s1",
        payload: {
          event_type: "decision_requested",
          round_index: 4,
          turn_index: 12,
          player_id: 2,
          request_type: "purchase_tile",
          legal_choices: [{ choice_id: "yes" }, { choice_id: "no" }],
          public_context: {
            tile_index: 7,
            external_ai_worker_id: "prod-bot-1",
            external_ai_resolution_status: "resolved_by_worker",
          },
        },
      },
    ]);

    expect(stage.currentBeatKind).toBe("decision");
    expect(stage.currentBeatDetail).toContain("8번 칸");
    expect(stage.currentBeatDetail).toContain("선택지 2개");
    expect(stage.currentBeatDetail).toContain("prod-bot-1");
  });

  it("includes landing tile position in landing summaries when available", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 400,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 5,
          turn_index: 2,
          acting_player_id: 1,
          character: "Builder",
        },
      },
      {
        type: "event",
        seq: 401,
        session_id: "s1",
        payload: {
          event_type: "landing_resolved",
          round_index: 5,
          turn_index: 2,
          acting_player_id: 1,
          position: 11,
          result_type: "PURCHASE",
        },
      },
    ]);

    expect(stage.landingSummary).toContain("12");
    expect(stage.focusTileIndex).toBe(11);
  });

  it("keeps fortune reveal and fortune resolution as separate turn-stage fields", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 500,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 6,
          turn_index: 4,
          acting_player_id: 3,
          character: "Messenger",
        },
      },
      {
        type: "event",
        seq: 501,
        session_id: "s1",
        payload: {
          event_type: "fortune_drawn",
          round_index: 6,
          turn_index: 4,
          acting_player_id: 3,
          card_name: "Blessed Dice",
        },
      },
      {
        type: "event",
        seq: 502,
        session_id: "s1",
        payload: {
          event_type: "fortune_resolved",
          round_index: 6,
          turn_index: 4,
          acting_player_id: 3,
          summary: "Dice +2",
        },
      },
    ]);

    expect(stage.fortuneDrawSummary).toContain("Blessed Dice");
    expect(stage.fortuneResolvedSummary).toContain("Dice +2");
    expect(stage.fortuneSummary).toContain("Dice +2");
  });

  it("keeps turn end snapshot as the closing beat of the current turn", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 510,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 7,
          turn_index: 1,
          acting_player_id: 2,
          character: "Courier",
        },
      },
      {
        type: "event",
        seq: 511,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          round_index: 7,
          turn_index: 1,
          acting_player_id: 2,
          from_tile_index: 4,
          to_tile_index: 9,
        },
      },
      {
        type: "event",
        seq: 512,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          round_index: 7,
          turn_index: 1,
          acting_player_id: 2,
          summary: "turn closed",
        },
      },
    ]);

    expect(stage.turnEndSummary).toContain("turn closed");
    expect(stage.currentBeatLabel).not.toBe("Turn start");
    expect(stage.progressTrail.at(-1)).toBe(stage.currentBeatLabel);
  });

  it("surfaces actor resource status from lap reward prompts", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 520,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 7,
          turn_index: 2,
          acting_player_id: 1,
          character: "Scholar",
        },
      },
      {
        type: "prompt",
        seq: 521,
        session_id: "s1",
        payload: {
          request_id: "req_lap_1",
          request_type: "lap_reward",
          player_id: 1,
          public_context: {
            budget: 10,
            player_cash: 18,
            player_shards: 4,
            player_hand_coins: 2,
            player_placed_coins: 3,
            player_total_score: 5,
            player_owned_tile_count: 6,
          },
        },
      },
    ]);

    expect(stage.actorCash).toBe(18);
    expect(stage.actorShards).toBe(4);
    expect(stage.actorHandCoins).toBe(2);
    expect(stage.actorPlacedCoins).toBe(3);
    expect(stage.actorTotalScore).toBe(5);
    expect(stage.actorOwnedTileCount).toBe(6);
  });

  it("derives trick tile target focus from canonical legal choices", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 530,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 7,
          turn_index: 3,
          acting_player_id: 3,
          character: "박수",
        },
      },
      {
        type: "prompt",
        seq: 531,
        session_id: "s1",
        payload: {
          request_id: "req_trick_tile_1",
          request_type: "trick_tile_target",
          player_id: 3,
          legal_choices: [
            { choice_id: "4", label: "5번 칸", value: { tile_index: 4 } },
            { choice_id: "7", label: "8번 칸", value: { tile_index: 7 } },
          ],
          public_context: {
            card_name: "재뿌리기",
            candidate_count: 2,
          },
        },
      },
    ]);

    expect(stage.focusTileIndex).toBe(4);
    expect(stage.focusTileIndices).toEqual([4, 7]);
    expect(stage.currentBeatKind).toBe("decision");
  });

  it("prefers backend-projected turn stage beat and progress when view_state turn_stage is present", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 600,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 8,
          turn_index: 4,
          acting_player_id: 2,
          character: "교리 연구관",
        },
      },
      {
        type: "event",
        seq: 601,
        session_id: "s1",
        payload: {
          event_type: "player_move",
          round_index: 8,
          turn_index: 4,
          acting_player_id: 2,
          from_tile_index: 4,
          to_tile_index: 9,
        },
      },
      {
        type: "event",
        seq: 602,
        session_id: "s1",
        payload: {
          event_type: "turn_end_snapshot",
          view_state: {
            turn_stage: {
              turn_start_seq: 600,
              actor_player_id: 3,
              round_index: 9,
              turn_index: 1,
              character: "-",
              weather_name: "긴급 피난",
              weather_effect: "모든 짐 제거 비용이 2배가 됩니다.",
              current_beat_kind: "decision",
              current_beat_event_code: "prompt_active",
              current_beat_request_type: "draft_card",
              current_beat_seq: 603,
              focus_tile_index: null,
              focus_tile_indices: [],
              prompt_request_type: "draft_card",
              external_ai_worker_id: "-",
              external_ai_failure_code: "-",
              external_ai_fallback_mode: "-",
              external_ai_resolution_status: "-",
              external_ai_attempt_count: null,
              external_ai_attempt_limit: null,
              external_ai_ready_state: "-",
              external_ai_policy_mode: "-",
              external_ai_worker_adapter: "-",
              external_ai_policy_class: "-",
              external_ai_decision_style: "-",
              actor_cash: null,
              actor_shards: null,
              actor_hand_coins: null,
              actor_placed_coins: null,
              actor_total_score: null,
              actor_owned_tile_count: null,
              progress_codes: ["turn_start", "prompt_active"],
            },
          },
        },
      },
      {
        type: "prompt",
        seq: 603,
        session_id: "s1",
        payload: {
          request_id: "req_draft_backend",
          request_type: "draft_card",
          player_id: 3,
          public_context: {
            round_index: 9,
            turn_index: 1,
          },
        },
      },
    ]);

    expect(stage.actorPlayerId).toBe(3);
    expect(stage.round).toBe(9);
    expect(stage.turn).toBe(1);
    expect(stage.currentBeatKind).toBe("decision");
    expect(stage.currentBeatLabel).toBe("드래프트 인물 선택");
    expect(stage.progressTrail).toEqual(["턴 시작", "드래프트 인물 선택"]);
  });

  it("prefers backend-projected turn stage focus and external ai status", () => {
    const stage = selectTurnStage([
      {
        type: "event",
        seq: 700,
        session_id: "s1",
        payload: {
          event_type: "turn_start",
          round_index: 4,
          turn_index: 11,
          acting_player_id: 2,
          character: "Scholar",
        },
      },
      {
        type: "event",
        seq: 701,
        session_id: "s1",
        payload: {
          event_type: "decision_timeout_fallback",
          round_index: 4,
          turn_index: 11,
          player_id: 2,
          request_type: "purchase_tile",
          summary: "defaulted to local AI",
          public_context: {
            tile_index: 9,
            external_ai_worker_id: "prod-bot-1",
          },
          view_state: {
            turn_stage: {
              turn_start_seq: 700,
              actor_player_id: 2,
              round_index: 4,
              turn_index: 11,
              character: "Scholar",
              weather_name: "-",
              weather_effect: "-",
              current_beat_kind: "decision",
              current_beat_event_code: "decision_timeout_fallback",
              current_beat_request_type: "purchase_tile",
              current_beat_seq: 701,
              focus_tile_index: 9,
              focus_tile_indices: [9],
              prompt_request_type: "purchase_tile",
              external_ai_worker_id: "prod-bot-1",
              external_ai_failure_code: "external_ai_timeout",
              external_ai_fallback_mode: "local_ai",
              external_ai_resolution_status: "-",
              external_ai_attempt_count: 3,
              external_ai_attempt_limit: 4,
              external_ai_ready_state: "not_ready",
              external_ai_policy_mode: "heuristic_v3_gpt",
              external_ai_worker_adapter: "priority_score_v1",
              external_ai_policy_class: "PriorityScoredPolicy",
              external_ai_decision_style: "priority_scored_contract",
              actor_cash: null,
              actor_shards: null,
              actor_hand_coins: null,
              actor_placed_coins: null,
              actor_total_score: null,
              actor_owned_tile_count: null,
              progress_codes: ["turn_start", "decision_timeout_fallback"],
            },
          },
        },
      },
    ]);

    expect(stage.focusTileIndex).toBe(9);
    expect(stage.focusTileIndices).toEqual([9]);
    expect(stage.externalAiWorkerId).toBe("prod-bot-1");
    expect(stage.externalAiFailureCode).toBe("external_ai_timeout");
    expect(stage.currentBeatLabel).toBe("시간 초과 기본 처리");
  });
});
