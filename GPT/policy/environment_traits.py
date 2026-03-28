from __future__ import annotations

from typing import Any, Iterable

from policy.character_traits import (
    is_ajeon,
    is_assassin,
    is_bandit,
    is_baksu,
    is_card_face,
    is_gakju,
    is_mansin,
    is_pabalggun,
    is_tamgwanori,
)
from weather_cards import COLOR_RENT_DOUBLE_WEATHERS

CLEANUP_THREAT_WEATHERS = {"긴급 피난"}
FORTUNE_CLEANUP_CARD_MULTIPLIERS = {"화재 발생": 1.0, "산불 발생": 2.0}
FORTUNE_POSITIVE_CLEANUP_CARD_MULTIPLIERS = {"자원 순환": -1.0, "모두의 순환": -1.0}
WEATHER_SHARD_BONUS_WEATHERS = {"풍년든 가을", "기우제", "성물의 날"}
WEATHER_TRICK_BONUS_WEATHERS = {"잔꾀 부리기"}

FORTUNE_FIRE_CARD = "화재 발생"
FORTUNE_WILDFIRE_CARD = "산불 발생"
FORTUNE_RECYCLE_CARD = "자원 순환"
FORTUNE_PUBLIC_RECYCLE_CARD = "모두의 순환"


def is_cleanup_threat_weather(name: str) -> bool:
    return name in CLEANUP_THREAT_WEATHERS


def weather_character_adjustment(active_weathers: Iterable[str], character_name: str) -> tuple[float, list[str]]:
    active = set(active_weathers or ())
    if not active:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    if active & WEATHER_SHARD_BONUS_WEATHERS:
        if (
            is_bandit(character_name)
            or is_tamgwanori(character_name)
            or is_ajeon(character_name)
            or is_baksu(character_name)
            or is_mansin(character_name)
        ):
            score += 0.6
            reasons.append("weather_shard_synergy")
        if is_card_face(character_name, 7, 1):
            score += 0.35
            reasons.append("weather_shard_expansion")
    if active & WEATHER_TRICK_BONUS_WEATHERS:
        if (
            is_pabalggun(character_name)
            or is_gakju(character_name)
            or is_baksu(character_name)
            or is_mansin(character_name)
            or is_assassin(character_name)
        ):
            score += 0.55
            reasons.append("weather_trick_synergy")
        if is_card_face(character_name, 7, 1) or is_card_face(character_name, 8, 0):
            score += 0.25
            reasons.append("weather_trick_setup")
    return score, reasons


def count_cleanup_fortunes(cards: list[Any]) -> tuple[int, int, int, int]:
    fire = wildfire = recycle = public_recycle = 0
    for card in cards:
        name = getattr(card, "name", "")
        if name == FORTUNE_FIRE_CARD:
            fire += 1
        elif name == FORTUNE_WILDFIRE_CARD:
            wildfire += 1
        elif name == FORTUNE_RECYCLE_CARD:
            recycle += 1
        elif name == FORTUNE_PUBLIC_RECYCLE_CARD:
            public_recycle += 1
    return fire, wildfire, recycle, public_recycle


def has_color_rent_double_weather(active_weathers: Iterable[str], tile_color: str | None) -> bool:
    if tile_color is None:
        return False
    return any(COLOR_RENT_DOUBLE_WEATHERS.get(name) == tile_color for name in active_weathers)


