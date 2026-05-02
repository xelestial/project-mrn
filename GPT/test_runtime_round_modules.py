from __future__ import annotations

import random

from ai_policy import HeuristicPolicy
import pytest

from config import GameConfig
from engine import GameEngine
from runtime_modules.round_modules import (
    assert_round_end_card_flip_ready,
    build_player_turn_module,
    build_round_frame,
)


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
