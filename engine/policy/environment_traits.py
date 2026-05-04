from __future__ import annotations

import csv
from typing import Any, Iterable
from functools import lru_cache
from pathlib import Path

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

from weather_cards import load_weather_definitions

LEGACY_FORTUNE_NAME_ALIASES = {
    "자원 순환": "자원 재활용",
    "모두의 순환": "모두의 재활용",
}

WEATHER_HUNTING_SEASON_ID = 1
WEATHER_COLD_WINTER_DAY_ID = 2
WEATHER_HARVEST_AUTUMN_ID = 3
WEATHER_FATTENED_HORSES_ID = 4
WEATHER_FOREIGN_INVASION_ID = 5
WEATHER_LEAD_BY_EXAMPLE_ID = 6
WEATHER_RAINMAKING_ID = 7
WEATHER_LOVE_AND_FRIENDSHIP_ID = 8
WEATHER_RELIEF_SYMBOL_ID = 9
WEATHER_HOLY_RELIC_DAY_ID = 10
WEATHER_BETRAYAL_MARKER_ID = 11
WEATHER_TRICKSTER_DAY_ID = 12
WEATHER_STRATEGY_SHIFT_ID = 13
WEATHER_ALL_TO_RESOURCES_ID = 14
WEATHER_EMERGENCY_EVACUATION_ID = 15
WEATHER_MASS_UPRISING_ID = 16
WEATHER_FORTUNE_LUCKY_DAY_ID = 17
WEATHER_BRIGHT_NIGHT_ID = 24
WEATHER_LONG_WINTER_ID = 25
WEATHER_CLEAR_WARM_DAY_ID = 26

FORTUNE_MOVE_BACK_2_ID = 1
FORTUNE_MOVE_BACK_3_ID = 2
FORTUNE_TAKEOVER_BACK_2_ID = 3
FORTUNE_TAKEOVER_BACK_3_ID = 4
FORTUNE_PERFORMANCE_BONUS_ID = 5
FORTUNE_HIGH_PERFORMANCE_BONUS_ID = 6
FORTUNE_TRAFFIC_VIOLATION_ID = 7
FORTUNE_DRUNK_RIDING_ID = 8
FORTUNE_SUBSCRIPTION_WIN_ID = 9
FORTUNE_POOR_CONSTRUCTION_ID = 10
FORTUNE_LAND_THIEF_ID = 11
FORTUNE_DONATION_ANGEL_ID = 12
FORTUNE_PARTY_ID = 13
FORTUNE_SUSPICIOUS_DRINK_ID = 14
FORTUNE_VERY_SUSPICIOUS_DRINK_ID = 15
FORTUNE_HALF_PRICE_SALE_ID = 16
FORTUNE_BLESSED_DICE_ID = 17
FORTUNE_CURSED_DICE_ID = 18
FORTUNE_GOOD_FOR_OTHERS_ID = 19
FORTUNE_BITTER_ENVY_ID = 20
FORTUNE_UNBEARABLE_SMILE_ID = 21
FORTUNE_IRRESISTIBLE_DEAL_ID = 22
FORTUNE_PIOUS_MARKER_ID = 23
FORTUNE_BEAST_HEART_ID = 24
FORTUNE_SHORT_TRIP_ID = 25
FORTUNE_CUT_IN_LINE_ID = 26
FORTUNE_LONG_TRIP_ID = 27
FORTUNE_REST_STOP_ID = 28
FORTUNE_SAFE_MOVE_ID = 29
FORTUNE_RECYCLE_RESOURCES_ID = 30
FORTUNE_RECYCLE_RESOURCES_ALL_ID = 31
FORTUNE_FIRE_OUTBREAK_ID = 32
FORTUNE_WILDFIRE_OUTBREAK_ID = 33
FORTUNE_METEOR_FALL_ID = 34
FORTUNE_PIG_DREAM_ID = 35


def _fortune_csv_path() -> Path:
    return Path(__file__).resolve().parents[1] / "fortune.csv"


@lru_cache(maxsize=1)
def _weather_ids_by_name() -> dict[str, int]:
    return {card.name: index for index, card in enumerate(load_weather_definitions(), start=1)}


@lru_cache(maxsize=1)
def _fortune_ids_by_name() -> dict[str, int]:
    with _fortune_csv_path().open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        mapping: dict[str, int] = {}
        card_id = 1
        for row in reader:
            raw_name = " ".join((row.get("이름") or "").split())
            raw_effect = (row.get("효과") or "").strip()
            raw_copies = (row.get("카드 장수") or "").strip()
            if not raw_name or not raw_effect or not raw_copies:
                continue
            mapping[raw_name] = card_id
            card_id += 1
        return mapping


def weather_id_for_name(name: str | None) -> int | None:
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    if not normalized:
        return None
    return _weather_ids_by_name().get(normalized)


def fortune_card_id_for_name(name: str | None) -> int | None:
    if not isinstance(name, str):
        return None
    normalized = name.strip()
    if not normalized:
        return None
    normalized = LEGACY_FORTUNE_NAME_ALIASES.get(normalized, normalized)
    return _fortune_ids_by_name().get(normalized)


CLEANUP_THREAT_WEATHER_IDS = {15}
FORTUNE_CLEANUP_CARD_MULTIPLIERS = {32: 1.0, 33: 2.0}
FORTUNE_POSITIVE_CLEANUP_CARD_MULTIPLIERS = {30: -1.0, 31: -1.0}
WEATHER_SHARD_BONUS_WEATHER_IDS = {3, 7, 10}
WEATHER_TRICK_BONUS_WEATHER_IDS = {12}


def is_cleanup_threat_weather(name: str) -> bool:
    return weather_id_for_name(name) in CLEANUP_THREAT_WEATHER_IDS


def _weather_id_set(active_weathers: Iterable[str]) -> set[int]:
    result: set[int] = set()
    for name in active_weathers or ():
        weather_id = weather_id_for_name(name)
        if weather_id is not None:
            result.add(weather_id)
    return result


def has_weather_id(active_weathers: Iterable[str], weather_id: int) -> bool:
    return weather_id in _weather_id_set(active_weathers)


def weather_character_adjustment(active_weathers: Iterable[str], character_name: str) -> tuple[float, list[str]]:
    active = _weather_id_set(active_weathers)
    if not active:
        return 0.0, []

    score = 0.0
    reasons: list[str] = []
    if active & WEATHER_SHARD_BONUS_WEATHER_IDS:
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
    if active & WEATHER_TRICK_BONUS_WEATHER_IDS:
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
        card_id = fortune_card_id_for_name(getattr(card, "name", ""))
        if card_id == 32:
            fire += 1
        elif card_id == 33:
            wildfire += 1
        elif card_id == 30:
            recycle += 1
        elif card_id == 31:
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
            total += cleanup_cards.get(fortune_card_id_for_name(getattr(card, "name", "")), 0.0)
        return total / len(cards)

    def _expected_negative_multiplier(cards: list[Any]) -> float:
        if not cards:
            return 0.0
        total = 0.0
        for card in cards:
            total += max(0.0, cleanup_cards.get(fortune_card_id_for_name(getattr(card, "name", "")), 0.0))
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
