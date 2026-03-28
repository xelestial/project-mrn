from __future__ import annotations

"""policy/registry/strategy_registry — SurvivalStrategy 레지스트리.

설계 원칙:
- StrategyRegistry: key → SurvivalStrategy 인스턴스 맵.
- 모듈 수준 싱글톤 _STRATEGY_REGISTRY에 기본 전략 등록.
- Phase 3에서 프로파일별 전략 분리 시 이 레지스트리에서 resolve.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from policy.survival.strategy import SurvivalStrategy


class StrategyRegistry:
    """전략 인스턴스 레지스트리."""

    def __init__(self) -> None:
        self._map: dict[str, "SurvivalStrategy"] = {}

    def register(self, key: str, instance: "SurvivalStrategy") -> None:
        self._map[key] = instance

    def resolve(self, key: str) -> "SurvivalStrategy":
        if key not in self._map:
            raise KeyError(f"StrategyRegistry: unknown key {key!r}")
        return self._map[key]

    def resolve_or_default(self, key: str, default_key: str = "survival/default_v1") -> "SurvivalStrategy":
        return self._map.get(key, self._map[default_key])


def _build_default_registry() -> StrategyRegistry:
    from policy.survival.strategy import DefaultSurvivalStrategy, V3ClaudeSurvivalStrategy

    reg = StrategyRegistry()
    reg.register("survival/default_v1", DefaultSurvivalStrategy())
    reg.register("survival/v3_claude_v1", V3ClaudeSurvivalStrategy())
    return reg


_STRATEGY_REGISTRY: StrategyRegistry = _build_default_registry()
