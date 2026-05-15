from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_PRIVATE_DECISION_REQUEST_TYPES = {"draft_card", "final_character", "final_character_choice", "hidden_trick_card"}
_PRIVATE_PAYLOAD_KEYS = {
    "full_hand",
    "hand_names",
    "hidden_trick_deck_index",
    "legal_choices",
    "offered_names",
    "picked_card",
}


@dataclass(frozen=True, slots=True)
class ViewerContext:
    role: str
    session_id: str = ""
    seat: int | None = None
    player_id: int | None = None
    legacy_player_id: int | None = None
    public_player_id: str | None = None
    seat_id: str | None = None
    viewer_id: str | None = None
    seat_index: int | None = None
    turn_order_index: int | None = None
    player_label: str | None = None

    @property
    def is_seat(self) -> bool:
        return self.role == "seat" and self.player_id is not None

    @property
    def is_spectator(self) -> bool:
        return self.role == "spectator"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_backend(self) -> bool:
        return self.role == "backend"


def viewer_from_auth_context(auth_ctx: dict[str, Any], *, session_id: str = "") -> ViewerContext:
    role = str(auth_ctx.get("role") or "spectator").strip().lower()
    seat = _optional_int(auth_ctx.get("seat"))
    player_id = _optional_int(auth_ctx.get("player_id"))
    return ViewerContext(
        role=role,
        session_id=session_id,
        seat=seat,
        player_id=player_id,
        legacy_player_id=_optional_int(auth_ctx.get("legacy_player_id")),
        public_player_id=_optional_str(auth_ctx.get("public_player_id")),
        seat_id=_optional_str(auth_ctx.get("seat_id")),
        viewer_id=_optional_str(auth_ctx.get("viewer_id")),
        seat_index=_optional_int(auth_ctx.get("seat_index")),
        turn_order_index=_optional_int(auth_ctx.get("turn_order_index")),
        player_label=_optional_str(auth_ctx.get("player_label")),
    )


def can_view(visibility: dict[str, Any] | None, viewer: ViewerContext) -> bool:
    if not visibility:
        return True
    scope = str(visibility.get("scope") or "public").strip().lower()
    if scope == "public":
        return True
    if scope == "spectator_safe":
        return viewer.is_spectator or viewer.is_seat or viewer.is_admin or viewer.is_backend
    if scope == "player":
        return viewer.is_admin or viewer.is_backend or viewer.player_id == _optional_int(visibility.get("player_id"))
    if scope == "players":
        player_ids = visibility.get("player_ids")
        allowed = {_optional_int(item) for item in player_ids} if isinstance(player_ids, list) else set()
        allowed.discard(None)
        return viewer.is_admin or viewer.is_backend or viewer.player_id in allowed
    if scope == "admin":
        return viewer.is_admin or viewer.is_backend
    if scope == "backend_only":
        return viewer.is_backend
    return False


def project_stream_message_for_viewer(message: dict[str, Any], viewer: ViewerContext) -> dict[str, Any] | None:
    cloned = _copy_message(message)
    payload = _payload(cloned)
    visibility = payload.get("visibility")
    if isinstance(visibility, dict) and not can_view(visibility, viewer):
        return None

    message_type = str(cloned.get("type", "")).strip().lower()
    target_player_id = _target_player_id(payload)
    viewer_is_target = viewer.is_seat and target_player_id == viewer.player_id

    if message_type in {"prompt", "decision_ack"}:
        return _redact_projected_message(cloned, viewer, target_player_id) if viewer_is_target else None

    if message_type != "event":
        return _redact_projected_message(cloned, viewer, target_player_id)

    event_type = _event_type(payload)
    request_type = _request_type(payload)
    if event_type in {"decision_requested", "decision_resolved", "decision_timeout_fallback"} and request_type in _PRIVATE_DECISION_REQUEST_TYPES:
        return _redact_projected_message(cloned, viewer, target_player_id) if viewer_is_target else None

    if event_type == "final_character_choice" and not viewer_is_target:
        return None

    if event_type == "draft_pick" and not viewer_is_target:
        payload.pop("picked_card", None)
        payload.pop("choice_id", None)

    return _redact_projected_message(cloned, viewer, target_player_id)


def _redact_projected_message(message: dict[str, Any], viewer: ViewerContext, target_player_id: int | None) -> dict[str, Any]:
    payload = _payload(message)
    viewer_is_target = viewer.is_seat and target_player_id == viewer.player_id
    if viewer.is_admin or viewer.is_backend or viewer_is_target:
        return message
    _redact_private_payload(payload)
    view_state = payload.get("view_state")
    if isinstance(view_state, dict):
        _redact_view_state(view_state, viewer)
    return message


def _redact_view_state(view_state: dict[str, Any], viewer: ViewerContext) -> None:
    prompt = view_state.get("prompt")
    if isinstance(prompt, dict):
        active = prompt.get("active")
        prompt_player_id = _target_player_id(active) if isinstance(active, dict) else None
        if not (viewer.is_seat and prompt_player_id == viewer.player_id):
            view_state.pop("prompt", None)
    view_state.pop("hand_tray", None)
    _redact_private_payload(view_state)


def _redact_private_payload(payload: dict[str, Any]) -> None:
    for key in list(payload.keys()):
        if key in _PRIVATE_PAYLOAD_KEYS:
            payload.pop(key, None)
            continue
        value = payload.get(key)
        if isinstance(value, dict):
            _redact_private_payload(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _redact_private_payload(item)


def _copy_message(message: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(message)
    payload = cloned.get("payload")
    cloned["payload"] = _deep_copy(payload) if isinstance(payload, dict) else {}
    return cloned


def _deep_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def _payload(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload")
    if isinstance(payload, dict):
        return payload
    message["payload"] = {}
    return message["payload"]


def _event_type(payload: dict[str, Any]) -> str:
    value = payload.get("event_type")
    return value.strip().lower() if isinstance(value, str) else ""


def _request_type(payload: dict[str, Any]) -> str:
    value = payload.get("request_type")
    return value.strip().lower() if isinstance(value, str) else ""


def _target_player_id(payload: dict[str, Any]) -> int | None:
    direct_player_id = _optional_int(payload.get("player_id"))
    if direct_player_id is not None:
        return direct_player_id
    return _optional_int(payload.get("legacy_player_id"))


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except Exception:
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
