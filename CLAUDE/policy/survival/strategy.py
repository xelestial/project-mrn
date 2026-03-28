from __future__ import annotations

"""policy/survival/strategy — SurvivalStrategy ABC + 구현체.

설계 원칙:
- SurvivalStrategy.evaluate(ctx) → SurvivalAssessment
- TurnContext를 입력으로 받아 SurvivalAssessment를 반환한다.
- 상태 변경 없음. 엔진 접근 없음.
- Phase 2: DefaultSurvivalStrategy / V3ClaudeSurvivalStrategy는 동일 로직.
  Phase 3에서 프로파일별 임계값 주입으로 분리한다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .signals import SurvivalSignals
from .orchestrator import SurvivalOrchestratorState, build_survival_orchestrator

if TYPE_CHECKING:
    from policy.context.turn_context import TurnContext


@dataclass(frozen=True, slots=True)
class SurvivalAssessment:
    """SurvivalStrategy.evaluate() 반환값. choose_* 메서드에 주입된다."""

    signals: SurvivalSignals
    orchestrator: SurvivalOrchestratorState

    # ── Convenience accessors ─────────────────────────────────────────────

    @property
    def severe_distress(self) -> bool:
        return self.orchestrator.severe_distress

    @property
    def income_emergency(self) -> bool:
        return self.orchestrator.income_emergency

    @property
    def cleanup_emergency(self) -> bool:
        return self.orchestrator.cleanup_emergency

    @property
    def survival_first(self) -> bool:
        return self.orchestrator.survival_first

    @property
    def weight_multiplier(self) -> float:
        return self.orchestrator.weight_multiplier


class SurvivalStrategy(ABC):
    """생존 평가 전략 인터페이스."""

    @abstractmethod
    def evaluate(self, ctx: TurnContext) -> SurvivalAssessment:
        """TurnContext로부터 SurvivalAssessment를 계산한다."""
        ...


class DefaultSurvivalStrategy(SurvivalStrategy):
    """기본 생존 전략 — survival_common.build_survival_orchestrator 위임."""

    def evaluate(self, ctx: TurnContext) -> SurvivalAssessment:
        signals = SurvivalSignals(
            reserve=ctx.reserve,
            money_distress=ctx.money_distress,
            survival_urgency=ctx.survival_urgency,
            two_turn_lethal_prob=ctx.two_turn_lethal_prob,
            latent_cleanup_cost=ctx.latent_cleanup_cost,
            active_cleanup_cost=ctx.active_cleanup_cost,
            public_cleanup_active=ctx.public_cleanup_active,
        )
        orchestrator = build_survival_orchestrator(signals)
        return SurvivalAssessment(signals=signals, orchestrator=orchestrator)


class V3ClaudeSurvivalStrategy(DefaultSurvivalStrategy):
    """v3_claude 전용 생존 전략.

    Phase 2: DefaultSurvivalStrategy와 동일 로직.
    Phase 3: profiles/survival_threshold_v3_claude.json 분리 후 임계값 주입.
    """
