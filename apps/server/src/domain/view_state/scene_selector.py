from __future__ import annotations

from typing import Any

from .types import (
    CoreActionFeedItemViewState,
    CriticalAlertItemViewState,
    SceneViewState,
    SituationSceneViewState,
    TheaterFeedItemViewState,
    TimelineItemViewState,
)


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
    "mark_queued",
    "mark_target_none",
    "mark_target_missing",
    "mark_blocked",
    "bankruptcy",
    "game_end",
    "turn_end_snapshot",
}

PROMPT_EVENT_CODES = {"decision_requested", "decision_resolved", "decision_timeout_fallback"}
WEATHER_EVENT_CODES = {"weather_reveal", "turn_start", "round_start"}
MOVE_EVENT_CODES = {"player_move", "dice_roll"}
ECONOMY_EVENT_CODES = {
    "tile_purchased",
    "landing_resolved",
    "rent_paid",
    "marker_transferred",
    "lap_reward_chosen",
    "fortune_drawn",
    "fortune_resolved",
}
CRITICAL_EVENT_CODES = {"bankruptcy", "game_end", "trick_used"}


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


def _decision_provider(payload: dict[str, Any]) -> str:
    return _string(payload.get("provider"))


def _message_actor_player_id(message: dict[str, Any]) -> int | None:
    payload = _record(message.get("payload")) or {}
    if message.get("type") == "event":
        return _number(payload.get("acting_player_id", payload.get("player_id", payload.get("player"))))
    return _number(payload.get("player_id"))


def _round_turn(message: dict[str, Any]) -> tuple[int | None, int | None]:
    payload = _record(message.get("payload")) or {}
    return (_number(payload.get("round_index")), _number(payload.get("turn_index")))


def _tone_from_message(message: dict[str, Any]) -> str:
    message_type = _string(message.get("type"))
    if message_type == "error":
        return "critical"
    if message_type in {"prompt", "decision_ack"}:
        return "system"
    if message_type != "event":
        return "system"
    event_code = _event_code(_record(message.get("payload")) or {})
    if event_code in CRITICAL_EVENT_CODES:
        return "critical"
    if event_code in MOVE_EVENT_CODES:
        return "move"
    if event_code in ECONOMY_EVENT_CODES:
        return "economy"
    return "system"


def _lane_from_message(message: dict[str, Any]) -> str:
    message_type = _string(message.get("type"))
    if message_type == "decision_ack":
        return "prompt"
    if message_type == "prompt":
        return "system"
    if message_type != "event":
        return "system"
    payload = _record(message.get("payload")) or {}
    event_code = _event_code(payload)
    if event_code in PROMPT_EVENT_CODES:
        if _decision_provider(payload) == "ai":
            return "system"
        return "prompt"
    if event_code in CORE_EVENT_CODES:
        return "core"
    return "system"


def _is_core_action_message(message: dict[str, Any]) -> bool:
    if _string(message.get("type")) != "event":
        return False
    event_code = _event_code(_record(message.get("payload")) or {})
    return event_code in CORE_EVENT_CODES or event_code == "decision_timeout_fallback"


def _is_critical_alert_message(message: dict[str, Any]) -> bool:
    message_type = _string(message.get("type"))
    if message_type == "error":
        payload = _record(message.get("payload")) or {}
        return _string(payload.get("code")) == "RUNTIME_EXECUTION_FAILED"
    if message_type != "event":
        return False
    event_code = _event_code(_record(message.get("payload")) or {})
    return event_code in {"bankruptcy", "game_end", "decision_timeout_fallback"}


def _is_situation_noise(message: dict[str, Any]) -> bool:
    message_type = _string(message.get("type"))
    if message_type in {"heartbeat", "prompt", "decision_ack", "error"}:
        return True
    if message_type == "event":
        event_code = _event_code(_record(message.get("payload")) or {})
        if event_code in PROMPT_EVENT_CODES or event_code == "parameter_manifest":
            return True
    return False


