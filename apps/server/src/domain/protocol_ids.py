from __future__ import annotations

from typing import Any
from uuid import uuid4


def new_protocol_id(prefix: str) -> str:
    normalized = str(prefix or "").strip().lower().rstrip("_")
    if not normalized:
        raise ValueError("missing_protocol_id_prefix")
    return f"{normalized}_{uuid4()}"


def new_public_player_id() -> str:
    return new_protocol_id("ply")


def new_seat_id() -> str:
    return new_protocol_id("seat")


def new_viewer_id() -> str:
    return new_protocol_id("view")


def new_event_id() -> str:
    return new_protocol_id("evt")


def new_request_uuid() -> str:
    return new_protocol_id("req")


def int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def player_label(seat_index: Any) -> str:
    return f"P{int_or_default(seat_index, 0)}"


def turn_label(round_index: Any, turn_index: Any) -> str:
    return f"R{int_or_default(round_index, 0)}-T{int_or_default(turn_index, 0)}"
