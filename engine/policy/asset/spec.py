from __future__ import annotations

from dataclasses import dataclass, field


DEFAULT_ARENA_CHARACTER_LINEUP = (
    "heuristic_v1",
    "heuristic_v2_token_opt",
    "heuristic_v2_control",
    "heuristic_v2_balanced",
)


@dataclass(frozen=True, slots=True)
class HeuristicPolicyAsset:
    character_policy_mode: str = "heuristic_v1"
    lap_policy_mode: str = "heuristic_v1"
    player_lap_policy_modes: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ArenaPolicyAsset:
    player_character_policy_modes: dict[int, str] = field(default_factory=dict)
    player_lap_policy_modes: dict[int, str] = field(default_factory=dict)
