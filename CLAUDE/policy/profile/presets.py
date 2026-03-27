from __future__ import annotations

"""ProfilePresets — profiles/*.json에서 기본 프리셋을 로드해 registry에 등록.

사용법:
    registry = build_default_registry()
    spec = registry.resolve("v3_claude")
"""

import json
import os
from .spec import PolicyProfileSpec
from .registry import ProfileRegistry

_PROFILES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "profiles")


def _load_json(filename: str) -> dict:
    path = os.path.join(_PROFILES_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_weights(profile_key: str) -> dict[str, float]:
    return _load_json(f"policy_weights_{profile_key}.json")


def _load_character_values(key: str = "default") -> dict[str, float]:
    return _load_json(f"character_values_{key}.json")


def build_default_registry() -> ProfileRegistry:
    """기본 프리셋 전체를 로드해 반환하는 ProfileRegistry."""
    registry = ProfileRegistry()
    char_values = _load_character_values("default")

    _PRESETS: list[tuple[str, tuple[str, ...], str, str]] = [
        # (canonical_name, aliases, weights_key, survival_key)
        (
            "heuristic_v3_claude_exp",
            ("v3_claude", "heuristic_v2_v3_claude"),
            "v3_claude",
            "survival/v3_claude_v1",
        ),
        (
            "heuristic_v2_balanced",
            ("balanced",),
            "balanced",
            "survival/default_v1",
        ),
        (
            "heuristic_v2_control",
            ("control",),
            "control",
            "survival/default_v1",
        ),
        (
            "heuristic_v2_token_opt",
            ("token_opt",),
            "token_opt",
            "survival/default_v1",
        ),
        (
            "heuristic_v2_growth",
            ("growth",),
            "growth",
            "survival/default_v1",
        ),
        (
            "heuristic_v2_avoid_control",
            ("avoid_control",),
            "avoid_control",
            "survival/default_v1",
        ),
        (
            "heuristic_v2_aggressive",
            ("aggressive",),
            "aggressive",
            "survival/default_v1",
        ),
    ]

    for canonical, aliases, weights_key, survival_key in _PRESETS:
        spec = PolicyProfileSpec(
            name=canonical,
            aliases=aliases,
            weights=_load_weights(weights_key),
            character_values=char_values,
            survival_strategy_key=survival_key,
        )
        registry.register(spec)

    return registry


# 싱글턴 — 모듈 임포트 시 한 번만 로드
_DEFAULT_REGISTRY: ProfileRegistry | None = None


def get_default_registry() -> ProfileRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = build_default_registry()
    return _DEFAULT_REGISTRY
