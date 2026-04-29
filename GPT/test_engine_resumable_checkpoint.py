from __future__ import annotations

import random

from ai_policy import HeuristicPolicy
from config import CellKind, GameConfig
from engine import GameEngine
from state import ActionEnvelope, GameState
from viewer.stream import VisEventStream


def _run_standard_move_action_path(
    engine: GameEngine,
    state: GameState,
    player_index: int,
    move: int,
    movement_meta: dict,
) -> None:
    player = state.players[player_index]
    engine._enqueue_standard_move_action(
        state,
        player,
        move,
        dict(movement_meta),
        emit_move_event=False,
    )
    while state.pending_actions:
        engine.run_next_transition(state)


def _assert_core_move_state_matches(action_state: GameState, legacy_state: GameState, player_index: int = 0) -> None:
    action_player = action_state.players[player_index]
    legacy_player = legacy_state.players[player_index]
    assert action_player.position == legacy_player.position
    assert action_player.total_steps == legacy_player.total_steps
    assert action_player.cash == legacy_player.cash
    assert action_player.shards == legacy_player.shards
    assert action_player.hand_coins == legacy_player.hand_coins
    assert action_player.trick_encounter_boost_this_turn == legacy_player.trick_encounter_boost_this_turn
    assert action_state.f_value == legacy_state.f_value


def _last_turn_log(engine: GameEngine) -> dict:
    return next(row for row in reversed(engine._action_log) if row.get("event") == "turn")


def test_engine_run_accepts_hydrated_checkpoint_state() -> None:
    config = GameConfig(player_count=2)
    state = GameState.create(config)
    state.rounds_completed = 1
    state.turn_index = 0
    state.current_round_order = []
    state.winner_ids = [0]
    state.end_reason = "checkpoint_test"
    restored = GameState.from_checkpoint_payload(config, state.to_checkpoint_payload())
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(1))

    result = engine.run(initial_state=restored)

    assert result.total_turns == 0
    assert result.alive_count == 2


def test_engine_next_transition_commits_one_turn_boundary() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(2))
    state = engine.prepare_run()

    step = engine.run_next_transition(state)
    payload = state.to_checkpoint_payload()

    assert step["status"] in {"committed", "finished"}
    assert payload["schema_version"] == 1
    assert payload["turn_index"] >= 1 or step["status"] == "finished"
    assert len(payload["players"]) == 2


def test_engine_next_transition_drains_one_pending_action_before_turn() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(3))
    state = engine.prepare_run()
    player = state.players[0]
    player.position = 1
    target = state.first_tile_position(kinds=[CellKind.F1])
    before_turn = state.turn_index
    before_f = state.f_value
    state.pending_actions = [
        ActionEnvelope(
            action_id="act_move_to_f1",
            type="apply_move",
            actor_player_id=0,
            source="test",
            payload={
                "target_pos": target,
                "lap_credit": False,
                "schedule_arrival": True,
                "emit_move_event": False,
                "trigger": "test_action",
            },
        )
    ]

    first = engine.run_next_transition(state)

    assert first["status"] == "committed"
    assert first["action_type"] == "apply_move"
    assert state.turn_index == before_turn
    assert player.position == target
    assert state.f_value == before_f
    assert len(state.pending_actions) == 1
    assert state.pending_actions[0].type == "resolve_arrival"

    second = engine.run_next_transition(state)

    assert second["status"] == "committed"
    assert second["action_type"] == "resolve_arrival"
    assert state.turn_index == before_turn
    assert state.f_value > before_f
    assert state.pending_actions == []


def test_engine_queued_step_move_separates_lap_reward_from_arrival() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(4))
    state = engine.prepare_run()
    player = state.players[0]
    player.position = len(state.board) - 1
    start_cash = player.cash
    start_shards = player.shards
    start_hand_coins = player.hand_coins
    before_f = state.f_value
    state.pending_actions = [
        ActionEnvelope(
            action_id="act_step_to_f1",
            type="apply_move",
            actor_player_id=0,
            source="test_step",
            payload={
                "move_value": 1,
                "lap_credit": True,
                "schedule_arrival": True,
                "emit_move_event": False,
                "trigger": "test_step_move",
            },
        )
    ]

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    assert player.position == 0
    assert player.total_steps == 1
    assert (player.cash, player.shards, player.hand_coins) != (start_cash, start_shards, start_hand_coins)
    assert state.f_value == before_f
    assert len(state.pending_actions) == 1
    assert state.pending_actions[0].type == "resolve_arrival"

    second = engine.run_next_transition(state)

    assert second["action_type"] == "resolve_arrival"
    assert state.pending_actions == []
    assert state.f_value > before_f


