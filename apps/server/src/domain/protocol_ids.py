from __future__ import annotations

from urllib.parse import quote
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5


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


def public_prompt_request_id(request_id: Any) -> str:
    return _stable_protocol_id("req", f"prompt-request:{str(request_id or '').strip()}")


def public_prompt_instance_id(request_id: Any, prompt_instance_id: Any) -> str:
    return _stable_protocol_id(
        "pin",
        f"prompt-instance:{str(request_id or '').strip()}:{str(prompt_instance_id or '').strip()}",
    )


def prompt_protocol_identity_fields(*, request_id: Any, prompt_instance_id: Any) -> dict[str, str]:
    legacy_request_id = str(request_id or "").strip()
    if not legacy_request_id:
        return {}
    return {
        "legacy_request_id": legacy_request_id,
        "public_request_id": public_prompt_request_id(legacy_request_id),
        "public_prompt_instance_id": public_prompt_instance_id(legacy_request_id, prompt_instance_id),
    }


def int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def player_label(seat_index: Any) -> str:
    return f"P{int_or_default(seat_index, 0)}"


def turn_label(round_index: Any, turn_index: Any) -> str:
    return f"R{int_or_default(round_index, 0)}-T{int_or_default(turn_index, 0)}"


def stable_prompt_request_id(
    *,
    session_id: str,
    envelope: dict[str, Any],
    public_context: dict[str, Any],
) -> str:
    request_type = str(envelope.get("request_type") or "prompt")
    player_id = int_or_default(envelope.get("player_id"), 0)
    prompt_instance_id = int_or_default(envelope.get("prompt_instance_id"), 0)
    if _has_prompt_boundary_identity(envelope):
        return _boundary_prompt_request_id(
            session_id=session_id,
            envelope=envelope,
            request_type=request_type,
            player_id=player_id,
            prompt_instance_id=prompt_instance_id,
        )
    return legacy_prompt_request_id(
        session_id=session_id,
        public_context=public_context,
        request_type=request_type,
        player_id=player_id,
        prompt_instance_id=prompt_instance_id,
    )


def legacy_prompt_request_id(
    *,
    session_id: str,
    public_context: dict[str, Any],
    request_type: str,
    player_id: int,
    prompt_instance_id: int,
) -> str:
    round_index = int_or_default(public_context.get("round_index"), 0)
    turn_index = int_or_default(public_context.get("turn_index"), 0)
    return f"{session_id}:r{round_index}:t{turn_index}:p{player_id}:{request_type}:{prompt_instance_id}"


def _boundary_prompt_request_id(
    *,
    session_id: str,
    envelope: dict[str, Any],
    request_type: str,
    player_id: int,
    prompt_instance_id: int,
) -> str:
    parts = [str(session_id), "prompt"]
    batch_id = _prompt_boundary_value(envelope, "batch_id")
    if batch_id:
        parts.extend(["batch", _prompt_id_token(batch_id)])
    parts.extend(
        [
            "frame",
            _prompt_id_token(_prompt_boundary_value(envelope, "frame_id") or "-"),
            "module",
            _prompt_id_token(_prompt_boundary_value(envelope, "module_id") or "-"),
            "cursor",
            _prompt_id_token(_prompt_boundary_value(envelope, "module_cursor") or "-"),
            f"p{player_id}",
            request_type,
            str(prompt_instance_id),
        ]
    )
    return ":".join(parts)


def _has_prompt_boundary_identity(envelope: dict[str, Any]) -> bool:
    return any(_prompt_boundary_value(envelope, key) for key in ("batch_id", "frame_id", "module_id", "module_cursor"))


def _prompt_boundary_value(envelope: dict[str, Any], key: str) -> str:
    value = envelope.get(key)
    if str(value or "").strip():
        return str(value).strip()
    runtime_module = envelope.get("runtime_module")
    if isinstance(runtime_module, dict):
        value = runtime_module.get(key)
        if str(value or "").strip():
            return str(value).strip()
    return ""


def _prompt_id_token(value: Any) -> str:
    return quote(str(value), safe="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")


def _stable_protocol_id(prefix: str, source: str) -> str:
    normalized = str(prefix or "").strip().lower().rstrip("_")
    if not normalized:
        raise ValueError("missing_protocol_id_prefix")
    stable_source = str(source or "").strip()
    if not stable_source:
        raise ValueError("missing_protocol_id_source")
    return f"{normalized}_{uuid5(NAMESPACE_URL, stable_source)}"