def _latest_situation_message(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if not _is_situation_noise(message):
            return message
    return messages[-1] if messages else None


def _find_latest_field(messages: list[dict[str, Any]], keys: tuple[str, ...]) -> Any:
    for message in reversed(messages):
        payload = _record(message.get("payload")) or {}
        for key in keys:
            value = payload.get(key)
            if value is not None:
                return value
    return None


def _find_persisted_weather(messages: list[dict[str, Any]]) -> tuple[str, str]:
    for message in reversed(messages):
        if _string(message.get("type")) != "event":
            continue
        payload = _record(message.get("payload")) or {}
        event_code = _event_code(payload)
        if event_code not in WEATHER_EVENT_CODES:
            continue
        weather_name = _string(payload.get("weather_name", payload.get("weather", payload.get("card"))))
        effects = payload.get("effects")
        if isinstance(effects, list):
            effect_parts = [item for item in effects if isinstance(item, str) and item.strip()]
            weather_effect = " / ".join(effect_parts) if effect_parts else ""
        else:
            weather_effect = _string(
                payload.get("weather_effect", payload.get("effect_text", payload.get("effect", payload.get("description"))))
            )
        if weather_name:
            return (weather_name, weather_effect or "-")
    return ("-", "-")


def build_scene_view_state(
    messages: list[dict[str, Any]],
    theater_limit: int = 20,
    core_limit: int = 10,
    timeline_limit: int = 12,
    alert_limit: int = 4,
) -> SceneViewState | None:
    if not messages:
        return None

    latest = _latest_situation_message(messages)
    if latest is None:
        return None
    latest_payload = _record(latest.get("payload")) or {}
    weather_name, weather_effect = _find_persisted_weather(messages)
    situation: SituationSceneViewState = {
        "actor_player_id": _number(_find_latest_field(messages, ("acting_player_id", "player_id"))),
        "round_index": _number(_find_latest_field(messages, ("round_index",))),
        "turn_index": _number(_find_latest_field(messages, ("turn_index",))),
        "headline_seq": _number(latest.get("seq")),
        "headline_message_type": _string(latest.get("type")) or "event",
        "headline_event_code": _event_code(latest_payload) if _string(latest.get("type")) == "event" else _string(latest.get("type")) or "event",
        "weather_name": weather_name,
        "weather_effect": weather_effect,
    }

    safe_theater_limit = max(1, int(theater_limit))
    core_cap = max(1, safe_theater_limit // 2)
    prompt_cap = max(1, int(safe_theater_limit * 0.3))
    system_cap = max(1, safe_theater_limit - core_cap - prompt_cap)
    caps = {"core": core_cap, "prompt": prompt_cap, "system": system_cap}
    lane_counts = {"core": 0, "prompt": 0, "system": 0}
    theater_items: list[TheaterFeedItemViewState] = []
    picked_seq: set[int] = set()

    for message in reversed(messages):
        message_type = _string(message.get("type"))
        if message_type == "heartbeat":
            continue
        seq = _number(message.get("seq"))
        if seq is None:
            continue
        lane = _lane_from_message(message)
        if lane_counts[lane] >= caps[lane]:
            continue
        round_index, turn_index = _round_turn(message)
        theater_items.append(
            {
                "seq": seq,
                "message_type": message_type or "event",
                "event_code": _event_code(_record(message.get("payload")) or {}) if message_type == "event" else message_type or "event",
                "tone": _tone_from_message(message),  # type: ignore[typeddict-item]
                "lane": lane,  # type: ignore[typeddict-item]
                "actor_player_id": _message_actor_player_id(message),
                "round_index": round_index,
                "turn_index": turn_index,
            }
        )
        picked_seq.add(seq)
        lane_counts[lane] += 1
        if len(theater_items) >= safe_theater_limit:
            break

    if len(theater_items) < safe_theater_limit:
        for message in reversed(messages):
            message_type = _string(message.get("type"))
            if message_type == "heartbeat":
                continue
            seq = _number(message.get("seq"))
            if seq is None or seq in picked_seq:
                continue
            round_index, turn_index = _round_turn(message)
            theater_items.append(
                {
                    "seq": seq,
                    "message_type": message_type or "event",
                    "event_code": _event_code(_record(message.get("payload")) or {}) if message_type == "event" else message_type or "event",
                    "tone": _tone_from_message(message),  # type: ignore[typeddict-item]
                    "lane": _lane_from_message(message),  # type: ignore[typeddict-item]
                    "actor_player_id": _message_actor_player_id(message),
                    "round_index": round_index,
                    "turn_index": turn_index,
                }
            )
            if len(theater_items) >= safe_theater_limit:
                break

    theater_items.sort(key=lambda item: item["seq"], reverse=True)

    safe_core_limit = max(1, int(core_limit))
    core_items: list[CoreActionFeedItemViewState] = []
    for message in reversed(messages):
        if not _is_core_action_message(message):
            continue
        seq = _number(message.get("seq"))
        if seq is None:
            continue
        payload = _record(message.get("payload")) or {}
        round_index, turn_index = _round_turn(message)
        core_items.append(
            {
                "seq": seq,
                "event_code": _event_code(payload),
                "actor_player_id": _message_actor_player_id(message),
                "round_index": round_index,
                "turn_index": turn_index,
            }
        )
        if len(core_items) >= safe_core_limit:
            break

    safe_timeline_limit = max(1, int(timeline_limit))
    timeline_items: list[TimelineItemViewState] = []
    for message in reversed(messages[-safe_timeline_limit:]):
        message_type = _string(message.get("type")) or "event"
        payload = _record(message.get("payload")) or {}
        seq = _number(message.get("seq"))
        if seq is None:
            continue
        timeline_items.append(
            {
                "seq": seq,
                "message_type": message_type,
                "event_code": _event_code(payload) if message_type == "event" else message_type,
            }
        )

    safe_alert_limit = max(1, int(alert_limit))
    critical_alerts: list[CriticalAlertItemViewState] = []
    for message in reversed(messages):
        if not _is_critical_alert_message(message):
            continue
        message_type = _string(message.get("type")) or "event"
        payload = _record(message.get("payload")) or {}
        seq = _number(message.get("seq"))
        if seq is None:
            continue
        critical_alerts.append(
            {
                "seq": seq,
                "message_type": message_type,
                "event_code": _event_code(payload) if message_type == "event" else message_type,
                "severity": "warning"
                if message_type == "event" and _event_code(payload) == "decision_timeout_fallback"
                else "critical",
            }
        )
        if len(critical_alerts) >= safe_alert_limit:
            break

    return {
        "situation": situation,
        "theater_feed": theater_items,
        "core_action_feed": core_items,
        "timeline": timeline_items,
        "critical_alerts": critical_alerts,
    }
