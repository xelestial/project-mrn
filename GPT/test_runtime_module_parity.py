from __future__ import annotations

import random
from typing import Any

from ai_policy import HeuristicPolicy
from config import GameConfig
from engine import GameEngine


def _state_digest(state: Any) -> dict[str, Any]:
    tile_owner_by_index = list(state.tile_owner)
    return {
        "rounds_completed": state.rounds_completed,
        "turn_index": state.turn_index,
        "current_round_order": list(state.current_round_order),
        "marker_owner_id": state.marker_owner_id,
        "marker_draft_clockwise": state.marker_draft_clockwise,
        "current_weather": getattr(state.current_weather, "name", None),
        "f_value": state.f_value,
        "players": [
            {
                "player_id": player.player_id,
                "alive": player.alive,
                "current_character": player.current_character,
                "position": player.position,
                "cash": player.cash,
                "shards": player.shards,
                "turns_taken": player.turns_taken,
                "owned_tiles": [index for index, owner in enumerate(tile_owner_by_index) if owner == player.player_id],
            }
            for player in state.players
        ],
    }


def test_module_runner_matches_legacy_after_initial_round_setup() -> None:
    config = GameConfig(player_count=2)

    legacy_engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(11), enable_logging=False)
    legacy_state = legacy_engine.prepare_run()

    module_engine = GameEngine(config, HeuristicPolicy(), rng=random.Random(11), enable_logging=False)
    module_engine._reset_run_trackers()
    module_state = module_engine.create_initial_state(deal_initial_tricks=False)
    module_state.runtime_runner_kind = "module"
    result = module_engine.run_next_transition(module_state)

    assert result.get("module_type") == "TurnSchedulerModule"
    assert module_state.runtime_runner_kind == "module"
    assert module_state.runtime_checkpoint_schema_version == 3
    assert _state_digest(module_state) == _state_digest(legacy_state)
