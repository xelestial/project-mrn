from __future__ import annotations

from typing import Any

from .types import RuntimeProjectionViewState


ROUND_STAGE_BY_MODULE = {
    "RoundStartModule": "round_setup",
    "WeatherModule": "round_setup",
    "DraftModule": "draft",
    "TurnSchedulerModule": "turn_scheduler",
    "RoundEndCardFlipModule": "round_end_card_flip",
}

TURN_STAGE_BY_MODULE = {
    "TurnStartModule": "turn_start",
    "PendingMarkResolutionModule": "mark_resolution",
    "CharacterStartModule": "character_start",
    "ImmediateMarkerTransferModule": "marker_transfer",
    "TrickWindowModule": "trick_window",
    "TrickResolveModule": "trick",
    "TrickDiscardModule": "trick",
    "TrickVisibilitySyncModule": "trick",
    "DiceRollModule": "dice",
    "MapMoveModule": "movement",
    "ArrivalTileModule": "arrival",
    "FortuneResolveModule": "fortune",
    "LapRewardModule": "lap_reward",
    "TurnEndSnapshotModule": "turn_end",
}


def build_runtime_view_state(messages: list[dict]) -> RuntimeProjectionViewState:
    module = _latest_runtime_module(messages)
    prompt_request_id = _latest_active_prompt_request_id(messages)
    if not module and not prompt_request_id:
        return {}

    module_type = str(module.get("module_type") or "") if module else ""
    module_path = _string_list(module.get("module_path")) if module else []
    active_sequence = _active_sequence(module, module_path)
    round_stage = ROUND_STAGE_BY_MODULE.get(module_type, "in_round" if module else "")
    turn_stage = TURN_STAGE_BY_MODULE.get(module_type, "" if round_stage in {"round_setup", "draft", "turn_scheduler"} else "legacy")

    return {
        "runner_kind": str(module.get("runner_kind") or "legacy") if module else "legacy",
        "latest_module_path": module_path,
        "round_stage": round_stage,
        "turn_stage": turn_stage,
        "active_sequence": active_sequence,
        "active_prompt_request_id": prompt_request_id,
        "active_frame_id": str(module.get("frame_id") or "") if module else "",
        "active_frame_type": str(module.get("frame_type") or "") if module else "",
        "active_module_id": str(module.get("module_id") or "") if module else "",
        "active_module_type": module_type,
        "active_module_status": str(module.get("module_status") or "") if module else "",
        "active_module_cursor": str(module.get("module_cursor") or "") if module else "",
        "active_module_idempotency_key": str(module.get("idempotency_key") or "") if module else "",
        "draft_active": module_type == "DraftModule" or _is_draft_prompt(messages, prompt_request_id),
        "trick_sequence_active": active_sequence == "trick" or module_type.startswith("Trick"),
        "card_flip_legal": module_type == "RoundEndCardFlipModule",
    }


def _latest_runtime_module(messages: list[dict]) -> dict[str, Any] | None:
    for message in reversed(messages):
        payload = message.get("payload")
        if not isinstance(payload, dict):
            continue
        checkpoint_module = _runtime_module_from_checkpoint(payload.get("engine_checkpoint"))
        if checkpoint_module is not None:
            return checkpoint_module
        runtime_module = payload.get("runtime_module")
        if isinstance(runtime_module, dict):
            return runtime_module
        payload_module = _runtime_module_from_payload_fields(payload)
        if payload_module is not None:
            return payload_module
    return None


def _runtime_module_from_payload_fields(payload: dict[str, Any]) -> dict[str, Any] | None:
    module_type = str(payload.get("module_type") or "")
    module_id = str(payload.get("module_id") or "")
    frame_id = str(payload.get("frame_id") or "")
    if not module_type and not module_id and not frame_id:
        return None
    frame_type = str(payload.get("frame_type") or "") or _frame_type_from_frame_id(frame_id)
    module_path = _string_list(payload.get("module_path"))
    if not module_path:
        module_path = [item for item in [frame_id, module_id] if item]
    return {
        "runner_kind": str(payload.get("runner_kind") or payload.get("runtime_runner_kind") or "module"),
        "frame_id": frame_id,
        "frame_type": frame_type,
        "module_id": module_id,
        "module_type": module_type,
        "module_status": str(payload.get("module_status") or ""),
        "module_cursor": str(payload.get("module_cursor") or ""),
        "module_path": module_path,
        "idempotency_key": str(payload.get("idempotency_key") or ""),
    }


def _frame_type_from_frame_id(frame_id: str) -> str:
    if frame_id.startswith("round:"):
        return "round"
    if frame_id.startswith("turn:"):
        return "turn"
    if frame_id.startswith("seq:"):
        return "sequence"
    if frame_id.startswith("simul:"):
        return "simultaneous"
    return ""