def test_standard_move_action_adapter_matches_simple_advance_player_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_standard", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(5))
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    legacy_player.position = len(legacy_state.board) - 1
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(5))
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = len(action_state.board) - 1
    action = action_engine._enqueue_standard_move_action(
        action_state,
        action_player,
        1,
        dict(movement_meta),
        emit_move_event=False,
    )

    first = action_engine.run_next_transition(action_state)
    second = action_engine.run_next_transition(action_state)

    assert action.type == "apply_move"
    assert first["action_type"] == "apply_move"
    assert second["action_type"] == "resolve_arrival"
    assert action_state.pending_actions == []
    assert action_player.position == legacy_player.position
    assert action_player.total_steps == legacy_player.total_steps
    assert action_player.cash == legacy_player.cash
    assert action_player.shards == legacy_player.shards
    assert action_player.hand_coins == legacy_player.hand_coins
    assert action_state.f_value == legacy_state.f_value


def test_standard_move_action_adapter_preserves_card_movement_meta_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "card_pair_fixed", "formula": "2+3", "used_cards": [2, 3]}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(6))
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    legacy_player.position = 2
    legacy_engine._advance_player(legacy_state, legacy_player, 5, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(6))
    action_state = action_engine.prepare_run()
    action_state.players[0].position = 2
    _run_standard_move_action_path(action_engine, action_state, 0, 5, movement_meta)

    _assert_core_move_state_matches(action_state, legacy_state)


def test_standard_move_action_adapter_matches_obstacle_slowdown_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_obstacle", "formula": "4"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(7))
    legacy_state = legacy_engine.prepare_run()
    legacy_mover = legacy_state.players[1]
    legacy_blocker = legacy_state.players[0]
    legacy_mover.position = 0
    legacy_blocker.position = 2
    legacy_blocker.trick_obstacle_this_round = True
    legacy_engine._advance_player(legacy_state, legacy_mover, 4, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(7))
    action_state = action_engine.prepare_run()
    action_mover = action_state.players[1]
    action_blocker = action_state.players[0]
    action_mover.position = 0
    action_blocker.position = 2
    action_blocker.trick_obstacle_this_round = True
    action = action_engine._enqueue_standard_move_action(
        action_state,
        action_mover,
        4,
        dict(movement_meta),
        emit_move_event=False,
    )
    assert action.payload["obstacle_slowdown"]["effective_move"] == 3
    while action_state.pending_actions:
        action_engine.run_next_transition(action_state)

    _assert_core_move_state_matches(action_state, legacy_state, player_index=1)


def test_standard_move_action_adapter_matches_encounter_boost_result() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_encounter", "formula": "2"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(8))
    legacy_state = legacy_engine.prepare_run()
    legacy_mover = legacy_state.players[0]
    legacy_other = legacy_state.players[1]
    legacy_mover.position = 0
    legacy_mover.trick_encounter_boost_this_turn = True
    legacy_other.position = 1
    legacy_engine._advance_player(legacy_state, legacy_mover, 2, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(8))
    action_state = action_engine.prepare_run()
    action_mover = action_state.players[0]
    action_other = action_state.players[1]
    action_mover.position = 0
    action_mover.trick_encounter_boost_this_turn = True
    action_other.position = 1
    action = action_engine._enqueue_standard_move_action(
        action_state,
        action_mover,
        2,
        dict(movement_meta),
        emit_move_event=False,
    )
    assert action.payload["encounter_bonus"]["met_at"] == 1
    while action_state.pending_actions:
        action_engine.run_next_transition(action_state)

    _assert_core_move_state_matches(action_state, legacy_state)


