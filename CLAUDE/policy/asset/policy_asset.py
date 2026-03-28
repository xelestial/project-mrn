from __future__ import annotations

"""policy/asset/policy_asset — PolicyAsset 조합 자산 (Phase 4 완성).

설계 원칙:
- PolicyAsset: spec + survival + context_builder + character_evaluators 전체 묶음.
- asset_hash()로 재현 식별자를 제공한다.
- PolicyAssetFactory: from_profile / from_json / from_spec 세 가지 생성 경로.
"""

import hashlib
import json as _json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from policy.profile.spec import PolicyProfileSpec
    from policy.survival.strategy import SurvivalStrategy
    from policy.context.builder import TurnContextBuilder
    from policy.character_eval.base import CharacterEvaluator


@dataclass(slots=True)
class PolicyAsset:
    """단일 HeuristicPolicy 인스턴스에 귀속되는 전략 조합 묶음."""

    spec: "PolicyProfileSpec"
    survival: "SurvivalStrategy"
    context_builder: "TurnContextBuilder"
    character_evaluators: dict = field(default_factory=dict)
    """character_name → CharacterEvaluator. 전체 16인물 커버."""

    def asset_hash(self) -> str:
        """spec 내용 기반 8자리 SHA-256 해시. 재현 식별자로 사용."""
        d = {
            "name": self.spec.name,
            "weights": {k: round(v, 6) for k, v in sorted(self.spec.weights.items())},
            "character_values": {k: round(v, 6) for k, v in sorted(self.spec.character_values.items())},
            "survival": self.spec.survival_strategy_key,
        }
        return hashlib.sha256(_json.dumps(d, sort_keys=True).encode()).hexdigest()[:8]


def compute_spec_hash(spec: "PolicyProfileSpec") -> str:
    """PolicyProfileSpec으로부터 asset hash를 계산한다 (PolicyAsset 없이도 호출 가능)."""
    d = {
        "name": spec.name,
        "weights": {k: round(v, 6) for k, v in sorted(spec.weights.items())},
        "character_values": {k: round(v, 6) for k, v in sorted(spec.character_values.items())},
        "survival": spec.survival_strategy_key,
    }
    return hashlib.sha256(_json.dumps(d, sort_keys=True).encode()).hexdigest()[:8]


class PolicyAssetFactory:
    """PolicyAsset 팩토리 — spec / json / profile 세 경로."""

    @staticmethod
    def from_profile(
        spec: "PolicyProfileSpec",
        policy_ref: Any,
    ) -> "PolicyAsset":
        """PolicyProfileSpec + policy_ref → PolicyAsset."""
        from policy.registry.strategy_registry import _STRATEGY_REGISTRY
        from policy.context.builder import TurnContextBuilder
        from policy.character_eval.registry import _REGISTRY as _CHAR_REGISTRY

        survival_key = getattr(spec, "survival_strategy_key", "survival/default_v1")
        survival = _STRATEGY_REGISTRY.resolve_or_default(survival_key)
        builder = TurnContextBuilder(policy_ref)
        return PolicyAsset(
            spec=spec,
            survival=survival,
            context_builder=builder,
            character_evaluators=_CHAR_REGISTRY,
        )

    @staticmethod
    def from_json(path: str, policy_ref: Any) -> "PolicyAsset":
        """policy_profiles/*.json 파일에서 PolicyAsset을 조립한다."""
        with open(path, encoding="utf-8") as f:
            spec_dict = _json.load(f)
        return PolicyAssetFactory.from_spec(spec_dict, policy_ref)

    @staticmethod
    def from_spec(spec_dict: dict, policy_ref: Any) -> "PolicyAsset":
        """dict 명세에서 PolicyAsset을 조립한다.

        spec_dict 형식:
        {
          "name": "heuristic_v3_claude_exp",
          "profile_key": "v3_claude",          # profiles/policy_weights_{key}.json
          "survival_strategy_key": "survival/v3_claude_v1",
          "character_values_key": "default"    # optional, 기본 "default"
        }
        """
        import os
        from policy.profile.spec import PolicyProfileSpec

        profiles_dir = os.path.join(os.path.dirname(__file__), "..", "..", "profiles")

        def _load(filename: str) -> dict:
            with open(os.path.join(profiles_dir, filename), encoding="utf-8") as f:
                return _json.load(f)

        profile_key = spec_dict.get("profile_key", spec_dict.get("name", "balanced"))
        weights = _load(f"policy_weights_{profile_key}.json")
        char_values_key = spec_dict.get("character_values_key", "default")
        character_values = _load(f"character_values_{char_values_key}.json")

        spec = PolicyProfileSpec(
            name=spec_dict["name"],
            weights=weights,
            character_values=character_values,
            survival_strategy_key=spec_dict.get("survival_strategy_key", "survival/default_v1"),
        )
        return PolicyAssetFactory.from_profile(spec, policy_ref)
