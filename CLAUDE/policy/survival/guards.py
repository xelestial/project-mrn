from __future__ import annotations

"""policy/survival/guards — ActionGuard, SwindleGuard, is_action_survivable."""

from dataclasses import dataclass

from .thresholds import _T
from .signals import SurvivalSignals


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


def is_action_survivable(
    *,
    cash: float,
    immediate_cost: float = 0.0,
    post_action_cash: float | None = None,
    reserve_floor: float,
    buffer: float = 0.0,
) -> bool:
    remaining_cash = cash - immediate_cost if post_action_cash is None else post_action_cash
    return float(remaining_cash) >= float(reserve_floor) + float(buffer)


def swindle_operating_reserve(signals: SurvivalSignals) -> float:
    reserve = signals.reserve
    reserve = max(reserve, signals.active_cleanup_cost, _T.swindle_latent_multiplier * signals.latent_cleanup_cost)
    reserve += (
        _T.swindle_lethal_weight * signals.two_turn_lethal_prob
        + _T.swindle_distress_weight * signals.money_distress
        + _T.swindle_urgency_weight * signals.survival_urgency
    )
    return max(0.0, reserve)


def evaluate_swindle_guard(
    *,
    cash: float,
    required_cost: float,
    signals: SurvivalSignals,
    is_leader: bool,
    near_end: bool,
) -> SwindleGuardDecision:
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
