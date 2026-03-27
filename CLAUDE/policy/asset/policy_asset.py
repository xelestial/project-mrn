from __future__ import annotations

"""policy/asset/policy_asset — PolicyAsset 브리지 (Phase 2 scaffold).

설계 원칙:
- PolicyAsset: spec + survival 전략 + context_builder를 한 묶음으로 보유.
- Phase 2: TurnContextBuilder를 policy_ref 약참조로 초기화.
- Phase 3: context_builder를 독립 feature 모듈로 분리.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from policy.profile.spec import PolicyProfileSpec
    from policy.survival.strategy import SurvivalStrategy
    from policy.context.builder import TurnContextBuilder


@dataclass(slots=True)
class PolicyAsset:
    """단일 HeuristicPolicy 인스턴스에 귀속되는 전략 묶음."""

    spec: "PolicyProfileSpec"
    survival: "SurvivalStrategy"
    context_builder: "TurnContextBuilder"


class PolicyAssetFactory:
    """PolicyAsset 팩토리."""

    @staticmethod
    def from_profile(
        spec: "PolicyProfileSpec",
        policy_ref: Any,
    ) -> "PolicyAsset":
        """spec + policy_ref → PolicyAsset."""
        from policy.registry.strategy_registry import _STRATEGY_REGISTRY
        from policy.context.builder import TurnContextBuilder

        survival_key = getattr(spec, "survival_strategy_key", "survival/default_v1")
        survival = _STRATEGY_REGISTRY.resolve_or_default(survival_key)
        builder = TurnContextBuilder(policy_ref)
        return PolicyAsset(spec=spec, survival=survival, context_builder=builder)
