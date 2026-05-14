from __future__ import annotations

from typing import Any

from .types import (
    ActivePromptBehaviorViewState,
    ActivePromptViewState,
    PromptEffectContextViewState,
    PromptSurfaceCoinPlacementOptionViewState,
    PromptSurfaceCoinPlacementViewState,
    PromptChoiceItemViewState,
    PromptSurfaceDoctrineReliefOptionViewState,
    PromptSurfaceDoctrineReliefViewState,
    PromptFeedbackViewState,
    PromptSurfaceActiveFlipOptionViewState,
    PromptSurfaceActiveFlipViewState,
    PromptSurfaceBurdenCardViewState,
    PromptSurfaceBurdenExchangeViewState,
    PromptSurfaceCharacterPickOptionViewState,
    PromptSurfaceCharacterPickViewState,
    PromptSurfaceGeoBonusOptionViewState,
    PromptSurfaceGeoBonusViewState,
    PromptSurfaceHandChoiceCardViewState,
    PromptSurfaceHandChoiceViewState,
    PromptSurfaceLapRewardOptionViewState,
    PromptSurfaceLapRewardViewState,
    PromptSurfaceMarkTargetCandidateViewState,
    PromptSurfaceMarkTargetViewState,
    PromptSurfaceMovementCardChoiceViewState,
    PromptSurfaceMovementViewState,
    PromptSurfacePabalDiceModeOptionViewState,
    PromptSurfacePabalDiceModeViewState,
    PromptSurfacePurchaseTileViewState,
    PromptSurfaceRunawayStepViewState,
    PromptSurfaceSpecificTrickRewardOptionViewState,
    PromptSurfaceSpecificTrickRewardViewState,
    PromptSurfaceTileTargetOptionViewState,
    PromptSurfaceTrickTileTargetViewState,
    PromptSurfaceViewState,
    PromptViewState,
)


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _string(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _legacy_prompt_player_id(active_prompt: dict[str, Any]) -> int | None:
    return _number(active_prompt.get("legacy_player_id")) or _number(active_prompt.get("player_id"))


def _protocol_prompt_player_id(active_prompt: dict[str, Any]) -> int | str | None:
    player_id = active_prompt.get("player_id")
    public_player_id = _string(active_prompt.get("public_player_id"))
    if public_player_id:
        return public_player_id
    if isinstance(player_id, str) and player_id.strip():
        return player_id.strip()
    return _legacy_prompt_player_id(active_prompt)


def _active_prompt_primary_identity(active_prompt: dict[str, Any]) -> tuple[int | str, str] | None:
    player_id = active_prompt.get("player_id")
    public_player_id = _string(active_prompt.get("public_player_id"))
    legacy_player_id = _legacy_prompt_player_id(active_prompt)
    if public_player_id:
        return public_player_id, "public"
    if isinstance(player_id, str) and player_id.strip():
        return player_id.strip(), "protocol"
    if legacy_player_id is not None:
        return legacy_player_id, "legacy"
    return None


def _secondary_choice(choice_id: str, item: dict[str, Any]) -> bool:
    priority = item.get("priority")
    return item.get("secondary") is True or priority in {"secondary", "passive"} or choice_id in {"none", "no"}


def _choice_value(item: dict[str, Any]) -> dict[str, object] | None:
    value = _record(item.get("value"))
    return {key: val for key, val in value.items()} if value else None


def _choice_description(item: dict[str, Any], value: dict[str, object] | None) -> str:
    explicit = _string(item.get("description"))
    if explicit:
        return explicit
    if value:
        card_description = _string(value.get("card_description"))
        if card_description:
            return card_description
        return _string(value.get("description"))
    return ""


def _choice_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _parse_choices(raw: Any) -> list[PromptChoiceItemViewState]:
    parsed: list[PromptChoiceItemViewState] = []
    for choice in _choice_list(raw):
        choice_id = _string(choice.get("choice_id"))
        if not choice_id:
            continue
        value = _choice_value(choice)
        parsed.append(
            {
                "choice_id": choice_id,
                "title": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, value),
                "value": value,
                "secondary": _secondary_choice(choice_id, choice),
            }
        )
    return parsed


