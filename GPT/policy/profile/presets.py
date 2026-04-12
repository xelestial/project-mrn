from __future__ import annotations

from characters import CARD_TO_NAMES
from policy.profile.registry import PolicyProfileRegistry
from policy.profile.spec import PolicyProfileSpec


DEFAULT_CHARACTER_VALUES = {
    CARD_TO_NAMES[1][0]: 6.0,
    CARD_TO_NAMES[1][1]: 7.5,
    CARD_TO_NAMES[2][0]: 7.2,
    CARD_TO_NAMES[2][1]: 7.0,
    CARD_TO_NAMES[3][0]: 6.8,
    CARD_TO_NAMES[3][1]: 6.2,
    CARD_TO_NAMES[4][0]: 7.9,
    CARD_TO_NAMES[4][1]: 7.0,
    CARD_TO_NAMES[5][0]: 6.4,
    CARD_TO_NAMES[5][1]: 6.4,
    CARD_TO_NAMES[6][0]: 7.2,
    CARD_TO_NAMES[6][1]: 6.9,
    CARD_TO_NAMES[7][0]: 7.6,
    CARD_TO_NAMES[7][1]: 7.4,
    CARD_TO_NAMES[8][0]: 7.8,
    CARD_TO_NAMES[8][1]: 7.7,
}


def _profile_spec(key: str, weights: dict[str, float], *, canonical_mode: str, aliases: tuple[str, ...] = ()) -> PolicyProfileSpec:
    return PolicyProfileSpec(
        key=key,
        canonical_mode=canonical_mode,
        aliases=aliases,
        weights=weights,
        character_values=DEFAULT_CHARACTER_VALUES,
    )


DEFAULT_PROFILE_REGISTRY = PolicyProfileRegistry(
    [
        _profile_spec(
            "control",
            {"expansion": 1.0, "economy": 1.1, "disruption": 1.7, "meta": 1.6, "combo": 1.0, "survival": 1.4},
            canonical_mode="heuristic_v2_control",
        ),
        _profile_spec(
            "growth",
            {"expansion": 1.8, "economy": 1.7, "disruption": 0.7, "meta": 0.9, "combo": 1.2, "survival": 1.0},
            canonical_mode="heuristic_v2_growth",
        ),
        _profile_spec(
            "balanced",
            {"expansion": 1.2, "economy": 1.2, "disruption": 1.2, "meta": 1.1, "combo": 1.1, "survival": 1.1},
            canonical_mode="heuristic_v2_balanced",
        ),
        _profile_spec(
            "avoid_control",
            {"expansion": 1.0, "economy": 1.4, "disruption": 0.7, "meta": 1.0, "combo": 1.0, "survival": 1.8},
            canonical_mode="heuristic_v2_avoid_control",
        ),
        _profile_spec(
            "aggressive",
            {"expansion": 2.0, "economy": 1.0, "disruption": 1.3, "meta": 0.8, "combo": 1.5, "survival": 0.6},
            canonical_mode="heuristic_v2_aggressive",
        ),
        _profile_spec(
            "token_opt",
            {"expansion": 1.5, "economy": 1.4, "disruption": 1.0, "meta": 1.0, "combo": 1.9, "survival": 0.9},
            canonical_mode="heuristic_v2_token_opt",
        ),
        _profile_spec(
            "v3_gpt",
            {"expansion": 1.68, "economy": 1.55, "disruption": 1.28, "meta": 1.18, "combo": 2.15, "survival": 1.18},
            canonical_mode="heuristic_v3_gpt",
            aliases=("heuristic_v2_v3_gpt",),
        ),
    ]
)
