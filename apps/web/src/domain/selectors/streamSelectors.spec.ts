import { describe, expect, it } from "vitest";
import type { InboundMessage, ViewCommitPayload } from "../../core/contracts/stream";
import {
  selectActiveCharacterSlots,
  selectCoreActionFeed,
  selectCriticalAlerts,
  selectCurrentActorPlayerId,
  selectCurrentRoundRevealItems,
  selectCurrentTurnRevealItems,
  selectDerivedPlayers,
  selectLastMove,
  selectLatestManifest,
  selectLatestSnapshot,
  selectLivePlayers,
  selectLiveSnapshot,
  selectMarkTargetCharacterSlots,
  selectMarkerOrderedPlayers,
  selectRuntimeProjection,
  selectSituation,
  selectTheaterFeed,
  selectTimeline,
  selectTurnHistory,
  selectTurnStage,
} from "./streamSelectors";

function viewCommit(commitSeq: number, viewState: Record<string, unknown>): InboundMessage {
  const payload: ViewCommitPayload = {
    schema_version: 1,
    commit_seq: commitSeq,
    source_event_seq: commitSeq + 100,
    viewer: { role: "spectator" },
    runtime: {
      status: "running",
      round_index: 3,
      turn_index: 1,
      active_frame_id: "turn:3:p2",
      active_module_id: "mod:turn:3:p2:move",
      active_module_type: "MapMoveModule",
      module_path: ["RoundModule", "TurnModule", "MapMoveModule"],
    },
    view_state: viewState,
  };
  return {
    type: "view_commit",
    seq: commitSeq + 1000,
    session_id: "s1",
    server_time_ms: commitSeq + 2000,
    payload,
  };
}

