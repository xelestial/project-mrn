from __future__ import annotations

"""policy/context/builder — TurnContextBuilder.

Phase 2: 기존 policy 헬퍼 메서드에 위임해 TurnContext를 조립한다.
Phase 3에서 feature 모듈(_economy_features, _danger_features 등)로 이전한다.

설계 원칙:
- 상태 변경 없음 — 순수 조회/계산만.
- policy_ref는 약참조(런타임 전용). 직렬화/저장 금지.
"""

from typing import TYPE_CHECKING, Any

from .turn_context import TurnContext

if TYPE_CHECKING:
    from state import GameState, PlayerState


class TurnContextBuilder:
    """TurnContext를 빌드한다.

    Parameters
    ----------
    policy_ref:
        HeuristicPolicy 인스턴스. 헬퍼 메서드 접근에만 사용.
    """

    def __init__(self, policy_ref: Any) -> None:
        self._policy = policy_ref

    def build(
        self,
        state: GameState,
        player: PlayerState,
        character_name: str | None = None,
    ) -> TurnContext:
        """state + player → TurnContext 스냅샷."""
        p = self._policy

        # ── 기존 메서드에서 dict 수집 ────────────────────────────────────────
        survival = p._generic_survival_context(state, player, character_name)
        f_ctx = p._f_progress_context(state, player)
        burden = p._burden_context(state, player)

        return TurnContext(
            # Economy / liquidity
            reserve=float(survival["reserve"]),
            reserve_gap=float(survival["reserve_gap"]),
            cash_after_reserve=float(survival["cash_after_reserve"]),
            money_distress=float(survival["money_distress"]),
            needs_income=bool(survival.get("needs_income", 0.0)),
            # Survival scores
            generic_survival_score=float(survival["generic_survival_score"]),
            survival_urgency=float(survival["survival_urgency"]),
            hazard_score=float(survival["hazard_score"]),
            recovery_score=float(survival["recovery_score"]),
            # External threats
            rent_pressure=float(survival["rent_pressure"]),
            lethal_hit_prob=float(survival["lethal_hit_prob"]),
            two_turn_hit_prob=float(survival["two_turn_hit_prob"]),
            two_turn_lethal_prob=float(survival["two_turn_lethal_prob"]),
            two_turn_recovery_prob=float(survival["two_turn_recovery_prob"]),
            front_enemy_density=float(survival["front_enemy_density"]),
            front_recovery_density=float(survival["front_recovery_density"]),
            front_peak_cost=float(survival["front_peak_cost"]),
            active_drain_pressure=float(survival["active_drain_pressure"]),
            controller_need=float(survival["controller_need"]),
            # Cleanup / burdens
            cleanup_pressure=float(survival["cleanup_pressure"]),
            own_burden_cost=float(survival["own_burden_cost"]),
            own_burdens=int(burden.get("own_burdens", 0)),
            active_cleanup_cost=float(survival["active_cleanup_cost"]),
            latent_cleanup_cost=float(survival["latent_cleanup_cost"]),
            expected_cleanup_cost=float(survival["expected_cleanup_cost"]),
            cleanup_cash_gap=float(survival["cleanup_cash_gap"]),
            latent_cleanup_gap=float(survival["latent_cleanup_gap"]),
            expected_cleanup_gap=float(survival["expected_cleanup_gap"]),
            public_cleanup_active=float(survival["public_cleanup_active"]) > 0.0,
            # Movement hints
            cross_start=float(survival["cross_start"]) > 0.0,
            land_f=float(survival["land_f"]) > 0.0,
            special_reach=float(survival["special_reach"]),
            # Race / position
            is_leader=bool(f_ctx["is_leader"]),
            near_leader=bool(f_ctx["near_leader"]),
            rank=int(f_ctx["rank"]),
            leader_gap=float(f_ctx["leader_gap"]),
            lead_margin=float(f_ctx["lead_margin"]),
            f_remaining=float(f_ctx["f_remaining"]),
            land_f_value=float(f_ctx["land_f_value"]),
            card_f_penalty=float(f_ctx["card_f_penalty"]),
            avoid_f_acceleration=float(f_ctx["avoid_f_acceleration"]),
            # Table state
            median_cash=float(survival["median_cash"]),
            cash_gap_to_table=float(survival["cash_gap_to_table"]),
            poor_ratio=float(survival["poor_ratio"]),
        )