def _lap_reward_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceLapRewardViewState | None:
    budget = _number(public_context.get("budget"))
    pools = _record(public_context.get("pools")) or {}
    cash_pool = _number(pools.get("cash"))
    shards_pool = _number(pools.get("shards"))
    coins_pool = _number(pools.get("coins"))
    cash_point_cost = _number(public_context.get("cash_point_cost"))
    shards_point_cost = _number(public_context.get("shards_point_cost"))
    coins_point_cost = _number(public_context.get("coins_point_cost"))
    if (
        budget is None
        or cash_pool is None
        or shards_pool is None
        or coins_pool is None
        or cash_point_cost is None
        or shards_point_cost is None
        or coins_point_cost is None
    ):
        return None

    options: list[PromptSurfaceLapRewardOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        value = _record(choice.get("value")) or {}
        cash_units = _number(value.get("cash_units"))
        shard_units = _number(value.get("shard_units"))
        coin_units = _number(value.get("coin_units"))
        spent_points = _number(value.get("spent_points"))
        if not choice_id or cash_units is None or shard_units is None or coin_units is None or spent_points is None:
            continue
        options.append(
            {
                "choice_id": choice_id,
                "cash_units": cash_units,
                "shard_units": shard_units,
                "coin_units": coin_units,
                "spent_points": spent_points,
            }
        )

    return {
        "budget": budget,
        "cash_pool": cash_pool,
        "shards_pool": shards_pool,
        "coins_pool": coins_pool,
        "cash_point_cost": cash_point_cost,
        "shards_point_cost": shards_point_cost,
        "coins_point_cost": coins_point_cost,
        "options": options,
    }


def _movement_surface(raw_choices: Any) -> PromptSurfaceMovementViewState | None:
    roll_choice_id: str | None = None
    card_pool: set[int] = set()
    card_choices: list[PromptSurfaceMovementCardChoiceViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        if not choice_id:
            continue
        value = _record(choice.get("value")) or {}
        use_cards = value.get("use_cards") is True
        raw_values = value.get("card_values")
        card_values = [item for item in raw_values if isinstance(item, int)] if isinstance(raw_values, list) else []
        if not use_cards:
            if choice_id in {"dice", "roll"}:
                roll_choice_id = choice_id
            continue
        sorted_cards = sorted(card_values)
        if not sorted_cards:
            continue
        for card in sorted_cards:
            card_pool.add(card)
        card_choices.append(
            {
                "choice_id": choice_id,
                "cards": sorted_cards,
                "title": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, _choice_value(choice)),
            }
        )
    if roll_choice_id is None and not card_choices:
        return None
    return {
        "roll_choice_id": roll_choice_id,
        "card_pool": sorted(card_pool),
        "can_use_two_cards": any(len(choice["cards"]) == 2 for choice in card_choices),
        "card_choices": card_choices,
    }


def _burden_exchange_surface(public_context: dict[str, Any]) -> PromptSurfaceBurdenExchangeViewState | None:
    raw_cards = public_context.get("burden_cards")
    if not isinstance(raw_cards, list):
        return None

    cards: list[PromptSurfaceBurdenCardViewState] = []
    for item in raw_cards:
        card = _record(item)
        if not card:
            continue
        cards.append(
            {
                "deck_index": _number(card.get("deck_index")),
                "name": _string(card.get("name")) or "Burden",
                "description": _string(card.get("card_description")),
                "burden_cost": _number(card.get("burden_cost")),
                "is_current_target": card.get("is_current_target") is True,
            }
        )

    return {
        "burden_card_count": _number(public_context.get("burden_card_count")) or len(cards),
        "current_f_value": _number(public_context.get("current_f_value")),
        "supply_threshold": _number(public_context.get("supply_threshold")),
        "cards": cards,
    }


def _mark_target_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceMarkTargetViewState | None:
    actor_name = _string(public_context.get("actor_name"))
    if not actor_name:
        return None
    candidates: list[PromptSurfaceMarkTargetCandidateViewState] = []
    none_choice_id: str | None = None
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        if not choice_id:
            continue
        if choice_id == "none":
            none_choice_id = choice_id
            continue
        value = _record(choice.get("value")) or {}
        target_character = _string(value.get("target_character")) or _string(choice.get("title", choice.get("label")))
        if not target_character:
            continue
        candidates.append(
            {
                "choice_id": choice_id,
                "target_character": target_character,
                "target_card_no": _number(value.get("target_card_no")),
                "target_player_id": _number(value.get("target_player_id")),
            }
        )
    return {
        "actor_name": actor_name,
        "none_choice_id": none_choice_id,
        "candidates": candidates,
    }


def _character_pick_surface(
    request_type: str,
    public_context: dict[str, Any],
    raw_choices: Any,
) -> PromptSurfaceCharacterPickViewState | None:
    if request_type not in {"draft_card", "final_character", "final_character_choice"}:
        return None
    options: list[PromptSurfaceCharacterPickOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        if not choice_id:
            continue
        value = _choice_value(choice)
        item: PromptSurfaceCharacterPickOptionViewState = {
            "choice_id": choice_id,
            "name": _string(choice.get("title", choice.get("label"))) or choice_id,
            "description": _choice_description(choice, value),
        }
        inactive_name = _string(value.get("inactive_character_name")) if value else ""
        if inactive_name:
            item["inactive_name"] = inactive_name
        options.append(item)
    return {
        "phase": "draft" if request_type == "draft_card" else "final",
        "draft_phase": _number(public_context.get("draft_phase")) if request_type == "draft_card" else None,
        "draft_phase_label": _string(public_context.get("draft_phase_label")) if request_type == "draft_card" else None,
        "choice_count": len(options),
        "options": options,
    }


def _hand_choice_surface(request_type: str, public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceHandChoiceViewState | None:
    if request_type not in {"trick_to_use", "hidden_trick_card"}:
        return None
    choice_by_deck: dict[int, str] = {}
    pass_choice_id: str | None = None
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        if not choice_id:
            continue
        if choice_id == "none":
            pass_choice_id = choice_id
            continue
        value = _record(choice.get("value")) or {}
        deck_index = _number(value.get("deck_index"))
        if deck_index is not None:
            choice_by_deck[deck_index] = choice_id

    cards: list[PromptSurfaceHandChoiceCardViewState] = []
    raw_full_hand = public_context.get("full_hand")
    if isinstance(raw_full_hand, list):
        for item in raw_full_hand:
            card = _record(item)
            if not card:
                continue
            deck_index = _number(card.get("deck_index"))
            cards.append(
                {
                    "choice_id": choice_by_deck.get(deck_index) if deck_index is not None else None,
                    "deck_index": deck_index,
                    "name": _string(card.get("name")) or "Trick",
                    "description": _string(card.get("card_description")),
                    "is_hidden": card.get("is_hidden") is True,
                    "is_usable": card.get("is_usable") is True and (deck_index in choice_by_deck if deck_index is not None else False),
                }
            )
    else:
        for choice in _choice_list(raw_choices):
            choice_id = _string(choice.get("choice_id"))
            if not choice_id or choice_id == "none":
                continue
            value = _record(choice.get("value")) or {}
            cards.append(
                {
                    "choice_id": choice_id,
                    "deck_index": _number(value.get("deck_index")),
                    "name": _string(choice.get("title", choice.get("label"))) or choice_id,
                    "description": _choice_description(choice, _choice_value(choice)),
                    "is_hidden": value.get("is_hidden") is True,
                    "is_usable": True,
                }
            )
    return {
        "mode": "hidden" if request_type == "hidden_trick_card" else "use",
        "pass_choice_id": pass_choice_id,
        "cards": cards,
    }


def _purchase_tile_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfacePurchaseTileViewState | None:
    yes_choice_id: str | None = None
    no_choice_id: str | None = None
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        if choice_id == "yes":
            yes_choice_id = choice_id
        elif choice_id == "no":
            no_choice_id = choice_id
    return {
        "tile_index": _number(public_context.get("tile_index")),
        "cost": _number(public_context.get("cost")) or _number(public_context.get("tile_purchase_cost")),
        "yes_choice_id": yes_choice_id,
        "no_choice_id": no_choice_id,
    }


def _trick_tile_target_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceTrickTileTargetViewState | None:
    raw_candidate_tiles = public_context.get("candidate_tiles")
    candidate_tiles = [int(tile) for tile in raw_candidate_tiles if isinstance(tile, int)] if isinstance(raw_candidate_tiles, list) else []
    options: list[PromptSurfaceTileTargetOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        value = _record(choice.get("value")) or {}
        tile_index = _number(value.get("tile_index"))
        if not choice_id or tile_index is None:
            continue
        options.append(
            {
                "choice_id": choice_id,
                "tile_index": tile_index,
                "title": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, _choice_value(choice)),
            }
        )
    return {
        "card_name": _string(public_context.get("card_name")),
        "target_scope": _string(public_context.get("target_scope")),
        "candidate_tiles": candidate_tiles,
        "options": options,
    }


def _active_flip_surface(raw_choices: Any) -> PromptSurfaceActiveFlipViewState | None:
    options: list[PromptSurfaceActiveFlipOptionViewState] = []
    finish_choice_id: str | None = None
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        if not choice_id:
            continue
        if choice_id == "none":
            finish_choice_id = choice_id
            continue
        value = _record(choice.get("value")) or {}
        options.append(
            {
                "choice_id": choice_id,
                "card_index": _number(value.get("card_index")),
                "current_name": _string(value.get("current_name")),
                "flipped_name": _string(value.get("flipped_name")),
            }
        )
    return {
        "finish_choice_id": finish_choice_id,
        "options": options,
    }


def _coin_placement_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceCoinPlacementViewState | None:
    options: list[PromptSurfaceCoinPlacementOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        value = _record(choice.get("value")) or {}
        tile_index = _number(value.get("tile_index"))
        if not choice_id or tile_index is None:
            continue
        options.append(
            {
                "choice_id": choice_id,
                "tile_index": tile_index,
                "title": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, _choice_value(choice)),
            }
        )
    if not options and _number(public_context.get("owned_tile_count")) is None:
        return None
    return {
        "owned_tile_count": _number(public_context.get("owned_tile_count")) or len(options),
        "options": options,
    }


def _doctrine_relief_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceDoctrineReliefViewState | None:
    options: list[PromptSurfaceDoctrineReliefOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        value = _record(choice.get("value")) or {}
        if not choice_id:
            continue
        options.append(
            {
                "choice_id": choice_id,
                "target_player_id": _number(value.get("target_player_id")),
                "burden_count": _number(value.get("burden_count")),
                "title": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, _choice_value(choice)),
            }
        )
    if not options and _number(public_context.get("candidate_count")) is None:
        return None
    return {
        "candidate_count": _number(public_context.get("candidate_count")) or len(options),
        "options": options,
    }


def _geo_bonus_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceGeoBonusViewState | None:
    options: list[PromptSurfaceGeoBonusOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        value = _record(choice.get("value")) or {}
        reward_kind = _string(value.get("choice")) or choice_id
        if not choice_id:
            continue
        options.append(
            {
                "choice_id": choice_id,
                "reward_kind": reward_kind,
                "title": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, _choice_value(choice)),
            }
        )
    if not options:
        return None
    return {
        "actor_name": _string(public_context.get("actor_name")),
        "options": options,
    }


def _specific_trick_reward_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceSpecificTrickRewardViewState | None:
    options: list[PromptSurfaceSpecificTrickRewardOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        value = _record(choice.get("value")) or {}
        if not choice_id:
            continue
        options.append(
            {
                "choice_id": choice_id,
                "deck_index": _number(value.get("deck_index")),
                "name": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, _choice_value(choice)),
            }
        )
    if not options:
        return None
    return {
        "reward_count": _number(public_context.get("reward_count")) or len(options),
        "options": options,
    }


def _pabal_dice_mode_surface(raw_choices: Any) -> PromptSurfacePabalDiceModeViewState | None:
    options: list[PromptSurfacePabalDiceModeOptionViewState] = []
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        value = _record(choice.get("value")) or {}
        dice_mode = _string(value.get("dice_mode")) or choice_id
        if not choice_id:
            continue
        options.append(
            {
                "choice_id": choice_id,
                "dice_mode": dice_mode,
                "title": _string(choice.get("title", choice.get("label"))) or choice_id,
                "description": _choice_description(choice, _choice_value(choice)),
            }
        )
    return {"options": options} if options else None


def _runaway_step_surface(public_context: dict[str, Any], raw_choices: Any) -> PromptSurfaceRunawayStepViewState | None:
    bonus_choice_id: str | None = None
    stay_choice_id: str | None = None
    for choice in _choice_list(raw_choices):
        choice_id = _string(choice.get("choice_id"))
        if choice_id == "yes":
            bonus_choice_id = choice_id
        elif choice_id == "no":
            stay_choice_id = choice_id
    if bonus_choice_id is None and stay_choice_id is None:
        return None
    return {
        "bonus_choice_id": bonus_choice_id,
        "stay_choice_id": stay_choice_id,
        "one_short_pos": _number(public_context.get("one_short_pos")),
        "bonus_target_pos": _number(public_context.get("bonus_target_pos")),
        "bonus_target_kind": _string(public_context.get("bonus_target_kind")),
    }


def _prompt_surface(payload: dict[str, Any], public_context: dict[str, Any]) -> PromptSurfaceViewState:
    request_type = _string(payload.get("request_type")) or "-"
    raw_choices = payload.get("legal_choices")
    surface: PromptSurfaceViewState = {
        "kind": request_type,
        "blocks_public_events": True,
    }
    if request_type in {"lap_reward", "start_reward"}:
        lap_reward = _lap_reward_surface(public_context, raw_choices)
        if lap_reward:
            surface["lap_reward"] = lap_reward
    elif request_type == "movement":
        movement = _movement_surface(raw_choices)
        if movement:
            surface["movement"] = movement
    elif request_type == "burden_exchange":
        burden_exchange = _burden_exchange_surface(public_context)
        if burden_exchange:
            surface["kind"] = "burden_exchange_batch"
            surface["burden_exchange_batch"] = burden_exchange
    elif request_type == "mark_target":
        mark_target = _mark_target_surface(public_context, raw_choices)
        if mark_target:
            surface["mark_target"] = mark_target
    elif request_type in {"draft_card", "final_character", "final_character_choice"}:
        character_pick = _character_pick_surface(request_type, public_context, raw_choices)
        if character_pick:
            surface["kind"] = "character_pick"
            surface["character_pick"] = character_pick
    elif request_type in {"trick_to_use", "hidden_trick_card"}:
        hand_choice = _hand_choice_surface(request_type, public_context, raw_choices)
        if hand_choice:
            surface["hand_choice"] = hand_choice
    elif request_type == "purchase_tile":
        surface["purchase_tile"] = _purchase_tile_surface(public_context, raw_choices)
    elif request_type == "trick_tile_target":
        surface["trick_tile_target"] = _trick_tile_target_surface(public_context, raw_choices)
    elif request_type == "coin_placement":
        coin_placement = _coin_placement_surface(public_context, raw_choices)
        if coin_placement:
            surface["coin_placement"] = coin_placement
    elif request_type == "doctrine_relief":
        doctrine_relief = _doctrine_relief_surface(public_context, raw_choices)
        if doctrine_relief:
            surface["doctrine_relief"] = doctrine_relief
    elif request_type == "geo_bonus":
        geo_bonus = _geo_bonus_surface(public_context, raw_choices)
        if geo_bonus:
            surface["geo_bonus"] = geo_bonus
    elif request_type == "specific_trick_reward":
        specific_trick_reward = _specific_trick_reward_surface(public_context, raw_choices)
        if specific_trick_reward:
            surface["specific_trick_reward"] = specific_trick_reward
    elif request_type == "pabal_dice_mode":
        pabal_dice_mode = _pabal_dice_mode_surface(raw_choices)
        if pabal_dice_mode:
            surface["pabal_dice_mode"] = pabal_dice_mode
    elif request_type == "runaway_step_choice":
        runaway_step = _runaway_step_surface(public_context, raw_choices)
        if runaway_step:
            surface["runaway_step"] = runaway_step
    elif request_type == "active_flip":
        active_flip = _active_flip_surface(raw_choices)
        if active_flip:
            surface["active_flip"] = active_flip
    return surface


def _prompt_behavior(payload: dict[str, Any], public_context: dict[str, Any]) -> ActivePromptBehaviorViewState:
    request_type = _string(payload.get("request_type")) or "-"
    behavior: ActivePromptBehaviorViewState = {
        "normalized_request_type": request_type,
        "single_surface": False,
        "auto_continue": False,
    }
    if request_type == "burden_exchange":
        player_id = _legacy_prompt_player_id(payload) or 0
        current_f = _number(public_context.get("current_f_value"))
        current_deck_index = _number(public_context.get("card_deck_index"))
        burden_count = _number(public_context.get("burden_card_count")) or 0
        behavior = {
            "normalized_request_type": "burden_exchange_batch",
            "single_surface": True,
            "auto_continue": True,
            "chain_key": f"burden_exchange:{player_id}:{current_f if current_f is not None else 'na'}",
            "chain_item_count": burden_count,
            "current_item_deck_index": current_deck_index,
        }
    return behavior


def _prompt_effect_context(public_context: dict[str, Any]) -> PromptEffectContextViewState | None:
    raw = _record(public_context.get("effect_context"))
    if not raw:
        return None
    label = _string(raw.get("label")) or _string(raw.get("source_name"))
    detail = _string(raw.get("detail")) or label
    if not label and not detail:
        return None
    tone = _string(raw.get("tone"))
    if tone not in {"move", "effect", "economy"}:
        tone = "effect"
    effect_context: PromptEffectContextViewState = {
        "label": label or detail,
        "detail": detail or label,
        "attribution": _string(raw.get("attribution")),
        "tone": tone,
        "source": _string(raw.get("source")) or _string(raw.get("source_family")) or "system",
        "intent": _string(raw.get("intent")) or "neutral",
        "enhanced": raw.get("enhanced") is True,
    }
    source_player_id = _number(raw.get("source_player_id"))
    if source_player_id is not None:
        effect_context["source_player_id"] = source_player_id
    source_family = _string(raw.get("source_family"))
    if source_family:
        effect_context["source_family"] = source_family
    source_name = _string(raw.get("source_name"))
    if source_name:
        effect_context["source_name"] = source_name
    resource_delta = _record(raw.get("resource_delta"))
    if resource_delta is not None:
        effect_context["resource_delta"] = {key: value for key, value in resource_delta.items()}
    return effect_context


def _event_player_id(payload: dict[str, Any]) -> int | None:
    return _number(payload.get("player_id", payload.get("acting_player_id", payload.get("player"))))


def _closes_prompt_by_phase_progress(request_type: str, payload: dict[str, Any], prompt_player_id: int) -> bool:
    event_type = _string(payload.get("event_type"))
    payload_player_id = _event_player_id(payload)
    if request_type == "draft_card":
        return ((event_type == "draft_pick" and payload_player_id == prompt_player_id) or event_type in {"final_character_choice", "turn_start"})
    if request_type in {"final_character", "final_character_choice"}:
        return ((event_type == "final_character_choice" and payload_player_id == prompt_player_id) or event_type == "turn_start")
    if request_type in {"trick_to_use", "hidden_trick_card", "hand_choice"}:
        return (
            (event_type == "trick_used" and payload_player_id == prompt_player_id)
            or (event_type == "trick_window_closed" and payload_player_id == prompt_player_id)
            or event_type in {"dice_roll", "player_move", "turn_end_snapshot"}
        )
    return False


def _is_prompt_closed(
    messages: list[dict[str, Any]],
    prompt_index: int,
    request_id: str,
    request_type: str,
    player_id: int,
) -> bool:
    for message in messages[prompt_index + 1 :]:
        message_type = message.get("type")
        payload = _record(message.get("payload")) or {}
        if message_type == "decision_ack":
            if payload.get("request_id") != request_id:
                continue
            if payload.get("status") in {"accepted", "stale"}:
                return True
            continue
        if message_type != "event":
            continue
        if payload.get("request_id") == request_id and payload.get("event_type") in {"decision_resolved", "decision_timeout_fallback"}:
            return True
        if _closes_prompt_by_phase_progress(request_type, payload, player_id):
            return True
    return False


def latest_active_prompt(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("type") != "prompt":
            continue
        payload = _record(message.get("payload")) or {}
        request_id = _string(payload.get("request_id"))
        if not request_id:
            continue
        request_type = _string(payload.get("request_type"))
        player_id = _legacy_prompt_player_id(payload) or 0
        if _is_prompt_closed(messages, index, request_id, request_type, player_id):
            continue
        return payload
    return None


def build_prompt_feedback_view_state(messages: list[dict[str, Any]]) -> PromptFeedbackViewState | None:
    for message in reversed(messages):
        message_type = message.get("type")
        payload = _record(message.get("payload")) or {}
        if message_type == "decision_ack":
            request_id = _string(payload.get("request_id"))
            status = _string(payload.get("status"))
            if request_id and status in {"accepted", "rejected", "stale"}:
                return {
                    "request_id": request_id,
                    "status": status,
                    "reason": _string(payload.get("reason")),
                }
            continue
        if message_type != "event":
            continue
        request_id = _string(payload.get("request_id"))
        if not request_id:
            continue
        event_type = _string(payload.get("event_type"))
        if event_type == "decision_timeout_fallback":
            return {
                "request_id": request_id,
                "status": "timeout_fallback",
                "reason": _string(payload.get("summary", payload.get("reason"))),
            }
        if event_type == "decision_resolved":
            resolution = _string(payload.get("resolution")) or "accepted"
            return {
                "request_id": request_id,
                "status": resolution,
                "reason": _string(payload.get("reason")),
            }
    return None


def build_prompt_view_state(messages: list[dict[str, Any]]) -> PromptViewState | None:
    active_prompt = latest_active_prompt(messages)
    last_feedback = build_prompt_feedback_view_state(messages)
    if not active_prompt and not last_feedback:
        return None
    payload: PromptViewState = {}
    if active_prompt:
        request_id = _string(active_prompt.get("request_id"))
        request_type = _string(active_prompt.get("request_type")) or "-"
        player_id = _protocol_prompt_player_id(active_prompt) or 0
        timeout_ms = _number(active_prompt.get("timeout_ms")) or 30000
        public_context = _record(active_prompt.get("public_context")) or {}
        active: ActivePromptViewState = {
            "request_id": request_id,
            "request_type": request_type,
            "player_id": player_id,
            "timeout_ms": timeout_ms,
            "choices": _parse_choices(active_prompt.get("legal_choices")),
            "public_context": {key: value for key, value in public_context.items()},
            "behavior": _prompt_behavior(active_prompt, public_context),
            "surface": _prompt_surface(active_prompt, public_context),
        }
        primary_identity = _active_prompt_primary_identity(active_prompt)
        if primary_identity is not None:
            primary_player_id, primary_player_id_source = primary_identity
            active["primary_player_id"] = primary_player_id
            active["primary_player_id_source"] = primary_player_id_source
            if isinstance(player_id, int):
                active["player_id_alias_role"] = "legacy_compatibility_alias"
        legacy_player_id = _number(active_prompt.get("legacy_player_id"))
        if legacy_player_id is not None:
            active["legacy_player_id"] = legacy_player_id
        for field in (
            "legacy_request_id",
            "public_request_id",
            "public_prompt_instance_id",
            "public_player_id",
            "seat_id",
            "viewer_id",
        ):
            value = _string(active_prompt.get(field))
            if value:
                active[field] = value
        effect_context = _prompt_effect_context(public_context)
        if effect_context:
            active["effect_context"] = effect_context
        for field in ("runner_kind", "resume_token", "frame_id", "module_id", "module_type", "module_cursor", "batch_id"):
            value = _string(active_prompt.get(field))
            if value:
                active[field] = value
        prompt_instance_id = _number(active_prompt.get("prompt_instance_id"))
        if prompt_instance_id is not None:
            active["prompt_instance_id"] = prompt_instance_id
        missing_player_ids = [
            int(raw)
            for raw in active_prompt.get("missing_player_ids") or []
            if _number(raw) is not None
        ]
        if missing_player_ids:
            active["missing_player_ids"] = missing_player_ids
        for field in ("missing_public_player_ids", "missing_seat_ids", "missing_viewer_ids"):
            values = [
                str(raw).strip()
                for raw in active_prompt.get(field) or []
                if str(raw or "").strip()
            ]
            if values:
                active[field] = values
        raw_resume_tokens = _record(active_prompt.get("resume_tokens_by_player_id")) or {}
        resume_tokens_by_player_id = {
            str(raw_player_id): str(token)
            for raw_player_id, token in raw_resume_tokens.items()
            if str(raw_player_id).strip() and str(token).strip()
        }
        if resume_tokens_by_player_id:
            active["resume_tokens_by_player_id"] = resume_tokens_by_player_id
        for field in (
            "resume_tokens_by_public_player_id",
            "resume_tokens_by_seat_id",
            "resume_tokens_by_viewer_id",
        ):
            token_map = {
                str(identity_id).strip(): str(token).strip()
                for identity_id, token in (_record(active_prompt.get(field)) or {}).items()
                if str(identity_id).strip() and str(token).strip()
            }
            if token_map:
                active[field] = token_map
        payload["active"] = active
    if last_feedback:
        payload["last_feedback"] = last_feedback
    return payload
