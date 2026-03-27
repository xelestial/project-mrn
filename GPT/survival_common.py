from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


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
class CleanupStrategyContext:
    burden_count: float
    shard_tier: str
    shard_buffer_cash: float
    cleanup_stage: str
    stage_score: float
    deck_pressure: float
    cash_pressure: float
    controller_bias: float
    lap_cash_preference: float
    lap_shard_preference: float
    growth_locked: bool


@dataclass(frozen=True, slots=True)
class SwindleGuardDecision:
    allowed: bool
    reserve: float
    post_cash: float
    reason: str


def build_action_guard_context(signals: SurvivalSignals) -> ActionGuardContext:
    reserve = signals.reserve
    reserve += 1.50 * signals.two_turn_lethal_prob
    reserve += 0.60 * signals.money_distress
    reserve += 0.35 * signals.survival_urgency
    reserve += 0.25 * signals.latent_cleanup_cost
    if signals.public_cleanup_active:
        reserve = max(reserve, signals.active_cleanup_cost)
    return ActionGuardContext(
        reserve_floor=max(0.0, reserve),
        money_distress=signals.money_distress,
        survival_urgency=signals.survival_urgency,
        two_turn_lethal_prob=signals.two_turn_lethal_prob,
    )


def build_cleanup_strategy_context(data: Mapping[str, float], *, cash: float, shards: int) -> CleanupStrategyContext:
    burden_count = float(data.get("own_burdens", 0.0))
    cleanup_cash_gap = float(data.get("cleanup_cash_gap", 0.0))
    expected_cleanup_cost = float(data.get("expected_cleanup_cost", 0.0))
    money_distress = float(data.get("money_distress", 0.0))
    next_negative = float(data.get("next_draw_negative_cleanup_prob", 0.0))
    two_draw_negative = float(data.get("two_draw_negative_cleanup_prob", 0.0))
    cycle_negative = float(data.get("cycle_negative_cleanup_prob", 0.0))
    remaining_negative = float(data.get("remaining_negative_cleanup_cards", 0.0))
    remaining_positive = float(data.get("remaining_positive_cleanup_cards", 0.0))
    public_cleanup_active = float(data.get("public_cleanup_active", 0.0)) > 0.0

    if shards >= 10:
        shard_tier = "overflow"
        shard_buffer_cash = 5.0
    elif shards >= 7:
        shard_tier = "stable"
        shard_buffer_cash = 3.0
    elif shards >= 5:
        shard_tier = "buffered"
        shard_buffer_cash = 1.5
    else:
        shard_tier = "low"
        shard_buffer_cash = 0.0

    deck_pressure = (
        0.95 * next_negative
        + 1.20 * two_draw_negative
        + 0.70 * cycle_negative
        + 0.08 * max(0.0, remaining_negative - remaining_positive)
    )
    cash_pressure = (
        max(0.0, 8.0 - float(cash)) / 3.0
        + max(0.0, cleanup_cash_gap) / 3.0
        + max(0.0, expected_cleanup_cost - (float(cash) + shard_buffer_cash)) / 5.0
        + max(0.0, money_distress)
    )

    stage_score = 0.0
    if public_cleanup_active and cleanup_cash_gap > shard_buffer_cash:
        stage_score = 3.0
    elif burden_count >= 3.0 and (cash_pressure >= 1.25 or two_draw_negative >= 0.18):
        stage_score = 3.0
    elif burden_count >= 2.0 and (cleanup_cash_gap > 0.0 or cash_pressure >= 0.95 or two_draw_negative >= 0.18):
        stage_score = 2.0
    elif burden_count >= 1.0 and (cash_pressure >= 0.45 or deck_pressure >= 0.35 or expected_cleanup_cost > float(cash) + shard_buffer_cash):
        stage_score = 1.0

    if shard_tier == "overflow" and stage_score > 0.0 and not public_cleanup_active:
        stage_score = max(0.0, stage_score - 1.0)
    elif shard_tier == "stable" and stage_score >= 2.0 and not public_cleanup_active:
        stage_score -= 0.5

    if stage_score >= 3.0:
        cleanup_stage = "meltdown"
    elif stage_score >= 2.0:
        cleanup_stage = "critical"
    elif stage_score >= 1.0:
        cleanup_stage = "strained"
    else:
        cleanup_stage = "stable"

    controller_bias = (
        0.55 * burden_count
        + 0.70 * stage_score
        + 0.35 * max(0.0, 5.0 - float(cash)) / 2.0
        + 0.20 * max(0.0, remaining_negative - remaining_positive)
    )
    lap_cash_preference = (
        0.45 * stage_score
        + 0.30 * max(0.0, 7.0 - float(cash)) / 2.0
        + 0.18 * deck_pressure
    )
    lap_shard_preference = 0.0
    if shards < 5:
        lap_shard_preference += 2.05 + 0.55 * stage_score + 0.22 * burden_count
    elif shards < 7:
        lap_shard_preference += 0.95 + 0.25 * stage_score + 0.12 * burden_count
    elif shards >= 10:
        lap_shard_preference -= 0.55
    elif shards >= 7:
        lap_shard_preference -= 0.15

    growth_locked = bool(
        cleanup_stage in {"critical", "meltdown"}
        or (cleanup_stage == "strained" and shard_tier == "low" and cash_pressure >= 0.95)
    )
    return CleanupStrategyContext(
        burden_count=burden_count,
        shard_tier=shard_tier,
        shard_buffer_cash=shard_buffer_cash,
        cleanup_stage=cleanup_stage,
        stage_score=float(stage_score),
        deck_pressure=float(deck_pressure),
        cash_pressure=float(cash_pressure),
        controller_bias=float(controller_bias),
        lap_cash_preference=float(lap_cash_preference),
        lap_shard_preference=float(lap_shard_preference),
        growth_locked=growth_locked,
    )