const authoritativeViewState: Record<string, unknown> = {
  runtime: {
    runner_kind: "module",
    latest_module_path: ["RoundModule", "TurnModule", "MapMoveModule"],
    round_stage: "turns",
    turn_stage: "movement",
    active_sequence: "",
    active_prompt_request_id: "req_move",
    active_frame_id: "turn:3:p2",
    active_frame_type: "turn",
    active_module_id: "mod:turn:3:p2:move",
    active_module_type: "MapMoveModule",
    active_module_status: "suspended",
    active_module_cursor: "movement:await_choice",
    active_module_idempotency_key: "idem_move",
    draft_active: false,
    trick_sequence_active: false,
    card_flip_legal: false,
  },
  turn_stage: {
    turn_start_seq: 31,
    actor_player_id: 2,
    round_index: 3,
    turn_index: 1,
    character: "산적",
    weather_name: "안개",
    weather_effect: "이동 후 효과가 제한됩니다.",
    current_beat_kind: "decision",
    current_beat_event_code: "prompt_active",
    current_beat_request_type: "movement",
    current_beat_seq: 44,
    focus_tile_index: 8,
    focus_tile_indices: [8, 9],
    prompt_request_type: "movement",
    actor_cash: 21,
    actor_shards: 5,
    actor_hand_coins: 4,
    actor_placed_coins: 6,
    actor_total_score: 10,
    actor_owned_tile_count: 2,
    progress_codes: ["turn_start", "dice_roll", "prompt_active"],
  },
  board: {
    marker_owner_player_id: 2,
    marker_draft_direction: "clockwise",
    f_value: 7,
    last_move: {
      player_id: 2,
      from_tile_index: 4,
      to_tile_index: 8,
      path_tile_indices: [5, 6, 7, 8],
    },
    tiles: [
      {
        tile_index: 4,
        tile_kind: "T2",
        zone_color: "blue",
        purchase_cost: 4,
        rent_cost: 2,
        score_coin_count: 1,
        owner_player_id: 1,
        pawn_player_ids: [1],
      },
      {
        tile_index: 8,
        tile_kind: "T3",
        zone_color: "red",
        purchase_cost: 6,
        rent_cost: 3,
        score_coin_count: 2,
        owner_player_id: 2,
        pawn_player_ids: [2],
      },
    ],
  },
  players: {
    ordered_player_ids: [2, 1],
    items: [
      {
        player_id: 1,
        display_name: "P1",
        current_character_face: "박수",
        cash: 10,
        shards: 2,
        hand_coins: 3,
        placed_coins: 4,
        placed_score_coins: 4,
        total_score: 7,
        score: 7,
        owned_tile_count: 1,
        trick_count: 2,
        public_tricks: ["장막"],
        hidden_trick_count: 1,
        priority_slot: 3,
        is_marker_owner: false,
        is_current_actor: false,
        position: 4,
      },
      {
        player_id: 2,
        display_name: "P2",
        current_character_face: "산적",
        cash: 20,
        shards: 4,
        hand_coins: 2,
        placed_coins: 5,
        placed_score_coins: 5,
        total_score: 7,
        score: 7,
        owned_tile_count: 2,
        trick_count: 1,
        public_tricks: [],
        hidden_trick_count: 1,
        priority_slot: 5,
        is_marker_owner: true,
        is_current_actor: true,
        position: 8,
      },
    ],
  },
  player_cards: {
    items: [
      {
        player_id: 1,
        character: "박수",
        priority_slot: 3,
        turn_order_rank: 2,
        reveal_state: "revealed",
        is_current_actor: false,
      },
      {
        player_id: 2,
        character: "산적",
        priority_slot: 5,
        turn_order_rank: 1,
        reveal_state: "revealed",
        is_current_actor: true,
      },
    ],
  },
  active_slots: {
    items: [
      {
        slot: 3,
        player_id: 1,
        label: "P1",
        character: "박수",
        inactive_character: "광대",
        is_current_actor: false,
      },
      {
        slot: 5,
        player_id: 2,
        label: "P2",
        character: "산적",
        inactive_character: "어사",
        is_current_actor: true,
      },
    ],
  },
  mark_target: {
    candidates: [
      {
        slot: 3,
        player_id: 1,
        label: "P1",
        character: "박수",
      },
    ],
  },
  scene: {
    situation: {
      actor_player_id: 2,
      round_index: 3,
      turn_index: 1,
      headline_seq: 40,
      headline_message_type: "event",
      headline_event_code: "player_move",
      weather_name: "안개",
      weather_effect: "이동 후 효과가 제한됩니다.",
    },
    theater_feed: [
      {
        seq: 40,
        message_type: "event",
        event_code: "player_move",
        tone: "move",
        lane: "core",
        actor_player_id: 2,
        round_index: 3,
        turn_index: 1,
      },
    ],
    core_action_feed: [
      {
        seq: 40,
        event_code: "player_move",
        actor_player_id: 2,
        round_index: 3,
        turn_index: 1,
      },
    ],
    timeline: [
      { seq: 40, message_type: "event", event_code: "player_move" },
      { seq: 44, message_type: "prompt", event_code: "movement" },
    ],
    critical_alerts: [
      {
        seq: 50,
        message_type: "event",
        event_code: "decision_timeout_fallback",
        severity: "warning",
      },
    ],
  },
  reveals: {
    items: [
      {
        seq: 40,
        event_code: "player_move",
        label: "이동",
        detail: "P2가 4칸 이동",
        tone: "move",
        focus_tile_index: 8,
        is_interrupt: false,
      },
    ],
  },
  parameter_manifest: {
    manifest_hash: "abcdef123456",
    manifest_version: 2,
    version: "v2",
    source_fingerprints: { rules: "rules-1" },
    board: {
      topology: "ring",
      tiles: [
        { tile_index: 0, tile_kind: "START", zone_color: "white", purchase_cost: 0, rent_cost: 0 },
        { tile_index: 1, tile_kind: "T1", zone_color: "blue", purchase_cost: 2, rent_cost: 1 },
      ],
    },
    seats: { allowed: [1, 2] },
    labels: { title: "MRN" },
    dice: { values: [1, 2, 3], max_cards_per_turn: 2, use_one_card_plus_one_die: true },
    economy: { starting_cash: 10 },
    resources: { starting_shards: 1 },
  },
};

function contradictoryRawEvent(): InboundMessage {
  return {
    type: "event",
    seq: 999,
    session_id: "s1",
    payload: {
      event_type: "turn_end_snapshot",
      round_index: 99,
      turn_index: 99,
      acting_player_id: 1,
      view_state: {
        runtime: {
          runner_kind: "module",
          active_module_type: "RoundEndCardFlipModule",
          card_flip_legal: true,
        },
        turn_stage: {
          actor_player_id: 1,
          round_index: 99,
          turn_index: 99,
          current_beat_event_code: "marker_flip",
        },
        board: {
          marker_owner_player_id: 1,
          f_value: 99,
          tiles: [],
        },
        players: { items: [] },
      },
    },
  };
}

