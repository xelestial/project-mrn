from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Mapping, Any


@dataclass(frozen=True, slots=True)
class SurvivalThresholdSpec:
    """생존 판단에 사용되는 임계값/가중치 모음. profiles/survival_threshold_*.json에서 로드."""

    # build_action_guard_context
    action_guard_lethal_weight: float = 1.50
    action_guard_distress_weight: float = 0.60
    action_guard_urgency_weight: float = 0.35
    action_guard_latent_weight: float = 0.25

    # swindle_operating_reserve
    swindle_latent_multiplier: float = 0.65
    swindle_lethal_weight: float = 2.0
    swindle_distress_weight: float = 1.5
    swindle_urgency_weight: float = 0.75

    # evaluate_swindle_guard
    swindle_buffer: float = 2.0
    swindle_guard_floor_margin: float = 1.0
    swindle_high_cost_threshold_strict: float = 16.0
    swindle_high_cost_threshold_abs: float = 12.0
    swindle_high_cost_ratio: float = 0.60
    swindle_distress_gate: float = 0.35
    swindle_urgency_gate: float = 0.35
    swindle_lethal_gate: float = 0.10
    swindle_critical_distress: float = 0.55
    swindle_critical_urgency: float = 0.55
    swindle_critical_lethal: float = 0.18
    swindle_critical_reserve_buffer: float = 6.0

    # build_survival_orchestrator
    orchestrator_weight_lethal: float = 2.25
    orchestrator_weight_distress: float = 1.75
    orchestrator_weight_urgency: float = 1.35
    orchestrator_cleanup_bonus: float = 1.25
    severe_distress_lethal: float = 0.18
    severe_distress_money: float = 1.10
    severe_distress_urgency: float = 1.00
    severe_cleanup_cost_abs: float = 8.0
    severe_cleanup_reserve_margin: float = 2.0
    income_emergency_latent_abs: float = 10.0
    income_emergency_latent_reserve_margin: float = 4.0
    cleanup_emergency_urgency: float = 0.70
    cleanup_emergency_money: float = 0.85

    # evaluate_character_survival_advice
    soft_distress_urgency: float = 0.40
    soft_distress_money: float = 0.45
    medium_latent_abs: float = 8.0
    medium_latent_reserve_margin: float = 2.0

    @classmethod
    def from_json(cls, path: str) -> "SurvivalThresholdSpec":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _load_default_thresholds() -> SurvivalThresholdSpec:
    path = os.path.join(os.path.dirname(__file__), "profiles", "survival_threshold_default.json")
    try:
        return SurvivalThresholdSpec.from_json(path)
    except (FileNotFoundError, KeyError):
        return SurvivalThresholdSpec()


_T: SurvivalThresholdSpec = _load_default_thresholds()


@dataclass(frozen=True, slots=True)
class SurvivalSignals:
    reserve: float
    money_distress: float
    survival_urgency: float
    two_turn_lethal_prob: float
    latent_cleanup_cost: float
    active_cleanup_cost: float
    public_cleanup_active: bool

    @classmethod
    def from_mapping(cls, data: Mapping[str, float]) -> "SurvivalSignals":
        return cls(
            reserve=float(data.get("reserve", 0.0)),
            money_distress=float(data.get("money_distress", 0.0)),
            survival_urgency=float(data.get("survival_urgency", 0.0)),
            two_turn_lethal_prob=float(data.get("two_turn_lethal_prob", 0.0)),
            latent_cleanup_cost=float(data.get("latent_cleanup_cost", 0.0)),
            active_cleanup_cost=float(data.get("active_cleanup_cost", 0.0)),
            public_cleanup_active=float(data.get("public_cleanup_active", 0.0)) > 0.0,
        )


@dataclass(frozen=True, slots=True)
class ActionGuardContext:
    reserve_floor: float
    money_distress: float
    survival_urgency: float
    two_turn_lethal_prob: float


@dataclass(frozen=True, slots=True)
class SwindleGuardDecision:
    allowed: bool
    reserve: float
    post_cash: float
    reason: str


def build_action_guard_context(signals: SurvivalSignals) -> ActionGuardContext:
    reserve = signals.reserve
    reserve += _T.action_guard_lethal_weight * signals.two_turn_lethal_prob
    reserve += _T.action_guard_distress_weight * signals.money_distress
    reserve += _T.action_guard_urgency_weight * signals.survival_urgency
    reserve += _T.action_guard_latent_weight * signals.latent_cleanup_cost
    if signals.public_cleanup_active:
        reserve = max(reserve, signals.active_cleanup_cost)
    return ActionGuardContext(
        reserve_floor=max(0.0, reserve),
        money_distress=signals.money_distress,
        survival_urgency=signals.survival_urgency,
        two_turn_lethal_prob=signals.two_turn_lethal_prob,
    )