def is_action_survivable(*, cash: float, immediate_cost: float = 0.0, post_action_cash: float | None = None, reserve_floor: float, buffer: float = 0.0) -> bool:
    remaining_cash = cash - immediate_cost if post_action_cash is None else post_action_cash
    return float(remaining_cash) >= float(reserve_floor) + float(buffer)


def swindle_operating_reserve(signals: SurvivalSignals) -> float:
    reserve = signals.reserve
    reserve = max(reserve, signals.active_cleanup_cost, 0.65 * signals.latent_cleanup_cost)
    reserve += 2.0 * signals.two_turn_lethal_prob + 1.5 * signals.money_distress + 0.75 * signals.survival_urgency
    return max(0.0, reserve)


def evaluate_swindle_guard(*, cash: float, required_cost: float, signals: SurvivalSignals, is_leader: bool, near_end: bool) -> SwindleGuardDecision:
    if required_cost <= 0.0:
        return SwindleGuardDecision(True, 0.0, cash, "no_cost")
    reserve = swindle_operating_reserve(signals)
    post_cash = float(cash) - float(required_cost)
    common_guard_floor = reserve + 1.0
    if not is_action_survivable(cash=float(cash), immediate_cost=float(required_cost), reserve_floor=common_guard_floor, buffer=2.0):
        return SwindleGuardDecision(False, reserve, post_cash, "global_action_survival_guard")
    if float(required_cost) >= 16.0 and not (is_leader and near_end and post_cash >= reserve + 6.0):
        return SwindleGuardDecision(False, reserve, post_cash, "high_cost_not_leader_finish_window")
    if float(required_cost) >= max(12.0, 0.60 * float(cash)) and (signals.money_distress >= 0.35 or signals.survival_urgency >= 0.35 or signals.two_turn_lethal_prob >= 0.10):
        return SwindleGuardDecision(False, reserve, post_cash, "high_cost_under_distress")
    if (signals.money_distress >= 0.55 or signals.survival_urgency >= 0.55 or signals.two_turn_lethal_prob >= 0.18) and post_cash < reserve + 6.0:
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
        signals.money_distress >= 1.10
        or signals.survival_urgency >= 1.00
        or signals.two_turn_lethal_prob >= 0.18
        or (signals.public_cleanup_active and signals.active_cleanup_cost > max(8.0, signals.reserve + 2.0))
    )
    income_emergency = (
        severe_distress
        or signals.money_distress >= 0.85
        or signals.latent_cleanup_cost >= max(10.0, signals.reserve + 4.0)
    )
    survival_first = severe_distress or cleanup_emergency or signals.survival_urgency >= 0.70
    weight_multiplier = 1.0 + 1.75 * max(0.0, signals.money_distress) + 1.35 * max(0.0, signals.survival_urgency) + 2.25 * max(0.0, signals.two_turn_lethal_prob)
    if cleanup_emergency:
        weight_multiplier += 1.25
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
    if state.severe_distress or signals.two_turn_lethal_prob >= 0.18 or signals.money_distress >= 1.10:
        severity = "critical"
    elif state.cleanup_emergency or signals.survival_urgency >= 0.70 or signals.money_distress >= 0.85:
        severity = "high"
    elif signals.survival_urgency >= 0.40 or signals.money_distress >= 0.45 or signals.latent_cleanup_cost >= max(8.0, signals.reserve + 2.0):
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
