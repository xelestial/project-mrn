from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from survival_common import ActionGuardContext, CleanupStrategyContext, SurvivalSignals, build_action_guard_context, build_cleanup_strategy_context


@dataclass(frozen=True, slots=True)
class PolicySurvivalContext:
    raw: Mapping[str, float]
    signals: SurvivalSignals
    action_guard: ActionGuardContext
    cleanup_strategy: CleanupStrategyContext
    generic_survival_score: float
    reserve: float
    survival_urgency: float
    cleanup_pressure: float
    cash_after_reserve: float
    own_burdens: float
    expected_cleanup_cost: float
    next_draw_negative_cleanup_prob: float
    two_draw_negative_cleanup_prob: float
    recovery_score: float
    rent_pressure: float
    lethal_hit_prob: float
    controller_need: float
    money_distress: float
    own_burden_cost: float
    reserve_gap: float
    needs_income: bool
    cleanup_cash_gap: float
    latent_cleanup_cost: float
    cycle_negative_cleanup_prob: float
    expected_cleanup_gap: float
    downside_expected_cleanup_cost: float
    worst_cleanup_cost: float
    public_cleanup_active: bool
    cross_start: float
    land_f: float
    active_cleanup_cost: float
    remaining_negative_cleanup_cards: float


def build_policy_survival_context(data: Mapping[str, float], *, cash: int, shards: int) -> PolicySurvivalContext:
    signals = SurvivalSignals.from_mapping(data)
    action_guard = build_action_guard_context(signals)
    cleanup_strategy = build_cleanup_strategy_context(data, cash=cash, shards=shards)
    return PolicySurvivalContext(
        raw=data,
        signals=signals,
        action_guard=action_guard,
        cleanup_strategy=cleanup_strategy,
        generic_survival_score=float(data.get("generic_survival_score", 0.0)),
        reserve=float(data.get("reserve", 0.0)),
        survival_urgency=float(data.get("survival_urgency", 0.0)),
        cleanup_pressure=float(data.get("cleanup_pressure", 0.0)),
        cash_after_reserve=float(data.get("cash_after_reserve", 0.0)),
        own_burdens=float(data.get("own_burdens", 0.0)),
        expected_cleanup_cost=float(data.get("expected_cleanup_cost", 0.0)),
        next_draw_negative_cleanup_prob=float(data.get("next_draw_negative_cleanup_prob", 0.0)),
        two_draw_negative_cleanup_prob=float(data.get("two_draw_negative_cleanup_prob", 0.0)),
        recovery_score=float(data.get("recovery_score", 0.0)),
        rent_pressure=float(data.get("rent_pressure", 0.0)),
        lethal_hit_prob=float(data.get("lethal_hit_prob", 0.0)),
        controller_need=float(data.get("controller_need", 0.0)),
        money_distress=float(data.get("money_distress", 0.0)),
        own_burden_cost=float(data.get("own_burden_cost", 0.0)),
        reserve_gap=float(data.get("reserve_gap", 0.0)),
        needs_income=bool(float(data.get("needs_income", 0.0)) > 0.0),
        cleanup_cash_gap=float(data.get("cleanup_cash_gap", 0.0)),
        latent_cleanup_cost=float(data.get("latent_cleanup_cost", 0.0)),
        cycle_negative_cleanup_prob=float(data.get("cycle_negative_cleanup_prob", 0.0)),
        expected_cleanup_gap=float(data.get("expected_cleanup_gap", 0.0)),
        downside_expected_cleanup_cost=float(data.get("downside_expected_cleanup_cost", 0.0)),
        worst_cleanup_cost=float(data.get("worst_cleanup_cost", 0.0)),
        public_cleanup_active=bool(float(data.get("public_cleanup_active", 0.0)) > 0.0),
        cross_start=float(data.get("cross_start", 0.0)),
        land_f=float(data.get("land_f", 0.0)),
        active_cleanup_cost=float(data.get("active_cleanup_cost", 0.0)),
        remaining_negative_cleanup_cards=float(data.get("remaining_negative_cleanup_cards", 0.0)),
    )
