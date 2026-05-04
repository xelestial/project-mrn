from __future__ import annotations


def round_frame_id(round_index: int) -> str:
    return f"round:{int(round_index)}"


def turn_frame_id(round_index: int, player_id: int) -> str:
    return f"turn:{int(round_index)}:p{int(player_id)}"


def sequence_frame_id(kind: str, round_index: int, player_id: int | None, ordinal: int) -> str:
    owner = "none" if player_id is None else f"p{int(player_id)}"
    return f"seq:{_slug(kind)}:{int(round_index)}:{owner}:{int(ordinal)}"


def simultaneous_frame_id(kind: str, round_index: int, ordinal: int) -> str:
    return f"simul:{_slug(kind)}:{int(round_index)}:{int(ordinal)}"


def round_module_id(round_index: int, name: str) -> str:
    return f"mod:round:{int(round_index)}:{_slug(name)}"


def turn_module_id(round_index: int, player_id: int, name: str) -> str:
    return f"mod:turn:{int(round_index)}:p{int(player_id)}:{_slug(name)}"


def sequence_module_id(kind: str, round_index: int, player_id: int | None, ordinal: int, name: str) -> str:
    owner = "none" if player_id is None else f"p{int(player_id)}"
    return f"mod:seq:{_slug(kind)}:{int(round_index)}:{owner}:{int(ordinal)}:{_slug(name)}"


def simultaneous_module_id(kind: str, round_index: int, ordinal: int, name: str) -> str:
    return f"mod:simul:{_slug(kind)}:{int(round_index)}:{int(ordinal)}:{_slug(name)}"


def idempotency_key(session_id: str, *parts: object) -> str:
    normalized = ":".join(_slug(str(part)) for part in parts if str(part) != "")
    return f"session:{_slug(session_id)}:{normalized}" if normalized else f"session:{_slug(session_id)}"


def _slug(value: str) -> str:
    return "_".join(value.strip().lower().replace("/", "_").replace(":", "_").split())
