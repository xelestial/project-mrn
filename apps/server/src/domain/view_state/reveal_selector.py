from __future__ import annotations

from typing import Any

from .types import RevealItemViewState, RevealsViewState

CURRENT_TURN_REVEAL_EVENT_CODES: tuple[str, ...] = (
    "weather_reveal",
    "dice_roll",
    "player_move",
    "action_move",
    "landing_resolved",
    "tile_purchased",
    "rent_paid",
    "fortune_drawn",
    "fortune_resolved",
)

CURRENT_TURN_REVEAL_ORDER: dict[str, int] = {
    "weather_reveal": 10,
    "dice_roll": 20,
    "player_move": 30,
    "action_move": 30,
    "landing_resolved": 40,
    "rent_paid": 50,
    "tile_purchased": 50,
    "fortune_drawn": 60,
    "fortune_resolved": 70,
}

INTERRUPT_REVEAL_EVENT_CODES = {"weather_reveal", "fortune_drawn", "fortune_resolved"}


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _string(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def _event_type(payload: dict[str, Any]) -> str:
    return _string(payload.get("event_type")).lower()


def _same_round_turn(payload: dict[str, Any], round_index: int | None, turn_index: int | None) -> bool:
    payload_round = _number(payload.get("round_index"))
    payload_turn = _number(payload.get("turn_index"))
    return payload_round == round_index and payload_turn == turn_index


def _focus_tile_index(payload: dict[str, Any], event_code: str) -> int | None:
    if event_code in {"player_move", "action_move", "fortune_move", "forced_move", "chain_move"}:
        return _number(payload.get("to_tile_index", payload.get("to_tile", payload.get("to_pos"))))
    if event_code == "landing_resolved":
        return _number(payload.get("position", payload.get("tile_index", payload.get("tile"))))
    if event_code in {"tile_purchased", "rent_paid"}:
        return _number(payload.get("tile_index", payload.get("position", payload.get("tile"))))
    if event_code in {"fortune_drawn", "fortune_resolved"}:
        return _number(
            payload.get(
                "tile_index",
                payload.get("position", payload.get("end_pos", payload.get("target_pos", payload.get("tile")))),
            )
        )
    if event_code == "trick_used":
        return _number(payload.get("tile_index", payload.get("position", payload.get("target_pos", payload.get("tile")))))
    return None


def _tone_for_event(event_code: str) -> str:
    if event_code in {"dice_roll", "player_move", "action_move", "fortune_move", "forced_move", "chain_move"}:
        return "move"
    if event_code in {"tile_purchased", "rent_paid"}:
        return "economy"
    return "effect"


def build_reveals_view_state(messages: list[dict[str, Any]], limit: int = 6) -> RevealsViewState | None:
    safe_limit = max(1, int(limit))
    turn_start_index = -1
    target_round: int | None = None
    target_turn: int | None = None

    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        if _event_type(payload) != "turn_start":
            continue
        turn_start_index = index
        target_round = _number(payload.get("round_index"))
        target_turn = _number(payload.get("turn_index"))
        break

    if turn_start_index < 0:
        return None

    items: list[RevealItemViewState] = []
    for message in messages[turn_start_index + 1 :]:
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        if not _same_round_turn(payload, target_round, target_turn):
            continue
        event_code = _event_type(payload)
        if event_code not in CURRENT_TURN_REVEAL_EVENT_CODES:
            continue
        seq = _number(message.get("seq"))
        if seq is None:
            continue
        items.append(
            {
                "seq": seq,
                "event_code": event_code,
                "event_order": CURRENT_TURN_REVEAL_ORDER.get(event_code, 999),
                "tone": _tone_for_event(event_code),  # type: ignore[typeddict-item]
                "focus_tile_index": _focus_tile_index(payload, event_code),
                "is_interrupt": event_code in INTERRUPT_REVEAL_EVENT_CODES,
            }
        )

    items.sort(key=lambda item: (item["event_order"], item["seq"]))
    return {
        "round_index": target_round,
        "turn_index": target_turn,
        "items": items[-safe_limit:],
    }
