from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_policy import HeuristicPolicy, LapRewardDecision, MovementDecision
from rl.runtime_adapter import (
    build_movement_replay_row,
    build_purchase_replay_row,
    build_resource_reward_replay_row,
    movement_decision_from_action,
    predict_runtime_action,
    resource_reward_decision_from_action,
)


class RlRuntimePolicy(HeuristicPolicy):
    runtime_policy_mode = "rl_v1"
    supported_decisions = frozenset({"purchase_decision", "movement_decision", "lap_reward", "start_reward"})

    def __init__(
        self,
        *,
        model_dir: str | Path,
        base_character_policy_mode: str = "heuristic_v3_engine",
        base_lap_policy_mode: str = "heuristic_v3_engine",
        rng=None,
    ) -> None:
        super().__init__(
            character_policy_mode=base_character_policy_mode,
            lap_policy_mode=base_lap_policy_mode,
            rng=rng,
        )
        self.model_dir = Path(model_dir)

    def choose_purchase_tile(self, state: Any, player: Any, pos: int, cell: Any, cost: int, *, source: str = "landing") -> bool:
        row = build_purchase_replay_row(state, player, tile_index=pos, cost=cost, source=source)
        prediction = predict_runtime_action(model_dir=self.model_dir, row=row)
        return prediction["action_id"] == "buy"

    def choose_movement(self, state: Any, player: Any) -> MovementDecision:
        row = build_movement_replay_row(state, player)
        prediction = predict_runtime_action(model_dir=self.model_dir, row=row)
        return movement_decision_from_action(prediction["action_id"])

    def choose_lap_reward(self, state: Any, player: Any) -> LapRewardDecision:
        row = build_resource_reward_replay_row(state, player, decision_key="lap_reward", rule_name="lap_reward")
        prediction = predict_runtime_action(model_dir=self.model_dir, row=row)
        return resource_reward_decision_from_action(prediction["action_id"], state, rule_name="lap_reward")

    def choose_start_reward(self, state: Any, player: Any) -> LapRewardDecision:
        row = build_resource_reward_replay_row(state, player, decision_key="start_reward", rule_name="start_reward")
        prediction = predict_runtime_action(model_dir=self.model_dir, row=row)
        return resource_reward_decision_from_action(prediction["action_id"], state, rule_name="start_reward")
