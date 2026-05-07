from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

from ai_policy import LapRewardDecision, MovementDecision
from policy.decision.lap_reward import resolve_lap_reward_bundle

from rl.train_policy import predict_action


def build_purchase_replay_row(
    state: Any,
    player: Any,
    *,
    tile_index: int,
    cost: int,
    source: str,
) -> dict[str, Any]:
    return _base_runtime_row(
        state,
        player,
        decision_key="purchase_decision",
        legal_actions=[
            {"action_id": "buy", "legal": True, "label": "BUY"},
            {"action_id": "skip", "legal": True, "label": "SKIP"},
        ],
        observation_extra={
            "tile_index": int(tile_index),
            "cost": int(cost),
            "source": source,
        },
    )


def build_resource_reward_replay_row(
    state: Any,
    player: Any,
    *,
    decision_key: str,
    rule_name: str,
) -> dict[str, Any]:
    rules = getattr(state.config.rules, rule_name)
    prefix = f"{rule_name}_"
    return _base_runtime_row(
        state,
        player,
        decision_key=decision_key,
        legal_actions=[
            {"action_id": "cash", "legal": True, "label": "cash"},
            {"action_id": "shards", "legal": True, "label": "shards"},
            {"action_id": "coins", "legal": True, "label": "coins"},
        ],
        observation_extra={
            "rule_name": rule_name,
            "cash_pool_remaining": _int_attr(state, f"{prefix}cash_pool_remaining", rules.cash_pool),
            "shards_pool_remaining": _int_attr(state, f"{prefix}shards_pool_remaining", rules.shards_pool),
            "coins_pool_remaining": _int_attr(state, f"{prefix}coins_pool_remaining", rules.coins_pool),
            "points_budget": int(rules.points_budget),
            "cash_point_cost": int(rules.cash_point_cost),
            "shards_point_cost": int(rules.shards_point_cost),
            "coins_point_cost": int(rules.coins_point_cost),
        },
    )


def build_movement_replay_row(state: Any, player: Any) -> dict[str, Any]:
    remaining_cards = _remaining_dice_cards(player)
    legal_actions = [{"action_id": "no_cards", "legal": True, "label": "no_cards"}]
    legal_actions.extend({"action_id": str(card), "legal": True, "label": str(card)} for card in remaining_cards)
    legal_actions.extend(
        {"action_id": f"{left}+{right}", "legal": True, "label": f"{left}+{right}"}
        for left, right in combinations(remaining_cards, 2)
    )
    return _base_runtime_row(
        state,
        player,
        decision_key="movement_decision",
        legal_actions=legal_actions,
        observation_extra={
            "remaining_cards": remaining_cards,
            "used_dice_cards": sorted(set(range(1, 7)) - set(remaining_cards)),
            "available_card_count": len(remaining_cards),
            "board_len": len(getattr(state, "board", []) or []),
        },
    )


def movement_decision_from_action(action_id: str) -> MovementDecision:
    raw = str(action_id or "no_cards")
    if raw == "no_cards":
        return MovementDecision(use_cards=False, card_values=())
    try:
        cards = tuple(int(part) for part in raw.split("+"))
    except ValueError as exc:
        raise ValueError(f"invalid movement action id: {action_id!r}") from exc
    if len(cards) not in {1, 2}:
        raise ValueError(f"movement action must use one or two cards: {action_id!r}")
    if any(card < 1 or card > 6 for card in cards):
        raise ValueError(f"movement card out of range: {action_id!r}")
    if len(set(cards)) != len(cards):
        raise ValueError(f"movement action cannot repeat a card: {action_id!r}")
    return MovementDecision(use_cards=True, card_values=cards)


def resource_reward_decision_from_action(action_id: str, state: Any, *, rule_name: str) -> LapRewardDecision:
    preferred = action_id if action_id in {"cash", "shards", "coins"} else None
    if preferred is None:
        return LapRewardDecision(choice="blocked")
    rules = getattr(state.config.rules, rule_name)
    prefix = f"{rule_name}_"
    scores = {
        "cash": (1.0, 0.01, 0.01),
        "shards": (0.01, 1.0, 0.01),
        "coins": (0.01, 0.01, 1.0),
    }[preferred]
    choice, cash_units, shard_units, coin_units = resolve_lap_reward_bundle(
        cash_pool=max(0, _int_attr(state, f"{prefix}cash_pool_remaining", rules.cash_pool)),
        shards_pool=max(0, _int_attr(state, f"{prefix}shards_pool_remaining", rules.shards_pool)),
        coins_pool=max(0, _int_attr(state, f"{prefix}coins_pool_remaining", rules.coins_pool)),
        points_budget=int(rules.points_budget),
        cash_point_cost=int(rules.cash_point_cost),
        shards_point_cost=int(rules.shards_point_cost),
        coins_point_cost=int(rules.coins_point_cost),
        cash_unit_score=scores[0],
        shard_unit_score=scores[1],
        coin_unit_score=scores[2],
        preferred=preferred,
    )
    return LapRewardDecision(choice=choice, cash_units=cash_units, shard_units=shard_units, coin_units=coin_units)


def predict_runtime_action(*, model_dir: str | Path, row: dict[str, Any]) -> dict[str, Any]:
    prediction = predict_action(model_dir=model_dir, row=row)
    legal_ids = {str(action.get("action_id")) for action in row.get("legal_actions", []) if action.get("legal", True)}
    if prediction.get("action_id") not in legal_ids:
        raise RuntimeError(
            f"RL policy predicted illegal action {prediction.get('action_id')!r} "
            f"for {row.get('decision_key')!r}; legal={sorted(legal_ids)!r}"
        )
    return prediction


def _base_runtime_row(
    state: Any,
    player: Any,
    *,
    decision_key: str,
    legal_actions: list[dict[str, Any]],
    observation_extra: dict[str, Any],
) -> dict[str, Any]:
    observation = {
        "round_index": _int_attr(state, "round_index", 0),
        "turn_index": _int_attr(state, "turn_index", 0),
        "f_value": _int_attr(state, "f_value", 0),
        "player_id": _int_attr(player, "player_id", 0),
        "cash": _int_attr(player, "cash", 0),
        "shards": _int_attr(player, "shards", 0),
        "score": _int_attr(player, "score", 0),
        "position": _int_attr(player, "position", 0),
        "character": str(getattr(player, "current_character", "") or ""),
    }
    observation.update(observation_extra)
    return {
        "game_id": None,
        "step": None,
        "player_id": _int_attr(player, "player_id", 0),
        "decision_key": decision_key,
        "observation": observation,
        "legal_actions": legal_actions,
        "chosen_action_id": "",
        "action_space_source": "runtime_adapter",
        "reward": {"total": 0.0, "components": {}},
        "done": False,
        "outcome": {},
    }


def _int_attr(obj: Any, name: str, default: int) -> int:
    try:
        return int(getattr(obj, name, default))
    except (TypeError, ValueError):
        return int(default)


def _remaining_dice_cards(player: Any) -> list[int]:
    used_raw = getattr(player, "used_dice_cards", set()) or set()
    used: set[int] = set()
    for value in used_raw:
        try:
            used.add(int(value))
        except (TypeError, ValueError):
            continue
    return [value for value in range(1, 7) if value not in used]
