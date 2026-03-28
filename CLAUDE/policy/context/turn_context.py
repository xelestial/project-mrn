from __future__ import annotations

"""policy/context/turn_context — 단일 턴 타입 안전 컨텍스트.

설계 원칙:
- choose_* 메서드들이 dict["key"] 대신 ctx.field로 접근한다.
- 빌드는 TurnContextBuilder가 담당한다.
- Phase 2: to_survival_dict() / to_f_dict()로 기존 dict 접근과 병행.
  Phase 3에서 dict 접근 코드를 직접 ctx.field로 전환한다.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TurnContext:
    """단일 턴의 상태 스냅샷. choose_* 메서드가 공유하는 타입 안전 컨텍스트."""

    # ── Economy / liquidity ─────────────────────────────────────────────────
    reserve: float
    reserve_gap: float
    cash_after_reserve: float
    money_distress: float
    needs_income: bool

    # ── Survival scores ──────────────────────────────────────────────────────
    generic_survival_score: float
    survival_urgency: float
    hazard_score: float
    recovery_score: float

    # ── External threats ─────────────────────────────────────────────────────
    rent_pressure: float
    lethal_hit_prob: float
    two_turn_hit_prob: float
    two_turn_lethal_prob: float
    two_turn_recovery_prob: float
    front_enemy_density: float
    front_recovery_density: float
    front_peak_cost: float
    active_drain_pressure: float
    controller_need: float

    # ── Cleanup / burdens ────────────────────────────────────────────────────
    cleanup_pressure: float
    own_burden_cost: float
    own_burdens: int
    active_cleanup_cost: float
    latent_cleanup_cost: float
    expected_cleanup_cost: float
    cleanup_cash_gap: float
    latent_cleanup_gap: float
    expected_cleanup_gap: float
    public_cleanup_active: bool

    # ── Movement hints ───────────────────────────────────────────────────────
    cross_start: bool
    land_f: bool
    special_reach: float

    # ── Race / position ──────────────────────────────────────────────────────
    is_leader: bool
    near_leader: bool
    rank: int
    leader_gap: float
    lead_margin: float
    f_remaining: float
    land_f_value: float
    card_f_penalty: float
    avoid_f_acceleration: float

    # ── Table state ──────────────────────────────────────────────────────────
    median_cash: float
    cash_gap_to_table: float
    poor_ratio: float

    # ── Backward-compat conversion ───────────────────────────────────────────

    def to_survival_dict(self) -> dict[str, float]:
        """_generic_survival_context() 호환 dict. 점진 교체 기간 동안 사용."""
        return {
            "generic_survival_score": self.generic_survival_score,
            "survival_urgency": self.survival_urgency,
            "hazard_score": self.hazard_score,
            "recovery_score": self.recovery_score,
            "rent_pressure": self.rent_pressure,
            "lethal_hit_prob": self.lethal_hit_prob,
            "reserve": self.reserve,
            "reserve_gap": self.reserve_gap,
            "cash_after_reserve": self.cash_after_reserve,
            "cross_start": float(self.cross_start),
            "land_f": float(self.land_f),
            "special_reach": self.special_reach,
            "cleanup_pressure": self.cleanup_pressure,
            "own_burden_cost": self.own_burden_cost,
            "own_burdens": float(self.own_burdens),
            "active_cleanup_cost": self.active_cleanup_cost,
            "latent_cleanup_cost": self.latent_cleanup_cost,
            "expected_cleanup_cost": self.expected_cleanup_cost,
            "cleanup_cash_gap": self.cleanup_cash_gap,
            "latent_cleanup_gap": self.latent_cleanup_gap,
            "expected_cleanup_gap": self.expected_cleanup_gap,
            "public_cleanup_active": float(self.public_cleanup_active),
            "front_enemy_density": self.front_enemy_density,
            "front_recovery_density": self.front_recovery_density,
            "front_peak_cost": self.front_peak_cost,
            "two_turn_hit_prob": self.two_turn_hit_prob,
            "two_turn_lethal_prob": self.two_turn_lethal_prob,
            "two_turn_recovery_prob": self.two_turn_recovery_prob,
            "active_drain_pressure": self.active_drain_pressure,
            "controller_need": self.controller_need,
            "money_distress": self.money_distress,
            "needs_income": 1.0 if self.needs_income else 0.0,
            "median_cash": self.median_cash,
            "cash_gap_to_table": self.cash_gap_to_table,
            "poor_ratio": self.poor_ratio,
        }

    def to_f_dict(self) -> dict:
        """_f_progress_context() 호환 dict. 점진 교체 기간 동안 사용."""
        return {
            "is_leader": self.is_leader,
            "near_leader": self.near_leader,
            "rank": self.rank,
            "leader_gap": self.leader_gap,
            "lead_margin": self.lead_margin,
            "f_remaining": self.f_remaining,
            "land_f_value": self.land_f_value,
            "card_f_penalty": self.card_f_penalty,
            "avoid_f_acceleration": self.avoid_f_acceleration,
        }
