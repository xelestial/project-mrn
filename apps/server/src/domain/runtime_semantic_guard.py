from __future__ import annotations

from typing import Any


class RuntimeSemanticViolation(ValueError):
    pass


MODULE_ALLOWED_FRAMES: dict[str, set[str]] = {
    "RoundStartModule": {"round"},
    "WeatherModule": {"round"},
    "DraftModule": {"round"},
    "TurnSchedulerModule": {"round"},
    "PlayerTurnModule": {"round"},
    "RoundEndCardFlipModule": {"round"},
    "RoundCleanupAndNextRoundModule": {"round"},
    "TurnStartModule": {"turn"},
    "ScheduledStartActionsModule": {"turn"},
    "PendingMarkResolutionModule": {"turn", "sequence"},
    "CharacterStartModule": {"turn"},
    "ImmediateMarkerTransferModule": {"turn"},
    "TargetJudicatorModule": {"turn"},
    "TrickWindowModule": {"turn"},
    "DiceRollModule": {"turn"},
    "MovementResolveModule": {"turn"},
    "MapMoveModule": {"turn", "sequence"},
    "ArrivalTileModule": {"turn", "sequence"},
    "LapRewardModule": {"turn"},
    "FortuneResolveModule": {"turn", "sequence"},
    "TurnEndSnapshotModule": {"turn", "sequence"},
    "TrickChoiceModule": {"sequence"},
    "TrickSkipModule": {"sequence"},
    "TrickResolveModule": {"sequence"},
    "TrickDiscardModule": {"sequence"},
    "TrickDeferredFollowupsModule": {"sequence"},
    "TrickVisibilitySyncModule": {"sequence"},
    "PurchaseDecisionModule": {"sequence"},
    "PurchaseCommitModule": {"sequence"},
    "UnownedPostPurchaseModule": {"sequence"},
    "ScoreTokenPlacementPromptModule": {"sequence"},
    "ScoreTokenPlacementCommitModule": {"sequence"},
    "LandingPostEffectsModule": {"sequence"},
    "TrickTileRentModifierModule": {"sequence"},
    "LegacyActionAdapterModule": {"sequence"},
    "ResupplyModule": {"simultaneous"},
    "SimultaneousProcessingModule": {"simultaneous"},
    "SimultaneousPromptBatchModule": {"simultaneous"},
    "SimultaneousCommitModule": {"simultaneous"},
    "CompleteSimultaneousResolutionModule": {"simultaneous"},
}

ROUND_ONLY_EVENTS = {
    "round_start",
    "weather_reveal",
    "draft_pick",
    "final_character_choice",
    "round_order",
    "marker_flip",
    "active_flip",
}

EVENT_REQUIRED_MODULES = {
    "draft_pick": {"DraftModule"},
    "final_character_choice": {"DraftModule"},
    "trick_used": {"TrickResolveModule"},
    "marker_flip": {"RoundEndCardFlipModule"},
    "active_flip": {"RoundEndCardFlipModule"},
}


def validate_stream_payload(*, history: list[dict], msg_type: str, payload: dict[str, Any]) -> None:
    runtime_module = _record(payload.get("runtime_module"))
    if runtime_module:
        _validate_runtime_module(runtime_module)
    event_type = str(payload.get("event_type") or "").strip()
    if msg_type == "prompt":
        _validate_prompt_payload(payload)
    if msg_type == "event" and event_type:
        _validate_event_payload(event_type, runtime_module)
        _validate_event_against_active_turn(history, event_type, runtime_module)
    checkpoint = _record(payload.get("engine_checkpoint"))
    if checkpoint:
        validate_checkpoint_payload(checkpoint)


def validate_checkpoint_payload(payload: dict[str, Any]) -> None:
    frames = payload.get("runtime_frame_stack")
    runtime_state = _record(payload.get("runtime_state")) or {}
    if not isinstance(frames, list):
        frames = runtime_state.get("frame_stack")
    if not isinstance(frames, list):
        return
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        frame_type = str(frame.get("frame_type") or "").strip()
        for module in frame.get("module_queue") or []:
            if isinstance(module, dict):
                _validate_runtime_module({**module, "frame_type": frame_type, "frame_id": frame.get("frame_id")})
        _validate_card_flip_not_before_turns_complete(frame)


