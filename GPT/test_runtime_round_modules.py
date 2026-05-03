from __future__ import annotations

import random

from ai_policy import HeuristicPolicy
import pytest

from config import GameConfig
from engine import GameEngine
from runtime_modules.runner import ModuleRunner
from runtime_modules.round_modules import (
    assert_round_end_card_flip_ready,
    build_player_turn_module,
    build_round_frame,
)
from runtime_modules.turn_modules import build_turn_frame


def test_round_frame_order_weather_draft_scheduler_turns_flip_cleanup() -> None:
    frame = build_round_frame(1, player_order=[2, 0, 1], completed_setup=False)

    assert [module.module_type for module in frame.module_queue] == [
        "RoundStartModule",
        "WeatherModule",
        "DraftModule",
        "TurnSchedulerModule",
        "PlayerTurnModule",
        "PlayerTurnModule",
        "PlayerTurnModule",
        "RoundEndCardFlipModule",
        "RoundCleanupAndNextRoundModule",
    ]
    assert [module.owner_player_id for module in frame.module_queue if module.module_type == "PlayerTurnModule"] == [2, 0, 1]


def test_draft_module_idempotency_per_round() -> None:
    first = build_round_frame(3, player_order=[0])
    second = build_round_frame(3, player_order=[1])
    draft_one = next(module for module in first.module_queue if module.module_type == "DraftModule")
    draft_two = next(module for module in second.module_queue if module.module_type == "DraftModule")

    assert draft_one.module_id == draft_two.module_id
    assert draft_one.idempotency_key == draft_two.idempotency_key


def test_first_player_turn_module_exists_after_scheduler() -> None:
    frame = build_round_frame(1, player_order=[1, 0], completed_setup=True)

    assert frame.completed_module_ids
    assert frame.module_queue[0].module_type == "PlayerTurnModule"
    assert frame.module_queue[0].owner_player_id == 1


def test_round_end_card_flip_rejects_incomplete_player_turns() -> None:
    frame = build_round_frame(1, player_order=[0], completed_setup=True)

    with pytest.raises(RuntimeError, match="PlayerTurnModule"):
        assert_round_end_card_flip_ready(frame)

    frame.module_queue[0].status = "completed"
    assert_round_end_card_flip_ready(frame)


def test_round_end_card_flip_rejects_active_child_frames_even_if_turn_module_completed() -> None:
    frame = build_round_frame(1, player_order=[0], completed_setup=True)
    frame.module_queue[0].status = "completed"
    turn_frame = build_turn_frame(1, 0, parent_module_id=frame.module_queue[0].module_id)
    turn_frame.status = "suspended"

    with pytest.raises(RuntimeError, match="active child frame"):
        assert_round_end_card_flip_ready(frame, frame_stack=[frame, turn_frame])


def test_module_runner_session_builds_explicit_round_frame_after_setup() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"

    result = engine.run_next_transition(state)

    assert result["runner_kind"] == "module"
    assert state.runtime_checkpoint_schema_version == 3
    assert state.runtime_frame_stack
    round_frame = state.runtime_frame_stack[0]
    assert round_frame.frame_type == "round"
    assert round_frame.module_queue[0].module_type == "PlayerTurnModule"
    assert state.current_round_order


def test_module_player_turn_spawns_turn_frame_without_legacy_take_turn(monkeypatch) -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"

    setup_result = engine.run_next_transition(state)
    assert setup_result["runner_kind"] == "module"
    assert state.runtime_frame_stack

    def forbidden_take_turn(*_args, **_kwargs) -> None:
        raise AssertionError("module runner must not call legacy _take_turn")

    monkeypatch.setattr(engine, "_take_turn", forbidden_take_turn)

    result = engine.run_next_transition(state)

    assert result["runner_kind"] == "module"
    assert result["module_type"] == "PlayerTurnModule"
    assert any(frame.frame_type == "turn" for frame in state.runtime_frame_stack)


def test_suspended_child_sequence_returns_to_next_turn_module() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"

    round_frame = build_round_frame(1, player_order=[0], completed_setup=True)
    player_turn = next(module for module in round_frame.module_queue if module.module_type == "PlayerTurnModule")
    player_turn.status = "suspended"
    player_turn.cursor = "child_turn_running"

    turn_frame = build_turn_frame(1, 0, parent_module_id=player_turn.module_id)
    for module in turn_frame.module_queue:
        if module.module_type in {
            "TurnStartModule",
            "ScheduledStartActionsModule",
            "PendingMarkResolutionModule",
            "CharacterStartModule",
        }:
            module.status = "completed"
            module.cursor = "completed"
        if module.module_type == "TrickWindowModule":
            module.status = "suspended"
            module.cursor = "pending_trick_sequence"
            module.suspension_id = turn_frame.frame_id
            turn_frame.active_module_id = module.module_id
            break
    turn_frame.status = "suspended"
    state.runtime_frame_stack = [round_frame, turn_frame]

    ModuleRunner()._sync_active_player_turn_after_legacy_work(state)

    trick = next(module for module in turn_frame.module_queue if module.module_type == "TrickWindowModule")
    dice = next(module for module in turn_frame.module_queue if module.module_type == "DiceRollModule")
    character = next(module for module in turn_frame.module_queue if module.module_type == "CharacterStartModule")

    assert trick.status == "completed"
    assert trick.cursor == "completed"
    assert dice.status == "queued"
    assert character.status == "completed"
    assert turn_frame.status == "running"
    assert player_turn.status == "suspended"
    assert player_turn.cursor == "child_turn_running"


def test_module_runner_keeps_round_end_as_explicit_module() -> None:
    config = GameConfig(player_count=2)
    engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(7), enable_logging=False)
    engine._reset_run_trackers()
    state = engine.create_initial_state(deal_initial_tricks=False)
    state.runtime_runner_kind = "module"

    round_end_result = None
    for _ in range(80):
        result = engine.run_next_transition(state)
        if result.get("module_type") == "RoundEndCardFlipModule":
            round_end_result = result
            break

    assert round_end_result is not None
    assert state.rounds_completed == 0
    assert state.current_round_order
    frame = state.runtime_frame_stack[0]
    player_turns = [module for module in frame.module_queue if module.module_type == "PlayerTurnModule"]
    assert player_turns
    assert all(module.status == "completed" for module in player_turns)

    cleanup_result = engine.run_next_transition(state)
    assert cleanup_result["module_type"] == "RoundCleanupAndNextRoundModule"
    assert state.rounds_completed == 1
    assert state.current_round_order == []
    assert state.runtime_frame_stack == []


def test_player_turn_module_ids_include_actor_and_ordinal() -> None:
    first = build_player_turn_module(2, 1, 0)
    second = build_player_turn_module(2, 1, 1)

    assert first.module_id != second.module_id
    assert "p1" in first.module_id
    assert first.idempotency_key != second.idempotency_key
