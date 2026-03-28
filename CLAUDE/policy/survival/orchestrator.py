from __future__ import annotations

"""policy/survival/orchestrator — SurvivalOrchestratorState + CleanupStrategyContext + 어드바이스."""

from dataclasses import dataclass
from typing import Mapping, Any

from .thresholds import _T
from .signals import SurvivalSignals
from .guards import ActionGuardContext, build_action_guard_context


@dataclass(frozen=True, slots=True)
class SurvivalOrchestratorState:
    signals: SurvivalSignals
    action_guard: ActionGuardContext
    severe_distress: bool
    income_emergency: bool
    cleanup_emergency: bool
    survival_first: bool
    weight_multiplier: float


def build_survival_orchestrator(signals: SurvivalSignals) -> SurvivalOrchestratorState:
    action_guard = build_action_guard_context(signals)
    cleanup_emergency = signals.public_cleanup_active and signals.active_cleanup_cost > 0.0
    severe_distress = (
        signals.money_distress >= _T.severe_distress_money
        or signals.survival_urgency >= _T.severe_distress_urgency
        or signals.two_turn_lethal_prob >= _T.severe_distress_lethal
        or (signals.public_cleanup_active and signals.active_cleanup_cost > max(_T.severe_cleanup_cost_abs, signals.reserve + _T.severe_cleanup_reserve_margin))
    )
    income_emergency = (
        severe_distress
        or signals.money_distress >= _T.cleanup_emergency_money
        or signals.latent_cleanup_cost >= max(_T.income_emergency_latent_abs, signals.reserve + _T.income_emergency_latent_reserve_margin)
    )
    survival_first = severe_distress or cleanup_emergency or signals.survival_urgency >= _T.cleanup_emergency_urgency
    weight_multiplier = (
        1.0
        + _T.orchestrator_weight_distress * max(0.0, signals.money_distress)
        + _T.orchestrator_weight_urgency * max(0.0, signals.survival_urgency)
        + _T.orchestrator_weight_lethal * max(0.0, signals.two_turn_lethal_prob)
    )
    if cleanup_emergency:
        weight_multiplier += _T.orchestrator_cleanup_bonus
    return SurvivalOrchestratorState(
        signals=signals,
        action_guard=action_guard,
        severe_distress=severe_distress,
        income_emergency=income_emergency,
        cleanup_emergency=cleanup_emergency,
        survival_first=survival_first,
        weight_multiplier=max(1.0, weight_multiplier),
    )


@dataclass(frozen=True, slots=True)
class CharacterSurvivalAdvice:
    severity: str
    bias_score: float
    hard_block: bool
    recommended_biases: tuple[str, ...]
    reason: str


def evaluate_character_survival_advice(
    *,
    state: SurvivalOrchestratorState,
    is_growth: bool,
    is_income: bool,
    is_controller: bool,
    is_cleanup: bool,
    cash: float,
    purchase_floor: float | None = None,
    swindle_floor: float | None = None,
) -> CharacterSurvivalAdvice:
    signals = state.signals
    action_guard = state.action_guard
    severity = "low"
    if state.severe_distress or signals.two_turn_lethal_prob >= _T.severe_distress_lethal or signals.money_distress >= _T.severe_distress_money:
        severity = "critical"
    elif state.cleanup_emergency or signals.survival_urgency >= _T.cleanup_emergency_urgency or signals.money_distress >= _T.cleanup_emergency_money:
        severity = "high"
    elif signals.survival_urgency >= _T.soft_distress_urgency or signals.money_distress >= _T.soft_distress_money or signals.latent_cleanup_cost >= max(_T.medium_latent_abs, signals.reserve + _T.medium_latent_reserve_margin):
        severity = "medium"

    biases: list[str] = []
    score = 0.0
    m = state.weight_multiplier
    hard_block = False
    reasons: list[str] = [f"severity={severity}"]

    if is_income:
        score += 1.6 * m if severity in {"critical", "high"} else 0.8 * m if severity == "medium" else 0.2
        biases.append('income')
        reasons.append('income_bias')
    if is_controller and severity in {"critical", "high", "medium"}:
        score += 1.0 * m if severity in {"critical", "high"} else 0.45 * m
        biases.append('control')
        reasons.append('controller_bias')
    if is_cleanup and (severity in {"critical", "high"} or state.cleanup_emergency):
        score += 1.4 * m if severity == "critical" else 1.0 * m
        biases.append('cleanup')
        reasons.append('cleanup_bias')

    if is_growth:
        growth_penalty = 0.0
        if severity == "critical":
            growth_penalty += 2.2 * m
            reasons.append('critical_growth_penalty')
        elif severity == "high":
            growth_penalty += 1.5 * m
            reasons.append('high_growth_penalty')
        elif severity == "medium":
            growth_penalty += 0.7 * m
            reasons.append('medium_growth_penalty')
        if purchase_floor is not None and cash < purchase_floor + action_guard.reserve_floor + 1.0:
            growth_penalty += 1.2 * m
            reasons.append('purchase_not_fundable')
        if swindle_floor is not None and cash < swindle_floor + action_guard.reserve_floor + 2.0:
            growth_penalty += 1.4 * m
            reasons.append('swindle_not_fundable')
        score -= growth_penalty

        true_suicide = (
            severity == "critical"
            and (purchase_floor is not None or swindle_floor is not None)
            and (
                (purchase_floor is not None and cash < purchase_floor + action_guard.reserve_floor)
                or (swindle_floor is not None and cash < swindle_floor + action_guard.reserve_floor + 1.0)
            )
        )
        hard_block = bool(true_suicide)
        if hard_block:
            reasons.append('true_suicide_growth_pick')

    return CharacterSurvivalAdvice(
        severity=severity,
        bias_score=float(score),
        hard_block=hard_block,
        recommended_biases=tuple(biases),
        reason=','.join(reasons),
    )