def _validate_runtime_module(module: dict[str, Any]) -> None:
    module_type = str(module.get("module_type") or "").strip()
    frame_type = str(module.get("frame_type") or "").strip()
    if not module_type or not frame_type:
        return
    allowed = MODULE_ALLOWED_FRAMES.get(module_type)
    if allowed and frame_type not in allowed:
        raise RuntimeSemanticViolation(f"{module_type} is not allowed in {frame_type} frame")


def _validate_event_payload(event_type: str, runtime_module: dict[str, Any] | None) -> None:
    expected_modules = EVENT_REQUIRED_MODULES.get(event_type)
    if expected_modules and runtime_module:
        module_type = str(runtime_module.get("module_type") or "")
        if module_type not in expected_modules:
            raise RuntimeSemanticViolation(f"{event_type} requires one of {sorted(expected_modules)}, got {module_type}")
    if event_type in ROUND_ONLY_EVENTS and runtime_module:
        frame_type = str(runtime_module.get("frame_type") or "")
        if frame_type and frame_type != "round":
            raise RuntimeSemanticViolation(f"{event_type} is round-only and cannot be emitted from {frame_type}")


def _validate_event_against_active_turn(
    history: list[dict],
    event_type: str,
    runtime_module: dict[str, Any] | None,
) -> None:
    if event_type not in {"marker_flip", "active_flip"}:
        return
    if _latest_active_turn_start(history) is None:
        return
    if (
        runtime_module
        and str(runtime_module.get("module_type") or "") == "RoundEndCardFlipModule"
        and str(runtime_module.get("frame_type") or "") == "round"
    ):
        return
    raise RuntimeSemanticViolation(f"{event_type} cannot be projected as active turn progress")


def _validate_prompt_payload(payload: dict[str, Any]) -> None:
    if str(payload.get("runner_kind") or payload.get("runtime_runner_kind") or "") != "module" and not payload.get("resume_token"):
        return
    for field in ("resume_token", "frame_id", "module_id", "module_type", "module_cursor"):
        if not str(payload.get(field) or "").strip():
            raise RuntimeSemanticViolation(f"module prompt missing {field}")
    module_type = str(payload.get("module_type") or "")
    frame_id = str(payload.get("frame_id") or "")
    frame_type = _frame_type_from_frame_id(frame_id)
    if frame_type:
        _validate_runtime_module({"module_type": module_type, "frame_type": frame_type, "frame_id": frame_id})
    if module_type in {"ResupplyModule", "SimultaneousPromptBatchModule"} and not str(payload.get("batch_id") or "").strip():
        raise RuntimeSemanticViolation("simultaneous prompt missing batch_id")


def _validate_card_flip_not_before_turns_complete(frame: dict[str, Any]) -> None:
    if str(frame.get("frame_type") or "") != "round":
        return
    modules = [module for module in frame.get("module_queue") or [] if isinstance(module, dict)]
    active_module_id = str(frame.get("active_module_id") or "")
    active = next((module for module in modules if str(module.get("module_id") or "") == active_module_id), None)
    if not active or str(active.get("module_type") or "") != "RoundEndCardFlipModule":
        return
    pending_turns = [
        module
        for module in modules
        if str(module.get("module_type") or "") == "PlayerTurnModule"
        and str(module.get("status") or "queued") not in {"completed", "skipped"}
    ]
    if pending_turns:
        raise RuntimeSemanticViolation("card flip cannot run before all player turns complete")


def _latest_active_turn_start(history: list[dict]) -> dict[str, Any] | None:
    for message in reversed(history):
        payload = _record(message.get("payload")) or {}
        event_type = str(payload.get("event_type") or "")
        if event_type in {"turn_end_snapshot", "game_end", "round_start"}:
            return None
        if event_type == "turn_start":
            return payload
    return None


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


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None
