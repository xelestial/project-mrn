from __future__ import annotations

"""policy/survival/signals — SurvivalSignals dataclass."""

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class SurvivalSignals:
    reserve: float
    money_distress: float
    survival_urgency: float
    two_turn_lethal_prob: float
    latent_cleanup_cost: float
    active_cleanup_cost: float
    public_cleanup_active: bool

    @classmethod
    def from_mapping(cls, data: Mapping[str, float]) -> "SurvivalSignals":
        return cls(
            reserve=float(data.get("reserve", 0.0)),
            money_distress=float(data.get("money_distress", 0.0)),
            survival_urgency=float(data.get("survival_urgency", 0.0)),
            two_turn_lethal_prob=float(data.get("two_turn_lethal_prob", 0.0)),
            latent_cleanup_cost=float(data.get("latent_cleanup_cost", 0.0)),
            active_cleanup_cost=float(data.get("active_cleanup_cost", 0.0)),
            public_cleanup_active=float(data.get("public_cleanup_active", 0.0)) > 0.0,
        )
