from __future__ import annotations

"""policy/survival/thresholds — SurvivalThresholdSpec + 기본값 로더."""

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SurvivalThresholdSpec:
    """생존 판단에 사용되는 임계값/가중치 모음. profiles/survival_threshold_*.json에서 로드."""

    # build_action_guard_context
    action_guard_lethal_weight: float = 1.50
    action_guard_distress_weight: float = 0.60
    action_guard_urgency_weight: float = 0.35
    action_guard_latent_weight: float = 0.25

    # swindle_operating_reserve
    swindle_latent_multiplier: float = 0.65
    swindle_lethal_weight: float = 2.0
    swindle_distress_weight: float = 1.5
    swindle_urgency_weight: float = 0.75

    # evaluate_swindle_guard
    swindle_buffer: float = 2.0
    swindle_guard_floor_margin: float = 1.0
    swindle_high_cost_threshold_strict: float = 16.0
    swindle_high_cost_threshold_abs: float = 12.0
    swindle_high_cost_ratio: float = 0.60
    swindle_distress_gate: float = 0.35
    swindle_urgency_gate: float = 0.35
    swindle_lethal_gate: float = 0.10
    swindle_critical_distress: float = 0.55
    swindle_critical_urgency: float = 0.55
    swindle_critical_lethal: float = 0.18
    swindle_critical_reserve_buffer: float = 6.0

    # build_survival_orchestrator
    orchestrator_weight_lethal: float = 2.25
    orchestrator_weight_distress: float = 1.75
    orchestrator_weight_urgency: float = 1.35
    orchestrator_cleanup_bonus: float = 1.25
    severe_distress_lethal: float = 0.18
    severe_distress_money: float = 1.10
    severe_distress_urgency: float = 1.00
    severe_cleanup_cost_abs: float = 8.0
    severe_cleanup_reserve_margin: float = 2.0
    income_emergency_latent_abs: float = 10.0
    income_emergency_latent_reserve_margin: float = 4.0
    cleanup_emergency_urgency: float = 0.70
    cleanup_emergency_money: float = 0.85

    # evaluate_character_survival_advice
    soft_distress_urgency: float = 0.40
    soft_distress_money: float = 0.45
    medium_latent_abs: float = 8.0
    medium_latent_reserve_margin: float = 2.0

    @classmethod
    def from_json(cls, path: str) -> "SurvivalThresholdSpec":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def _load_default_thresholds() -> SurvivalThresholdSpec:
    path = os.path.join(os.path.dirname(__file__), "..", "..", "profiles", "survival_threshold_default.json")
    try:
        return SurvivalThresholdSpec.from_json(path)
    except (FileNotFoundError, KeyError):
        return SurvivalThresholdSpec()


_T: SurvivalThresholdSpec = _load_default_thresholds()
