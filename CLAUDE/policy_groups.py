from __future__ import annotations

"""Shared policy-level character groups and mark-risk constants.

This module exists to keep ai_policy.py focused on decision flow instead of
scattered static tables. The values are intentionally behavior-preserving.
"""

MARK_ACTOR_NAMES = {"자객", "산적", "추노꾼", "박수", "만신"}
MARK_ACTOR_BASE_RISK = {"자객": 2.6, "산적": 2.0, "추노꾼": 1.8, "박수": 1.2, "만신": 1.0}
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

RENT_ESCAPE_CHARACTERS = {"파발꾼", "탈출 노비", "객주"}
RENT_EXPANSION_CHARACTERS = {"중매꾼", "건설업자", "사기꾼"}
RENT_FRAGILE_DISRUPTORS = {"자객", "산적", "추노꾼"}

GROWTH_LIKE_CHARACTERS = {"객주", "중매꾼", "건설업자", "파발꾼", "사기꾼"}
ECONOMY_LIKE_CHARACTERS = {"탐관오리", "아전", "객주", "중매꾼", "건설업자"}
DISRUPTION_LIKE_CHARACTERS = {"자객", "산적", "추노꾼", "박수", "만신", "어사"}
