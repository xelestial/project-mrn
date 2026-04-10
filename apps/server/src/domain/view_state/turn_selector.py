from __future__ import annotations

from typing import Any

from .types import TurnStageViewState


CORE_EVENT_CODES = {
    "round_start",
    "weather_reveal",
    "draft_pick",
    "final_character_choice",
    "turn_start",
    "dice_roll",
    "trick_used",
    "player_move",
    "landing_resolved",
    "rent_paid",
    "tile_purchased",
    "marker_transferred",
    "marker_flip",
    "lap_reward_chosen",
    "fortune_drawn",
    "fortune_resolved",
    "decision_requested",
    "decision_resolved",
    "decision_timeout_fallback",
    "mark_queued",
    "mark_target_none",
    "mark_target_missing",
    "mark_blocked",
    "bankruptcy",
    "game_end",
    "turn_end_snapshot",
}


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _string(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _event_code(payload: dict[str, Any]) -> str:
    return _string(payload.get("event_type", payload.get("type"))) or "event"


def _round_turn(payload: dict[str, Any]) -> tuple[int | None, int | None]:
    return (_number(payload.get("round_index")), _number(payload.get("turn_index")))


def _same_round_turn(payload: dict[str, Any], round_index: int | None, turn_index: int | None) -> bool:
    if round_index is None or turn_index is None:
        return False
    current_round, current_turn = _round_turn(payload)
    return current_round == round_index and current_turn == turn_index


def _event_player_id(payload: dict[str, Any]) -> int | None:
    return _number(payload.get("player_id", payload.get("acting_player_id", payload.get("player"))))


def _find_persisted_weather(messages: list[dict[str, Any]]) -> tuple[str, str]:
    for message in reversed(messages):
        payload = _record(message.get("payload")) or {}
        public_context = _record(payload.get("public_context")) or {}
        message_type = _string(message.get("type"))
        event_code = _event_code(payload) if message_type == "event" else ""
        if message_type == "event" and event_code not in {"weather_reveal", "turn_start", "round_start"}:
            if not _string(public_context.get("weather_name")):
                continue
        elif message_type not in {"event", "prompt"}:
            continue
        weather_name = _string(
            payload.get("weather_name", payload.get("weather", payload.get("card", public_context.get("weather_name"))))
        )
        weather_effect = _string(
            payload.get(
                "weather_effect",
                payload.get("effect_text", payload.get("effect", payload.get("description", public_context.get("weather_effect")))),
            )
        )
        if weather_name:
            return (weather_name, weather_effect or "-")
    return ("-", "-")


def _turn_beat_kind(event_code: str) -> str:
    if event_code in {"dice_roll", "player_move"}:
        return "move"
    if event_code in {"tile_purchased", "rent_paid", "lap_reward_chosen"}:
        return "economy"
    if event_code in {
        "weather_reveal",
        "fortune_drawn",
        "fortune_resolved",
        "trick_used",
        "marker_flip",
        "marker_transferred",
        "landing_resolved",
    }:
        return "effect"
    if event_code in {"draft_pick", "final_character_choice", "decision_requested", "decision_resolved", "decision_timeout_fallback"}:
        return "decision"
    return "system"


def _focus_tile_indices_from_prompt_payload(payload: dict[str, Any]) -> list[int]:
    public_context = _record(payload.get("public_context")) or {}
    context_tile_index = _number(public_context.get("tile_index"))
    landing_tile_index = _number(public_context.get("landing_tile_index"))
    candidate_tiles = public_context.get("candidate_tiles")
    context_candidate_tiles = (
        [_number(item) for item in candidate_tiles if _number(item) is not None] if isinstance(candidate_tiles, list) else []
    )
    if landing_tile_index is not None:
        ordered = []
        for item in [landing_tile_index, context_tile_index, *context_candidate_tiles]:
            if item is not None and item not in ordered:
                ordered.append(item)
        if ordered:
            return ordered
    if context_tile_index is not None and context_candidate_tiles:
        return [context_tile_index, *[item for item in context_candidate_tiles if item != context_tile_index]]
    if context_tile_index is not None:
        return [context_tile_index]
    legal_choices = payload.get("legal_choices")
    from_choices: list[int] = []
    if isinstance(legal_choices, list):
        for choice in legal_choices:
            item = _record(choice)
            if not item:
                continue
            value = _record(item.get("value")) or {}
            choice_tile_index = _number(value.get("tile_index"))
            if choice_tile_index is not None and choice_tile_index not in from_choices:
                from_choices.append(choice_tile_index)
    if from_choices:
        return from_choices
    return context_candidate_tiles


def _focus_tile_index_from_event_payload(payload: dict[str, Any], event_code: str) -> int | None:
    if event_code == "player_move":
        return _number(payload.get("to_tile_index", payload.get("to_tile", payload.get("to_pos"))))
    if event_code == "landing_resolved":
        return _number(payload.get("position", payload.get("tile_index", payload.get("tile"))))
    if event_code in {"tile_purchased", "rent_paid"}:
        return _number(payload.get("tile_index", payload.get("position", payload.get("tile"))))
    if event_code in {"fortune_drawn", "fortune_resolved", "trick_used"}:
        return _number(payload.get("tile_index", payload.get("position", payload.get("end_pos", payload.get("target_pos", payload.get("tile"))))))
    return None


def _update_actor_status(model: TurnStageViewState, payload: dict[str, Any]) -> None:
    public_context = _record(payload.get("public_context")) or payload
    cash = _number(public_context.get("player_cash"))
    shards = _number(public_context.get("player_shards"))
    hand_coins = _number(public_context.get("player_hand_coins"))
    placed_coins = _number(public_context.get("player_placed_coins"))
    total_score = _number(public_context.get("player_total_score"))
    owned_tile_count = _number(public_context.get("player_owned_tile_count"))
    if cash is not None:
        model["actor_cash"] = cash
    if shards is not None:
        model["actor_shards"] = shards
    if hand_coins is not None:
        model["actor_hand_coins"] = hand_coins
    if placed_coins is not None:
        model["actor_placed_coins"] = placed_coins
    if total_score is not None:
        model["actor_total_score"] = total_score
    if owned_tile_count is not None:
        model["actor_owned_tile_count"] = owned_tile_count


def _is_pre_character_selection_request_type(request_type: str) -> bool:
    return request_type in {"draft_card", "final_character", "final_character_choice"}


def _update_actor_from_prompt(model: TurnStageViewState, payload: dict[str, Any]) -> None:
    prompt_actor = _number(payload.get("player_id", payload.get("acting_player_id")))
    if prompt_actor is not None:
        model["actor_player_id"] = prompt_actor
    public_context = _record(payload.get("public_context")) or {}
    round_index = _number(public_context.get("round_index", payload.get("round_index")))
    turn_index = _number(public_context.get("turn_index", payload.get("turn_index")))
    if round_index is not None:
        model["round_index"] = round_index
    if turn_index is not None:
        model["turn_index"] = turn_index
    request_type = _string(payload.get("request_type"))
    if _is_pre_character_selection_request_type(request_type):
        model["character"] = "-"
        return
    actor_name = _string(public_context.get("actor_name", payload.get("actor_name", payload.get("character"))))
    if actor_name:
        model["character"] = actor_name


def _update_external_ai_status(model: TurnStageViewState, payload: dict[str, Any]) -> None:
    public_context = _record(payload.get("public_context")) or {}
    mapping = {
        "external_ai_worker_id": "external_ai_worker_id",
        "external_ai_failure_code": "external_ai_failure_code",
        "external_ai_fallback_mode": "external_ai_fallback_mode",
        "external_ai_resolution_status": "external_ai_resolution_status",
        "external_ai_ready_state": "external_ai_ready_state",
        "external_ai_policy_mode": "external_ai_policy_mode",
        "external_ai_worker_adapter": "external_ai_worker_adapter",
        "external_ai_policy_class": "external_ai_policy_class",
        "external_ai_decision_style": "external_ai_decision_style",
    }
    for source_key, target_key in mapping.items():
        value = _string(public_context.get(source_key))
        if value:
            model[target_key] = value
    attempt_count = _number(public_context.get("external_ai_attempt_count"))
    attempt_limit = _number(public_context.get("external_ai_attempt_limit"))
    if attempt_count is not None:
        model["external_ai_attempt_count"] = attempt_count
    if attempt_limit is not None:
        model["external_ai_attempt_limit"] = attempt_limit


def build_turn_stage_view_state(messages: list[dict[str, Any]]) -> TurnStageViewState | None:
    turn_start_index = -1
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        if _event_code(payload) == "turn_start":
            turn_start_index = index
            break
    if turn_start_index < 0:
        return None

    start_message = messages[turn_start_index]
    start_payload = _record(start_message.get("payload")) or {}
    actor_player_id = _number(start_payload.get("acting_player_id", start_payload.get("player_id")))
    round_index, turn_index = _round_turn(start_payload)
    weather_name, weather_effect = _find_persisted_weather(messages)
    model: TurnStageViewState = {
        "turn_start_seq": start_message.get("seq"),
        "actor_player_id": actor_player_id,
        "round_index": round_index,
        "turn_index": turn_index,
        "character": _string(start_payload.get("character", start_payload.get("actor_name"))) or "-",
        "weather_name": weather_name,
        "weather_effect": weather_effect,
        "current_beat_kind": "system",
        "current_beat_event_code": "turn_start",
        "current_beat_request_type": "-",
        "current_beat_seq": start_message.get("seq"),
        "focus_tile_index": None,
        "focus_tile_indices": [],
        "prompt_request_type": "-",
        "external_ai_worker_id": "-",
        "external_ai_failure_code": "-",
        "external_ai_fallback_mode": "-",
        "external_ai_resolution_status": "-",
        "external_ai_attempt_count": None,
        "external_ai_attempt_limit": None,
        "external_ai_ready_state": "-",
        "external_ai_policy_mode": "-",
        "external_ai_worker_adapter": "-",
        "external_ai_policy_class": "-",
        "external_ai_decision_style": "-",
        "actor_cash": None,
        "actor_shards": None,
        "actor_hand_coins": None,
        "actor_placed_coins": None,
        "actor_total_score": None,
        "actor_owned_tile_count": None,
        "progress_codes": ["turn_start"],
    }

    def update_beat(event_code: str, seq: int | None, kind: str, focus_tile_index: int | None) -> None:
        model["current_beat_event_code"] = event_code
        model["current_beat_seq"] = seq
        model["current_beat_kind"] = kind  # type: ignore[assignment]
        if focus_tile_index is not None:
            model["focus_tile_index"] = focus_tile_index
            model["focus_tile_indices"] = [focus_tile_index]
        model["progress_codes"] = [*model["progress_codes"], event_code]

    for message in messages[turn_start_index + 1 :]:
        payload = _record(message.get("payload")) or {}
        if message.get("type") == "prompt":
            request_type = _string(payload.get("request_type"))
            prompt_actor = _number(payload.get("player_id"))
            public_context = _record(payload.get("public_context")) or {}
            if request_type and (
                model["actor_player_id"] is None
                or model["actor_player_id"] == prompt_actor
                or _is_pre_character_selection_request_type(request_type)
            ):
                _update_actor_from_prompt(model, payload)
                _update_actor_status(model, payload)
                model["prompt_request_type"] = request_type
                model["current_beat_kind"] = "decision"
                model["current_beat_event_code"] = "prompt_active"
                model["current_beat_request_type"] = request_type
                model["current_beat_seq"] = message.get("seq")
                prompt_focus_tile_indices = _focus_tile_indices_from_prompt_payload(payload)
                if prompt_focus_tile_indices:
                    model["focus_tile_indices"] = prompt_focus_tile_indices
                    model["focus_tile_index"] = prompt_focus_tile_indices[0]
                if not model["progress_codes"] or model["progress_codes"][-1] != "prompt_active":
                    model["progress_codes"] = [*model["progress_codes"], "prompt_active"]
            prompt_weather_name = _string(public_context.get("weather_name"))
            prompt_weather_effect = _string(public_context.get("weather_effect"))
            if prompt_weather_name:
                model["weather_name"] = prompt_weather_name
            if prompt_weather_effect:
                model["weather_effect"] = prompt_weather_effect
            continue
        if message.get("type") != "event":
            continue
        if not _same_round_turn(payload, model["round_index"], model["turn_index"]):
            continue
        event_code = _event_code(payload)
        if event_code == "turn_start":
            continue
        if event_code in CORE_EVENT_CODES and event_code != "turn_end_snapshot":
            update_beat(
                event_code,
                message.get("seq"),
                _turn_beat_kind(event_code),
                _focus_tile_index_from_event_payload(payload, event_code),
            )
        if event_code == "weather_reveal":
            weather_name = _string(payload.get("weather_name", payload.get("weather", payload.get("card"))))
            weather_effect = _string(payload.get("weather_effect", payload.get("effect_text", payload.get("effect", payload.get("description")))))
            if weather_name:
                model["weather_name"] = weather_name
            if weather_effect:
                model["weather_effect"] = weather_effect
            continue
        if event_code in {"decision_requested", "decision_resolved", "decision_timeout_fallback"}:
            _update_actor_from_prompt(model, payload)
            _update_external_ai_status(model, payload)
            _update_actor_status(model, payload)
            request_type = _string(payload.get("request_type"))
            if request_type:
                model["prompt_request_type"] = request_type
                model["current_beat_request_type"] = request_type
            prompt_focus_tile_indices = _focus_tile_indices_from_prompt_payload(payload)
            if prompt_focus_tile_indices:
                model["focus_tile_indices"] = prompt_focus_tile_indices
                model["focus_tile_index"] = prompt_focus_tile_indices[0]
            continue
        if event_code == "turn_end_snapshot":
            update_beat(
                event_code,
                message.get("seq"),
                "system",
                _focus_tile_index_from_event_payload(payload, event_code),
            )
            continue
        if event_code in {"lap_reward_chosen", "mark_queued", "mark_target_none", "mark_target_missing", "mark_blocked", "mark_resolved", "marker_flip"}:
            continue

    return model
