from __future__ import annotations

import random

from ai_policy import HeuristicPolicy
from config import GameConfig
from engine import GameEngine
from state import GameState


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