def is_action_survivable(*, cash: float, immediate_cost: float = 0.0, post_action_cash: float | None = None, reserve_floor: float, buffer: float = 0.0) -> bool:
    remaining_cash = cash - immediate_cost if post_action_cash is None else post_action_cash
    return float(remaining_cash) >= float(reserve_floor) + float(buffer)


def swindle_operating_reserve(signals: SurvivalSignals) -> float:
    reserve = signals.reserve
    reserve = max(reserve, signals.active_cleanup_cost, _T.swindle_latent_multiplier * signals.latent_cleanup_cost)
    reserve += _T.swindle_lethal_weight * signals.two_turn_lethal_prob + _T.swindle_distress_weight * signals.money_distress + _T.swindle_urgency_weight * signals.survival_urgency
    return max(0.0, reserve)


def evaluate_swindle_guard(*, cash: float, required_cost: float, signals: SurvivalSignals, is_leader: bool, near_end: bool) -> SwindleGuardDecision:
    if required_cost <= 0.0:
        return SwindleGuardDecision(True, 0.0, cash, "no_cost")
    reserve = swindle_operating_reserve(signals)
    post_cash = float(cash) - float(required_cost)
    common_guard_floor = reserve + _T.swindle_guard_floor_margin
    if not is_action_survivable(cash=float(cash), immediate_cost=float(required_cost), reserve_floor=common_guard_floor, buffer=_T.swindle_buffer):
        return SwindleGuardDecision(False, reserve, post_cash, "global_action_survival_guard")
    if float(required_cost) >= _T.swindle_high_cost_threshold_strict and not (is_leader and near_end and post_cash >= reserve + _T.swindle_critical_reserve_buffer):
        return SwindleGuardDecision(False, reserve, post_cash, "high_cost_not_leader_finish_window")
    if float(required_cost) >= max(_T.swindle_high_cost_threshold_abs, _T.swindle_high_cost_ratio * float(cash)) and (signals.money_distress >= _T.swindle_distress_gate or signals.survival_urgency >= _T.swindle_urgency_gate or signals.two_turn_lethal_prob >= _T.swindle_lethal_gate):
        return SwindleGuardDecision(False, reserve, post_cash, "high_cost_under_distress")
    if (signals.money_distress >= _T.swindle_critical_distress or signals.survival_urgency >= _T.swindle_critical_urgency or signals.two_turn_lethal_prob >= _T.swindle_critical_lethal) and post_cash < reserve + _T.swindle_critical_reserve_buffer:
        return SwindleGuardDecision(False, reserve, post_cash, "post_cash_below_operating_reserve")
    return SwindleGuardDecision(True, reserve, post_cash, "allowed")


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
    weight_multiplier = 1.0 + _T.orchestrator_weight_distress * max(0.0, signals.money_distress) + _T.orchestrator_weight_urgency * max(0.0, signals.survival_urgency) + _T.orchestrator_weight_lethal * max(0.0, signals.two_turn_lethal_prob)
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


def evaluate_character_survival_advice(*, state: SurvivalOrchestratorState, is_growth: bool, is_income: bool, is_controller: bool, is_cleanup: bool, cash: float, purchase_floor: float | None = None, swindle_floor: float | None = None) -> CharacterSurvivalAdvice:
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

        # Only mark hard-block on true suicide-like growth picks. The policy still decides how to use this.
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
    """CLAUDE-side 짐 정리 전략 컨텍스트.

    _burden_context() dict 대신 타입 안전 접근 제공.
    GPT의 CleanupStrategyContext와 개념은 같지만 필드는 CLAUDE 독자적으로 정의.
    """
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
        """_burden_context() 반환 dict로부터 생성."""
        own_burden_cost = float(ctx.get("own_burden_cost", 0.0))
        cleanup_pressure = float(ctx.get("cleanup_pressure", 0.0))
        public_cleanup_active = float(ctx.get("public_cleanup_active", 0.0)) > 0.0
        active_cleanup_cost = float(ctx.get("active_cleanup_cost", 0.0))
        latent_cleanup_cost = float(ctx.get("latent_cleanup_cost", 0.0))

        # Cleanup stage 분류 (CLAUDE 자체 기준)
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


def evaluate_character_survival_priority(*, state: SurvivalOrchestratorState, is_growth: bool, is_income: bool, is_controller: bool, is_cleanup: bool, cash: float, purchase_floor: float | None = None, swindle_floor: float | None = None) -> tuple[float, str]:
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
