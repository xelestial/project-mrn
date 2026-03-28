from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class BurdenExchangeDecisionInputs:
    remaining_cash: float
    reserve: float
    target_floor: float
    hard_reason: str | None


@dataclass(frozen=True, slots=True)
class GeoBonusDecisionInputs:
    own_burdens: float
    next_neg: float
    two_neg: float
    cleanup_cash_gap: float
    downside_cleanup: float
    cash: float
    cash_score: float
    shard_score: float
    coin_score: float


@dataclass(frozen=True, slots=True)
class EscapeSeekInputs:
    burden_count: float
    cleanup_pressure: float
    rent_pressure: float
    money_distress: float
    two_turn_lethal_prob: float
    cash_after_reserve: float
    front_enemy_density: float
    controller_need: float
    active_drain_pressure: float
    cash: float


@dataclass(frozen=True, slots=True)
class DistressMarkerInputs:
    rescue_pressure: bool
    urgent_denial: bool
    leader_emergency: float
    controller_need: float
    money_distress: float
    future_rescue_live: bool
    marker_counter: float
    near_end: bool
    marker_owner_id: int | None
    player_id: int
    candidate_names: tuple[str, ...]
    marker_names: frozenset[str]
    rescue_names: frozenset[str]
    direct_denial_names: frozenset[str]


def choose_doctrine_relief_player_id(*, self_player_id: int, candidate_ids: Iterable[int]) -> int | None:
    ordered = list(candidate_ids)
    if not ordered:
        return None
    if self_player_id in ordered:
        return self_player_id
    return ordered[0]


def should_exchange_burden_on_supply(inputs: BurdenExchangeDecisionInputs) -> bool:
    if inputs.remaining_cash <= max(5.0, 0.80 * inputs.reserve):
        return False
    if inputs.hard_reason is not None:
        return False
    return inputs.remaining_cash >= inputs.target_floor


def choose_geo_bonus_kind(inputs: GeoBonusDecisionInputs) -> str:
    if inputs.own_burdens >= 2.0 and (
        inputs.next_neg >= 0.10
        or inputs.two_neg >= 0.22
        or inputs.cleanup_cash_gap > 0.0
        or inputs.downside_cleanup >= max(6.0, inputs.cash * 0.45)
    ):
        return "cash"
    if (
        inputs.own_burdens >= 1.0
        and (inputs.next_neg >= 0.10 or inputs.two_neg >= 0.22)
        and inputs.cash_score >= max(inputs.shard_score, inputs.coin_score) - 0.25
    ):
        return "cash"
    ranked = sorted(
        (
            ("cash", inputs.cash_score),
            ("shards", inputs.shard_score),
            ("coins", inputs.coin_score),
        ),
        key=lambda item: (item[1], item[0]),
        reverse=True,
    )
    return ranked[0][0]


def should_seek_escape_package_from_inputs(inputs: EscapeSeekInputs) -> bool:
    if inputs.two_turn_lethal_prob >= 0.18:
        return True
    if inputs.money_distress >= 1.15:
        return True
    if inputs.controller_need >= 0.85 and inputs.active_drain_pressure > 0.0:
        return True
    if inputs.rent_pressure >= 1.9:
        return True
    if inputs.cash <= 8.0 and (inputs.burden_count >= 1.0 or inputs.cash_after_reserve <= 0.0):
        return True
    if inputs.burden_count >= 1.0 and inputs.cleanup_pressure >= 2.5:
        return True
    if inputs.front_enemy_density >= 0.70 and inputs.cash <= 10.0:
        return True
    return inputs.cash_after_reserve <= -2.0


def build_distress_marker_bonus(inputs: DistressMarkerInputs) -> dict[str, float]:
    bonus = {name: 0.0 for name in inputs.candidate_names}
    if not inputs.candidate_names:
        return bonus
    if not inputs.rescue_pressure and not inputs.urgent_denial and inputs.controller_need <= 0.0:
        return bonus

    available_markers = [name for name in inputs.candidate_names if name in inputs.marker_names]
    if not available_markers:
        return bonus

    direct_options_present = any(name in inputs.direct_denial_names for name in inputs.candidate_names)
    base = 0.0
    if inputs.rescue_pressure and not any(name in inputs.rescue_names for name in inputs.candidate_names):
        base = max(base, 2.35 if inputs.future_rescue_live else 1.55)
    if inputs.controller_need > 0.0:
        base = max(base, 1.35 + 0.75 * inputs.controller_need + 0.20 * inputs.money_distress)
    if inputs.urgent_denial:
        base = max(
            base,
            1.55 + 0.30 * inputs.leader_emergency + 0.70 * inputs.marker_counter + (0.30 if inputs.near_end else 0.0),
        )
        if direct_options_present:
            base -= 0.35
        if inputs.marker_counter <= 0.0 and direct_options_present and inputs.controller_need <= 0.0:
            return bonus

    for name in available_markers:
        bonus[name] = max(0.0, base)
        if inputs.marker_owner_id == inputs.player_id:
            bonus[name] += 0.35
    return bonus


def count_burden_cards(cards: Sequence[object]) -> int:
    return sum(1 for card in cards if getattr(card, "is_burden", False))