@dataclass(frozen=True, slots=True)
class CleanupStrategyContext:
    """CLAUDE-side 짐 정리 전략 컨텍스트."""
    own_burdens: int
    own_burden_cost: float
    cleanup_pressure: float
    public_cleanup_active: bool
    active_cleanup_cost: float
    latent_cleanup_cost: float
    expected_cleanup_cost: float
    cleanup_cash_gap: float
    latent_cleanup_gap: float
    deck_next_draw_cleanup_prob: float
    deck_two_draw_cleanup_prob: float
    deck_cycle_cleanup_prob: float
    cleanup_stage: str  # safe / strained / critical / meltdown

    @classmethod
    def from_burden_context(cls, ctx: Mapping[str, Any], cash: float = 0.0) -> "CleanupStrategyContext":
        own_burden_cost = float(ctx.get("own_burden_cost", 0.0))
        cleanup_pressure = float(ctx.get("cleanup_pressure", 0.0))
        public_cleanup_active = float(ctx.get("public_cleanup_active", 0.0)) > 0.0
        active_cleanup_cost = float(ctx.get("active_cleanup_cost", 0.0))
        latent_cleanup_cost = float(ctx.get("latent_cleanup_cost", 0.0))
        if public_cleanup_active and active_cleanup_cost > max(cash * 0.6, 8.0):
            stage = "meltdown"
        elif public_cleanup_active or cleanup_pressure >= 2.5:
            stage = "critical"
        elif cleanup_pressure >= 1.0 or latent_cleanup_cost > 0.0:
            stage = "strained"
        else:
            stage = "safe"
        return cls(
            own_burdens=int(ctx.get("own_burdens", 0)),
            own_burden_cost=own_burden_cost,
            cleanup_pressure=cleanup_pressure,
            public_cleanup_active=public_cleanup_active,
            active_cleanup_cost=active_cleanup_cost,
            latent_cleanup_cost=latent_cleanup_cost,
            expected_cleanup_cost=float(ctx.get("expected_cleanup_cost", 0.0)),
            cleanup_cash_gap=float(ctx.get("cleanup_cash_gap", 0.0)),
            latent_cleanup_gap=float(ctx.get("latent_cleanup_gap", 0.0)),
            deck_next_draw_cleanup_prob=float(ctx.get("deck_next_draw_cleanup_prob", 0.0)),
            deck_two_draw_cleanup_prob=float(ctx.get("deck_two_draw_cleanup_prob", 0.0)),
            deck_cycle_cleanup_prob=float(ctx.get("deck_cycle_cleanup_prob", 0.0)),
            cleanup_stage=stage,
        )


def evaluate_character_survival_priority(
    *,
    state: SurvivalOrchestratorState,
    is_growth: bool,
    is_income: bool,
    is_controller: bool,
    is_cleanup: bool,
    cash: float,
    purchase_floor: float | None = None,
    swindle_floor: float | None = None,
) -> tuple[float, str]:
    score = 0.0
    reasons: list[str] = []
    m = state.weight_multiplier
    if state.survival_first:
        if is_income:
            score += 2.2 * m
            reasons.append('survival_first_income')
        if is_controller:
            score += 1.3 * m
            reasons.append('survival_first_controller')
        if is_cleanup:
            score += 1.8 * m
            reasons.append('survival_first_cleanup')
        if is_growth:
            score -= 2.4 * m
            reasons.append('survival_first_growth_penalty')
    if state.income_emergency and is_income:
        score += 1.5 * m
        reasons.append('income_emergency_bonus')
    if state.cleanup_emergency and is_cleanup:
        score += 1.4 * m
        reasons.append('cleanup_emergency_bonus')
    if is_growth:
        if purchase_floor is not None and cash < purchase_floor + state.action_guard.reserve_floor + 1.0:
            score -= 1.9 * m
            reasons.append('growth_purchase_not_fundable')
        if swindle_floor is not None and cash < swindle_floor + state.action_guard.reserve_floor + 2.0:
            score -= 2.1 * m
            reasons.append('growth_swindle_not_fundable')
        if state.severe_distress:
            score -= 1.0 * m
            reasons.append('growth_blocked_by_distress')
    return score, ','.join(reasons)
