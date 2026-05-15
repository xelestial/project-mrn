from __future__ import annotations

import re
from typing import Any

from apps.server.src.domain.protocol_ids import int_or_default, player_label

_NUMERIC_STRING_RE = re.compile(r"^[+-]?\d+(?:\.0+)?$")

_PUBLIC_ID_SCALAR_KEYS = {
    "public_player_id",
    "seat_id",
    "viewer_id",
    "public_request_id",
    "public_prompt_instance_id",
    "event_id",
    "source_event_id",
}

_PUBLIC_ID_LIST_KEYS = {
    "public_player_ids",
    "seat_ids",
    "viewer_ids",
    "expected_public_player_ids",
    "missing_public_player_ids",
    "missing_seat_ids",
    "missing_viewer_ids",
}

_PUBLIC_ID_MAP_KEY_SUFFIXES = (
    "_by_public_player_id",
    "_by_seat_id",
    "_by_viewer_id",
)


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


def public_primary_player_wire_payload(
    payload: dict[str, Any],
    *,
    legacy_player_id: Any | None = None,
    omit_player_id_for_public: bool = False,
) -> dict[str, Any]:
    result = dict(payload)
    public_player_id = str(result.get("public_player_id") or "").strip()
    legacy_id = _int_or_none(legacy_player_id)
    if legacy_id is None:
        legacy_id = _int_or_none(result.get("legacy_player_id"))
    if legacy_id is None:
        legacy_id = _int_or_none(result.get("player_id"))

    if public_player_id:
        if omit_player_id_for_public:
            result.pop("player_id", None)
        else:
            result["player_id"] = public_player_id
        if legacy_id is not None:
            result["legacy_player_id"] = legacy_id
        result.pop("player_id_alias_role", None)
        result["primary_player_id"] = public_player_id
        result["primary_player_id_source"] = "public"
        return result

    if legacy_id is not None:
        result["player_id"] = legacy_id
        result.setdefault("player_id_alias_role", "legacy_compatibility_alias")
        result.setdefault("primary_player_id", legacy_id)
        result.setdefault("primary_player_id_source", "legacy")
    return result


def public_identity_numeric_leaks(payload: Any, *, path: str = "$") -> list[str]:
    leaks: list[str] = []
    _collect_public_identity_numeric_leaks(payload, path=path, leaks=leaks, key=None)
    return leaks


def assert_no_public_identity_numeric_leaks(payload: Any, *, boundary: str = "protocol_payload") -> None:
    leaks = public_identity_numeric_leaks(payload)
    if leaks:
        joined = ", ".join(leaks[:10])
        extra = "" if len(leaks) <= 10 else f", ... +{len(leaks) - 10} more"
        raise AssertionError(f"{boundary} public identity numeric leak: {joined}{extra}")


def _collect_public_identity_numeric_leaks(
    value: Any,
    *,
    path: str,
    leaks: list[str],
    key: str | None,
) -> None:
    if key is not None and _is_public_identity_scalar_key(key) and _is_numeric_like(value):
        leaks.append(path)
    if key is not None and _is_public_identity_list_key(key) and isinstance(value, list):
        for index, item in enumerate(value):
            if _is_numeric_like(item):
                leaks.append(f"{path}[{index}]")
    if key is not None and _is_public_identity_keyed_map(key) and isinstance(value, dict):
        for raw_key in value:
            if _is_numeric_like(raw_key):
                leaks.append(f"{path}.<key:{raw_key}>")

    if isinstance(value, dict):
        for raw_key, child in value.items():
            child_key = str(raw_key)
            _collect_public_identity_numeric_leaks(
                child,
                path=f"{path}.{child_key}",
                leaks=leaks,
                key=child_key,
            )
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _collect_public_identity_numeric_leaks(
                child,
                path=f"{path}[{index}]",
                leaks=leaks,
                key=None,
            )


def _is_public_identity_scalar_key(key: str) -> bool:
    return (
        key in _PUBLIC_ID_SCALAR_KEYS
        or key.endswith("_public_player_id")
        or key.endswith("_seat_id")
        or key.endswith("_viewer_id")
        or key.endswith("_public_request_id")
        or key.endswith("_public_prompt_instance_id")
        or key.endswith("_event_id")
    )


def _is_public_identity_list_key(key: str) -> bool:
    return (
        key in _PUBLIC_ID_LIST_KEYS
        or key.endswith("_public_player_ids")
        or key.endswith("_seat_ids")
        or key.endswith("_viewer_ids")
    )


def _is_public_identity_keyed_map(key: str) -> bool:
    return any(key.endswith(suffix) for suffix in _PUBLIC_ID_MAP_KEY_SUFFIXES)


def _is_numeric_like(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped and _NUMERIC_STRING_RE.fullmatch(stripped))
    return False


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
