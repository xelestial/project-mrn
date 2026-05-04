from __future__ import annotations

import asyncio
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Literal

from apps.server.src.services.prompt_fingerprint import ensure_prompt_fingerprint, prompt_fingerprint_mismatch

DecisionProvider = Literal["human", "ai"]

ChoiceSerializer = Callable[[Any], str]
ContextBuilder = Callable[[tuple[Any, ...], dict[str, Any], Any, Any], dict[str, Any]]
LegalChoiceBuilder = Callable[[tuple[Any, ...], dict[str, Any], Any, Any], list[dict[str, Any]]]
ChoiceParser = Callable[[str, tuple[Any, ...], dict[str, Any], Any, Any], Any]


def _ensure_gpt_import_path() -> None:
    root = Path(__file__).resolve().parents[4]
    gpt_dir = root / "GPT"
    claude_dir = root / "CLAUDE"
    gpt_text = str(gpt_dir)
    if gpt_text in sys.path:
        sys.path.remove(gpt_text)
    sys.path.insert(0, gpt_text)
    for name, module in list(sys.modules.items()):
        if isinstance(module, ModuleType) and _module_belongs_to_root(module, claude_dir):
            sys.modules.pop(name, None)


def _module_belongs_to_root(module: ModuleType, root_dir: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str):
        try:
            return Path(module_file).resolve().is_relative_to(root_dir)
        except OSError:
            return False
    module_path = getattr(module, "__path__", None)
    if module_path is None:
        return False
    try:
        return any(Path(entry).resolve().is_relative_to(root_dir) for entry in module_path)
    except OSError:
        return False


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


