"""TurnFrame module builders for the staged module-runtime migration."""

from __future__ import annotations

from .contracts import FrameState, ModuleRef
from .ids import idempotency_key, turn_frame_id, turn_module_id

TURN_MODULE_TYPES = (
    "TurnStartModule",
    "ScheduledStartActionsModule",
    "PendingMarkResolutionModule",
    "CharacterStartModule",
    "ImmediateMarkerTransferModule",
    "TargetJudicatorModule",
    "TrickWindowModule",
    "DiceRollModule",
    "MovementResolveModule",
    "MapMoveModule",
    "ArrivalTileModule",
    "LapRewardModule",
    "FortuneResolveModule",
    "TurnEndSnapshotModule",
)


def build_turn_module(
    round_index: int,
    player_id: int,
    module_type: str,
    *,
    session_id: str = "",
    payload: dict | None = None,
) -> ModuleRef:
    if module_type not in TURN_MODULE_TYPES:
        raise ValueError(f"unknown turn module type: {module_type}")
    name = module_type.removesuffix("Module")
    return ModuleRef(
        module_id=turn_module_id(round_index, player_id, name),
        module_type=module_type,
        phase=name.lower(),
        owner_player_id=player_id,
        payload=dict(payload or {}),
        idempotency_key=idempotency_key(session_id, "turn", round_index, f"p{int(player_id)}", name),
    )


def build_turn_frame(
    round_index: int,
    player_id: int,
    *,
    parent_module_id: str,
    session_id: str = "",
) -> FrameState:
    return FrameState(
        frame_id=turn_frame_id(round_index, player_id),
        frame_type="turn",
        owner_player_id=player_id,
        parent_frame_id=parent_module_id,
        created_by_module_id=parent_module_id,
        module_queue=[
            build_turn_module(round_index, player_id, module_type, session_id=session_id)
            for module_type in TURN_MODULE_TYPES
            if module_type != "ImmediateMarkerTransferModule"
        ],
    )
