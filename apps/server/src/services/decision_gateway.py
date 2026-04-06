from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Literal

DecisionProvider = Literal["human", "ai"]

ChoiceSerializer = Callable[[Any], str]
ContextBuilder = Callable[[tuple[Any, ...], dict[str, Any], Any, Any], dict[str, Any]]
LegalChoiceBuilder = Callable[[tuple[Any, ...], dict[str, Any], Any, Any], list[dict[str, Any]]]
ChoiceParser = Callable[[str, tuple[Any, ...], dict[str, Any], Any, Any], Any]


@dataclass(frozen=True)
class DecisionMethodSpec:
    request_type: str
    choice_serializer: ChoiceSerializer
    public_context_builder: ContextBuilder | None = None
    legal_choice_builder: LegalChoiceBuilder | None = None
    choice_parser: ChoiceParser | None = None


@dataclass(frozen=True)
class PreparedDecisionMethod:
    request_type: str
    public_context: dict[str, Any]
    legal_choices: list[dict[str, Any]]
    choice_serializer: ChoiceSerializer
    choice_parser: ChoiceParser | None


@dataclass(frozen=True)
class DecisionInvocation:
    method_name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    state: Any
    player: Any
    player_id: int | None


@dataclass(frozen=True)
class CanonicalDecisionRequest:
    decision_name: str
    request_type: str
    player_id: int | None
    round_index: int | None
    turn_index: int | None
    public_context: dict[str, Any]
    fallback_policy: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class RoutedDecisionCall:
    invocation: DecisionInvocation
    request: CanonicalDecisionRequest
    legal_choices: list[dict[str, Any]]
    choice_serializer: ChoiceSerializer
    choice_parser: ChoiceParser | None


