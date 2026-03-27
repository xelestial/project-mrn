from __future__ import annotations

"""ProfileRegistry — 프로파일 등록 및 alias 해석.

사용법:
    registry = ProfileRegistry()
    registry.register(spec)
    spec = registry.resolve("v3_claude")       # alias로 조회 가능
    spec = registry.resolve("heuristic_v3_claude_exp")  # canonical name 조회
"""

from .spec import PolicyProfileSpec


class ProfileRegistry:
    def __init__(self) -> None:
        self._by_canonical: dict[str, PolicyProfileSpec] = {}
        self._alias_map: dict[str, str] = {}  # alias → canonical name

    def register(self, spec: PolicyProfileSpec) -> None:
        """spec을 등록한다. 이미 같은 canonical name이 있으면 덮어쓴다."""
        self._by_canonical[spec.name] = spec
        for alias in spec.aliases:
            self._alias_map[alias] = spec.name

    def resolve(self, name: str) -> PolicyProfileSpec:
        """canonical name 또는 alias로 spec을 반환한다."""
        canonical = self._alias_map.get(name, name)
        if canonical not in self._by_canonical:
            raise KeyError(f"ProfileRegistry: unknown profile '{name}'")
        return self._by_canonical[canonical]

    def names(self) -> list[str]:
        """등록된 모든 canonical name 목록."""
        return list(self._by_canonical.keys())
