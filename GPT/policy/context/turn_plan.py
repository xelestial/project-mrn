from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from survival_common import CleanupStrategyContext


@dataclass(frozen=True, slots=True)
class PlayerIntentState:
    plan_key: str
    resource_intent: str
    reason: str
    source_character: str
    plan_confidence: float
    plan_start_round: int
    expires_after_round: int
    locked_target_character: Optional[str] = None
    locked_block_id: Optional[int] = None


@dataclass(frozen=True, slots=True)
class TurnPlanContext:
    plan_key: str
    resource_intent: str
    reason: str
    source_character: str
    plan_confidence: float
    cleanup_stage: str
    shard_tier: str
    growth_locked: bool
    current_character: Optional[str]
    cash: int
    shards: int


def build_turn_plan_context(
    intent: PlayerIntentState | None,
    cleanup_strategy: CleanupStrategyContext,
    *,
    current_character: str | None,
    cash: int,
    shards: int,
) -> TurnPlanContext:
    return TurnPlanContext(
        plan_key=intent.plan_key if intent else "unplanned",
        resource_intent=intent.resource_intent if intent else "none",
        reason=intent.reason if intent else "no_intent",
        source_character=intent.source_character if intent else (current_character or ""),
        plan_confidence=float(intent.plan_confidence) if intent else 0.0,
        cleanup_stage=cleanup_strategy.cleanup_stage,
        shard_tier=cleanup_strategy.shard_tier,
        growth_locked=bool(cleanup_strategy.growth_locked),
        current_character=current_character,
        cash=int(cash),
        shards=int(shards),
    )
