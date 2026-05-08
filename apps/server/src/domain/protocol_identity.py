from __future__ import annotations

from typing import Any

from apps.server.src.domain.protocol_ids import int_or_default, player_label


def display_identity_fields(seat_index: Any, *, legacy_player_id: Any | None = None) -> dict[str, Any]:
    index = int_or_default(seat_index, 0)
    fields: dict[str, Any] = {
        "seat_index": index,
        "turn_order_index": index,
        "player_label": player_label(index),
    }
    if legacy_player_id is not None:
        fields["legacy_player_id"] = int_or_default(legacy_player_id, index)
    return fields


def seat_protocol_fields(seat: Any) -> dict[str, Any]:
    fields = display_identity_fields(getattr(seat, "seat", None), legacy_player_id=getattr(seat, "player_id", None))
    fields.update(
        {
            "seat_id": getattr(seat, "seat_id", None),
            "public_player_id": getattr(seat, "public_player_id", None),
            "viewer_id": getattr(seat, "viewer_id", None),
        }
    )
    return fields
