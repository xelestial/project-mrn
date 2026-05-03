"""Runtime module placement catalog."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import FrameState, FrameType, ModuleRef


@dataclass(frozen=True, slots=True)
class ModuleRule:
    module_type: str
    frame_types: frozenset[FrameType]


MODULE_RULES: dict[str, ModuleRule] = {
    "RoundStartModule": ModuleRule("RoundStartModule", frozenset({"round"})),
    "WeatherModule": ModuleRule("WeatherModule", frozenset({"round"})),
    "DraftModule": ModuleRule("DraftModule", frozenset({"round"})),
    "TurnSchedulerModule": ModuleRule("TurnSchedulerModule", frozenset({"round"})),
    "PlayerTurnModule": ModuleRule("PlayerTurnModule", frozenset({"round"})),
    "RoundEndCardFlipModule": ModuleRule("RoundEndCardFlipModule", frozenset({"round"})),
    "RoundCleanupAndNextRoundModule": ModuleRule("RoundCleanupAndNextRoundModule", frozenset({"round"})),
    "TurnStartModule": ModuleRule("TurnStartModule", frozenset({"turn"})),
    "ScheduledStartActionsModule": ModuleRule("ScheduledStartActionsModule", frozenset({"turn"})),
    "CharacterStartModule": ModuleRule("CharacterStartModule", frozenset({"turn"})),
    "ImmediateMarkerTransferModule": ModuleRule("ImmediateMarkerTransferModule", frozenset({"turn"})),
    "TargetJudicatorModule": ModuleRule("TargetJudicatorModule", frozenset({"turn"})),
    "TrickWindowModule": ModuleRule("TrickWindowModule", frozenset({"turn"})),
    "DiceRollModule": ModuleRule("DiceRollModule", frozenset({"turn"})),
    "MovementResolveModule": ModuleRule("MovementResolveModule", frozenset({"turn"})),
    "LapRewardModule": ModuleRule("LapRewardModule", frozenset({"turn"})),
    "PendingMarkResolutionModule": ModuleRule("PendingMarkResolutionModule", frozenset({"turn", "sequence"})),
    "MapMoveModule": ModuleRule("MapMoveModule", frozenset({"turn", "sequence"})),
    "ArrivalTileModule": ModuleRule("ArrivalTileModule", frozenset({"turn", "sequence"})),
    "RentPaymentModule": ModuleRule("RentPaymentModule", frozenset({"sequence"})),
    "FortuneResolveModule": ModuleRule("FortuneResolveModule", frozenset({"turn", "sequence"})),
    "PurchaseDecisionModule": ModuleRule("PurchaseDecisionModule", frozenset({"sequence"})),
    "PurchaseCommitModule": ModuleRule("PurchaseCommitModule", frozenset({"sequence"})),
    "UnownedPostPurchaseModule": ModuleRule("UnownedPostPurchaseModule", frozenset({"sequence"})),
    "ScoreTokenPlacementPromptModule": ModuleRule("ScoreTokenPlacementPromptModule", frozenset({"sequence"})),
    "ScoreTokenPlacementCommitModule": ModuleRule("ScoreTokenPlacementCommitModule", frozenset({"sequence"})),
    "LandingPostEffectsModule": ModuleRule("LandingPostEffectsModule", frozenset({"sequence"})),
    "TrickTileRentModifierModule": ModuleRule("TrickTileRentModifierModule", frozenset({"sequence"})),
    "TrickChoiceModule": ModuleRule("TrickChoiceModule", frozenset({"sequence"})),
    "TrickSkipModule": ModuleRule("TrickSkipModule", frozenset({"sequence"})),
    "TrickResolveModule": ModuleRule("TrickResolveModule", frozenset({"sequence"})),
    "TrickDiscardModule": ModuleRule("TrickDiscardModule", frozenset({"sequence"})),
    "TrickDeferredFollowupsModule": ModuleRule("TrickDeferredFollowupsModule", frozenset({"sequence"})),
    "TrickVisibilitySyncModule": ModuleRule("TrickVisibilitySyncModule", frozenset({"sequence"})),
    "TurnEndSnapshotModule": ModuleRule("TurnEndSnapshotModule", frozenset({"turn"})),
    "SimultaneousProcessingModule": ModuleRule("SimultaneousProcessingModule", frozenset({"simultaneous"})),
    "SimultaneousPromptBatchModule": ModuleRule("SimultaneousPromptBatchModule", frozenset({"simultaneous"})),
    "ResupplyModule": ModuleRule("ResupplyModule", frozenset({"simultaneous"})),
    "SimultaneousCommitModule": ModuleRule("SimultaneousCommitModule", frozenset({"simultaneous"})),
    "CompleteSimultaneousResolutionModule": ModuleRule(
        "CompleteSimultaneousResolutionModule",
        frozenset({"simultaneous"}),
    ),
}


def module_rule(module_type: str) -> ModuleRule | None:
    return MODULE_RULES.get(module_type)


def validate_module_placement(frame: FrameState, module: ModuleRef) -> None:
    rule = module_rule(module.module_type)
    if rule is None:
        return
    if frame.frame_type not in rule.frame_types:
        if frame.frame_type == "simultaneous":
            raise ValueError(f"{module.module_type} is not allowed in SimultaneousResolutionFrame")
        allowed = ", ".join(sorted(rule.frame_types))
        raise ValueError(f"{module.module_type} is not allowed in {frame.frame_type} frame; allowed: {allowed}")
