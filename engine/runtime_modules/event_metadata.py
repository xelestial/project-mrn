from __future__ import annotations

import hashlib
import json
from typing import Any


ROUND_EVENT_MODULES = {
    "round_start": ("round", "RoundStartModule", "round_start"),
    "weather_reveal": ("round", "WeatherModule", "weather"),
    "draft_pick": ("round", "DraftModule", "draft"),
    "final_character_choice": ("round", "DraftModule", "draft"),
    "round_order": ("round", "TurnSchedulerModule", "turn_scheduler"),
    "marker_flip": ("round", "RoundEndCardFlipModule", "card_flip"),
    "active_flip": ("round", "RoundEndCardFlipModule", "card_flip"),
}

TURN_EVENT_MODULES = {
    "turn_start": ("TurnStartModule", "turn_start"),
    "mark_resolved": ("PendingMarkResolutionModule", "mark_resolution"),
    "mark_target_missing": ("PendingMarkResolutionModule", "mark_resolution"),
    "mark_queued": ("CharacterStartModule", "character_start"),
    "marker_transferred": ("ImmediateMarkerTransferModule", "marker_transfer"),
    "trick_window_open": ("TrickWindowModule", "trick_window"),
    "trick_window_closed": ("TrickWindowModule", "trick_window"),
    "dice_roll": ("DiceRollModule", "dice"),
    "player_move": ("MapMoveModule", "move"),
    "action_move": ("MapMoveModule", "move"),
    "landing_resolved": ("ArrivalTileModule", "arrival"),
    "lap_reward_chosen": ("LapRewardModule", "lap_reward"),
    "turn_end_snapshot": ("TurnEndSnapshotModule", "turn_end"),
}

SEQUENCE_EVENT_MODULES = {
    "trick_used": ("trick", "TrickResolveModule", "trick_resolve"),
    "trick_discarded": ("trick", "TrickDiscardModule", "trick_discard"),
    "trick_visibility_sync": ("trick", "TrickVisibilitySyncModule", "trick_visibility"),
    "fortune_drawn": ("fortune", "FortuneResolveModule", "fortune"),
    "fortune_resolved": ("fortune", "FortuneResolveModule", "fortune"),
}


def runtime_module_for_event(
    state: Any,
    event_type: str,
    phase: str,
    player_id: int | None,
    payload: dict[str, Any] | None = None,
    *,
    session_id: str = "",
) -> dict[str, Any]:
    payload = payload or {}
    round_index = int(getattr(state, "rounds_completed", 0)) + 1
    turn_index = int(getattr(state, "turn_index", 0)) + 1
    actor = player_id if player_id is not None else _payload_player(payload)
    if event_type in ROUND_EVENT_MODULES:
        frame_type, module_type, slug = ROUND_EVENT_MODULES[event_type]
        frame_id = f"round:{round_index}"
        module_id = f"mod:round:{round_index}:{slug}"
        module_path = [frame_id, module_id]
    elif event_type in SEQUENCE_EVENT_MODULES:
        sequence_kind, module_type, slug = SEQUENCE_EVENT_MODULES[event_type]
        owner = 0 if actor is None else actor
        round_frame = f"round:{round_index}"
        turn_frame = f"turn:{round_index}:p{owner}"
        frame_id = f"seq:{sequence_kind}:{round_index}:p{owner}"
        module_id = f"mod:seq:{sequence_kind}:{round_index}:p{owner}:{slug}"
        frame_type = "sequence"
        module_path = [round_frame, turn_frame, frame_id, module_id]
    else:
        module_type, slug = TURN_EVENT_MODULES.get(event_type, ("EventProjectionModule", _slug(event_type or phase)))
        owner = 0 if actor is None else actor
        round_frame = f"round:{round_index}"
        frame_id = f"turn:{round_index}:p{owner}"
        module_id = f"mod:turn:{round_index}:p{owner}:{slug}"
        frame_type = "turn"
        module_path = [round_frame, frame_id, module_id]
    key = _idempotency_key(
        session_id=session_id,
        round_index=round_index,
        turn_index=turn_index,
        event_type=event_type,
        module_id=module_id,
        payload=payload,
    )
    return {
        "schema_version": 1,
        "runner_kind": "module",
        "frame_id": frame_id,
        "frame_type": frame_type,
        "module_id": module_id,
        "module_type": module_type,
        "module_status": "completed",
        "module_path": module_path,
        "idempotency_key": key,
        "round_index": round_index,
        "turn_index": turn_index,
        "public_phase": phase,
    }


def _payload_player(payload: dict[str, Any]) -> int | None:
    for key in ("acting_player_id", "player_id", "actor_player_id"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def _idempotency_key(
    *,
    session_id: str,
    round_index: int,
    turn_index: int,
    event_type: str,
    module_id: str,
    payload: dict[str, Any],
) -> str:
    explicit = str(payload.get("idempotency_key") or "").strip()
    if explicit:
        return explicit
    request_id = str(payload.get("request_id") or "").strip()
    if request_id:
        return f"module:{session_id}:request:{request_id}:{event_type}"
    step = str(payload.get("step_index") or payload.get("event_order") or "").strip()
    suffix = step or hashlib.sha1(_stable_payload(payload).encode("utf-8")).hexdigest()[:12]
    return f"module:{session_id}:round:{round_index}:turn:{turn_index}:{module_id}:{event_type}:{suffix}"


def _stable_payload(payload: dict[str, Any]) -> str:
    ignored = {"engine_checkpoint", "view_state"}
    normalized = {str(key): value for key, value in payload.items() if key not in ignored}
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, default=str)


def _slug(value: str) -> str:
    text = value.strip().lower()
    return "_".join(text.replace("/", "_").replace(":", "_").split()) or "event"
