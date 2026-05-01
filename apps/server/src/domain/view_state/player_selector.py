from __future__ import annotations

from typing import Any

from ..gameplay_catalog import (
    opposite_character_name_for_slot,
    priority_slot_for_character_name,
)
from .prompt_selector import latest_active_prompt
from .snapshot_selector import latest_player_snapshot_entry, marker_state_from_messages
from .types import (
    ActiveSlotItemViewState,
    ActiveSlotsViewState,
    DerivedPlayerItemViewState,
    MarkTargetCandidateViewState,
    MarkTargetViewState,
    PlayerOrderingViewState,
)

def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _string(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _priority_slot_for_character(character: Any) -> int | None:
    normalized = _string(character)
    if not normalized:
        return None
    return priority_slot_for_character_name(normalized)


def _opposite_character_for_slot(slot: int, active_character: str | None) -> str | None:
    return opposite_character_name_for_slot(slot, active_character)


def _event_type(payload: dict[str, Any]) -> str:
    return _string(payload.get("event_type")).lower()


def _current_actor_player_id(messages: list[dict[str, Any]]) -> int | None:
    for message in reversed(messages):
        payload = _record(message.get("payload")) or {}
        actor = payload.get("acting_player_id", payload.get("player_id"))
        if isinstance(actor, int):
            return actor
    return None


def _merge_active_by_card(target: dict[int, str], raw: Any) -> None:
    record = _record(raw)
    if not record:
        return
    for key, value in record.items():
        try:
            card_no = int(key)
        except Exception:
            continue
        name = _string(value)
        if card_no >= 1 and name:
            target[card_no] = name


def _merge_prompt_context_active_by_card(target: dict[int, str], public_context: Any) -> None:
    record = _record(public_context)
    if not record:
        return
    _merge_active_by_card(target, record.get("active_by_card"))
    target_pairs = record.get("target_pairs")
    if not isinstance(target_pairs, list):
        return
    for item in target_pairs:
        pair = _record(item)
        if not pair:
            continue
        slot = _number(pair.get("target_card_no"))
        character = _string(pair.get("target_character"))
        if slot is not None and character:
            target[slot] = character


def _merge_mark_target_choices(target: dict[int, str], payload: dict[str, Any]) -> None:
    if _string(payload.get("request_type")) != "mark_target":
        return
    legal_choices = payload.get("legal_choices")
    if not isinstance(legal_choices, list):
        return
    for item in legal_choices:
        choice = _record(item)
        if not choice:
            continue
        choice_id = _string(choice.get("choice_id"))
        if choice_id in {"none", "no"}:
            continue
        value = _record(choice.get("value")) or {}
        character = _string(value.get("target_character", choice.get("title", choice.get("label"))))
        slot = _number(value.get("target_card_no")) or _priority_slot_for_character(character)
        if slot is not None and character:
            target[slot] = character


def _clear_active_by_card(target: dict[int, str]) -> None:
    target.clear()


def _has_active_by_card_payload(payload: dict[str, Any]) -> bool:
    if _record(payload.get("active_by_card")):
        return True
    snapshot = _record(payload.get("snapshot")) or {}
    if _record(snapshot.get("active_by_card")):
        return True
    public_context = _record(payload.get("public_context")) or {}
    if _record(public_context.get("active_by_card")):
        return True
    return False


def _should_reset_active_by_card(event_type: str, payload: dict[str, Any]) -> bool:
    return event_type in {"round_start", "round_order"} and _has_active_by_card_payload(payload)


def _collect_active_by_card(messages: list[dict[str, Any]]) -> dict[int, str]:
    active_by_card: dict[int, str] = {}
    for message in messages:
        message_type = message.get("type")
        payload = _record(message.get("payload")) or {}
        if message_type == "prompt":
            _merge_prompt_context_active_by_card(active_by_card, payload.get("public_context"))
            _merge_mark_target_choices(active_by_card, payload)
            continue
        if message_type != "event":
            continue
        event_type = _event_type(payload)
        if _should_reset_active_by_card(event_type, payload):
            _clear_active_by_card(active_by_card)
        _merge_active_by_card(active_by_card, payload.get("active_by_card"))
        _merge_active_by_card(active_by_card, (_record(payload.get("snapshot")) or {}).get("active_by_card"))
        _merge_active_by_card(active_by_card, (_record(payload.get("public_context")) or {}).get("active_by_card"))
        if event_type == "marker_flip":
            slot = _number(payload.get("card_no"))
            character = _string(payload.get("to_character"))
            if slot is not None and character:
                active_by_card[slot] = character
    active_prompt = latest_active_prompt(messages)
    if active_prompt:
        _merge_prompt_context_active_by_card(active_by_card, active_prompt.get("public_context"))
        _merge_mark_target_choices(active_by_card, active_prompt)
    return active_by_card


def _to_player_item(raw: dict[str, Any]) -> DerivedPlayerItemViewState | None:
    player_id = _number(raw.get("player_id"))
    if player_id is None:
        return None
    public_tricks = _string_list(raw.get("public_tricks"))
    hidden_trick_count = _number(raw.get("hidden_trick_count")) or 0
    hand_coins = _number(raw.get("hand_coins"))
    if hand_coins is None:
        hand_coins = _number(raw.get("hand_score_coins")) or 0
    placed_coins = _number(raw.get("placed_score_coins"))
    if placed_coins is None:
        placed_coins = _number(raw.get("score_coins_placed")) or 0
    total_score = _number(raw.get("score"))
    if total_score is None:
        total_score = _number(raw.get("total_score"))
    if total_score is None:
        total_score = hand_coins + placed_coins
    return {
        "player_id": player_id,
        "display_name": _string(raw.get("display_name")) or f"Player {player_id}",
        "cash": _number(raw.get("cash")) or 0,
        "shards": _number(raw.get("shards")) or 0,
        "owned_tile_count": _number(raw.get("owned_tile_count")) or 0,
        "trick_count": _number(raw.get("trick_count")) or (len(public_tricks) + hidden_trick_count),
        "hidden_trick_count": hidden_trick_count,
        "public_tricks": public_tricks,
        "hand_coins": hand_coins,
        "placed_coins": placed_coins,
        "total_score": total_score,
        "priority_slot": None,
        "current_character_face": "-",
        "is_marker_owner": False,
        "is_current_actor": False,
    }


def _public_tricks_from_context(public_context: dict[str, Any]) -> list[str] | None:
    full_hand = public_context.get("full_hand")
    if isinstance(full_hand, list):
        names: list[str] = []
        for item in full_hand:
            card = _record(item)
            if not card or card.get("is_hidden") is True:
                continue
            name = _string(card.get("name"))
            if name:
                names.append(name)
        return names
    hand_names = _string_list(public_context.get("hand_names"))
    return hand_names if hand_names else None


def _apply_direct_hand_context_to_player(player: DerivedPlayerItemViewState, payload: dict[str, Any]) -> None:
    player_id = _number(payload.get("player_id", payload.get("acting_player_id")))
    if player_id != player["player_id"]:
        return
    hidden_trick_count = _number(payload.get("hidden_trick_count"))
    public_tricks = _string_list(payload.get("public_tricks"))
    hand_count = _number(payload.get("hand_count"))
    if hidden_trick_count is not None:
        player["hidden_trick_count"] = hidden_trick_count
    if public_tricks:
        player["public_tricks"] = public_tricks
    if hand_count is not None:
        player["trick_count"] = hand_count
    elif public_tricks or hidden_trick_count is not None:
        player["trick_count"] = len(player["public_tricks"]) + player["hidden_trick_count"]


def _apply_prompt_context_to_player(player: DerivedPlayerItemViewState, payload: dict[str, Any]) -> None:
    _apply_direct_hand_context_to_player(player, payload)
    player_id = _number(payload.get("player_id", payload.get("acting_player_id")))
    if player_id != player["player_id"]:
        return
    public_context = _record(payload.get("public_context")) or {}
    field_map = {
        "player_cash": "cash",
        "player_shards": "shards",
        "player_owned_tile_count": "owned_tile_count",
        "player_hand_coins": "hand_coins",
        "player_placed_coins": "placed_coins",
        "player_total_score": "total_score",
    }
    for source_key, target_key in field_map.items():
        value = _number(public_context.get(source_key))
        if value is not None:
            player[target_key] = value  # type: ignore[literal-required]
    hidden_trick_count = _number(public_context.get("hidden_trick_count"))
    if hidden_trick_count is not None:
        player["hidden_trick_count"] = hidden_trick_count
    public_tricks = _public_tricks_from_context(public_context)
    if public_tricks is not None:
        player["public_tricks"] = public_tricks
    hand_count = _number(public_context.get("hand_count"))
    if hand_count is not None:
        player["trick_count"] = hand_count
    elif public_tricks is not None or hidden_trick_count is not None:
        player["trick_count"] = len(player["public_tricks"]) + player["hidden_trick_count"]


def _latest_actor_character(messages: list[dict[str, Any]]) -> str | None:
    for message in reversed(messages):
        payload = _record(message.get("payload")) or {}
        if _event_type(payload) != "turn_start":
            continue
        actor_name = _string(payload.get("character", payload.get("actor_name")))
        if actor_name:
            return actor_name
    return None


def build_player_view_state(messages: list[dict[str, Any]]) -> PlayerOrderingViewState | None:
    entry = latest_player_snapshot_entry(messages)
    if not entry:
        return None
    _index, snapshot = entry
    players = [_to_player_item(raw) for raw in snapshot.get("players", []) if isinstance(raw, dict)]
    players = [player for player in players if player is not None]
    if not players:
        return None
    for message in messages[_index + 1 :]:
        payload = _record(message.get("payload")) or {}
        for player in players:
            _apply_prompt_context_to_player(player, payload)

    marker_owner_player_id, marker_draft_direction = marker_state_from_messages(
        messages,
        snapshot.get("marker_owner_player_id"),
        snapshot.get("marker_draft_direction"),
    )
    current_actor_player_id = _current_actor_player_id(messages)
    latest_actor_character = _latest_actor_character(messages)
    actor_slot = _priority_slot_for_character(latest_actor_character)

    for player in players:
        if current_actor_player_id == player["player_id"] and latest_actor_character:
            player["current_character_face"] = latest_actor_character
            player["priority_slot"] = actor_slot
        else:
            player["current_character_face"] = "-"
            player["priority_slot"] = None
        player["is_marker_owner"] = marker_owner_player_id == player["player_id"]
        player["is_current_actor"] = current_actor_player_id == player["player_id"]

    ordered_player_ids = sorted(player["player_id"] for player in players)
    if marker_owner_player_id in ordered_player_ids:
        owner_index = ordered_player_ids.index(marker_owner_player_id)
        direction = marker_draft_direction if marker_draft_direction in {"clockwise", "counterclockwise"} else "clockwise"
        ordered: list[int] = []
        for step in range(len(ordered_player_ids)):
            index = (owner_index + step) % len(ordered_player_ids) if direction == "clockwise" else (owner_index - step) % len(ordered_player_ids)
            ordered.append(ordered_player_ids[index])
        ordered_player_ids = ordered

    player_by_id = {player["player_id"]: player for player in players}
    ordered_items = [player_by_id[player_id] for player_id in ordered_player_ids if player_id in player_by_id]
    return {
        "ordered_player_ids": ordered_player_ids,
        "marker_owner_player_id": marker_owner_player_id,
        "marker_draft_direction": marker_draft_direction if marker_draft_direction in {"clockwise", "counterclockwise"} else None,
        "items": ordered_items,
    }


def build_active_slots_view_state(messages: list[dict[str, Any]]) -> ActiveSlotsViewState | None:
    players_view = build_player_view_state(messages)
    player_items = players_view.get("items", []) if players_view else []
    active_by_card = _collect_active_by_card(messages)
    actor = next((player for player in player_items if player.get("is_current_actor")), None)
    actor_slot = actor.get("priority_slot") if actor else None
    actor_face = actor.get("current_character_face") if actor else None
    items: list[ActiveSlotItemViewState] = []
    for slot in range(1, 9):
        owner = actor if actor and actor_slot == slot else None
        slot_character = active_by_card.get(slot)
        active_character = slot_character or (actor_face if owner and actor_face != "-" else None)
        items.append(
            {
                "slot": slot,
                "player_id": owner["player_id"] if owner else None,
                "label": f"P{owner['player_id']}" if owner else None,
                "character": active_character,
                "inactive_character": _opposite_character_for_slot(slot, active_character) if active_character else None,
                "is_current_actor": bool(owner and owner.get("is_current_actor")),
            }
        )
    return {"items": items}


def build_mark_target_view_state(messages: list[dict[str, Any]]) -> MarkTargetViewState | None:
    active_prompt = latest_active_prompt(messages)
    if not active_prompt or _string(active_prompt.get("request_type")) != "mark_target":
        return None
    actor_name = _string((_record(active_prompt.get("public_context")) or {}).get("actor_name"))
    actor_slot = _priority_slot_for_character(actor_name)
    active_slots = build_active_slots_view_state(messages)
    if not active_slots:
        return {
            "actor_slot": actor_slot,
            "candidates": [],
        }
    candidates: list[MarkTargetCandidateViewState] = []
    for slot in active_slots["items"]:
        if actor_slot is None or slot["slot"] <= actor_slot or not slot["character"]:
            continue
        candidates.append(
            {
                "slot": slot["slot"],
                "player_id": slot["player_id"],
                "label": slot["label"],
                "character": slot["character"],
            }
        )
    return {
        "actor_slot": actor_slot,
        "candidates": candidates,
    }
