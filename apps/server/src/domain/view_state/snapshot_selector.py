from __future__ import annotations

from typing import Any


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _direction_from_record(raw: Any) -> str | None:
    record = _record(raw)
    if not record:
        return None
    value = record.get("marker_draft_direction", record.get("draft_direction"))
    return value if value in {"clockwise", "counterclockwise"} else None


def latest_player_snapshot(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        explicit_snapshot = _record(payload.get("snapshot")) or {}
        snapshot_board = _record(explicit_snapshot.get("board")) or {}
        players = explicit_snapshot.get("players")
        if not isinstance(players, list):
            players = payload.get("players")
        if not isinstance(players, list):
            continue
        marker_owner_player_id = _number(
            snapshot_board.get("marker_owner_player_id", payload.get("marker_owner_player_id"))
        )
        marker_draft_direction = _direction_from_record(snapshot_board) or _direction_from_record(payload)
        return {
            "players": players,
            "marker_owner_player_id": marker_owner_player_id,
            "marker_draft_direction": marker_draft_direction,
        }
    return None


def latest_player_snapshot_entry(messages: list[dict[str, Any]]) -> tuple[int, dict[str, Any]] | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        explicit_snapshot = _record(payload.get("snapshot")) or {}
        snapshot_board = _record(explicit_snapshot.get("board")) or {}
        players = explicit_snapshot.get("players")
        if not isinstance(players, list):
            players = payload.get("players")
        if not isinstance(players, list):
            continue
        marker_owner_player_id = _number(
            snapshot_board.get("marker_owner_player_id", payload.get("marker_owner_player_id"))
        )
        marker_draft_direction = _direction_from_record(snapshot_board) or _direction_from_record(payload)
        return (
            index,
            {
                "players": players,
                "marker_owner_player_id": marker_owner_player_id,
                "marker_draft_direction": marker_draft_direction,
            },
        )
    return None


def marker_state_from_messages(
    messages: list[dict[str, Any]],
    marker_owner_player_id: int | None,
    marker_draft_direction: str | None,
) -> tuple[int | None, str | None]:
    owner = marker_owner_player_id
    direction = marker_draft_direction
    for message in messages:
        if message.get("type") != "event":
            continue
        payload = _record(message.get("payload")) or {}
        event_type = str(payload.get("event_type", "")).strip().lower()
        public_context = _record(payload.get("public_context")) or {}
        if event_type == "marker_transferred":
            owner = _number(payload.get("to_player_id", payload.get("to_owner"))) or owner
            direction = _direction_from_record(payload) or _direction_from_record(public_context) or direction
            continue
        if event_type in {"round_start", "round_order"}:
            owner = _number(payload.get("marker_owner_player_id", public_context.get("marker_owner_player_id"))) or owner
            direction = _direction_from_record(payload) or _direction_from_record(public_context) or direction
    return owner, direction
