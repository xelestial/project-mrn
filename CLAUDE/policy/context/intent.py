from __future__ import annotations

"""policy/context/intent — 플레이어별 의도 상태 (Intent Memory Contract).

설계 원칙:
- 엔진이 소유하지 않는다. 정책 런타임 내부 상태다.
- choose_* 메서드들이 동일 플레이어에 대해 일관된 플랜을 참조하도록 한다.
- 플랜 만료나 재계산은 정책이 직접 관리한다.
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Plan keys ──────────────────────────────────────────────────────────────

PLAN_KEYS = frozenset({
    "lap_engine",        # 랩 보상 최적화 중심
    "survival_recovery", # 생존/회복 최우선
    "controller_disrupt",# 컨트롤러 방해 집중
    "land_grab",         # 타일 선점
    "leader_denial",     # 선두 견제
    "none",              # 플랜 없음 (기본값)
})

RESOURCE_INTENTS = frozenset({
    "balanced",
    "cash_first",
    "shard_checkpoint",
    "card_preserve",
})


@dataclass
class PlayerIntentState:
    """플레이어별 현재 의도 상태.

    choose_* 메서드들이 이 상태를 읽어 일관성 있는 결정을 내린다.
    """
    plan_key: str = "none"
    plan_start_round: int = 0
    locked_target_character: Optional[str] = None
    locked_block_id: Optional[int] = None
    resource_intent: str = "balanced"
    plan_confidence: float = 0.5
    expires_after_round: int = 0  # 0 = 만료 없음

    def is_expired(self, current_round: int) -> bool:
        return self.expires_after_round > 0 and current_round > self.expires_after_round

    def reset(self) -> "PlayerIntentState":
        return PlayerIntentState()

    def with_plan(
        self,
        plan_key: str,
        *,
        round_number: int,
        confidence: float = 0.5,
        expires_after: int = 0,
        resource_intent: str = "balanced",
        locked_character: Optional[str] = None,
        locked_block: Optional[int] = None,
    ) -> "PlayerIntentState":
        """새 플랜으로 갱신된 인스턴스를 반환한다."""
        return PlayerIntentState(
            plan_key=plan_key,
            plan_start_round=round_number,
            locked_target_character=locked_character,
            locked_block_id=locked_block,
            resource_intent=resource_intent,
            plan_confidence=confidence,
            expires_after_round=expires_after,
        )


@dataclass(frozen=True, slots=True)
class TurnPlanContext:
    """단일 턴에서 choose_* 메서드가 공유하는 플랜 스냅샷."""
    player_id: int
    round_number: int
    intent: PlayerIntentState
    plan_changed: bool = False
    change_reason: str = ""
