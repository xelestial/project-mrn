from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RewardBreakdown:
    total: float
    components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total": float(self.total),
            "components": {str(k): float(v) for k, v in self.components.items()},
        }