def _compact_nested_payload(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _build_player_trick_hand_context(player: Any, *, usable_cards: list[Any] | None = None) -> dict[str, Any]:
    full_hand_cards = list(getattr(player, "trick_hand", []) or usable_cards or [])
    hidden_deck_index = getattr(player, "hidden_trick_deck_index", None)
    usable_deck_indices = {
        getattr(card, "deck_index", None)
        for card in (usable_cards or [])
    }
    return {
        "total_hand_count": len(full_hand_cards),
        "hidden_trick_count": sum(
            1
            for card in full_hand_cards
            if hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index
        ),
        "hidden_trick_deck_index": hidden_deck_index,
        "hand_names": [getattr(card, "name", str(card)) for card in full_hand_cards],
        "full_hand": [
            {
                "deck_index": getattr(card, "deck_index", None),
                "name": getattr(card, "name", str(card)),
                "card_description": getattr(card, "description", ""),
                "is_hidden": hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index,
                "is_usable": usable_cards is not None and getattr(card, "deck_index", None) in usable_deck_indices,
            }
            for card in full_hand_cards
        ],
    }


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
    cash_units = int(getattr(result, "cash_units", 0) or 0)
    shard_units = int(getattr(result, "shard_units", 0) or 0)
    coin_units = int(getattr(result, "coin_units", 0) or 0)
    if cash_units <= 0 and shard_units <= 0 and coin_units <= 0:
        return "blocked"
    return f"cash-{cash_units}_shards-{shard_units}_coins-{coin_units}"


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


def _active_character_for_card_index(state: Any, card_index: int) -> tuple[str, str]:
    try:
        _ensure_gpt_import_path()
        from characters import CARD_TO_NAMES, CHARACTERS

        active_name = str((getattr(state, "active_by_card", {}) or {}).get(int(card_index)) or "")
        if active_name:
            ability = str(getattr(CHARACTERS.get(active_name), "ability_text", "") or "")
            return active_name, ability

        names = CARD_TO_NAMES.get(int(card_index), ("", ""))
        fallback_name = next((candidate for candidate in names if candidate), "")
        ability = str(getattr(CHARACTERS.get(fallback_name), "ability_text", "") or "")
        return fallback_name, ability
    except Exception:
        return "", ""


def _public_active_by_card(state: Any) -> dict[int, str] | None:
    raw = getattr(state, "active_by_card", None)
    if not isinstance(raw, dict):
        return None
    active_by_card: dict[int, str] = {}
    for key, value in raw.items():
        try:
            card_index = int(key)
        except Exception:
            continue
        name = str(value or "").strip()
        if card_index >= 1 and name:
            active_by_card[card_index] = name
    return active_by_card or None


def _public_weather_context(state: Any) -> dict[str, str]:
    current_weather = getattr(state, "current_weather", None)
    weather_name = str(getattr(current_weather, "name", "") or "").strip()
    weather_effect = str(getattr(current_weather, "effect", "") or "").strip()
    payload: dict[str, str] = {}
    if weather_name:
        payload["weather_name"] = weather_name
    if weather_effect:
        payload["weather_effect"] = weather_effect
    return payload


def _effect_context_payload(
    *,
    label: str,
    detail: str,
    attribution: str,
    tone: Literal["move", "effect", "economy"],
    source: str,
    intent: str,
    source_player_id: int | None = None,
    source_family: str | None = None,
    source_name: str | None = None,
    resource_delta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _compact_nested_payload(
        {
            "label": label,
            "detail": detail,
            "attribution": attribution,
            "tone": tone,
            "source": source,
            "intent": intent,
            "enhanced": True,
            "source_player_id": source_player_id,
            "source_family": source_family,
            "source_name": source_name,
            "resource_delta": resource_delta,
        }
    )


def _prompt_effect_context(request_type: str, context: dict[str, Any], player: Any) -> dict[str, Any] | None:
    if isinstance(context.get("effect_context"), dict):
        return context["effect_context"]
    player_id = _number_or_none(getattr(player, "player_id", None))
    if request_type == "mark_target":
        actor_name = str(context.get("actor_name") or "").strip()
        if not actor_name:
            return None
        return _effect_context_payload(
            label=actor_name,
            detail=f"{actor_name}의 지목 효과로 다음 대상을 고릅니다.",
            attribution="Character mark",
            tone="effect",
            source="character",
            intent="mark",
            source_player_id=player_id,
            source_family="character",
            source_name=actor_name,
        )
    if request_type == "trick_tile_target":
        card_name = str(context.get("card_name") or "").strip()
        if not card_name:
            return None
        return _effect_context_payload(
            label=card_name,
            detail=f"{card_name} 효과로 대상 타일을 고릅니다.",
            attribution="Trick effect",
            tone="effect",
            source="trick",
            intent="target",
            source_player_id=player_id,
            source_family="trick",
            source_name=card_name,
        )
    if request_type == "lap_reward":
        return _effect_context_payload(
            label="LAP reward",
            detail="The player crossed the start tile and must choose the lap reward allocation.",
            attribution="Movement result",
            tone="economy",
            source="move",
            intent="gain",
            source_player_id=player_id,
            source_family="movement",
            source_name="lap_reward",
        )
    if request_type == "geo_bonus":
        actor_name = str(context.get("actor_name") or "").strip()
        if not actor_name:
            return None
        return _effect_context_payload(
            label=actor_name,
            detail=f"{actor_name} 효과 보상을 고릅니다.",
            attribution="Character effect",
            tone="economy",
            source="character",
            intent="gain",
            source_player_id=player_id,
            source_family="character",
            source_name=actor_name,
        )
    if request_type == "burden_exchange":
        card_name = str(context.get("card_name") or "").strip() or "Burden"
        return _effect_context_payload(
            label=card_name,
            detail="Supply threshold reached; choose the burden card to resolve.",
            attribution="Supply threshold",
            tone="economy",
            source="trick",
            intent="cost",
            source_player_id=player_id,
            source_family="trick",
            source_name=card_name,
        )
    return None


def _build_card_choice_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del player
    cards = _arg_or_kw(args, kwargs, 2, "offered_cards") or kwargs.get("card_choices")
    if isinstance(cards, list):
        names: list[str] = []
        abilities: list[str] = []
        for card_index in cards:
            name, ability = _active_character_for_card_index(state, int(card_index))
            if name:
                names.append(name)
            if ability:
                abilities.append(ability)
        return {
            "choice_count": len(cards),
            "choice_names": names,
            "choice_abilities": abilities,
        }
    return {}


def _build_draft_choice_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    context = _build_card_choice_context(args, kwargs, state, player)
    offered_cards = _arg_or_kw(args, kwargs, 2, "offered_cards") or []
    drafted_cards = list(getattr(player, "drafted_cards", []) or [])
    draft_phase = len(drafted_cards) + 1
    context.update(
        {
            "offered_count": len(offered_cards) if isinstance(offered_cards, list) else 0,
            "offered_names": context.get("choice_names", []),
            "offered_abilities": context.get("choice_abilities", []),
            "draft_phase": draft_phase,
            "draft_phase_label": f"draft_phase_{draft_phase}",
        }
    )
    context.update(_build_player_trick_hand_context(player))
    return context


def _build_final_character_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    context = _build_card_choice_context(args, kwargs, state, player)
    context["final_choice"] = True
    context["decision_phase_label"] = "final_character_confirmation"
    context.update(_build_player_trick_hand_context(player))
    return context


def _build_purchase_tile_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    def _legal_adjacent_purchase_targets(anchor_pos: int) -> list[int]:
        try:
            block_ids = list(getattr(state, "block_ids", []) or [])
            board = list(getattr(state, "board", []) or [])
            tile_owner = list(getattr(state, "tile_owner", []) or [])
            if anchor_pos < 0 or anchor_pos >= len(block_ids):
                return []
            block_id = block_ids[anchor_pos]
            if block_id < 0:
                return []
            candidates: list[int] = []
            for idx, bid in enumerate(block_ids):
                if idx == anchor_pos or bid != block_id:
                    continue
                if idx >= len(board) or idx >= len(tile_owner):
                    continue
                if abs(idx - anchor_pos) != 1 or tile_owner[idx] is not None:
                    continue
                cell_kind = getattr(board[idx], "name", str(board[idx]))
                if cell_kind not in {"T2", "T3"}:
                    continue
                candidates.append(int(idx))
            return candidates
        except Exception:
            return []

    pos = _arg_or_kw(args, kwargs, 2, "pos")
    cell = _arg_or_kw(args, kwargs, 3, "cell")
    tile = None
    if isinstance(pos, int):
        try:
            tiles = getattr(state, "tiles", None)
            if tiles is not None and 0 <= pos < len(tiles):
                tile = tiles[pos]
        except Exception:
            tile = None
    zone = getattr(tile, "zone_color", None) if tile is not None else None
    purchase_cost = getattr(tile, "purchase_cost", None) if tile is not None else getattr(cell, "purchase_cost", None)
    rent_cost = getattr(tile, "rent_cost", None) if tile is not None else getattr(cell, "rent_cost", None)
    score_coins = getattr(tile, "score_coins", None) if tile is not None else None
    tile_kind = getattr(getattr(tile, "kind", None), "name", None) if tile is not None else getattr(cell, "name", None)
    source = kwargs.get("source", "landing")
    landing_tile_index = getattr(player, "position", None) if isinstance(getattr(player, "position", None), int) else None
    candidate_tiles: list[int] = []
    if source in {"matchmaker_adjacent", "adjacent_extra"}:
        if isinstance(landing_tile_index, int):
            candidate_tiles = _legal_adjacent_purchase_targets(landing_tile_index)
        elif isinstance(pos, int):
            candidate_tiles = _legal_adjacent_purchase_targets(pos)
    context = {
        "tile_index": pos,
        "cost": _arg_or_kw(args, kwargs, 4, "cost"),
        "source": source,
        "tile_zone": zone,
        "tile_kind": tile_kind,
        "tile_purchase_cost": purchase_cost,
        "tile_rent_cost": rent_cost,
        "tile_score_coins": score_coins,
        "player_cash": getattr(player, "cash", None),
        "player_shards": getattr(player, "shards", None),
        "player_position": getattr(player, "position", None),
    }
    if landing_tile_index is not None:
        context["landing_tile_index"] = landing_tile_index
    if candidate_tiles:
        context["candidate_tiles"] = candidate_tiles
    return context


def _build_burden_exchange_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del kwargs
    card = _arg_or_kw(args, {}, 2, "card")
    next_threshold = _number_or_none(getattr(state, "next_supply_f_threshold", None))
    current_threshold = next_threshold - 3 if next_threshold is not None else None
    burden_cards = [
        hand_card
        for hand_card in list(getattr(player, "trick_hand", []) or [])
        if bool(getattr(hand_card, "is_burden", False))
    ]
    burden_cards_payload = [
        {
            "deck_index": getattr(hand_card, "deck_index", None),
            "name": getattr(hand_card, "name", None),
            "card_description": getattr(hand_card, "description", None),
            "burden_cost": getattr(hand_card, "burden_cost", None),
            "is_current_target": getattr(hand_card, "deck_index", None) == getattr(card, "deck_index", None),
        }
        for hand_card in burden_cards
    ]
    return {
        "card_name": getattr(card, "name", None),
        "card_description": getattr(card, "description", None),
        "card_deck_index": getattr(card, "deck_index", None),
        "burden_cost": getattr(card, "burden_cost", None),
        "player_hand_coins": getattr(player, "hand_coins", None),
        "burden_card_count": len(burden_cards),
        "burden_cards": burden_cards_payload,
        "decision_phase": "trick_supply",
        "decision_reason": "supply_threshold",
        "supply_threshold": current_threshold if current_threshold is None or current_threshold >= 0 else None,
        "current_f_value": getattr(state, "f_value", None),
    }


def _build_mark_target_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    actor_name = _arg_or_kw(args, kwargs, 2, "actor_name")
    context: dict[str, Any] = {
        "actor_name": actor_name,
        "target_rule": "future_turn_unrevealed_only",
    }
    try:
        _ensure_gpt_import_path()
        from viewer.human_policy import _is_mark_skill_blocked_by_uhsa, _legal_mark_target_public_choices

        if _is_mark_skill_blocked_by_uhsa(state, player, actor_name):
            context["blocked_by_eosa"] = True
            context["target_count"] = 0
            return context
        legal_targets = _legal_mark_target_public_choices(state, player)
    except Exception:
        legal_targets = []
    context["target_count"] = len(legal_targets)
    context["target_pairs"] = [
        {
            "target_character": str(target.get("target_character", "") or ""),
            "target_card_no": int(target.get("card_no", -1)),
        }
        for target in legal_targets
        if target.get("target_character") and isinstance(target.get("card_no"), int)
    ]
    context["no_legal_targets"] = len(context["target_pairs"]) == 0
    return context


def _build_active_flip_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    flippable_cards = _arg_or_kw(args, kwargs, 2, "flippable_cards")
    if isinstance(flippable_cards, list):
        return {
            "flip_count": len(flippable_cards),
            "flip_mode": "multi",
            "flip_submit_mode": "finish_once",
            "finish_choice_id": "none",
            "batch_payload_key": "selected_choice_ids",
        }
    return {}


def _build_hidden_trick_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    hand = _arg_or_kw(args, kwargs, 2, "hand")
    if isinstance(hand, list):
        full_hand_cards = list(getattr(player, "trick_hand", []) or hand)
        hidden_deck_index = getattr(player, "hidden_trick_deck_index", None)
        usable_deck_indices = {getattr(card, "deck_index", None) for card in hand}
        return {
            "hand_count": len(hand),
            "hidden_trick_count": sum(
                1
                for card in full_hand_cards
                if hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index
            ),
            "hidden_trick_deck_index": hidden_deck_index,
            "hand_names": [getattr(card, "name", str(card)) for card in hand],
            "full_hand": [
                {
                    "deck_index": getattr(card, "deck_index", None),
                    "name": getattr(card, "name", str(card)),
                    "card_description": getattr(card, "description", ""),
                    "is_hidden": hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index,
                    "is_usable": getattr(card, "deck_index", None) in usable_deck_indices,
                }
                for card in full_hand_cards
            ],
            "selection_required": True,
        }
    return {}


def _build_trick_redraw_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    hand = _arg_or_kw(args, kwargs, 2, "hand")
    source = str(_arg_or_kw(args, kwargs, 3, "source") or "")
    if isinstance(hand, list):
        return {
            "hand_count": len(hand),
            "source": source,
            "hand_names": [getattr(card, "name", str(card)) for card in hand],
        }
    return {"source": source} if source else {}


def _build_dice_card_value_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state
    candidates = _arg_or_kw(args, kwargs, 2, "candidates")
    source = str(_arg_or_kw(args, kwargs, 3, "source") or "")
    values = [int(value) for value in candidates if isinstance(value, int)] if isinstance(candidates, list) else []
    return _trim_public_context(
        {
            "candidate_count": len(values),
            "candidate_values": values,
            "source": source,
            "player_position": getattr(player, "position", None),
            "player_cash": getattr(player, "cash", None),
        }
    )


def _build_trick_to_use_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    hand = _arg_or_kw(args, kwargs, 2, "hand")
    if isinstance(hand, list):
        full_hand_cards = list(getattr(player, "trick_hand", []) or hand)
        hidden_deck_index = getattr(player, "hidden_trick_deck_index", None)
        usable_deck_indices = {getattr(card, "deck_index", None) for card in hand}
        return {
            "hand_count": len(hand),
            "usable_hand_count": len(hand),
            "total_hand_count": len(full_hand_cards),
            "hidden_trick_count": sum(
                1
                for card in full_hand_cards
                if hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index
            ),
            "hidden_trick_deck_index": hidden_deck_index,
            "hand_names": [getattr(card, "name", str(card)) for card in full_hand_cards],
            "full_hand": [
                {
                    "deck_index": getattr(card, "deck_index", None),
                    "name": getattr(card, "name", str(card)),
                    "card_description": getattr(card, "description", ""),
                    "is_hidden": hidden_deck_index is not None and getattr(card, "deck_index", None) == hidden_deck_index,
                    "is_usable": getattr(card, "deck_index", None) in usable_deck_indices,
                }
                for card in full_hand_cards
            ],
        }
    return {}


def _build_specific_trick_reward_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state
    choices = _arg_or_kw(args, kwargs, 2, "choices")
    if isinstance(choices, list):
        reward_cards = [
            {
                "deck_index": getattr(card, "deck_index", None),
                "name": getattr(card, "name", str(card)),
                "card_description": getattr(card, "description", ""),
            }
            for card in choices
            if getattr(card, "deck_index", None) is not None
        ]
        return {
            "player_cash": getattr(player, "cash", None),
            "player_position": getattr(player, "position", None),
            "player_shards": getattr(player, "shards", None),
            "reward_count": len(reward_cards),
            "reward_names": [str(card["name"]) for card in reward_cards],
            "reward_cards": reward_cards,
        }
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
        owned_tile_indices = [int(idx) for idx in owned_tiles if isinstance(idx, int)]
        return {
            "owned_tile_count": len(owned_tile_indices),
            "owned_tile_indices": owned_tile_indices,
            "player_cash": getattr(player, "cash", None),
        }
    return {}


def _build_doctrine_relief_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state
    candidates = _arg_or_kw(args, kwargs, 2, "candidates")
    if isinstance(candidates, list):
        return {
            "candidate_count": len(candidates),
            "candidate_player_ids": [getattr(candidate, "player_id", None) for candidate in candidates],
            "player_cash": getattr(player, "cash", None),
            "player_shards": getattr(player, "shards", None),
        }
    return {}


def _build_geo_bonus_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state
    actor_name = str(_arg_or_kw(args, kwargs, 2, "actor_name") or "")
    return {
        "actor_name": actor_name,
        "player_cash": getattr(player, "cash", None),
        "player_shards": getattr(player, "shards", None),
        "player_hand_coins": getattr(player, "hand_score_coins", None),
    }


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
    choices: list[dict[str, Any]] = []
    max_cash = min(cash_pool, budget // max(1, int(rules.cash_point_cost)))
    max_shards = min(shards_pool, budget // max(1, int(rules.shards_point_cost)))
    max_coins = min(coins_pool, budget // max(1, int(rules.coins_point_cost)))
    for cash_units in range(0, max_cash + 1):
        cash_points = cash_units * int(rules.cash_point_cost)
        if cash_points > budget:
            break
        shard_cap = min(shards_pool, (budget - cash_points) // max(1, int(rules.shards_point_cost)))
        for shard_units in range(0, shard_cap + 1):
            spent = cash_points + shard_units * int(rules.shards_point_cost)
            coin_cap = min(coins_pool, (budget - spent) // max(1, int(rules.coins_point_cost)))
            for coin_units in range(0, coin_cap + 1):
                total_points = spent + coin_units * int(rules.coins_point_cost)
                if total_points <= 0 or total_points > budget:
                    continue
                choice = "mixed"
                if cash_units > 0 and shard_units == 0 and coin_units == 0:
                    choice = "cash"
                elif shard_units > 0 and cash_units == 0 and coin_units == 0:
                    choice = "shards"
                elif coin_units > 0 and cash_units == 0 and shard_units == 0:
                    choice = "coins"
                title_parts: list[str] = []
                if cash_units > 0:
                    title_parts.append(f"Cash +{cash_units}")
                if shard_units > 0:
                    title_parts.append(f"Shards +{shard_units}")
                if coin_units > 0:
                    title_parts.append(f"Coins +{coin_units}")
                choices.append(
                    _choice_payload(
                        f"cash-{cash_units}_shards-{shard_units}_coins-{coin_units}",
                        title=" / ".join(title_parts),
                        description=f"Spend {total_points}/{budget} reward points",
                        value={
                            "choice": choice,
                            "cash_units": cash_units,
                            "shard_units": shard_units,
                            "coin_units": coin_units,
                            "spent_points": total_points,
                            "points_budget": budget,
                        },
                    )
                )
    choices.sort(
        key=lambda item: (
            int(((item.get("value") or {}).get("spent_points") or 0)),
            int(((item.get("value") or {}).get("cash_units") or 0)),
            int(((item.get("value") or {}).get("shard_units") or 0)),
            int(((item.get("value") or {}).get("coin_units") or 0)),
        ),
        reverse=True,
    )
    return choices


def _build_lap_reward_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del args, kwargs
    rules = state.config.rules.lap_reward
    return {
        "budget": int(rules.points_budget),
        "pools": {
            "cash": int(getattr(state, "lap_reward_cash_pool_remaining", rules.cash_pool)),
            "shards": int(getattr(state, "lap_reward_shards_pool_remaining", rules.shards_pool)),
            "coins": int(getattr(state, "lap_reward_coins_pool_remaining", rules.coins_pool)),
        },
        "cash_point_cost": int(rules.cash_point_cost),
        "shards_point_cost": int(rules.shards_point_cost),
        "coins_point_cost": int(rules.coins_point_cost),
        "player_cash": getattr(player, "cash", None),
        "player_shards": getattr(player, "shards", None),
        "player_hand_coins": getattr(player, "hand_coins", None),
        "player_placed_coins": getattr(player, "score_coins_placed", None),
        "player_total_score": int(getattr(player, "hand_coins", 0) or 0) + int(getattr(player, "score_coins_placed", 0) or 0),
        "player_owned_tile_count": getattr(player, "tiles_owned", None),
    }


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
        name, ability = _active_character_for_card_index(state, int(card_index))
        title = name or str(card_index)
        choices.append(
            _choice_payload(
                str(card_index),
                title=title,
                description=ability or None,
                value={"card_index": int(card_index), "character_name": title, "character_ability": ability},
            )
        )
    return choices


def _parse_draft_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    return int(choice_id)


def _parse_final_character_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del player
    choices = _arg_or_kw(args, kwargs, 2, "card_choices") or []
    for card_index in choices:
        if str(card_index) != str(choice_id):
            continue
        name, _ability = _active_character_for_card_index(state, int(card_index))
        if name:
            return name
    raise ValueError("invalid_final_character_choice_id")


def _build_integer_choices(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
    index: int,
    key: str,
    *,
    value_key: str,
    title_prefix: str,
    description_prefix: str,
    include_none: bool,
) -> list[dict[str, Any]]:
    del state, player
    values = list(_arg_or_kw(args, kwargs, index, key) or [])
    choices: list[dict[str, Any]] = []
    if include_none:
        choices.append(_choice_payload("none", title="Skip"))
    for raw_value in values:
        if not isinstance(raw_value, int):
            continue
        choices.append(
            _choice_payload(
                str(raw_value),
                title=f"{title_prefix} {raw_value}",
                description=f"{description_prefix} {raw_value}.",
                value={value_key: raw_value},
            )
        )
    return choices


def _parse_integer_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    if choice_id == "none":
        return None
    return int(choice_id)


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
        _ensure_gpt_import_path()
        from viewer.human_policy import _is_mark_skill_blocked_by_uhsa, _legal_mark_target_public_choices

        if _is_mark_skill_blocked_by_uhsa(state, player, actor_name):
            return [_choice_payload("none", title="No mark")]
        legal_targets = _legal_mark_target_public_choices(state, player)
    except Exception:
        legal_targets = []
    choices = [_choice_payload("none", title="No mark")]
    for target in legal_targets:
        character = str(target.get("target_character", "") or "")
        card_no = target.get("card_no")
        if not character or not isinstance(card_no, int):
            continue
        choices.append(
            _choice_payload(
                character,
                title=character,
                value={"target_character": character, "target_card_no": card_no},
            )
        )
    return choices


def _parse_mark_target_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    if choice_id == "none":
        return None
    for choice in _build_mark_target_choices(args, kwargs, state, player):
        if choice.get("choice_id") == choice_id:
            value = dict(choice.get("value") or {})
            target_character = value.get("target_character")
            return str(target_character) if target_character else None
    raise ValueError("invalid_mark_target_choice_id")


def _build_coin_placement_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del args, kwargs
    tile_owner = getattr(state, "tile_owner", None)
    if tile_owner is None:
        owned = [int(idx) for idx in getattr(player, "visited_owned_tile_indices", [])]
    else:
        owned = [int(idx) for idx in getattr(player, "visited_owned_tile_indices", []) if tile_owner[int(idx)] == getattr(player, "player_id", None)]
    return [
        _choice_payload(
            str(idx),
            title=f"Tile {idx}",
            description=f"Place one score point on tile {idx}.",
            value={"tile_index": idx},
        )
        for idx in owned
    ]


def _parse_coin_placement_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    return int(choice_id)


def _build_trick_tile_target_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    state: Any,
    player: Any,
) -> dict[str, Any]:
    del state, player
    card_name = str(_arg_or_kw(args, kwargs, 2, "card_name") or "")
    candidate_tiles = list(_arg_or_kw(args, kwargs, 3, "candidate_tiles") or [])
    target_scope = str(_arg_or_kw(args, kwargs, 4, "target_scope") or "")
    return {
        "card_name": card_name,
        "candidate_count": len(candidate_tiles),
        "candidate_tiles": [int(tile) for tile in candidate_tiles if isinstance(tile, int)],
        "target_scope": target_scope,
    }


def _build_trick_tile_target_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del state, player
    candidate_tiles = list(_arg_or_kw(args, kwargs, 3, "candidate_tiles") or [])
    choices: list[dict[str, Any]] = []
    for tile_index in candidate_tiles:
        if not isinstance(tile_index, int):
            continue
        choices.append(
            _choice_payload(
                str(tile_index),
                title=f"Tile {tile_index + 1}",
                value={"tile_index": tile_index},
            )
        )
    return choices


def _parse_trick_tile_target_choice(choice_id: str, args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> Any:
    del args, kwargs, state, player
    return int(choice_id)


def _build_geo_bonus_choices(args: tuple[Any, ...], kwargs: dict[str, Any], state: Any, player: Any) -> list[dict[str, Any]]:
    del args, kwargs, state, player
    return [
        _choice_payload("cash", title="Cash +1", description="Gain 1 cash.", value={"choice": "cash"}),
        _choice_payload("shards", title="Shards +1", description="Gain 1 shard.", value={"choice": "shards"}),
        _choice_payload("coins", title="Coins +1", description="Gain 1 score point.", value={"choice": "coins"}),
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
                description=f"Remove 1 burden from P{player_id + 1}.",
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
    flippable_cards = list(_arg_or_kw(args, kwargs, 2, "flippable_cards") or [])
    choices = [_choice_payload("none", title="Finish flipping")]
    for card_index in flippable_cards:
        current_name, flipped_name = _active_character_for_card_index(state, int(card_index))
        choices.append(
            _choice_payload(
                str(card_index),
                title=f"{current_name or f'Card {card_index}'} -> {flipped_name or 'Flip'}",
                value={
                    "card_index": int(card_index),
                    "current_name": current_name,
                    "flipped_name": flipped_name,
                },
            )
        )
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
            title=f"{getattr(card, 'name', str(getattr(card, 'deck_index', '')))} #{getattr(card, 'deck_index', '')}",
            description=getattr(card, "description", ""),
            value={"deck_index": getattr(card, "deck_index", None), "card_description": getattr(card, "description", "")},
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
    "choose_lap_reward": DecisionMethodSpec("lap_reward", _serialize_lap_reward_choice, _build_lap_reward_context, legal_choice_builder=_build_lap_reward_legal_choices, choice_parser=_parse_lap_reward_choice),
    "choose_draft_card": DecisionMethodSpec("draft_card", _serialize_string_choice, _build_draft_choice_context, lambda args, kwargs, state, player: _build_card_index_choices(args, kwargs, state, player, 2, "offered_cards"), _parse_draft_choice),
    "choose_final_character": DecisionMethodSpec(
        "final_character",
        _serialize_string_choice,
        _build_final_character_context,
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
    "choose_trick_redraw_card": DecisionMethodSpec(
        "trick_redraw_card",
        _serialize_trick_like_choice,
        _build_trick_redraw_context,
        lambda args, kwargs, state, player: _build_hand_choices(args, kwargs, state, player, 2, "hand", include_none=True),
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
    "choose_trick_tile_target": DecisionMethodSpec(
        "trick_tile_target",
        _serialize_string_choice,
        _build_trick_tile_target_context,
        _build_trick_tile_target_choices,
        _parse_trick_tile_target_choice,
    ),
    "choose_geo_bonus": DecisionMethodSpec(
        "geo_bonus",
        _serialize_string_choice,
        _build_geo_bonus_context,
        legal_choice_builder=_build_geo_bonus_choices,
        choice_parser=_parse_string_choice,
    ),
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
    "choose_burden_exchange_on_supply": DecisionMethodSpec(
        "burden_exchange",
        _serialize_yes_no_choice,
        _build_burden_exchange_context,
        _build_burden_exchange_choices,
        _parse_yes_no_choice,
    ),
    "choose_pabal_dice_mode": DecisionMethodSpec(
        "pabal_dice_mode",
        _serialize_string_choice,
        legal_choice_builder=lambda args, kwargs, state, player: [
            _choice_payload("plus_one", title="Roll three dice", description="Use the default three-die roll this turn.", value={"dice_mode": "plus_one"}),
            _choice_payload("minus_one", title="Roll one die", description="Reduce the roll to one die this turn.", value={"dice_mode": "minus_one"}),
        ],
        choice_parser=_parse_string_choice,
    ),
    "choose_dice_card_value": DecisionMethodSpec(
        "dice_card_value",
        _serialize_default_choice,
        _build_dice_card_value_context,
        lambda args, kwargs, state, player: _build_integer_choices(
            args,
            kwargs,
            state,
            player,
            2,
            "candidates",
            value_key="dice_value",
            title_prefix="Dice card",
            description_prefix="Recover dice card",
            include_none=False,
        ),
        _parse_integer_choice,
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
        "player_hand_coins": getattr(player, "hand_coins", None),
        "player_placed_coins": getattr(player, "score_coins_placed", None),
        "player_total_score": (
            int(getattr(player, "hand_coins", 0) or 0) + int(getattr(player, "score_coins_placed", 0) or 0)
            if player is not None
            else None
        ),
        "player_owned_tile_count": getattr(player, "tiles_owned", None),
    }
    active_by_card = _public_active_by_card(state)
    if active_by_card:
        context["active_by_card"] = active_by_card
    context.update(_public_weather_context(state))
    spec = _decision_method_spec_for_method(method_name)
    if spec.public_context_builder is not None:
        context.update(spec.public_context_builder(args, kwargs, state, player))
    effect_context = _prompt_effect_context(spec.request_type, context, player)
    if effect_context:
        context["effect_context"] = effect_context

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
    raw_args = tuple(getattr(request, "args", ()) or ())
    state = getattr(request, "state", None)
    player = getattr(request, "player", None)
    if state is not None or player is not None:
        if len(raw_args) >= 2 and raw_args[0] is state and raw_args[1] is player:
            args = raw_args
        else:
            prefix: tuple[Any, ...] = ()
            if state is not None:
                prefix += (state,)
            if player is not None:
                prefix += (player,)
            args = prefix + raw_args
    else:
        args = raw_args
    return build_decision_invocation(
        str(getattr(request, "decision_name")),
        args,
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
    public_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "event_type": "decision_requested",
        "request_id": request_id,
        "player_id": player_id,
        "request_type": request_type,
        "fallback_policy": fallback_policy,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }
    if public_context:
        payload["public_context"] = dict(public_context)
    return payload


def build_decision_resolved_payload(
    *,
    request_id: str,
    player_id: int,
    request_type: str | None,
    resolution: str,
    choice_id: str | None,
    provider: DecisionProvider,
    round_index: int | None = None,
    turn_index: int | None = None,
    public_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "event_type": "decision_resolved",
        "request_id": request_id,
        "player_id": player_id,
        "request_type": request_type,
        "resolution": resolution,
        "choice_id": choice_id,
        "provider": provider,
        "round_index": round_index,
        "turn_index": turn_index,
    }
    if public_context:
        payload["public_context"] = dict(public_context)
    return payload


def build_decision_timeout_fallback_payload(
    *,
    request_id: str,
    player_id: int,
    request_type: str | None,
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
        "request_type": request_type,
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
        ai_decision_delay_ms: int = 0,
        blocking_human_prompts: bool = True,
    ) -> None:
        self._session_id = session_id
        self._prompt_service = prompt_service
        self._stream_service = stream_service
        self._loop = loop
        self._touch_activity = touch_activity
        self._fallback_executor = fallback_executor
        self._request_seq = 0
        self._ai_decision_delay_ms = max(0, int(ai_decision_delay_ms))
        self._blocking_human_prompts = bool(blocking_human_prompts)

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
                public_context=public_context,
            ),
        )

    def _publish_decision_resolved(
        self,
        *,
        request_id: str,
        player_id: int,
        request_type: str,
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
                request_type=request_type,
                resolution=resolution,
                choice_id=choice_id,
                provider=provider,
                round_index=public_context.get("round_index"),
                turn_index=public_context.get("turn_index"),
                public_context=public_context,
            ),
        )

    def _publish_decision_timeout_fallback(
        self,
        *,
        request_id: str,
        player_id: int,
        request_type: str,
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
                request_type=request_type,
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
        timeout_ms = max(1, int(envelope.get("timeout_ms", 300000)))
        player_id = int(envelope.get("player_id", 0))
        fallback_policy = str(envelope.get("fallback_policy", "timeout_fallback"))
        request_type = str(envelope.get("request_type", ""))
        public_context = dict(envelope.get("public_context") or {})
        request_id = str(envelope.get("request_id") or self._stable_prompt_request_id(envelope, public_context))

        envelope["request_id"] = request_id
        envelope["timeout_ms"] = timeout_ms
        envelope = ensure_prompt_fingerprint(envelope)

        replayed_response = self._prompt_service.wait_for_decision(request_id=request_id, timeout_ms=1)
        if replayed_response is not None:
            self._require_matching_prompt_fingerprint(
                request_id=request_id,
                player_id=player_id,
                request_type=request_type,
                public_context=public_context,
                prompt_payload=envelope,
                response=replayed_response,
            )
            return self._parse_human_response(
                request_id=request_id,
                player_id=player_id,
                request_type=request_type,
                public_context=public_context,
                response=replayed_response,
                parser=parser,
                fallback_fn=fallback_fn,
            )

        try:
            self._prompt_service.create_prompt(session_id=self._session_id, prompt=envelope)
        except ValueError as exc:
            if str(exc) == "prompt_fingerprint_mismatch":
                raise PromptFingerprintMismatch(request_id=request_id) from exc
            if not self._blocking_human_prompts:
                raise PromptRequired(envelope)
            request_id = self.next_request_id()
            envelope["request_id"] = request_id
            envelope = ensure_prompt_fingerprint(envelope)
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
        if not self._blocking_human_prompts:
            raise PromptRequired(envelope)
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
                request_type=request_type,
                resolution="timeout_fallback",
                choice_id=fallback_result.get("choice_id"),
                provider="human",
                public_context=public_context,
            )
            self._publish_decision_timeout_fallback(
                request_id=request_id,
                player_id=player_id,
                request_type=request_type,
                fallback_policy=fallback_policy,
                fallback_execution=fallback_result.get("status"),
                fallback_choice_id=fallback_result.get("choice_id"),
                provider="human",
                public_context=public_context,
            )
            return fallback_fn()

        self._require_matching_prompt_fingerprint(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
            public_context=public_context,
            prompt_payload=envelope,
            response=response,
        )
        return self._parse_human_response(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
            public_context=public_context,
            response=response,
            parser=parser,
            fallback_fn=fallback_fn,
        )

    def _stable_prompt_request_id(self, envelope: dict[str, Any], public_context: dict[str, Any]) -> str:
        request_type = str(envelope.get("request_type") or "prompt")
        player_id = int(envelope.get("player_id", 0) or 0)
        round_index = int(public_context.get("round_index", 0) or 0)
        turn_index = int(public_context.get("turn_index", 0) or 0)
        prompt_instance_id = int(envelope.get("prompt_instance_id", 0) or 0)
        return f"{self._session_id}:r{round_index}:t{turn_index}:p{player_id}:{request_type}:{prompt_instance_id}"

    def _require_matching_prompt_fingerprint(
        self,
        *,
        request_id: str,
        player_id: int,
        request_type: str,
        public_context: dict[str, Any],
        prompt_payload: dict[str, Any],
        response: dict[str, Any],
    ) -> None:
        if not prompt_fingerprint_mismatch(prompt_payload, response):
            return
        self._publish_decision_resolved(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
            resolution="prompt_fingerprint_mismatch",
            choice_id=str(response.get("choice_id", "")),
            provider="human",
            public_context=public_context,
        )
        raise PromptFingerprintMismatch(request_id=request_id)

    def _parse_human_response(
        self,
        *,
        request_id: str,
        player_id: int,
        request_type: str,
        public_context: dict[str, Any],
        response: dict,
        parser,
        fallback_fn,
    ):
        try:
            parsed = parser(response)
        except Exception:
            self._publish_decision_resolved(
                request_id=request_id,
                player_id=player_id,
                request_type=request_type,
                resolution="parser_error_fallback",
                choice_id=str(response.get("choice_id", "")),
                provider="human",
                public_context=public_context,
            )
            return fallback_fn()

        self._publish_decision_resolved(
            request_id=request_id,
            player_id=int(response.get("player_id", player_id)),
            request_type=request_type,
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
        if self._ai_decision_delay_ms > 0:
            time.sleep(self._ai_decision_delay_ms / 1000.0)
        result = resolver()
        self._publish_decision_resolved(
            request_id=request_id,
            player_id=player_id,
            request_type=request_type,
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


class PromptRequired(RuntimeError):
    """Raised when a transition reaches a human prompt boundary."""

    def __init__(self, prompt: dict[str, Any]) -> None:
        super().__init__("prompt_required")
        self.prompt = dict(prompt)


class PromptFingerprintMismatch(RuntimeError):
    """Raised when a decision is replayed against a different prompt contract."""

    def __init__(self, *, request_id: str) -> None:
        super().__init__(f"prompt_fingerprint_mismatch:{request_id}")
        self.request_id = request_id
