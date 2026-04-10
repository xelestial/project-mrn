from __future__ import annotations

import math
from typing import Optional

from characters import CARD_TO_NAMES, CHARACTERS
from policy_groups import (
    DISRUPTION_LIKE_CHARACTERS,
    ECONOMY_LIKE_CHARACTERS,
    GROWTH_LIKE_CHARACTERS,
    MARK_GUESS_CONFIDENCE_THRESHOLDS,
    MARK_GUESS_MARGIN_THRESHOLDS,
    MARK_GUESS_TEMPERATURE,
    MARK_GUESS_UNIFORM_MIX_AMBIGUITY,
    MARK_GUESS_UNIFORM_MIX_BASE,
    MARK_GUESS_UNIFORM_MIX_EXTRA_CANDIDATE,
    MARK_PRIORITY_SAME_FACTOR,
)
from state import GameState, PlayerState


def _card_no_for_character(character_name: str | None) -> int | None:
    if not character_name:
        return None
    char_def = CHARACTERS.get(character_name)
    if char_def is None:
        return None
    return int(char_def.card_no)


def _holder_for_card_no(state: GameState, card_no: int) -> PlayerState | None:
    for other in state.players:
        if not other.alive or not other.current_character:
            continue
        if _card_no_for_character(other.current_character) == card_no:
            return other
    return None


def _public_character_for_card_no(state: GameState, card_no: int) -> str | None:
    active_by_card = getattr(state, "active_by_card", {}) or {}
    if isinstance(active_by_card, dict):
        public_name = active_by_card.get(card_no)
        if isinstance(public_name, str) and public_name:
            return public_name

    holder = _holder_for_card_no(state, card_no)
    if holder is not None and holder.current_character:
        return str(holder.current_character)

    pair = CARD_TO_NAMES.get(card_no)
    if pair:
        return str(pair[0])
    return None


def ordered_public_mark_targets(state: GameState, player: PlayerState) -> list[dict[str, int | str]]:
    """Return future priority-card public mark guesses in card order."""

    actor_card_no = _card_no_for_character(getattr(player, "current_character", None))
    if actor_card_no is None:
        return []

    ordered_targets: list[dict[str, int | str]] = []
    seen_characters: set[str] = set()
    max_card_no = max(CARD_TO_NAMES)
    for card_no in range(actor_card_no + 1, max_card_no + 1):
        holder = _holder_for_card_no(state, card_no)
        if holder is not None and getattr(holder, "revealed_this_round", False):
            continue
        public_character = _public_character_for_card_no(state, card_no)
        if not public_character or public_character in seen_characters:
            continue
        ordered_targets.append({"card_no": card_no, "target_character": public_character})
        seen_characters.add(public_character)
    return ordered_targets


def public_mark_guess_candidates(state: GameState, player: PlayerState) -> list[str]:
    """Return publicly plausible character guesses without peeking hidden assignments."""
    return [str(target["target_character"]) for target in ordered_public_mark_targets(state, player)]


def mark_guess_policy_params(profile: str, character_policy_mode: str) -> tuple[float, float]:
    confidence = MARK_GUESS_CONFIDENCE_THRESHOLDS.get(profile, 0.42)
    margin = MARK_GUESS_MARGIN_THRESHOLDS.get(profile, 0.08)
    if character_policy_mode == "heuristic_v1":
        return 0.40, 0.08
    return confidence, margin


def mark_guess_distribution(candidate_scores: dict[str, float], legal_target_count: int) -> tuple[dict[str, float], dict[str, float]]:
    if not candidate_scores:
        return {}, {"uniform_mix": 0.0, "ambiguity": 0.0, "top_probability": 0.0, "second_probability": 0.0}
    candidates = list(candidate_scores.keys())
    raw_scores = [candidate_scores[name] for name in candidates]
    max_score = max(raw_scores)
    soft_weights = [math.exp((score - max_score) / MARK_GUESS_TEMPERATURE) for score in raw_scores]
    soft_total = sum(soft_weights) or 1.0
    soft_probs = {name: weight / soft_total for name, weight in zip(candidates, soft_weights)}
    candidate_count = len(candidates)
    ambiguity = max(0.0, 1.0 - (legal_target_count / max(1, candidate_count)))
    extra_candidates = max(0, candidate_count - max(legal_target_count, 1) - 1)
    uniform_mix = min(
        0.80,
        MARK_GUESS_UNIFORM_MIX_BASE
        + MARK_GUESS_UNIFORM_MIX_AMBIGUITY * ambiguity
        + MARK_GUESS_UNIFORM_MIX_EXTRA_CANDIDATE * extra_candidates,
    )
    uniform_prob = 1.0 / candidate_count
    mixed_probs = {name: (1.0 - uniform_mix) * soft_probs[name] + uniform_mix * uniform_prob for name in candidates}
    ordered = sorted(mixed_probs.values(), reverse=True)
    details = {
        "uniform_mix": uniform_mix,
        "ambiguity": ambiguity,
        "top_probability": ordered[0],
        "second_probability": ordered[1] if len(ordered) > 1 else 0.0,
    }
    return mixed_probs, details


def mark_priority_exposure_factor(actor_name: str, target_name: str) -> float:
    actor_priority = CHARACTERS[actor_name].priority
    target_priority = CHARACTERS[target_name].priority
    if actor_priority < target_priority:
        return 1.0
    if actor_priority == target_priority:
        return MARK_PRIORITY_SAME_FACTOR
    return 0.0


def mark_target_profile_factor(actor_name: str, target_name: str) -> float:
    target_attr = CHARACTERS[target_name].attribute
    if actor_name == "자객":
        if target_attr == "무뢰":
            return 1.35
        if target_name in GROWTH_LIKE_CHARACTERS:
            return 1.15
        return 0.7
    if actor_name == "산적":
        if target_name in ECONOMY_LIKE_CHARACTERS:
            return 1.2
        if target_name in GROWTH_LIKE_CHARACTERS:
            return 0.95
        return 0.65
    if actor_name == "추노꾼":
        if target_name in GROWTH_LIKE_CHARACTERS or target_name in ECONOMY_LIKE_CHARACTERS:
            return 1.0
        return 0.7
    if actor_name == "박수":
        if target_name in GROWTH_LIKE_CHARACTERS:
            return 0.95
        return 0.6
    if actor_name == "만신":
        if target_name in DISRUPTION_LIKE_CHARACTERS or target_name == "중매꾼":
            return 0.9
        return 0.55
    return 0.0
