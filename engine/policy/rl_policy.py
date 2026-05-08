from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_policy import ArenaPolicy, HeuristicPolicy, LapRewardDecision, MovementDecision
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


class MixedRuntimePolicy(ArenaPolicy):
    """Routes selected arena seats to RL while keeping other seats on heuristic policies."""

    runtime_policy_mode = "mixed"

    def __init__(
        self,
        *,
        model_dir: str | Path,
        player_character_policy_modes: dict[int, str] | None = None,
        player_lap_policy_modes: dict[int, str] | None = None,
        base_character_policy_mode: str = "heuristic_v3_engine",
        base_lap_policy_mode: str = "heuristic_v3_engine",
        rng=None,
    ) -> None:
        self.character_policy_mode = "arena"
        self.lap_policy_mode = "arena"
        self.rng = rng
        src_character_modes = dict(player_character_policy_modes or {})
        src_lap_modes = dict(player_lap_policy_modes or {})
        if not src_character_modes:
            src_character_modes = {i + 1: mode for i, mode in enumerate(ArenaPolicy.DEFAULT_LINEUP)}

        self.player_character_policy_modes: dict[int, str] = {}
        self.player_lap_policy_modes: dict[int, str] = {}
        self._policies: dict[int, HeuristicPolicy] = {}
        for pid in range(1, 5):
            char_mode = src_character_modes.get(pid, ArenaPolicy.DEFAULT_LINEUP[(pid - 1) % len(ArenaPolicy.DEFAULT_LINEUP)])
            lap_mode = src_lap_modes.get(pid)
            if char_mode == "rl_v1":
                self.player_character_policy_modes[pid] = "rl_v1"
                self.player_lap_policy_modes[pid] = "rl_v1"
                self._policies[pid - 1] = RlRuntimePolicy(
                    model_dir=model_dir,
                    base_character_policy_mode=base_character_policy_mode,
                    base_lap_policy_mode=base_lap_policy_mode,
                    rng=rng,
                )
                continue
            if char_mode not in HeuristicPolicy.VALID_CHARACTER_POLICIES or char_mode == "arena":
                raise ValueError(f"Unsupported mixed character policy for player {pid}: {char_mode}")
            normalized_char = HeuristicPolicy.canonical_character_policy_mode(char_mode)
            if lap_mode is None:
                lap_mode = normalized_char if normalized_char in HeuristicPolicy.VALID_LAP_POLICIES else base_lap_policy_mode
            if lap_mode not in HeuristicPolicy.VALID_LAP_POLICIES:
                raise ValueError(f"Unsupported mixed lap policy for player {pid}: {lap_mode}")
            normalized_lap = HeuristicPolicy.canonical_lap_policy_mode(lap_mode)
            self.player_character_policy_modes[pid] = normalized_char
            self.player_lap_policy_modes[pid] = normalized_lap
            self._policies[pid - 1] = HeuristicPolicy(
                character_policy_mode=normalized_char,
                lap_policy_mode=normalized_lap,
                rng=rng,
            )