def fortune_cleanup_deck_profile(draw_pile: list[Any], discard_pile: list[Any]) -> dict[str, float]:
    negative_cards = dict(FORTUNE_CLEANUP_CARD_MULTIPLIERS)
    positive_cards = dict(FORTUNE_POSITIVE_CLEANUP_CARD_MULTIPLIERS)
    cleanup_cards = {**negative_cards, **positive_cards}

    def _at_least_one_prob(total_cards: int, success_cards: int, draws: int) -> float:
        if total_cards <= 0 or success_cards <= 0 or draws <= 0:
            return 0.0
        draws = min(draws, total_cards)
        failures = total_cards - success_cards
        if draws > failures:
            return 1.0
        try:
            import math

            no_success = math.comb(failures, draws) / math.comb(total_cards, draws)
        except ValueError:
            return 0.0
        return max(0.0, min(1.0, 1.0 - no_success))

    def _expected_multiplier(cards: list[Any]) -> float:
        if not cards:
            return 0.0
        total = 0.0
        for card in cards:
            total += cleanup_cards.get(getattr(card, "name", ""), 0.0)
        return total / len(cards)

    def _expected_negative_multiplier(cards: list[Any]) -> float:
        if not cards:
            return 0.0
        total = 0.0
        for card in cards:
            total += max(0.0, cleanup_cards.get(getattr(card, "name", ""), 0.0))
        return total / len(cards)

    source = draw_pile if draw_pile else discard_pile
    remaining_draws = len(source)
    fire_count, wildfire_count, recycle_count, public_recycle_count = count_cleanup_fortunes(source)
    negative_cleanup_cards = fire_count + wildfire_count
    positive_cleanup_cards = recycle_count + public_recycle_count
    all_cleanup_cards = negative_cleanup_cards + positive_cleanup_cards

    total_cycle_cards = len(draw_pile) + len(discard_pile)
    cycle_fire_count, cycle_wildfire_count, cycle_recycle_count, cycle_public_recycle_count = count_cleanup_fortunes(draw_pile + discard_pile)
    total_negative_cleanup_cards = cycle_fire_count + cycle_wildfire_count
    total_positive_cleanup_cards = cycle_recycle_count + cycle_public_recycle_count
    total_cleanup_cards = total_negative_cleanup_cards + total_positive_cleanup_cards

    next_draw_cleanup_prob = (all_cleanup_cards / remaining_draws) if remaining_draws > 0 else 0.0
    next_draw_negative_cleanup_prob = (negative_cleanup_cards / remaining_draws) if remaining_draws > 0 else 0.0
    next_draw_positive_cleanup_prob = (positive_cleanup_cards / remaining_draws) if remaining_draws > 0 else 0.0
    two_draw_cleanup_prob = _at_least_one_prob(remaining_draws, all_cleanup_cards, 2)
    two_draw_negative_cleanup_prob = _at_least_one_prob(remaining_draws, negative_cleanup_cards, 2)
    two_draw_positive_cleanup_prob = _at_least_one_prob(remaining_draws, positive_cleanup_cards, 2)
    three_draw_cleanup_prob = _at_least_one_prob(remaining_draws, all_cleanup_cards, 3)
    cycle_cleanup_prob = (total_cleanup_cards / total_cycle_cards) if total_cycle_cards > 0 else 0.0
    cycle_negative_cleanup_prob = (total_negative_cleanup_cards / total_cycle_cards) if total_cycle_cards > 0 else 0.0
    cycle_positive_cleanup_prob = (total_positive_cleanup_cards / total_cycle_cards) if total_cycle_cards > 0 else 0.0

    conditional_multiplier = (
        (((1.0 * cycle_fire_count) + (2.0 * cycle_wildfire_count) + (-1.0 * cycle_recycle_count) + (-1.0 * cycle_public_recycle_count)) / total_cleanup_cards)
        if total_cleanup_cards > 0 else 0.0
    )
    conditional_negative_multiplier = (
        (((1.0 * cycle_fire_count) + (2.0 * cycle_wildfire_count)) / total_negative_cleanup_cards)
        if total_negative_cleanup_cards > 0 else 0.0
    )
    next_draw_expected_factor = _expected_multiplier(source)
    next_draw_negative_expected_factor = _expected_negative_multiplier(source)
    persistent_expected_factor = cycle_cleanup_prob * conditional_multiplier
    persistent_negative_expected_factor = cycle_negative_cleanup_prob * conditional_negative_multiplier
    two_draw_expected_factor = two_draw_cleanup_prob * conditional_multiplier
    two_draw_negative_expected_factor = two_draw_negative_cleanup_prob * conditional_negative_multiplier
    three_draw_expected_factor = three_draw_cleanup_prob * conditional_multiplier
    worst_multiplier = 2.0 if cycle_wildfire_count > 0 else 1.0 if cycle_fire_count > 0 else 0.0
    return {
        "remaining_draws": float(remaining_draws),
        "remaining_fire_count": float(fire_count),
        "remaining_wildfire_count": float(wildfire_count),
        "remaining_recycle_count": float(recycle_count),
        "remaining_public_recycle_count": float(public_recycle_count),
        "remaining_cleanup_cards": float(all_cleanup_cards),
        "remaining_negative_cleanup_cards": float(negative_cleanup_cards),
        "remaining_positive_cleanup_cards": float(positive_cleanup_cards),
        "next_draw_cleanup_prob": float(next_draw_cleanup_prob),
        "next_draw_negative_cleanup_prob": float(next_draw_negative_cleanup_prob),
        "next_draw_positive_cleanup_prob": float(next_draw_positive_cleanup_prob),
        "two_draw_cleanup_prob": float(two_draw_cleanup_prob),
        "two_draw_negative_cleanup_prob": float(two_draw_negative_cleanup_prob),
        "two_draw_positive_cleanup_prob": float(two_draw_positive_cleanup_prob),
        "three_draw_cleanup_prob": float(three_draw_cleanup_prob),
        "cycle_cleanup_prob": float(cycle_cleanup_prob),
        "cycle_negative_cleanup_prob": float(cycle_negative_cleanup_prob),
        "cycle_positive_cleanup_prob": float(cycle_positive_cleanup_prob),
        "conditional_cleanup_multiplier": float(conditional_multiplier),
        "conditional_negative_cleanup_multiplier": float(conditional_negative_multiplier),
        "expected_cleanup_multiplier": float(next_draw_expected_factor),
        "expected_negative_cleanup_multiplier": float(next_draw_negative_expected_factor),
        "persistent_expected_cleanup_multiplier": float(persistent_expected_factor),
        "persistent_negative_expected_cleanup_multiplier": float(persistent_negative_expected_factor),
        "persistent_negative_cleanup_multiplier": float(persistent_negative_expected_factor),
        "two_draw_expected_cleanup_multiplier": float(two_draw_expected_factor),
        "two_draw_negative_expected_cleanup_multiplier": float(two_draw_negative_expected_factor),
        "three_draw_expected_cleanup_multiplier": float(three_draw_expected_factor),
        "worst_cleanup_multiplier": float(worst_multiplier),
        "reshuffle_imminent": 1.0 if (not draw_pile and bool(discard_pile)) else 0.0,
    }
