"""RoundFrame module builders and validation helpers."""

from __future__ import annotations

from .contracts import FrameState, ModuleRef
from .ids import idempotency_key, round_frame_id, round_module_id


ROUND_MODULE_TYPES = (
    "RoundStartModule",
    "WeatherModule",
    "DraftModule",
    "TurnSchedulerModule",
    "PlayerTurnModule",
    "RoundEndCardFlipModule",
    "RoundCleanupAndNextRoundModule",
)


def build_round_module(
    round_index: int,
    module_type: str,
    *,
    session_id: str = "",
    owner_player_id: int | None = None,
    payload: dict | None = None,
) -> ModuleRef:
    if module_type not in ROUND_MODULE_TYPES:
        raise ValueError(f"unknown round module type: {module_type}")
    name = module_type.removesuffix("Module")
    return ModuleRef(
        module_id=round_module_id(round_index, name),
        module_type=module_type,
        phase=name.lower(),
        owner_player_id=owner_player_id,
        payload=dict(payload or {}),
        idempotency_key=idempotency_key(session_id, "round", round_index, name, owner_player_id or ""),
    )


def build_player_turn_module(
    round_index: int,
    player_id: int,
    turn_ordinal: int,
    *,
    session_id: str = "",
) -> ModuleRef:
    module = build_round_module(
        round_index,
        "PlayerTurnModule",
        session_id=session_id,
        owner_player_id=player_id,
        payload={"turn_ordinal": int(turn_ordinal)},
    )
    module.module_id = round_module_id(round_index, f"player_turn_p{int(player_id)}_{int(turn_ordinal)}")
    module.phase = "player_turn"
    module.idempotency_key = idempotency_key(
        session_id,
        "round",
        round_index,
        "player_turn",
        f"p{int(player_id)}",
        turn_ordinal,
    )
    return module


def build_round_frame(
    round_index: int,
    *,
    session_id: str = "",
    player_order: list[int] | None = None,
    completed_setup: bool = False,
) -> FrameState:
    setup = [
        build_round_module(round_index, "RoundStartModule", session_id=session_id),
        build_round_module(round_index, "WeatherModule", session_id=session_id),
        build_round_module(round_index, "DraftModule", session_id=session_id),
        build_round_module(round_index, "TurnSchedulerModule", session_id=session_id),
    ]
    turn_modules = [
        build_player_turn_module(round_index, player_id, ordinal, session_id=session_id)
        for ordinal, player_id in enumerate(player_order or [])
    ]
    tail = [
        build_round_module(round_index, "RoundEndCardFlipModule", session_id=session_id),
        build_round_module(round_index, "RoundCleanupAndNextRoundModule", session_id=session_id),
    ]
    frame = FrameState(
        frame_id=round_frame_id(round_index),
        frame_type="round",
        owner_player_id=None,
        parent_frame_id=None,
        module_queue=[*setup, *turn_modules, *tail],
    )
    if completed_setup:
        for module in setup:
            module.status = "completed"
            frame.completed_module_ids.append(module.module_id)
        frame.module_queue = [*turn_modules, *tail]
    return frame


def assert_round_end_card_flip_ready(frame: FrameState) -> None:
    pending_turns = [
        module.module_id
        for module in frame.module_queue
        if module.module_type == "PlayerTurnModule" and module.status not in {"completed", "skipped"}
    ]
    if pending_turns:
        raise RuntimeError("RoundEndCardFlipModule requires all PlayerTurnModule entries to be completed")
