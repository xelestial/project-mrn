from __future__ import annotations

"""Shared policy-level character groups and mark-risk constants.

This module exists to keep ai_policy.py focused on decision flow instead of
scattered static tables. The values are intentionally behavior-preserving.
"""

from characters import CARD_TO_NAMES

MARK_ACTOR_NAMES = {
    CARD_TO_NAMES[2][0],
    CARD_TO_NAMES[2][1],
    CARD_TO_NAMES[3][0],
    CARD_TO_NAMES[6][0],
    CARD_TO_NAMES[6][1],
}
MARK_ACTOR_BASE_RISK = {
    CARD_TO_NAMES[2][0]: 2.6,
    CARD_TO_NAMES[2][1]: 2.0,
    CARD_TO_NAMES[3][0]: 1.8,
    CARD_TO_NAMES[6][0]: 1.2,
    CARD_TO_NAMES[6][1]: 1.0,
}
MARK_PRIORITY_SAME_FACTOR = 0.35
MARK_GUESS_TEMPERATURE = 1.8
MARK_GUESS_UNIFORM_MIX_BASE = 0.30
MARK_GUESS_UNIFORM_MIX_AMBIGUITY = 0.45
MARK_GUESS_UNIFORM_MIX_EXTRA_CANDIDATE = 0.04
MARK_GUESS_CONFIDENCE_THRESHOLDS = {
    "balanced": 0.42,
    "control": 0.44,
    "growth": 0.40,
    "avoid_control": 0.48,
    "aggressive": 0.34,
    "token_opt": 0.46,
}
MARK_GUESS_MARGIN_THRESHOLDS = {
    "balanced": 0.08,
    "control": 0.09,
    "growth": 0.08,
    "avoid_control": 0.10,
    "aggressive": 0.05,
    "token_opt": 0.09,
}

RENT_ESCAPE_CHARACTERS = {CARD_TO_NAMES[4][0], CARD_TO_NAMES[3][1], CARD_TO_NAMES[7][0]}
RENT_EXPANSION_CHARACTERS = {CARD_TO_NAMES[7][1], CARD_TO_NAMES[8][0], CARD_TO_NAMES[8][1]}
RENT_FRAGILE_DISRUPTORS = {CARD_TO_NAMES[2][0], CARD_TO_NAMES[2][1], CARD_TO_NAMES[3][0]}

GROWTH_LIKE_CHARACTERS = {CARD_TO_NAMES[7][0], CARD_TO_NAMES[7][1], CARD_TO_NAMES[8][0], CARD_TO_NAMES[4][0], CARD_TO_NAMES[8][1]}
ECONOMY_LIKE_CHARACTERS = {CARD_TO_NAMES[1][1], CARD_TO_NAMES[4][1], CARD_TO_NAMES[7][0], CARD_TO_NAMES[7][1], CARD_TO_NAMES[8][0]}
DISRUPTION_LIKE_CHARACTERS = {CARD_TO_NAMES[2][0], CARD_TO_NAMES[2][1], CARD_TO_NAMES[3][0], CARD_TO_NAMES[6][0], CARD_TO_NAMES[6][1], CARD_TO_NAMES[1][0]}
