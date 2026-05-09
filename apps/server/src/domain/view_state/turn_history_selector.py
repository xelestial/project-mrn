from __future__ import annotations

from typing import Any

from .types import TurnHistoryEventViewState, TurnHistoryTurnViewState, TurnHistoryViewState


MOVE_EVENT_CODES = {"player_move", "action_move", "fortune_move", "forced_move", "chain_move", "dice_roll"}
ECONOMY_EVENT_CODES = {
    "tile_purchased",
    "landing_resolved",
    "rent_paid",
    "marker_transferred",
    "start_reward_chosen",
    "lap_reward_chosen",
    "fortune_drawn",
    "fortune_resolved",
    "resource_gain",
    "cash_gain",
    "coin_gain",
    "score_gain",
    "shard_gain",
}
CRITICAL_EVENT_CODES = {"bankruptcy", "game_end"}
COMMON_EVENT_CODES = {
    "f_value_change",
    "game_completed",
    "game_end",
    "parameter_manifest",
    "round_start",
    "session_created",
    "session_start",
    "session_started",
    "weather_reveal",
}
IMPORTANT_EVENT_CODES = {
    *MOVE_EVENT_CODES,
    *ECONOMY_EVENT_CODES,
    "mark_queued",
    "mark_resolved",
    "mark_target_none",
    "mark_target_missing",
    "mark_blocked",
    "marker_flip",
    "f_value_change",
}
TURN_HISTORY_EVENT_CODES = {
    "round_start",
    "weather_reveal",
    "draft_pick",
    "final_character_choice",
    "turn_start",
    "dice_roll",
    "trick_used",
    "player_move",
    "action_move",
    "fortune_move",
    "forced_move",
    "chain_move",
    "landing_resolved",
    "rent_paid",
    "tile_purchased",
    "start_reward_chosen",
    "lap_reward_chosen",
    "fortune_drawn",
    "fortune_resolved",
    "mark_queued",
    "mark_resolved",
    "mark_target_none",
    "mark_target_missing",
    "mark_blocked",
    "marker_flip",
    "marker_transferred",
    "f_value_change",
    "ability_suppressed",
    "bankruptcy",
    "game_end",
    "turn_end_snapshot",
    "resource_gain",
    "cash_gain",
    "coin_gain",
    "score_gain",
    "shard_gain",
}


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _string(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _numeric(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _event_code(payload: dict[str, Any]) -> str:
    return _string(payload.get("event_type", payload.get("type"))) or "event"


def _message_seq(message: dict[str, Any]) -> int | None:
    return _number(message.get("seq"))


def _actor_player_id(payload: dict[str, Any]) -> int | None:
    return _number(payload.get("acting_player_id", payload.get("player_id", payload.get("player"))))


def _turn_numbers(payload: dict[str, Any], current_round: int | None, current_turn: int | None) -> tuple[int | None, int | None]:
    round_index = _number(payload.get("round_index")) or current_round
    turn_index = _number(payload.get("turn_index")) or current_turn
    return round_index, turn_index


def _turn_key(round_index: int | None, turn_index: int | None) -> str | None:
    if round_index is None or turn_index is None:
        return None
    return f"r{round_index}:t{turn_index}"


def _tone(event_code: str) -> str:
    if event_code in CRITICAL_EVENT_CODES:
        return "critical"
    if event_code in MOVE_EVENT_CODES:
        return "move"
    if event_code in ECONOMY_EVENT_CODES:
        return "economy"
    return "system"


def _scope(event_code: str) -> str:
    return "common" if event_code in COMMON_EVENT_CODES else "player"


def _participants(payload: dict[str, Any]) -> dict[str, int]:
    participants: dict[str, int] = {}
    field_names = (
        "actor_player_id",
        "acting_player_id",
        "player_id",
        "source_player_id",
        "target_player_id",
        "payer_player_id",
        "owner_player_id",
        "from_player_id",
        "to_player_id",
    )
    actor_id = _actor_player_id(payload)
    if actor_id is not None:
        participants["actor_player_id"] = actor_id
    for field_name in field_names:
        value = _number(payload.get(field_name))
        if value is not None:
            normalized = "actor_player_id" if field_name == "acting_player_id" else field_name
            participants[normalized] = value
    return participants


def _append_tile_index(indices: list[int], value: Any) -> None:
    index = _number(value)
    if index is not None and index not in indices:
        indices.append(index)


def _focus_tile_indices(payload: dict[str, Any]) -> list[int]:
    indices: list[int] = []
    for field_name in (
        "focus_tile_index",
        "tile_index",
        "position",
        "from_tile_index",
        "to_tile_index",
        "target_tile_index",
        "target_pos",
        "end_pos",
    ):
        _append_tile_index(indices, payload.get(field_name))
    path = payload.get("path_tile_indices")
    if isinstance(path, list):
        for item in path:
            _append_tile_index(indices, item)
    return indices


def _resource_delta(payload: dict[str, Any]) -> dict[str, int | float] | None:
    delta: dict[str, int | float] = {}
    for source_key in ("resource_delta", "amount"):
        source = _record(payload.get(source_key))
        if source is None:
            continue
        for key, value in source.items():
            numeric = _numeric(value)
            if numeric is not None and numeric != 0:
                delta[str(key)] = numeric
    for source_key, target_key in (
        ("cash_delta", "cash"),
        ("money_delta", "cash"),
        ("shards_delta", "shards"),
        ("shard_delta", "shards"),
        ("coins_delta", "coins"),
        ("coin_delta", "coins"),
        ("score_delta", "score"),
        ("score_coin_delta", "score_coin"),
    ):
        numeric = _numeric(payload.get(source_key))
        if numeric is not None and numeric != 0:
            delta[target_key] = numeric
    return delta or None


def _end_time_delta(event_code: str, payload: dict[str, Any]) -> dict[str, int | float] | None:
    if event_code != "f_value_change":
        return None
    before = _numeric(payload.get("before"))
    delta = _numeric(payload.get("delta"))
    after = _numeric(payload.get("after"))
    if before is None and delta is None and after is None:
        return None
    return {
        "before": before or 0,
        "delta": delta or 0,
        "after": after or 0,
    }


def _public_payload(event_code: str, payload: dict[str, Any]) -> dict[str, Any]:
    public_payload = dict(payload)
    if event_code != "rent_paid":
        return public_payload

    modifiers = _record(public_payload.get("modifiers"))
    rent_context = _record(modifiers.get("rent_context")) if modifiers else None
    owner_player_id = _number(public_payload.get("owner_player_id"))
    if modifiers is None or rent_context is None or owner_player_id is None:
        return public_payload

    next_modifiers = dict(modifiers)
    next_rent_context = dict(rent_context)
    next_rent_context["owner_player_id"] = owner_player_id
    next_modifiers["rent_context"] = next_rent_context
    public_payload["modifiers"] = next_modifiers
    return public_payload


def _has_participant(participants: dict[str, int], player_id: int | None) -> bool:
    return player_id is not None and any(value == player_id for value in participants.values())


def _relevance(
    event_code: str,
    *,
    participants: dict[str, int],
    resource_delta: dict[str, int | float] | None,
    local_player_id: int | None,
) -> str:
    if local_player_id is not None:
        if event_code == "rent_paid" and (
            participants.get("payer_player_id") == local_player_id or participants.get("owner_player_id") == local_player_id
        ):
            return "mine-critical"
        if event_code.startswith("mark_") and (
            participants.get("source_player_id") == local_player_id or participants.get("target_player_id") == local_player_id
        ):
            return "mine-critical"
        if _has_participant(participants, local_player_id) and resource_delta:
            return "mine"
    if event_code in IMPORTANT_EVENT_CODES:
        return "important"
    return "public"


def build_turn_history_view_state(
    messages: list[dict[str, Any]],
    *,
    local_player_id: int | None = None,
) -> TurnHistoryViewState | None:
    turns: list[TurnHistoryTurnViewState] = []
    turn_by_key: dict[str, TurnHistoryTurnViewState] = {}
    current_round: int | None = None
    current_turn: int | None = None
    current_actor: int | None = None

    for message in messages:
        if _string(message.get("type")) != "event":
            continue
        payload = _record(message.get("payload")) or {}
        event_code = _event_code(payload)
        if event_code not in TURN_HISTORY_EVENT_CODES:
            continue
        seq = _message_seq(message)
        if seq is None:
            continue
        if event_code == "turn_start":
            current_round = _number(payload.get("round_index")) or current_round
            current_turn = _number(payload.get("turn_index")) or current_turn
            current_actor = _actor_player_id(payload) or current_actor
        round_index, turn_index = _turn_numbers(payload, current_round, current_turn)
        key = _turn_key(round_index, turn_index)
        if key is None:
            continue
        if key not in turn_by_key:
            actor_player_id = _actor_player_id(payload) or current_actor
            turn_item: TurnHistoryTurnViewState = {
                "key": key,
                "round_index": round_index or 0,
                "turn_index": turn_index or 0,
                "actor_player_id": actor_player_id,
                "event_count": 0,
                "important_count": 0,
                "events": [],
            }
            turn_by_key[key] = turn_item
            turns.append(turn_item)
        turn = turn_by_key[key]
        if turn.get("actor_player_id") is None:
            turn["actor_player_id"] = _actor_player_id(payload) or current_actor
        participants = _participants(payload)
        focus_tile_indices = _focus_tile_indices(payload)
        resource_delta = _resource_delta(payload)
        end_time_delta = _end_time_delta(event_code, payload)
        relevance = _relevance(
            event_code,
            participants=participants,
            resource_delta=resource_delta,
            local_player_id=local_player_id,
        )
        event: TurnHistoryEventViewState = {
            "seq": seq,
            "event_code": event_code,
            "payload": _public_payload(event_code, payload),
            "tone": _tone(event_code),  # type: ignore[typeddict-item]
            "scope": _scope(event_code),  # type: ignore[typeddict-item]
            "relevance": relevance,  # type: ignore[typeddict-item]
            "participants": participants,
            "focus_tile_indices": focus_tile_indices,
            "resource_delta": resource_delta,
            "end_time_delta": end_time_delta,
        }
        turn["events"].append(event)
        turn["event_count"] = len(turn["events"])
        if relevance != "public" and event_code != "turn_start":
            turn["important_count"] = int(turn["important_count"]) + 1

    if not turns:
        return None
    return {
        "current_key": turns[-1]["key"],
        "turns": turns,
    }
