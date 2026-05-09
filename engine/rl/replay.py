from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from rl.action_space import normalize_decision_action_space
from rl.reward import compute_reward_from_event


def write_replay_row(path: str | Path, row: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def iter_replay_rows(path: str | Path) -> Iterable[dict]:
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_replay_rows(path: str | Path, rows: Iterable[dict]) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def build_replay_rows_from_game(game: dict) -> list[dict]:
    decisions = list(game.get("ai_decision_log") or [])
    if not decisions:
        return []
    rank_by_player = _player_rank_by_id(game)

    turns_by_player_turn: dict[tuple[int, int | None], dict] = {}
    turns_by_player_round: dict[tuple[int, int | None], dict] = {}
    for event in game.get("action_log") or []:
        if event.get("event") != "turn":
            continue
        player_id = int(event.get("player", 0) or 0)
        turn_index = event.get("turn_index_global")
        round_index = event.get("round_index")
        if player_id:
            turns_by_player_turn[(player_id, int(turn_index) if turn_index is not None else None)] = event
            turns_by_player_round[(player_id, int(round_index) if round_index is not None else None)] = event

    rows: list[dict] = []
    for step, decision in enumerate(decisions, start=1):
        player_id = int(decision.get("player_id", 0) or decision.get("player", 0) or 0)
        turn_index = decision.get("turn_index")
        round_index = decision.get("round_index")
        reward_event = None
        if _decision_can_use_turn_reward(decision):
            reward_event = turns_by_player_turn.get((player_id, int(turn_index) if turn_index is not None else None))
            if reward_event is None:
                reward_event = turns_by_player_round.get((player_id, int(round_index) if round_index is not None else None))
        reward = compute_reward_from_event(reward_event).to_dict()
        payload = decision.get("payload") if isinstance(decision.get("payload"), dict) else {}
        action_space = normalize_decision_action_space(decision)
        winner_ids = list(game.get("winner_ids") or [])
        rank = rank_by_player.get(player_id)
        won = player_id in winner_ids
        row = {
            "game_id": game.get("global_game_index", game.get("game_id")),
            "step": step,
            "seed": game.get("game_seed"),
            "policy_mode": game.get("policy_mode"),
            "player_id": player_id,
            "decision_key": decision.get("decision_key") or decision.get("decision"),
            "observation": _build_observation(decision, payload),
            "legal_actions": action_space.legal_actions,
            "chosen_action_id": action_space.chosen_action_id,
            "action_space_source": action_space.source,
            "reward": reward,
            "sample_weight": _sample_weight(
                reward_total=float(reward.get("total") or 0.0),
                won=won,
                rank=rank,
                decision_key=str(decision.get("decision_key") or decision.get("decision") or ""),
            ),
            "done": step == len(decisions),
            "outcome": {
                "winner_ids": winner_ids,
                "end_reason": game.get("end_reason"),
                "won": won,
                "rank": rank,
            },
        }
        rows.append(row)
    return rows


def _player_rank_by_id(game: dict) -> dict[int, int]:
    players = list(game.get("player_summary") or [])
    if not players:
        return {}
    ordered = sorted(
        players,
        key=lambda p: (
            _number(p.get("score")),
            _number(p.get("placed_score_coins")),
            _number(p.get("cash")),
            _number(p.get("tiles_owned")),
        ),
        reverse=True,
    )
    ranks: dict[int, int] = {}
    for rank, player in enumerate(ordered, start=1):
        player_id = player.get("player_id")
        if player_id is None:
            continue
        ranks[int(player_id) + 1] = rank
    return ranks


def _sample_weight(*, reward_total: float, won: bool, rank: int | None, decision_key: str) -> float:
    weight = 1.0 + min(1.5, abs(float(reward_total)) * 0.5)
    if won:
        weight += 0.5
    if rank == 1:
        weight += 0.4
    elif rank == 4:
        weight += 0.2
    if decision_key in {"purchase_decision", "movement_decision", "lap_reward", "start_reward"}:
        weight += 0.25
    return round(max(0.5, min(4.0, weight)), 4)


def _build_observation(decision: dict, payload: dict) -> dict:
    observation = {
        "round_index": decision.get("round_index"),
        "turn_index": decision.get("turn_index"),
        "turn_index_for_player": decision.get("turn_index_for_player"),
        "position": decision.get("position"),
        "f_value": decision.get("f_value"),
        "character": decision.get("character"),
    }
    for key, value in payload.items():
        if key in {"options", "candidates", "candidate_details"}:
            continue
        if _json_safe(value):
            observation[key] = value
    return observation


def _decision_can_use_turn_reward(decision: dict) -> bool:
    decision_key = str(decision.get("decision_key") or decision.get("decision") or "")
    if decision_key in {"draft_card", "hidden_trick"}:
        return False
    turn_index_for_player = decision.get("turn_index_for_player")
    if turn_index_for_player is not None and int(turn_index_for_player) <= 0:
        return False
    return True


def _json_safe(value) -> bool:
    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return False
    return True


def _number(value) -> float:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0