describe("streamSelectors authoritative ViewCommit contract", () => {
  it("ignores raw event/prompt payloads as live state sources", () => {
    const rawMessages: InboundMessage[] = [
      contradictoryRawEvent(),
      {
        type: "prompt",
        seq: 1000,
        session_id: "s1",
        payload: {
          request_id: "raw_prompt",
          request_type: "movement",
          player_id: 1,
          view_state: authoritativeViewState,
        },
      },
    ];

    expect(selectLatestSnapshot(rawMessages)).toBeNull();
    expect(selectLiveSnapshot(rawMessages)).toBeNull();
    expect(selectRuntimeProjection(rawMessages)).toBeNull();
    expect(selectCurrentActorPlayerId(rawMessages)).toBeNull();
    expect(selectDerivedPlayers(rawMessages)).toEqual([]);
    expect(selectActiveCharacterSlots(rawMessages)).toEqual([]);
    expect(selectMarkTargetCharacterSlots(rawMessages, "산적")).toEqual([]);
    expect(selectTimeline(rawMessages)).toEqual([]);
    expect(selectTheaterFeed(rawMessages)).toEqual([]);
    expect(selectCoreActionFeed(rawMessages)).toEqual([]);
    expect(selectCriticalAlerts(rawMessages)).toEqual([]);
    expect(selectLastMove(rawMessages)).toBeNull();
    expect(selectLatestManifest(rawMessages)).toBeNull();
    expect(selectSituation(rawMessages)).toEqual({
      actor: "-",
      round: "-",
      turn: "-",
      eventType: "-",
      weather: "-",
      weatherEffect: "-",
    });
  });

  it("uses a single ViewCommit snapshot for board, player, marker, and turn data", () => {
    const messages = [viewCommit(7, authoritativeViewState), contradictoryRawEvent()];

    expect(selectRuntimeProjection(messages)).toMatchObject({
      runnerKind: "module",
      turnStage: "movement",
      activeModuleType: "MapMoveModule",
      activeModuleCursor: "movement:await_choice",
      cardFlipLegal: false,
    });
    expect(selectTurnStage(messages)).toMatchObject({
      actorPlayerId: 2,
      round: 3,
      turn: 1,
      character: "산적",
      weatherName: "안개",
      promptRequestType: "movement",
      actorCash: 21,
      actorTotalScore: 10,
    });
    expect(selectCurrentActorPlayerId(messages)).toBe(2);

    const snapshot = selectLatestSnapshot(messages);
    expect(snapshot).toMatchObject({
      round: 3,
      turn: 1,
      markerOwnerPlayerId: 2,
      markerDraftDirection: "clockwise",
      fValue: 7,
      currentRoundOrder: [2, 1],
      activeByCard: { 3: "박수", 5: "산적" },
    });
    expect(snapshot?.players.map((player) => [player.playerId, player.character, player.position])).toEqual([
      [1, "박수", 4],
      [2, "산적", 8],
    ]);
    expect(snapshot?.tiles.map((tile) => [tile.tileIndex, tile.ownerPlayerId, tile.pawnPlayerIds])).toEqual([
      [4, 1, [1]],
      [8, 2, [2]],
    ]);
    expect(selectLiveSnapshot(messages)).toEqual(snapshot);
    expect(selectLastMove(messages)).toEqual({
      playerId: 2,
      fromTileIndex: 4,
      toTileIndex: 8,
      pathTileIndices: [5, 6, 7, 8],
    });
  });

  it("uses ViewCommit player surfaces for derived players, slots, and mark targets", () => {
    const messages = [viewCommit(7, authoritativeViewState), contradictoryRawEvent()];

    expect(selectLivePlayers(messages).find((player) => player.playerId === 2)).toMatchObject({
      playerId: 2,
      character: "산적",
      cash: 21,
      shards: 5,
      totalScore: 10,
    });
    expect(selectDerivedPlayers(messages, 2)).toEqual([
      expect.objectContaining({
        playerId: 1,
        currentCharacterFace: "박수",
        prioritySlot: 3,
        isMarkerOwner: false,
        isCurrentActor: false,
        isLocalPlayer: false,
      }),
      expect.objectContaining({
        playerId: 2,
        currentCharacterFace: "산적",
        prioritySlot: 5,
        isMarkerOwner: true,
        isCurrentActor: true,
        isLocalPlayer: true,
      }),
    ]);
    expect(selectActiveCharacterSlots(messages, 2)).toEqual([
      expect.objectContaining({ slot: 3, playerId: 1, character: "박수", isCurrentActor: false }),
      expect.objectContaining({ slot: 5, playerId: 2, character: "산적", isCurrentActor: true, isLocalPlayer: true }),
    ]);
    expect(selectMarkTargetCharacterSlots(messages, "산적")).toEqual([
      { slot: 3, playerId: 1, label: "P1", character: "박수" },
    ]);
    expect(selectMarkerOrderedPlayers(messages, 2).map((player) => player.playerId)).toEqual([2, 1]);
  });

  it("uses ViewCommit scene, reveal, and manifest data without replay projection", () => {
    const messages = [viewCommit(7, authoritativeViewState), contradictoryRawEvent()];

    expect(selectSituation(messages)).toMatchObject({
      actor: "P2",
      round: "3",
      turn: "1",
      weather: "안개",
      weatherEffect: "이동 후 효과가 제한됩니다.",
    });
    expect(selectTimeline(messages).map((item) => item.seq)).toEqual([40, 44]);
    expect(selectTheaterFeed(messages)).toEqual([
      expect.objectContaining({
        seq: 40,
        eventCode: "player_move",
        tone: "move",
        lane: "core",
        actor: "P2",
      }),
    ]);
    expect(selectCoreActionFeed(messages, 2)).toEqual([
      expect.objectContaining({
        seq: 40,
        eventCode: "player_move",
        round: 3,
        turn: 1,
        isLocalActor: true,
      }),
    ]);
    expect(selectCriticalAlerts(messages)).toEqual([
      expect.objectContaining({
        seq: 50,
        severity: "warning",
      }),
    ]);
    expect(selectCurrentTurnRevealItems(messages)).toEqual([
      {
        seq: 40,
        eventCode: "player_move",
        label: "이동",
        detail: "P2가 4칸 이동",
        tone: "move",
        focusTileIndex: 8,
        isInterrupt: false,
      },
    ]);
    expect(selectCurrentRoundRevealItems(messages)).toEqual(selectCurrentTurnRevealItems(messages));
    expect(selectLatestManifest(messages)).toMatchObject({
      manifestHash: "abcdef123456",
      manifestVersion: 2,
      version: "v2",
      sourceFingerprints: { rules: "rules-1" },
      boardTopology: "ring",
      seatAllowed: [1, 2],
      dice: { values: [1, 2, 3], maxCardsPerTurn: 2, useOneCardPlusOneDie: true },
      economy: { startingCash: 10 },
      resources: { startingShards: 1 },
    });
  });

  it("renders unresolved mark outcomes in the current reveal layer", () => {
    const viewState = JSON.parse(JSON.stringify(authoritativeViewState)) as Record<string, unknown>;
    viewState["reveals"] = {
      items: [
        {
          seq: 81,
          event_code: "mark_target_missing",
          label: "지목 대상 불일치",
          detail: "P4 / 지목 대상 건설업자을(를) 현재 차례 순서에서 찾지 못함",
          tone: "effect",
          focus_tile_index: null,
          is_interrupt: false,
        },
        {
          seq: 82,
          event_code: "mark_blocked",
          label: "지목 차단",
          detail: "P4 / P3 (중매꾼) 지목이 공개 상태라 차단됨",
          tone: "effect",
          focus_tile_index: null,
          is_interrupt: false,
        },
      ],
    };

    expect(selectCurrentTurnRevealItems([viewCommit(14, viewState)])).toEqual([
      {
        seq: 81,
        eventCode: "mark_target_missing",
        label: "지목 대상 불일치",
        detail: "P4 / 지목 대상 건설업자을(를) 현재 차례 순서에서 찾지 못함",
        tone: "effect",
        focusTileIndex: null,
        isInterrupt: false,
      },
      {
        seq: 82,
        eventCode: "mark_blocked",
        label: "지목 차단",
        detail: "P4 / P3 (중매꾼) 지목이 공개 상태라 차단됨",
        tone: "effect",
        focusTileIndex: null,
        isInterrupt: false,
      },
    ]);
  });

  it("projects turn history tabs and local relevance from ViewCommit only", () => {
    const viewState = JSON.parse(JSON.stringify(authoritativeViewState)) as Record<string, unknown>;
    viewState["turn_history"] = {
      current_key: "r1:t4",
      turns: [
        {
          key: "r1:t3",
          round_index: 1,
          turn_index: 3,
          actor_player_id: 2,
          event_count: 4,
          important_count: 2,
          events: [
            {
              seq: 71,
              event_code: "rent_paid",
              payload: {
                event_type: "rent_paid",
                round_index: 1,
                turn_index: 3,
                payer_player_id: 2,
                owner_player_id: 1,
                final_amount: 3,
                tile_index: 4,
              },
              tone: "economy",
              scope: "player",
              relevance: "public",
              participants: { payer_player_id: 2, owner_player_id: 1 },
              focus_tile_indices: [4],
              resource_delta: { cash: -3 },
              end_time_delta: null,
            },
            {
              seq: 72,
              event_code: "lap_reward_chosen",
              payload: {
                event_type: "lap_reward_chosen",
                round_index: 1,
                turn_index: 3,
                acting_player_id: 2,
                amount: { cash: 2, shards: 1 },
              },
              tone: "economy",
              relevance: "important",
              participants: { actor_player_id: 2 },
              focus_tile_indices: [],
              resource_delta: { cash: 2, shards: 1 },
              end_time_delta: null,
            },
          ],
        },
        {
          key: "r1:t4",
          round_index: 1,
          turn_index: 4,
          actor_player_id: 1,
          event_count: 3,
          important_count: 2,
          events: [
            {
              seq: 81,
              event_code: "mark_resolved",
              payload: {
                event_type: "mark_resolved",
                round_index: 1,
                turn_index: 4,
                source_player_id: 1,
                target_player_id: 2,
              },
              tone: "system",
              relevance: "public",
              participants: { source_player_id: 1, target_player_id: 2 },
              focus_tile_indices: [],
              resource_delta: null,
              end_time_delta: null,
            },
            {
              seq: 82,
              event_code: "fortune_move",
              payload: {
                event_type: "fortune_move",
                round_index: 1,
                turn_index: 4,
                acting_player_id: 2,
                from_tile_index: 2,
                to_tile_index: 6,
              },
              tone: "move",
              relevance: "important",
              participants: { actor_player_id: 2 },
              focus_tile_indices: [2, 6],
              resource_delta: null,
              end_time_delta: null,
            },
            {
              seq: 83,
              event_code: "f_value_change",
              payload: {
                event_type: "f_value_change",
                round_index: 1,
                turn_index: 4,
                before: 9,
                delta: 1,
                after: 10,
              },
              tone: "system",
              scope: "common",
              relevance: "important",
              participants: {},
              focus_tile_indices: [],
              resource_delta: null,
              end_time_delta: { before: 9, delta: 1, after: 10 },
            },
          ],
        },
      ],
    };

    const history = selectTurnHistory([viewCommit(8, viewState), contradictoryRawEvent()], 1);

    expect(history.currentKey).toBe("r1:t4");
    expect(history.turns.map((turn) => [turn.key, turn.label, turn.importantCount])).toEqual([
      ["r1:t3", "R1-T3", 2],
      ["r1:t4", "R1-T4", 2],
    ]);
    expect(history.turns[0].events[0]).toMatchObject({
      seq: 71,
      eventCode: "rent_paid",
      label: "렌트 지불",
      scope: "player",
      relevance: "mine-critical",
      participantPlayerIds: [1, 2],
      focusTileIndices: [4],
    });
    expect(history.turns[1].events[0]).toMatchObject({
      eventCode: "mark_resolved",
      relevance: "mine-critical",
      participantPlayerIds: [1, 2],
    });
    expect(history.turns[1].events[1]).toMatchObject({
      eventCode: "fortune_move",
      label: "운수 이동",
      relevance: "important",
      focusTileIndices: [2, 6],
    });
    expect(history.turns[1].events[2]).toMatchObject({
      eventCode: "f_value_change",
      label: "종료시간 변경",
      scope: "common",
      relevance: "important",
      detail: "종료시간 9 + (1) = 10",
      endTimeDelta: { before: 9, delta: 1, after: 10 },
    });
  });

  it("stacks reveal-only landing results into the matching turn history", () => {
    const viewState = JSON.parse(JSON.stringify(authoritativeViewState)) as Record<string, unknown>;
    viewState["turn_history"] = {
      current_key: "r2:t6",
      turns: [
        {
          key: "r2:t6",
          round_index: 2,
          turn_index: 6,
          actor_player_id: 4,
          event_count: 2,
          important_count: 1,
          events: [
            {
              seq: 100,
              event_code: "turn_start",
              payload: {
                event_type: "turn_start",
                round_index: 2,
                turn_index: 6,
                acting_player_id: 4,
              },
              tone: "system",
              relevance: "public",
              participants: { actor_player_id: 4 },
              focus_tile_indices: [],
              resource_delta: null,
              end_time_delta: null,
            },
            {
              seq: 101,
              event_code: "action_move",
              payload: {
                event_type: "action_move",
                round_index: 2,
                turn_index: 6,
                acting_player_id: 4,
                from_tile_index: 0,
                to_tile_index: 5,
                path: [1, 2, 3, 4, 5],
              },
              tone: "move",
              relevance: "important",
              participants: { actor_player_id: 4 },
              focus_tile_indices: [5],
              resource_delta: null,
              end_time_delta: null,
            },
          ],
        },
      ],
    };
    viewState["reveals"] = {
      items: [
        {
          seq: 102,
          event_code: "landing_resolved",
          label: "도착 결과",
          tone: "effect",
          focus_tile_index: 5,
          is_interrupt: false,
        },
      ],
    };

    const history = selectTurnHistory([viewCommit(12, viewState)], 1);
    const turn = history.latestTurn;

    expect(turn?.events.map((event) => event.eventCode)).toEqual(["turn_start", "action_move", "landing_resolved"]);
    expect(turn?.eventCount).toBe(3);
    expect(turn?.importantCount).toBe(2);
    expect(turn?.events[2]).toMatchObject({
      seq: 102,
      eventCode: "landing_resolved",
      label: "도착 결과",
      detail: "도착 결과 / 6번 칸",
      relevance: "important",
      focusTileIndices: [5],
    });
  });

  it("renders turn-start character names and mark attempts in turn history", () => {
    const viewState = JSON.parse(JSON.stringify(authoritativeViewState)) as Record<string, unknown>;
    viewState["turn_history"] = {
      current_key: "r1:t3",
      turns: [
        {
          key: "r1:t3",
          round_index: 1,
          turn_index: 3,
          actor_player_id: 4,
          event_count: 3,
          important_count: 2,
          events: [
            {
              seq: 10,
              event_code: "turn_start",
              payload: {
                event_type: "turn_start",
                round_index: 1,
                turn_index: 3,
                acting_player_id: 4,
                character: "어사",
              },
              tone: "system",
              relevance: "public",
              participants: { actor_player_id: 4 },
              focus_tile_indices: [],
              resource_delta: null,
              end_time_delta: null,
            },
            {
              seq: 11,
              event_code: "mark_queued",
              payload: {
                event_type: "mark_queued",
                round_index: 1,
                turn_index: 3,
                source_player_id: 4,
                target_player_id: 2,
                target_character: "교리 연구관",
                effect_type: "baksu_transfer",
              },
              tone: "critical",
              relevance: "important",
              participants: { source: 4, target: 2 },
              focus_tile_indices: [],
              resource_delta: null,
              end_time_delta: null,
            },
            {
              seq: 12,
              event_code: "mark_target_missing",
              payload: {
                event_type: "mark_target_missing",
                round_index: 1,
                turn_index: 3,
                source_player_id: 4,
                target_character: "건설업자",
              },
              tone: "critical",
              relevance: "important",
              participants: { source: 4 },
              focus_tile_indices: [],
              resource_delta: null,
              end_time_delta: null,
            },
          ],
        },
      ],
    };

    const history = selectTurnHistory([viewCommit(13, viewState)], 4);

    expect(history.latestTurn?.events[0]).toMatchObject({
      eventCode: "turn_start",
      detail: "P4 / 어사 / 턴 시작",
    });
    expect(history.latestTurn?.events[1]).toMatchObject({
      eventCode: "mark_queued",
      detail: "[박수] P4 -> P2 / 교리 연구관 / 대상 턴 시작 최우선 처리 예약",
      relevance: "mine-critical",
    });
    expect(history.latestTurn?.events[2]).toMatchObject({
      eventCode: "mark_target_missing",
      detail: "P4 / 지목 대상 건설업자을(를) 현재 차례 순서에서 찾지 못함",
      relevance: "mine-critical",
    });
  });
});
