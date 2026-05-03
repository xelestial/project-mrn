"""SequenceFrame module builders for nested follow-up work."""

from __future__ import annotations

from .contracts import FrameState, ModuleRef
from .ids import idempotency_key, sequence_frame_id, sequence_module_id

TRICK_SEQUENCE_MODULE_TYPES = (
    "TrickChoiceModule",
    "TrickSkipModule",
    "TrickResolveModule",
    "TrickDiscardModule",
    "TrickDeferredFollowupsModule",
    "TrickVisibilitySyncModule",
)

ACTION_SEQUENCE_MODULE_TYPES = (
    "PendingMarkResolutionModule",
    "MapMoveModule",
    "ArrivalTileModule",
    "RentPaymentModule",
    "PurchaseDecisionModule",
    "PurchaseCommitModule",
    "UnownedPostPurchaseModule",
    "ScoreTokenPlacementPromptModule",
    "ScoreTokenPlacementCommitModule",
    "LandingPostEffectsModule",
    "TrickTileRentModifierModule",
    "FortuneResolveModule",
    "LegacyActionAdapterModule",
)

TURN_COMPLETION_MODULE_TYPES = ("TurnEndSnapshotModule",)

SEQUENCE_MODULE_TYPES = TRICK_SEQUENCE_MODULE_TYPES + ACTION_SEQUENCE_MODULE_TYPES + TURN_COMPLETION_MODULE_TYPES

ACTION_TYPE_TO_MODULE_TYPE = {
    "resolve_mark": "PendingMarkResolutionModule",
    "apply_move": "MapMoveModule",
    "resolve_arrival": "ArrivalTileModule",
    "resolve_rent_payment": "RentPaymentModule",
    "request_purchase_tile": "PurchaseDecisionModule",
    "resolve_purchase_tile": "PurchaseCommitModule",
    "resolve_unowned_post_purchase": "UnownedPostPurchaseModule",
    "request_score_token_placement": "ScoreTokenPlacementPromptModule",
    "resolve_score_token_placement": "ScoreTokenPlacementCommitModule",
    "resolve_landing_post_effects": "LandingPostEffectsModule",
    "continue_after_trick_phase": "TrickDeferredFollowupsModule",
    "resolve_trick_tile_rent_modifier": "TrickTileRentModifierModule",
}

FORTUNE_ACTION_TYPE_TO_MODULE_TYPE = {
    "resolve_fortune_takeover_backward": "FortuneResolveModule",
    "resolve_fortune_subscription": "FortuneResolveModule",
    "resolve_fortune_land_thief": "FortuneResolveModule",
    "resolve_fortune_donation_angel": "FortuneResolveModule",
    "resolve_fortune_forced_trade": "FortuneResolveModule",
    "resolve_fortune_pious_marker": "FortuneResolveModule",
}

SIMULTANEOUS_ACTION_TYPES = frozenset({"resolve_supply_threshold"})


def module_type_for_action(action_type: str) -> str:
    return (
        ACTION_TYPE_TO_MODULE_TYPE.get(action_type)
        or FORTUNE_ACTION_TYPE_TO_MODULE_TYPE.get(action_type)
        or "LegacyActionAdapterModule"
    )


def _validate_action_sequence_action(action: dict) -> None:
    action_type = str(action.get("type", ""))
    if action_type in SIMULTANEOUS_ACTION_TYPES:
        raise ValueError(
            f"{action_type} must be scheduled as a SimultaneousResolutionFrame before action sequence construction"
        )


def build_sequence_module(
    kind: str,
    round_index: int,
    player_id: int | None,
    ordinal: int,
    module_type: str,
    *,
    session_id: str = "",
    payload: dict | None = None,
) -> ModuleRef:
    if module_type not in SEQUENCE_MODULE_TYPES:
        raise ValueError(f"unknown sequence module type: {module_type}")
    name = module_type.removesuffix("Module")
    return ModuleRef(
        module_id=sequence_module_id(kind, round_index, player_id, ordinal, name),
        module_type=module_type,
        phase=name.lower(),
        owner_player_id=player_id,
        payload=dict(payload or {}),
        idempotency_key=idempotency_key(session_id, "seq", kind, round_index, player_id or "none", ordinal, name),
    )


def build_trick_sequence_frame(
    round_index: int,
    player_id: int,
    ordinal: int,
    *,
    parent_frame_id: str,
    parent_module_id: str,
    session_id: str = "",
) -> FrameState:
    return FrameState(
        frame_id=sequence_frame_id("trick", round_index, player_id, ordinal),
        frame_type="sequence",
        owner_player_id=player_id,
        parent_frame_id=parent_frame_id,
        created_by_module_id=parent_module_id,
        module_queue=[
            build_sequence_module("trick", round_index, player_id, ordinal, module_type, session_id=session_id)
            for module_type in TRICK_SEQUENCE_MODULE_TYPES
        ],
    )


def build_roll_and_arrive_sequence_frame(
    round_index: int,
    player_id: int,
    ordinal: int,
    *,
    parent_frame_id: str,
    parent_module_id: str,
    session_id: str = "",
) -> FrameState:
    modules = ["FortuneResolveModule", "MapMoveModule", "ArrivalTileModule"]
    return FrameState(
        frame_id=sequence_frame_id("roll_and_arrive", round_index, player_id, ordinal),
        frame_type="sequence",
        owner_player_id=player_id,
        parent_frame_id=parent_frame_id,
        created_by_module_id=parent_module_id,
        module_queue=[
            build_sequence_module("roll_and_arrive", round_index, player_id, ordinal, module_type, session_id=session_id)
            for module_type in modules
        ],
    )


def build_action_sequence_frame(
    round_index: int,
    player_id: int | None,
    ordinal: int,
    actions: list[dict],
    *,
    parent_frame_id: str,
    parent_module_id: str,
    session_id: str = "",
) -> FrameState:
    for action in actions:
        _validate_action_sequence_action(action)
    return FrameState(
        frame_id=sequence_frame_id("action", round_index, player_id, ordinal),
        frame_type="sequence",
        owner_player_id=player_id,
        parent_frame_id=parent_frame_id,
        created_by_module_id=parent_module_id,
        module_queue=[
            build_sequence_module(
                "action",
                round_index,
                _action_owner(action, player_id),
                ordinal + index,
                module_type_for_action(str(action.get("type", ""))),
                session_id=session_id,
                payload={"action": dict(action), "action_type": str(action.get("type", "")), "source": str(action.get("source", ""))},
            )
            for index, action in enumerate(actions)
        ],
    )


def build_turn_completion_sequence_frame(
    round_index: int,
    player_id: int | None,
    ordinal: int,
    pending_turn_completion: dict,
    *,
    parent_frame_id: str,
    parent_module_id: str,
    session_id: str = "",
) -> FrameState:
    return FrameState(
        frame_id=sequence_frame_id("turn_completion", round_index, player_id, ordinal),
        frame_type="sequence",
        owner_player_id=player_id,
        parent_frame_id=parent_frame_id,
        created_by_module_id=parent_module_id,
        module_queue=[
            build_sequence_module(
                "turn_completion",
                round_index,
                player_id,
                ordinal,
                "TurnEndSnapshotModule",
                session_id=session_id,
                payload={"pending_turn_completion": dict(pending_turn_completion)},
            )
        ],
    )


def _action_owner(action: dict, fallback: int | None) -> int | None:
    try:
        return int(action.get("actor_player_id", fallback))
    except (TypeError, ValueError):
        return fallback
