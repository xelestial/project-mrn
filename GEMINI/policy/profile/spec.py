from dataclasses import dataclass

@dataclass(frozen=True)
class PolicyWeightProfile:
    expansion: float
    economy: float
    disruption: float
    meta: float
    combo: float
    survival: float

@dataclass(frozen=True)
class CharacterValueProfile:
    values: dict[str, float]

@dataclass(frozen=True)
class CharacterGroupProfile:
    rent_escape: frozenset[str]
    rent_expansion: frozenset[str]
    rent_fragile_disruptors: frozenset[str]
    growth_like: frozenset[str]
    economy_like: frozenset[str]
    disruption_like: frozenset[str]

@dataclass(frozen=True)
class MarkRiskProfile:
    actor_names: frozenset[str]
    base_risk: dict[str, float]
    priority_same_factor: float
    guess_temperature: float
    guess_uniform_mix_base: float
    guess_uniform_mix_ambiguity: float
    guess_uniform_mix_extra_candidate: float
    guess_confidence_thresholds: dict[str, float]
    guess_margin_thresholds: dict[str, float]

@dataclass(frozen=True)
class SurvivalThresholdSpec:
    # We will map the magic numbers from survival_common.py to this
    two_turn_lethal_reserve_multiplier: float
    money_distress_reserve_multiplier: float
    survival_urgency_reserve_multiplier: float
    latent_cleanup_cost_reserve_multiplier: float
    active_cleanup_cost_floor_enabled: bool

@dataclass(frozen=True)
class PolicyProfileSpec:
    name: str
    weights: PolicyWeightProfile
    character_values: CharacterValueProfile
    character_groups: CharacterGroupProfile
    mark_risk: MarkRiskProfile
    survival_threshold: SurvivalThresholdSpec
    survival_strategy_key: str = "survival/default_v1"
    lap_reward_strategy_key: str = "lap_reward/base_v1"
    purchase_gate_strategy_key: str = "purchase_gate/base_v1"
    draft_strategy_key: str = "draft/base_v1"
