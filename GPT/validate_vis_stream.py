from __future__ import annotations

from collections import Counter


KNOWN_EVENT_TYPES = {
    "session_start",
    "round_start",
    "weather_reveal",
    "round_order",
    "draft_pick",
    "final_character_choice",
    "turn_start",
    "trick_window_open",
    "trick_used",
    "trick_window_closed",
    "dice_roll",
    "player_move",
    "action_move",
    "landing_resolved",
    "rent_paid",
    "tile_purchased",
    "fortune_drawn",
    "fortune_resolved",
    "mark_resolved",
    "mark_queued",
    "mark_target_none",
    "mark_target_missing",
    "marker_transferred",
    "marker_flip",
    "lap_reward_chosen",
    "f_value_change",
    "bankruptcy",
    "turn_end_snapshot",
    "game_end",
}

REQUIRED_PAYLOAD_FIELDS: dict[str, set[str]] = {
    "session_start": {"player_count", "players"},
    "round_start": {"initial", "alive_player_ids", "marker_owner_player_id"},
    "weather_reveal": {"weather_name", "effects"},
    "trick_used": {"phase", "card_name", "card_description", "resolution"},
    "dice_roll": {"player_id", "dice_values", "cards_used", "total_move"},
    "player_move": {"player_id", "from_tile_index", "to_tile_index", "path", "movement_source"},
    "action_move": {"player_id", "from_tile_index", "to_tile_index", "path", "movement_source"},
    "rent_paid": {"payer_player_id", "owner_player_id", "tile_index", "base_amount", "final_amount"},
    "tile_purchased": {"player_id", "tile_index", "cost", "purchase_source"},
    "mark_resolved": {"source_player_id", "target_player_id", "success", "resolution"},
    "marker_transferred": {"from_player_id", "to_player_id"},
    "lap_reward_chosen": {"choice", "amount", "resource_delta"},
    "f_value_change": {"before", "delta", "after"},
    "game_end": {"winner_ids", "winner_player_id", "reason", "total_turns", "snapshot"},
}

def validate_vis_stream(events: list[dict], *, strict_payload: bool = False) -> dict:
    errors: list[str] = []
    if not events:
        return {"ok": False, "errors": ["empty_event_stream"], "counts": {}}

    counts = Counter(event["event_type"] for event in events)
    unknown = sorted(set(counts) - KNOWN_EVENT_TYPES)
    if unknown:
        errors.append(f"unknown_event_types:{','.join(unknown)}")

    session_ids = {event.get("session_id") for event in events}
    if len(session_ids) != 1:
        errors.append("session_id_inconsistent")

    step_indexes = [int(event["step_index"]) for event in events]
    if step_indexes != sorted(step_indexes) or len(step_indexes) != len(set(step_indexes)):
        errors.append("step_index_not_strictly_monotonic")

    if events[0].get("event_type") != "session_start":
        errors.append("first_event_not_session_start")
    if events[-1].get("event_type") != "game_end":
        errors.append("last_event_not_game_end")

    turn_starts = counts.get("turn_start", 0)
    turn_ends = counts.get("turn_end_snapshot", 0)
    if turn_starts != turn_ends:
        errors.append("turn_start_turn_end_snapshot_mismatch")

    dice_rolls = counts.get("dice_roll", 0)
    player_moves = counts.get("player_move", 0)
    if dice_rolls != player_moves:
        errors.append("dice_roll_player_move_mismatch")

    for event in events:
        for field in ("event_type", "session_id", "round_index", "turn_index", "step_index", "public_phase"):
            if field not in event:
                errors.append(f"missing_envelope:{field}")
                break
        if strict_payload:
            event_type = event.get("event_type")
            required_fields = REQUIRED_PAYLOAD_FIELDS.get(event_type, set())
            for field in required_fields:
                if field not in event:
                    errors.append(f"missing_payload:{event_type}:{field}:step={event.get('step_index')}")

    return {
        "ok": not errors,
        "errors": errors,
        "counts": dict(counts),
        "missing_known_event_types": sorted(KNOWN_EVENT_TYPES - set(counts)),
    }