def _number_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _trim_public_context(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _round_index_from_state(state: Any) -> int | None:
    rounds_completed = _number_or_none(getattr(state, "rounds_completed", None))
    if rounds_completed is None:
        return None
    return rounds_completed + 1


def _turn_index_from_state(state: Any) -> int | None:
    turn_index = _number_or_none(getattr(state, "turn_index", None))
    if turn_index is None:
        return None
    return turn_index + 1


def _arg_or_kw(args: tuple[Any, ...], kwargs: dict[str, Any], index: int, key: str) -> Any:
    return args[index] if len(args) > index else kwargs.get(key)


def _serialize_default_choice(result: Any) -> str:
    return "none" if result is None else str(result)


def _serialize_movement_choice(result: Any) -> str:
    use_cards = bool(getattr(result, "use_cards", False))
    card_values = tuple(getattr(result, "card_values", ()) or ())
    if not use_cards or not card_values:
        return "dice"
    return "card_" + "_".join(str(value) for value in card_values)


def _serialize_lap_reward_choice(result: Any) -> str:
    choice = getattr(result, "choice", None)
    return str(choice) if isinstance(choice, str) and choice else "blocked"


def _serialize_yes_no_choice(result: Any) -> str:
    return "yes" if bool(result) else "no"


def _serialize_trick_like_choice(result: Any) -> str:
    if result is None:
        return "none"
    deck_index = getattr(result, "deck_index", None)
    if isinstance(deck_index, int):
        return str(deck_index)
    return str(getattr(result, "name", result))


def _serialize_string_choice(result: Any) -> str:
    return str(result)


def _choice_payload(
    choice_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    value: Any = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"choice_id": str(choice_id)}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if value is not None:
        payload["value"] = value
    return payload


def _build_card_choice_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    cards = _arg_or_kw(args, kwargs, 2, "offered_cards") or kwargs.get("card_choices")
    if isinstance(cards, list):
        return {"choice_count": len(cards)}
    return {}


def _build_purchase_tile_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    return {
        "tile_index": _arg_or_kw(args, kwargs, 2, "pos"),
        "cost": _arg_or_kw(args, kwargs, 4, "cost"),
        "source": kwargs.get("source", "landing"),
    }


def _build_mark_target_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    return {"actor_name": _arg_or_kw(args, kwargs, 2, "actor_name")}


def _build_active_flip_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    flippable_cards = _arg_or_kw(args, kwargs, 2, "flippable_cards")
    if isinstance(flippable_cards, list):
        return {"flip_count": len(flippable_cards)}
    return {}


def _build_hidden_trick_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    hand = _arg_or_kw(args, kwargs, 2, "hand")
    if isinstance(hand, list):
        return {"hand_count": len(hand), "selection_required": True}
    return {}


def _build_trick_to_use_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    hand = _arg_or_kw(args, kwargs, 2, "hand")
    if isinstance(hand, list):
        return {"hand_count": len(hand)}
    return {}


def _build_specific_trick_reward_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    choices = _arg_or_kw(args, kwargs, 2, "choices")
    if isinstance(choices, list):
        return {"reward_count": len(choices)}
    return {}


def _build_coin_placement_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del args, kwargs, state
    owned_tiles = getattr(player, "visited_owned_tile_indices", None)
    if owned_tiles is not None:
        return {"owned_tile_count": len(list(owned_tiles))}
    return {}


def _build_doctrine_relief_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    candidates = _arg_or_kw(args, kwargs, 2, "candidates")
    if isinstance(candidates, list):
        return {"candidate_count": len(candidates)}
    return {}


def _build_runaway_step_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    return {
        "one_short_pos": _arg_or_kw(args, kwargs, 2, "one_short_pos"),
        "bonus_target_pos": _arg_or_kw(args, kwargs, 3, "bonus_target_pos"),
        "bonus_target_kind": str(_arg_or_kw(args, kwargs, 4, "bonus_target_kind")),
    }


def _build_movement_legal_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del args, kwargs, state
    remaining = sorted(v for v in range(1, 7) if v not in set(getattr(player, "used_dice_cards", set()) or set()))
    choices = [_choice_payload("dice", title="Roll dice", value={"use_cards": False, "card_values": []})]
    for first in remaining:
        choices.append(
            _choice_payload(
                f"card_{first}",
                title=f"Use card {first}",
                value={"use_cards": True, "card_values": [first]},
            )
        )
    for i, first in enumerate(remaining):
        for second in remaining[i + 1 :]:
            choices.append(
                _choice_payload(
                    f"card_{first}_{second}",
                    title=f"Use cards {first}+{second}",
                    value={"use_cards": True, "card_values": [first, second]},
                )
            )
    return choices


def _parse_movement_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state
    from ai_policy import MovementDecision

    remaining = {v for v in range(1, 7) if v not in set(getattr(player, "used_dice_cards", set()) or set())}
    if choice_id in {"dice", "roll"}:
        return MovementDecision(use_cards=False, card_values=())
    if not choice_id.startswith("card_"):
        raise ValueError("invalid_movement_choice_id")
    values = tuple(sorted(int(part) for part in choice_id.split("_")[1:] if part))
    if not values or any(value not in remaining for value in values):
        raise ValueError("invalid_movement_cards")
    return MovementDecision(use_cards=True, card_values=values)


def _build_runaway_legal_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del state, player
    one_short_pos = _arg_or_kw(args, kwargs, 2, "one_short_pos")
    bonus_target_pos = _arg_or_kw(args, kwargs, 3, "bonus_target_pos")
    bonus_target_kind = str(_arg_or_kw(args, kwargs, 4, "bonus_target_kind"))
    return [
        _choice_payload(
            "yes",
            title=f"+1 to {bonus_target_pos}",
            value={"take_bonus": True, "one_short_pos": one_short_pos, "bonus_target_pos": bonus_target_pos, "bonus_target_kind": bonus_target_kind},
        ),
        _choice_payload(
            "no",
            title=f"Stay on {one_short_pos}",
            value={"take_bonus": False, "one_short_pos": one_short_pos, "bonus_target_pos": bonus_target_pos, "bonus_target_kind": bonus_target_kind},
        ),
    ]


def _parse_runaway_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    if choice_id == "yes":
        return True
    if choice_id == "no":
        return False
    raise ValueError("invalid_runaway_choice_id")


def _build_lap_reward_legal_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del args, kwargs, player
    rules = state.config.rules.lap_reward
    cash_pool = int(getattr(state, "lap_reward_cash_pool_remaining", rules.cash_pool))
    shards_pool = int(getattr(state, "lap_reward_shards_pool_remaining", rules.shards_pool))
    coins_pool = int(getattr(state, "lap_reward_coins_pool_remaining", rules.coins_pool))
    budget = rules.points_budget
    max_cash = min(cash_pool, budget // max(1, rules.cash_point_cost))
    max_shards = min(shards_pool, budget // max(1, rules.shards_point_cost))
    max_coins = min(coins_pool, budget // max(1, rules.coins_point_cost))
    choices: list[dict[str, Any]] = []
    if max_cash > 0:
        choices.append(_choice_payload("cash", title=f"Cash +{max_cash}", value={"choice": "cash", "cash_units": max_cash, "shard_units": 0, "coin_units": 0}))
    if max_shards > 0:
        choices.append(_choice_payload("shards", title=f"Shards +{max_shards}", value={"choice": "shards", "cash_units": 0, "shard_units": max_shards, "coin_units": 0}))
    if max_coins > 0:
        choices.append(_choice_payload("coins", title=f"Coins +{max_coins}", value={"choice": "coins", "cash_units": 0, "shard_units": 0, "coin_units": max_coins}))
    return choices


def _parse_lap_reward_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, player
    from ai_policy import LapRewardDecision

    for choice in _build_lap_reward_legal_choices((), {}, state, None):
        if choice["choice_id"] == choice_id:
            value = dict(choice.get("value") or {})
            return LapRewardDecision(
                choice=str(value.get("choice", "blocked")),
                cash_units=int(value.get("cash_units", 0)),
                shard_units=int(value.get("shard_units", 0)),
                coin_units=int(value.get("coin_units", 0)),
            )
    raise ValueError("invalid_lap_reward_choice_id")


def _build_card_index_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any, index: int, key: str) -> list[dict[str, Any]]:
    del player
    raw_cards = _arg_or_kw(args, kwargs, index, key) or []
    choices: list[dict[str, Any]] = []
    for card_index in raw_cards:
        name = ""
        try:
            from characters import CARD_TO_NAMES

            names = CARD_TO_NAMES.get(int(card_index), ("", ""))
            name = next((candidate for candidate in names if candidate), "")
        except Exception:
            name = ""
        title = name or str(card_index)
        choices.append(_choice_payload(str(card_index), title=title, value={"card_index": int(card_index)}))
    return choices


def _parse_draft_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    return int(choice_id)


def _parse_final_character_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del player
    choices = _arg_or_kw(args, kwargs, 2, "card_choices") or []
    try:
        from characters import CARD_TO_NAMES

        for card_index in choices:
            if str(card_index) != str(choice_id):
                continue
            names = CARD_TO_NAMES.get(int(card_index), ("", ""))
            return next((candidate for candidate in names if candidate), str(card_index))
    except Exception:
        pass
    raise ValueError("invalid_final_character_choice_id")


def _build_hand_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any, index: int, key: str, *, include_none: bool) -> list[dict[str, Any]]:
    del state
    hand = list(_arg_or_kw(args, kwargs, index, key) or [])
    choices: list[dict[str, Any]] = []
    if include_none:
        choices.append(_choice_payload("none", title="Skip"))
    hidden_deck_index = getattr(player, "hidden_trick_deck_index", None)
    for card in hand:
        deck_index = getattr(card, "deck_index", None)
        if deck_index is None:
            continue
        choices.append(
            _choice_payload(
                str(deck_index),
                title=getattr(card, "name", str(deck_index)),
                description=getattr(card, "description", ""),
                value={
                    "deck_index": deck_index,
                    "card_description": getattr(card, "description", ""),
                    "is_hidden": hidden_deck_index is not None and deck_index == hidden_deck_index,
                },
            )
        )
    return choices


def _parse_hand_card_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del state, player
    hand = list(_arg_or_kw(args, kwargs, 2, "hand") or [])
    if choice_id == "none":
        return None
    for card in hand:
        if str(getattr(card, "deck_index", "")) == str(choice_id):
            return card
    raise ValueError("invalid_hand_choice_id")


def _build_purchase_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del state, player
    pos = _arg_or_kw(args, kwargs, 2, "pos")
    cost = _arg_or_kw(args, kwargs, 4, "cost")
    return [
        _choice_payload("yes", title=f"Buy tile {pos}", value={"buy": True, "tile_index": pos, "cost": cost}),
        _choice_payload("no", title="Skip purchase", value={"buy": False, "tile_index": pos, "cost": cost}),
    ]


def _build_burden_exchange_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del state, player
    card = _arg_or_kw(args, kwargs, 2, "card")
    cost = getattr(card, "burden_cost", 0)
    name = getattr(card, "name", "Burden")
    return [
        _choice_payload("yes", title=f"Pay {cost} to remove", value={"burden_cost": cost, "card_name": name}),
        _choice_payload("no", title="Keep burden", value={"burden_cost": cost, "card_name": name}),
    ]


def _parse_yes_no_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    if choice_id == "yes":
        return True
    if choice_id == "no":
        return False
    raise ValueError("invalid_yes_no_choice_id")


def _build_mark_target_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    actor_name = _arg_or_kw(args, kwargs, 2, "actor_name")
    try:
        from viewer.human_policy import _is_mark_skill_blocked_by_uhsa, _legal_mark_target_players

        if _is_mark_skill_blocked_by_uhsa(state, player, actor_name):
            return [_choice_payload("none", title="No mark")]
        legal_targets = _legal_mark_target_players(state, player)
    except Exception:
        legal_targets = [target for target in getattr(state, "players", []) if getattr(target, "alive", False) and getattr(target, "player_id", None) != getattr(player, "player_id", None)]
    choices = [_choice_payload("none", title="No mark")]
    for target in legal_targets:
        character = str(getattr(target, "current_character", "") or "")
        player_id = getattr(target, "player_id", None)
        if not character or not isinstance(player_id, int):
            continue
        choices.append(
            _choice_payload(
                str(player_id),
                title=f"{character} / P{player_id + 1}",
                value={"target_character": character, "target_player_id": player_id + 1},
            )
        )
    return choices


def _parse_mark_target_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, player
    if choice_id == "none":
        return None
    for target in getattr(state, "players", []):
        if str(getattr(target, "player_id", "")) == str(choice_id):
            return getattr(target, "current_character", None)
    raise ValueError("invalid_mark_target_choice_id")


def _build_coin_placement_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del args, kwargs
    tile_owner = getattr(state, "tile_owner", None)
    if tile_owner is None:
        owned = [int(idx) for idx in getattr(player, "visited_owned_tile_indices", [])]
    else:
        owned = [int(idx) for idx in getattr(player, "visited_owned_tile_indices", []) if tile_owner[int(idx)] == getattr(player, "player_id", None)]
    return [_choice_payload(str(idx), title=f"Tile {idx}", value={"tile_index": idx}) for idx in owned]


def _parse_coin_placement_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    return int(choice_id)


def _build_geo_bonus_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del args, kwargs, state, player
    return [
        _choice_payload("cash", title="Cash +1", value={"choice": "cash"}),
        _choice_payload("shards", title="Shards +1", value={"choice": "shards"}),
        _choice_payload("coins", title="Coins +1", value={"choice": "coins"}),
    ]


def _parse_string_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    return str(choice_id)


def _build_doctrine_relief_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del state, player
    candidates = list(_arg_or_kw(args, kwargs, 2, "candidates") or [])
    choices: list[dict[str, Any]] = []
    for target in candidates:
        player_id = getattr(target, "player_id", None)
        if not isinstance(player_id, int):
            continue
        burden_count = sum(1 for card in getattr(target, "trick_hand", []) if getattr(card, "is_burden", False))
        choices.append(
            _choice_payload(
                str(player_id),
                title=f"P{player_id + 1}",
                value={"target_player_id": player_id + 1, "burden_count": burden_count},
            )
        )
    return choices


def _parse_doctrine_relief_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del state, player
    candidates = list(_arg_or_kw(args, kwargs, 2, "candidates") or [])
    for target in candidates:
        if str(getattr(target, "player_id", "")) == str(choice_id):
            return getattr(target, "player_id")
    raise ValueError("invalid_doctrine_relief_choice_id")


def _build_active_flip_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del state, player
    flippable_cards = list(_arg_or_kw(args, kwargs, 2, "flippable_cards") or [])
    choices = [_choice_payload("none", title="Finish flipping")]
    for card_index in flippable_cards:
        choices.append(_choice_payload(str(card_index), title=f"Flip {card_index}", value={"card_index": int(card_index)}))
    return choices


def _parse_active_flip_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    if choice_id == "none":
        return None
    return int(choice_id)


def _build_specific_trick_reward_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del state, player
    choices = list(_arg_or_kw(args, kwargs, 2, "choices") or [])
    return [
        _choice_payload(
            str(getattr(card, "deck_index", "")),
            title=getattr(card, "name", str(getattr(card, "deck_index", ""))),
            value={"deck_index": getattr(card, "deck_index", None)},
        )
        for card in choices
        if getattr(card, "deck_index", None) is not None
    ]


def _parse_specific_trick_reward_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del state, player
    choices = list(_arg_or_kw(args, kwargs, 2, "choices") or [])
    for card in choices:
        if str(getattr(card, "deck_index", "")) == str(choice_id):
            return card
    raise ValueError("invalid_specific_trick_reward_choice_id")


METHOD_SPECS: dict[str, DecisionMethodSpec] = {
    "choose_movement": DecisionMethodSpec("movement", _serialize_movement_choice, legal_choice_builder=_build_movement_legal_choices, choice_parser=_parse_movement_choice),
    "choose_runaway_slave_step": DecisionMethodSpec(
        "runaway_step_choice",
        _serialize_yes_no_choice,
        _build_runaway_step_context,
        _build_runaway_legal_choices,
        _parse_runaway_choice,
    ),
    "choose_lap_reward": DecisionMethodSpec("lap_reward", _serialize_lap_reward_choice, legal_choice_builder=_build_lap_reward_legal_choices, choice_parser=_parse_lap_reward_choice),
    "choose_draft_card": DecisionMethodSpec("draft_card", _serialize_string_choice, _build_card_choice_context, lambda args, kwargs, state, player: _build_card_index_choices(args, kwargs, state, player, 2, "offered_cards"), _parse_draft_choice),
    "choose_final_character": DecisionMethodSpec(
        "final_character",
        _serialize_string_choice,
        _build_card_choice_context,
        lambda args, kwargs, state, player: _build_card_index_choices(args, kwargs, state, player, 2, "card_choices"),
        _parse_final_character_choice,
    ),
    "choose_trick_to_use": DecisionMethodSpec(
        "trick_to_use",
        _serialize_trick_like_choice,
        _build_trick_to_use_context,
        lambda args, kwargs, state, player: _build_hand_choices(args, kwargs, state, player, 2, "hand", include_none=True),
        _parse_hand_card_choice,
    ),
    "choose_purchase_tile": DecisionMethodSpec(
        "purchase_tile",
        _serialize_yes_no_choice,
        _build_purchase_tile_context,
        _build_purchase_choices,
        _parse_yes_no_choice,
    ),
    "choose_hidden_trick_card": DecisionMethodSpec(
        "hidden_trick_card",
        _serialize_trick_like_choice,
        _build_hidden_trick_context,
        lambda args, kwargs, state, player: _build_hand_choices(args, kwargs, state, player, 2, "hand", include_none=False),
        _parse_hand_card_choice,
    ),
    "choose_mark_target": DecisionMethodSpec("mark_target", _serialize_default_choice, _build_mark_target_context, _build_mark_target_choices, _parse_mark_target_choice),
    "choose_coin_placement_tile": DecisionMethodSpec(
        "coin_placement",
        _serialize_default_choice,
        _build_coin_placement_context,
        _build_coin_placement_choices,
        _parse_coin_placement_choice,
    ),
    "choose_geo_bonus": DecisionMethodSpec("geo_bonus", _serialize_string_choice, legal_choice_builder=_build_geo_bonus_choices, choice_parser=_parse_string_choice),
    "choose_doctrine_relief_target": DecisionMethodSpec(
        "doctrine_relief",
        _serialize_default_choice,
        _build_doctrine_relief_context,
        _build_doctrine_relief_choices,
        _parse_doctrine_relief_choice,
    ),
    "choose_active_flip_card": DecisionMethodSpec(
        "active_flip",
        _serialize_default_choice,
        _build_active_flip_context,
        _build_active_flip_choices,
        _parse_active_flip_choice,
    ),
    "choose_specific_trick_reward": DecisionMethodSpec(
        "specific_trick_reward",
        _serialize_trick_like_choice,
        _build_specific_trick_reward_context,
        _build_specific_trick_reward_choices,
        _parse_specific_trick_reward_choice,
    ),
    "choose_burden_exchange_on_supply": DecisionMethodSpec("burden_exchange", _serialize_yes_no_choice, legal_choice_builder=_build_burden_exchange_choices, choice_parser=_parse_yes_no_choice),
    "choose_pabal_dice_mode": DecisionMethodSpec(
        "pabal_dice_mode",
        _serialize_string_choice,
        legal_choice_builder=lambda args, kwargs, state, player: [
            _choice_payload("plus_one", title="Roll three dice", value={"dice_mode": "plus_one"}),
            _choice_payload("minus_one", title="Roll one die", value={"dice_mode": "minus_one"}),
        ],
        choice_parser=_parse_string_choice,
    ),
}


def _decision_method_spec_for_method(method_name: str) -> DecisionMethodSpec:
    return METHOD_SPECS.get(
        method_name,
        DecisionMethodSpec(
            request_type=method_name.removeprefix("choose_"),
            choice_serializer=_serialize_default_choice,
        ),
    )


def serialize_ai_choice_id(method_name: str, result: Any) -> str:
    return _decision_method_spec_for_method(method_name).choice_serializer(result)


def decision_request_type_for_method(method_name: str) -> str:
    return _decision_method_spec_for_method(method_name).request_type


def build_public_context(method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    state = args[0] if len(args) > 0 else kwargs.get("state")
    player = args[1] if len(args) > 1 else kwargs.get("player")
    context: dict[str, Any] = {
        "round_index": _round_index_from_state(state),
        "turn_index": _turn_index_from_state(state),
        "player_cash": getattr(player, "cash", None),
        "player_position": getattr(player, "position", None),
        "player_shards": getattr(player, "shards", None),
    }
    spec = _decision_method_spec_for_method(method_name)
    if spec.public_context_builder is not None:
        context.update(spec.public_context_builder(args, kwargs, state, player))

    return _trim_public_context(context)


def prepare_decision_method(method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> PreparedDecisionMethod:
    invocation = build_decision_invocation(method_name, args, kwargs)
    return prepare_decision_method_from_invocation(invocation)


def build_decision_invocation(method_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> DecisionInvocation:
    state = args[0] if len(args) > 0 else kwargs.get("state")
    player = args[1] if len(args) > 1 else kwargs.get("player")
    raw_player_id = getattr(player, "player_id", None)
    player_id = raw_player_id if isinstance(raw_player_id, int) else None
    return DecisionInvocation(
        method_name=method_name,
        args=args,
        kwargs=dict(kwargs),
        state=state,
        player=player,
        player_id=player_id,
    )


def build_decision_invocation_from_request(request: Any) -> DecisionInvocation:
    return build_decision_invocation(
        str(getattr(request, "decision_name")),
        tuple(getattr(request, "args", ()) or ()),
        dict(getattr(request, "kwargs", {}) or {}),
    )


def prepare_decision_method_from_invocation(invocation: DecisionInvocation) -> PreparedDecisionMethod:
    spec = _decision_method_spec_for_method(invocation.method_name)
    state = invocation.state
    player = invocation.player
    return PreparedDecisionMethod(
        request_type=spec.request_type,
        public_context=build_public_context(invocation.method_name, invocation.args, invocation.kwargs),
        legal_choices=spec.legal_choice_builder(invocation.args, invocation.kwargs, state, player) if spec.legal_choice_builder is not None else [],
        choice_serializer=spec.choice_serializer,
        choice_parser=spec.choice_parser,
    )


def build_canonical_decision_request(
    invocation: DecisionInvocation,
    *,
    fallback_policy: str = "ai",
) -> CanonicalDecisionRequest:
    prepared = prepare_decision_method_from_invocation(invocation)
    public_context = dict(prepared.public_context)
    return CanonicalDecisionRequest(
        decision_name=invocation.method_name,
        request_type=prepared.request_type,
        player_id=invocation.player_id,
        round_index=public_context.get("round_index"),
        turn_index=public_context.get("turn_index"),
        public_context=public_context,
        fallback_policy=fallback_policy,
        args=invocation.args,
        kwargs=dict(invocation.kwargs),
    )


def build_routed_decision_call(
    invocation: DecisionInvocation,
    *,
    fallback_policy: str = "ai",
) -> RoutedDecisionCall:
    prepared = prepare_decision_method_from_invocation(invocation)
    return RoutedDecisionCall(
        invocation=invocation,
        request=CanonicalDecisionRequest(
            decision_name=invocation.method_name,
            request_type=prepared.request_type,
            player_id=invocation.player_id,
            round_index=prepared.public_context.get("round_index"),
            turn_index=prepared.public_context.get("turn_index"),
            public_context=dict(prepared.public_context),
            fallback_policy=fallback_policy,
            args=invocation.args,
            kwargs=dict(invocation.kwargs),
        ),
        legal_choices=list(prepared.legal_choices),
        choice_serializer=prepared.choice_serializer,
        choice_parser=prepared.choice_parser,
    )


def build_decision_ack_payload(
    *,
    request_id: str,
    status: str,
    player_id: int,
    reason: str | None = None,
    provider: DecisionProvider = "human",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "request_id": request_id,
        "status": status,
        "player_id": player_id,
        "provider": provider,
    }
    if reason:
        payload["reason"] = reason
    return payload


def build_decision_requested_payload(
    *,
    request_id: str,
    player_id: int,
    request_type: str,
    fallback_policy: str,
    provider: DecisionProvider,
    round_index: int | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "decision_requested",
        "request_id": request_id,
        "player_id": player_id,
        "request_type": request_type,
        "fallback_policy": fallback_policy,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }


def build_decision_resolved_payload(
    *,
    request_id: str,
    player_id: int,
    resolution: str,
    choice_id: str | None,
    provider: DecisionProvider,
    round_index: int | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "decision_resolved",
        "request_id": request_id,
        "player_id": player_id,
        "resolution": resolution,
        "choice_id": choice_id,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }


def build_decision_timeout_fallback_payload(
    *,
    request_id: str,
    player_id: int,
    fallback_policy: str,
    fallback_execution: str | None,
    fallback_choice_id: str | None,
    provider: DecisionProvider = "human",
    round_index: int | None = None,
    turn_index: int | None = None,
) -> dict[str, Any]:
    return {
        "event_type": "decision_timeout_fallback",
        "request_id": request_id,
        "player_id": player_id,
        "fallback_policy": fallback_policy,
        "fallback_execution": fallback_execution,
        "fallback_choice_id": fallback_choice_id,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }


class DecisionGateway:
    """Canonical runtime decision contract publisher for human and AI seats."""

    def __init__(
        self,
        *,
        session_id: str,
        prompt_service,
        stream_service,
        loop: asyncio.AbstractEventLoop,
        touch_activity: Callable[[str], None],
        fallback_executor,
    ) -> None:
        self._session_id = session_id
        self._prompt_service = prompt_service
        self._stream_service = stream_service
        self._loop = loop
        self._touch_activity = touch_activity
        self._fallback_executor = fallback_executor
        self._request_seq = 0

    def next_request_id(self) -> str:
        self._request_seq += 1
        return f"{self._session_id}_req_{self._request_seq}_{uuid.uuid4().hex[:6]}"

    def _publish_decision_requested(
        self,
        *,
        request_id: str,
        player_id: int,
        request_type: str,
        fallback_policy: str,
        provider: DecisionProvider,
        public_context: dict[str, Any],
    ) -> None:
        self.publish(
            "event",
            build_decision_requested_payload(
                request_id=request_id,
                player_id=player_id,
                request_type=request_type,
                fallback_policy=fallback_policy,
                provider=provider,
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )

    def _publish_decision_resolved(
        self,
        *,
        request_id: str,
        player_id: int,
        resolution: str,
        choice_id: str | None,
        provider: DecisionProvider,
        public_context: dict[str, Any],
    ) -> None:
        self.publish(
            "event",
            build_decision_resolved_payload(
                request_id=request_id,
                player_id=player_id,
                resolution=resolution,
                choice_id=choice_id,
                provider=provider,
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )

    def _publish_decision_timeout_fallback(
        self,
        *,
        request_id: str,
        player_id: int,
        fallback_policy: str,
        fallback_execution: str | None,
        fallback_choice_id: str | None,
        provider: DecisionProvider,
        public_context: dict[str, Any],
    ) -> None:
        self.publish(
            "event",
            build_decision_timeout_fallback_payload(
                request_id=request_id,
                player_id=player_id,
                fallback_policy=fallback_policy,
                fallback_execution=fallback_execution,
                fallback_choice_id=fallback_choice_id,
                provider=provider,
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
            ),
        )

    def resolve_human_prompt(self, prompt: dict, parser, fallback_fn):
        envelope = dict(prompt)
        request_id = str(envelope.get("request_id") or self.next_request_id())
        timeout_ms = max(1, int(envelope.get("timeout_ms", 300000)))
        player_id = int(envelope.get("player_id", 0))
        fallback_policy = str(envelope.get("fallback_policy", "timeout_fallback"))
        public_context = dict(envelope.get("public_context") or {})

        envelope["request_id"] = request_id
        envelope["timeout_ms"] = timeout_ms

        try:
            self._prompt_service.create_prompt(session_id=self._session_id, prompt=envelope)
        except ValueError:
            request_id = self.next_request_id()
            envelope["request_id"] = request_id
            self._prompt_service.create_prompt(session_id=self._session_id, prompt=envelope)

        self.publish("prompt", {**envelope, "provider": "human"})
        self._publish_decision_requested(
            request_id=request_id,
            player_id=player_id,
            request_type=str(envelope.get("request_type", "")),
            fallback_policy=fallback_policy,
            provider="human",
            public_context=public_context,
        )
        self._touch_activity(self._session_id)
        response = self._prompt_service.wait_for_decision(request_id=request_id, timeout_ms=timeout_ms)

        if response is None:
            expired = self._prompt_service.expire_prompt(request_id=request_id, reason="prompt_timeout")
            if expired is None:
                return fallback_fn()
            fallback_result = asyncio.run_coroutine_threadsafe(
                self._fallback_executor(
                    session_id=self._session_id,
                    request_id=request_id,
                    player_id=player_id,
                    fallback_policy=fallback_policy,
                    prompt_payload=envelope,
                ),
                self._loop,
            ).result()
            self.publish(
                "decision_ack",
                build_decision_ack_payload(
                    request_id=request_id,
                    status="stale",
                    player_id=player_id,
                    reason="prompt_timeout",
                    provider="human",
                ),
            )
            self._publish_decision_resolved(
                request_id=request_id,
                player_id=player_id,
                resolution="timeout_fallback",
                choice_id=fallback_result.get("choice_id"),
                provider="human",
                public_context=public_context,
            )
            self._publish_decision_timeout_fallback(
                request_id=request_id,
                player_id=player_id,
                fallback_policy=fallback_policy,
                fallback_execution=fallback_result.get("status"),
                fallback_choice_id=fallback_result.get("choice_id"),
                provider="human",
                public_context=public_context,
            )
            return fallback_fn()

        try:
            parsed = parser(response)
        except Exception:
            self._publish_decision_resolved(
                request_id=request_id,
                player_id=player_id,
                resolution="parser_error_fallback",
                choice_id=str(response.get("choice_id", "")),
                provider="human",
                public_context=public_context,
            )
            return fallback_fn()

        self._publish_decision_resolved(
            request_id=request_id,
            player_id=int(response.get("player_id", player_id)),
            resolution="accepted",
            choice_id=str(response.get("choice_id", "")),
            provider="human",
            public_context=public_context,
        )
        return parsed

    def resolve_ai_decision(
        self,
        *,
        request_type: str,
        player_id: int,
        public_context: dict[str, Any],
        resolver: Callable[[], Any],
        choice_serializer: Callable[[Any], str],
    ) -> Any:
        request_id = self.next_request_id()
        self._publish_decision_requested(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
            fallback_policy="ai",
            provider="ai",
            public_context=public_context,
        )
        result = resolver()
        self._publish_decision_resolved(
            request_id=request_id,
            player_id=player_id,
            resolution="accepted",
            choice_id=choice_serializer(result),
            provider="ai",
            public_context=public_context,
        )
        return result

    def publish(self, message_type: str, payload: dict) -> None:
        fut = asyncio.run_coroutine_threadsafe(
            self._stream_service.publish(self._session_id, message_type, payload),
            self._loop,
        )
        fut.result()