def _runtime_module_from_checkpoint(checkpoint: Any) -> dict[str, Any] | None:
    if not isinstance(checkpoint, dict):
        return None
    runtime_state = checkpoint.get("runtime_state")
    runtime_state = runtime_state if isinstance(runtime_state, dict) else {}
    frame_stack = checkpoint.get("runtime_frame_stack") or runtime_state.get("frame_stack")
    if not isinstance(frame_stack, list):
        return None
    for frame_index in range(len(frame_stack) - 1, -1, -1):
        frame = frame_stack[frame_index]
        if not isinstance(frame, dict) or frame.get("status") == "completed":
            continue
        module = _active_module_from_frame(frame)
        if module is None:
            continue
        frame_id = str(frame.get("frame_id") or "")
        frame_type = str(frame.get("frame_type") or "")
        module_id = str(module.get("module_id") or "")
        module_path = _string_list(module.get("module_path"))
        if not module_path:
            frame_path = [
                str(candidate.get("frame_id") or "")
                for candidate in frame_stack[: frame_index + 1]
                if isinstance(candidate, dict) and str(candidate.get("frame_id") or "")
            ]
            module_path = [*frame_path, module_id] if module_id else frame_path
        return {
            "runner_kind": str(
                checkpoint.get("runtime_runner_kind")
                or runtime_state.get("runner_kind")
                or "module"
            ),
            "frame_id": frame_id,
            "frame_type": frame_type,
            "module_id": module_id,
            "module_type": str(module.get("module_type") or ""),
            "module_status": str(module.get("status") or "queued"),
            "module_cursor": str(module.get("cursor") or module.get("module_cursor") or ""),
            "module_path": module_path,
            "idempotency_key": str(module.get("idempotency_key") or ""),
            "round_index": checkpoint.get("rounds_completed") or runtime_state.get("round_index") or 0,
            "turn_index": checkpoint.get("turn_index") or runtime_state.get("turn_index") or 0,
        }
    return None


def _active_module_from_frame(frame: dict[str, Any]) -> dict[str, Any] | None:
    queue = frame.get("module_queue")
    if not isinstance(queue, list):
        return None
    active_module_id = str(frame.get("active_module_id") or "")
    if active_module_id:
        for module in queue:
            if isinstance(module, dict) and module.get("module_id") == active_module_id:
                return module
    for module in queue:
        if not isinstance(module, dict):
            continue
        if module.get("status") in {None, "queued", "running", "suspended"}:
            return module
    return None


def _latest_active_prompt_request_id(messages: list[dict]) -> str:
    active_request_id = ""
    active_request_type = ""
    active_player_id: int | None = None
    for message in messages:
        payload = message.get("payload")
        if not isinstance(payload, dict):
            continue
        request_id = str(payload.get("request_id") or "").strip()
        event_type = str(payload.get("event_type") or "").strip()
        if message.get("type") == "prompt" and request_id:
            active_request_id = request_id
            active_request_type = str(payload.get("request_type") or "")
            active_player_id = _payload_player(payload)
            continue
        if message.get("type") == "decision_ack" and request_id == active_request_id:
            status = str(payload.get("status") or "")
            if status in {"accepted", "stale"}:
                active_request_id = ""
            continue
        if message.get("type") != "event":
            continue
        if request_id == active_request_id and event_type in {"decision_resolved", "decision_timeout_fallback", "timeout_fallback"}:
            active_request_id = ""
            continue
        if active_request_id and _event_closes_prompt(active_request_type, active_player_id, payload):
            active_request_id = ""
    return active_request_id


def _event_closes_prompt(request_type: str, player_id: int | None, payload: dict[str, Any]) -> bool:
    event_type = str(payload.get("event_type") or "")
    payload_player_id = _payload_player(payload)
    if request_type in {"draft_card", "character_pick"}:
        return (
            (event_type == "draft_pick" and payload_player_id == player_id)
            or event_type == "final_character_choice"
            or event_type == "turn_start"
        )
    if request_type in {"final_character", "final_character_choice"}:
        return (event_type == "final_character_choice" and payload_player_id == player_id) or event_type == "turn_start"
    if request_type in {"trick_to_use", "hidden_trick_card", "hand_choice"}:
        return (
            (event_type == "trick_used" and payload_player_id == player_id)
            or (event_type == "trick_window_closed" and payload_player_id == player_id)
            or event_type in {"dice_roll", "player_move", "turn_end_snapshot"}
        )
    if request_type == "active_flip":
        return event_type in {"active_flip", "round_start", "turn_start"}
    return False


def _payload_player(payload: dict[str, Any]) -> int | None:
    for key in ("acting_player_id", "player_id", "actor_player_id", "player"):
        value = payload.get(key)
        if isinstance(value, int):
            return value
    return None


def _is_draft_prompt(messages: list[dict], request_id: str) -> bool:
    if not request_id:
        return False
    for message in reversed(messages):
        payload = message.get("payload")
        if not isinstance(payload, dict) or payload.get("request_id") != request_id:
            continue
        request_type = str(payload.get("request_type") or "")
        context = payload.get("public_context")
        draft_phase = context.get("draft_phase") if isinstance(context, dict) else None
        return request_type in {"draft_card", "character_pick", "final_character", "final_character_choice"} or draft_phase is not None
    return False


def _active_sequence(module: dict[str, Any] | None, module_path: list[str]) -> str:
    if not module:
        return ""
    frame_type = str(module.get("frame_type") or "")
    if frame_type == "sequence":
        frame_id = str(module.get("frame_id") or "")
        if frame_id.startswith("seq:trick"):
            return "trick"
        if frame_id.startswith("seq:fortune"):
            return "fortune"
    for item in module_path:
        if item.startswith("seq:trick"):
            return "trick"
        if item.startswith("seq:fortune"):
            return "fortune"
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]
