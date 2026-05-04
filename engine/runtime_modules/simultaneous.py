"""SimultaneousResolutionFrame builders and resupply batch helpers."""

from __future__ import annotations

from .contracts import FrameState, ModuleRef, SimultaneousPromptBatchContinuation
from .ids import idempotency_key, simultaneous_frame_id, simultaneous_module_id


SIMULTANEOUS_MODULE_TYPES = (
    "SimultaneousProcessingModule",
    "SimultaneousPromptBatchModule",
    "ResupplyModule",
    "SimultaneousCommitModule",
    "CompleteSimultaneousResolutionModule",
)


def build_simultaneous_module(
    kind: str,
    round_index: int,
    ordinal: int,
    module_type: str,
    *,
    session_id: str = "",
    payload: dict | None = None,
) -> ModuleRef:
    if module_type not in SIMULTANEOUS_MODULE_TYPES:
        raise ValueError(f"unknown simultaneous module type: {module_type}")
    name = module_type.removesuffix("Module")
    return ModuleRef(
        module_id=simultaneous_module_id(kind, round_index, ordinal, name),
        module_type=module_type,
        phase=name.lower(),
        owner_player_id=None,
        payload=dict(payload or {}),
        idempotency_key=idempotency_key(session_id, "simul", kind, round_index, ordinal, name),
    )


def build_resupply_frame(
    round_index: int,
    ordinal: int,
    *,
    parent_frame_id: str,
    parent_module_id: str,
    session_id: str = "",
    participants: list[int] | None = None,
) -> FrameState:
    return FrameState(
        frame_id=simultaneous_frame_id("resupply", round_index, ordinal),
        frame_type="simultaneous",
        owner_player_id=None,
        parent_frame_id=parent_frame_id,
        created_by_module_id=parent_module_id,
        module_queue=[
            build_simultaneous_module(
                "resupply",
                round_index,
                ordinal,
                "SimultaneousProcessingModule",
                session_id=session_id,
                payload={"participants": list(participants or [])},
            ),
            build_simultaneous_module(
                "resupply",
                round_index,
                ordinal,
                "SimultaneousPromptBatchModule",
                session_id=session_id,
                payload={"participants": list(participants or [])},
            ),
            build_simultaneous_module(
                "resupply",
                round_index,
                ordinal,
                "ResupplyModule",
                session_id=session_id,
                payload={"participants": list(participants or [])},
            ),
            build_simultaneous_module("resupply", round_index, ordinal, "SimultaneousCommitModule", session_id=session_id),
            build_simultaneous_module(
                "resupply",
                round_index,
                ordinal,
                "CompleteSimultaneousResolutionModule",
                session_id=session_id,
            ),
        ],
    )


def batch_is_ready_to_commit(batch: SimultaneousPromptBatchContinuation | None) -> bool:
    return batch is not None and not batch.missing_player_ids
