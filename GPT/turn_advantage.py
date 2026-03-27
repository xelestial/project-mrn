from __future__ import annotations

from dataclasses import dataclass

from config import DEFAULT_CONFIG
from action_log_parser import TurnBundle


@dataclass(slots=True)
class AdvantageSnapshot:
    turn_index: int
    player: int
    heuristic_score: float
    leader_player: int
    rank: int
    score_margin_to_leader: float
    state: dict[str, float | int | bool | str | None]


def _starting_player_state() -> dict[str, float | int | bool | str | None]:
    return {
        "cash": float(DEFAULT_CONFIG.economy.starting_cash),
        "tiles": 0.0,
        "placed_score_coins": 0.0,
        "hand_coins": float(DEFAULT_CONFIG.coins.starting_hand_coins),
        "shards": float(DEFAULT_CONFIG.shards.starting_shards),
        "laps_completed": 0.0,
        "alive": True,
        "character": None,
    }


def _heuristic_score(state: dict[str, float | int | bool | str | None]) -> float:
    alive_bonus = 100.0 if bool(state.get("alive", True)) else -100.0
    return (
        alive_bonus
        + float(state.get("cash", 0.0)) * 0.08
        + float(state.get("tiles", 0.0)) * 1.25
        + float(state.get("placed_score_coins", 0.0)) * 0.90
        + float(state.get("hand_coins", 0.0)) * 0.35
        + float(state.get("shards", 0.0)) * 0.18
        + float(state.get("laps_completed", 0.0)) * 0.75
    )


def build_advantage_snapshots(bundles: list[TurnBundle], player_count: int = 4) -> list[AdvantageSnapshot]:
    states = {pid: _starting_player_state() for pid in range(1, player_count + 1)}
    snapshots: list[AdvantageSnapshot] = []

    for bundle in bundles:
        row = bundle.turn_row
        pid = bundle.player
        state = states[pid]
        state["cash"] = float(row.get("cash_after", state["cash"]))
        state["tiles"] = float(row.get("tiles_after", state["tiles"]))
        state["placed_score_coins"] = float(row.get("placed_score_coins_after", row.get("placed_after", state["placed_score_coins"])))
        state["hand_coins"] = float(row.get("hand_coins_after", state["hand_coins"]))
        state["shards"] = float(row.get("shards_after", state["shards"]))
        state["laps_completed"] = float(row.get("laps_completed_after", float(state["laps_completed"]) + float(row.get("laps_gained", 0) or 0)))
        state["alive"] = bool(row.get("alive_after", state["alive"]))
        state["character"] = row.get("character") or state.get("character")

        scores = {player_id: _heuristic_score(player_state) for player_id, player_state in states.items()}
        ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
        leader_player, leader_score = ranked[0]
        ranks = {player_id: index + 1 for index, (player_id, _) in enumerate(ranked)}

        for player_id in range(1, player_count + 1):
            snapshots.append(
                AdvantageSnapshot(
                    turn_index=bundle.turn_index,
                    player=player_id,
                    heuristic_score=scores[player_id],
                    leader_player=leader_player,
                    rank=ranks[player_id],
                    score_margin_to_leader=scores[player_id] - leader_score,
                    state=dict(states[player_id]),
                )
            )
    return snapshots