def test_zone_chain_arrival_queues_followup_move_and_matches_advance_player() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_zone_chain", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(9))
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    chain_pos = legacy_state.first_tile_position(kinds=[CellKind.T3])
    legacy_player.position = (chain_pos - 1) % len(legacy_state.board)
    legacy_player.trick_zone_chain_this_turn = True
    legacy_player.rolled_dice_count_this_turn = 1
    legacy_player.tiles_owned = 1
    legacy_state.tile_owner[chain_pos] = legacy_player.player_id
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(9))
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = (chain_pos - 1) % len(action_state.board)
    action_player.trick_zone_chain_this_turn = True
    action_player.rolled_dice_count_this_turn = 1
    action_player.tiles_owned = 1
    action_state.tile_owner[chain_pos] = action_player.player_id
    action_engine._enqueue_standard_move_action(
        action_state,
        action_player,
        1,
        dict(movement_meta),
        emit_move_event=False,
    )

    first = action_engine.run_next_transition(action_state)
    second = action_engine.run_next_transition(action_state)

    assert first["action_type"] == "apply_move"
    assert second["action_type"] == "resolve_arrival"
    assert action_state.pending_actions
    assert action_state.pending_actions[0].type == "apply_move"
    assert action_state.pending_actions[0].source == "zone_chain"

    while action_state.pending_actions:
        action_engine.run_next_transition(action_state)

    _assert_core_move_state_matches(action_state, legacy_state)


def test_standard_move_action_adapter_emits_action_move_visual_event() -> None:
    config = GameConfig(player_count=2)
    stream = VisEventStream()
    engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(10), event_stream=stream)
    state = engine.prepare_run()
    player = state.players[0]
    player.position = 2
    engine._vis_session_id = "resumable-action-test"
    engine._enqueue_standard_move_action(
        state,
        player,
        3,
        {"mode": "test_visual_action", "formula": "3"},
        emit_move_event=True,
    )

    first = engine.run_next_transition(state)

    assert first["action_type"] == "apply_move"
    movement_events = [event for event in stream.events if event.event_type in {"player_move", "action_move"}]
    assert [event.event_type for event in movement_events] == ["action_move"]
    event = movement_events[0]
    assert event.payload["from_tile_index"] == 2
    assert event.payload["to_tile_index"] == 5
    assert event.payload["movement_source"] == "test_visual_action"
    assert event.payload["path"] == [3, 4, 5]


def test_standard_move_action_adapter_emits_turn_log_summary_like_advance_player() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_log", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(10), enable_logging=True)
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    legacy_player.position = len(legacy_state.board) - 1
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))
    legacy_row = _last_turn_log(legacy_engine)

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(10), enable_logging=True)
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = len(action_state.board) - 1
    _run_standard_move_action_path(action_engine, action_state, 0, 1, movement_meta)
    action_row = _last_turn_log(action_engine)

    for key in (
        "event",
        "player",
        "start_pos",
        "end_pos",
        "cell",
        "move",
        "movement",
        "laps_gained",
        "landing",
        "cash_before",
        "cash_after",
        "shards_before",
        "shards_after",
        "f_before",
        "f_after",
        "alive_before",
        "alive_after",
    ):
        assert action_row.get(key) == legacy_row.get(key)


def test_standard_move_action_adapter_emits_chain_turn_log_summary_like_advance_player() -> None:
    config = GameConfig(player_count=2)
    movement_meta = {"mode": "test_chain_log", "formula": "1"}

    legacy_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(11), enable_logging=True)
    legacy_state = legacy_engine.prepare_run()
    legacy_player = legacy_state.players[0]
    chain_pos = legacy_state.first_tile_position(kinds=[CellKind.T3])
    legacy_player.position = (chain_pos - 1) % len(legacy_state.board)
    legacy_player.trick_zone_chain_this_turn = True
    legacy_player.rolled_dice_count_this_turn = 1
    legacy_player.tiles_owned = 1
    legacy_state.tile_owner[chain_pos] = legacy_player.player_id
    legacy_engine._advance_player(legacy_state, legacy_player, 1, dict(movement_meta))
    legacy_row = _last_turn_log(legacy_engine)

    action_engine = GameEngine(config=config, policy=HeuristicPolicy(), rng=random.Random(11), enable_logging=True)
    action_state = action_engine.prepare_run()
    action_player = action_state.players[0]
    action_player.position = (chain_pos - 1) % len(action_state.board)
    action_player.trick_zone_chain_this_turn = True
    action_player.rolled_dice_count_this_turn = 1
    action_player.tiles_owned = 1
    action_state.tile_owner[chain_pos] = action_player.player_id
    _run_standard_move_action_path(action_engine, action_state, 0, 1, movement_meta)
    action_row = _last_turn_log(action_engine)

    for key in (
        "event",
        "player",
        "start_pos",
        "end_pos",
        "cell",
        "move",
        "movement",
        "laps_gained",
        "landing",
        "chain_segments",
        "cash_before",
        "cash_after",
        "shards_before",
        "shards_after",
        "f_before",
        "f_after",
        "alive_before",
        "alive_after",
    ):
        assert action_row.get(key) == legacy_row.get(key)
