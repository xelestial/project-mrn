import json
import os
from pathlib import Path
from typing import Dict

from .spec import (
    PolicyWeightProfile,
    CharacterValueProfile,
    CharacterGroupProfile,
    MarkRiskProfile,
    SurvivalThresholdSpec,
    PolicyProfileSpec,
)

class ProfileRegistry:
    def __init__(self, profiles_dir: str):
        self.profiles_dir = Path(profiles_dir)
        self._cache: Dict[str, PolicyProfileSpec] = {}

    def _load_json(self, filename: str) -> dict:
        path = self.profiles_dir / filename
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_profile(self, profile_name: str) -> PolicyProfileSpec:
        if profile_name in self._cache:
            return self._cache[profile_name]

        # 1. Load weights
        weights_file = f"policy_weights_{profile_name}.json"
        
        # Fallback to control if specific profile doesn't exist
        if not (self.profiles_dir / weights_file).exists():
            weights_file = "policy_weights_control.json"
        
        weights_data = self._load_json(weights_file)
        weights = PolicyWeightProfile(
            expansion=weights_data["expansion"],
            economy=weights_data["economy"],
            disruption=weights_data["disruption"],
            meta=weights_data["meta"],
            combo=weights_data["combo"],
            survival=weights_data["survival"],
        )

        # 2. Load character values
        char_val_data = self._load_json("character_values_default.json")
        character_values = CharacterValueProfile(values=char_val_data)

        # 3. Load groups
        groups_data = self._load_json("character_groups.json")
        character_groups = CharacterGroupProfile(
            rent_escape=frozenset(groups_data["rent_escape_characters"]),
            rent_expansion=frozenset(groups_data["rent_expansion_characters"]),
            rent_fragile_disruptors=frozenset(groups_data["rent_fragile_disruptors"]),
            growth_like=frozenset(groups_data["growth_like_characters"]),
            economy_like=frozenset(groups_data["economy_like_characters"]),
            disruption_like=frozenset(groups_data["disruption_like_characters"]),
        )

        # 4. Load mark risk
        mark_data = self._load_json("mark_risk.json")
        mark_risk = MarkRiskProfile(
            actor_names=frozenset(mark_data["actor_names"]),
            base_risk=mark_data["base_risk"],
            priority_same_factor=mark_data["priority_same_factor"],
            guess_temperature=mark_data["guess_temperature"],
            guess_uniform_mix_base=mark_data["guess_uniform_mix_base"],
            guess_uniform_mix_ambiguity=mark_data["guess_uniform_mix_ambiguity"],
            guess_uniform_mix_extra_candidate=mark_data["guess_uniform_mix_extra_candidate"],
            guess_confidence_thresholds=mark_data["guess_confidence_thresholds"],
            guess_margin_thresholds=mark_data["guess_margin_thresholds"],
        )

        # 5. Load survival threshold
        surv_data = self._load_json("survival_threshold_default.json")
        survival_threshold = SurvivalThresholdSpec(
            two_turn_lethal_reserve_multiplier=surv_data["two_turn_lethal_reserve_multiplier"],
            money_distress_reserve_multiplier=surv_data["money_distress_reserve_multiplier"],
            survival_urgency_reserve_multiplier=surv_data["survival_urgency_reserve_multiplier"],
            latent_cleanup_cost_reserve_multiplier=surv_data["latent_cleanup_cost_reserve_multiplier"],
            active_cleanup_cost_floor_enabled=surv_data["active_cleanup_cost_floor_enabled"],
        )

        spec = PolicyProfileSpec(
            name=profile_name,
            weights=weights,
            character_values=character_values,
            character_groups=character_groups,
            mark_risk=mark_risk,
            survival_threshold=survival_threshold,
        )

        self._cache[profile_name] = spec
        return spec

# Global registry instance
import pathlib
_project_root = pathlib.Path(__file__).parent.parent.parent
_profiles_dir = _project_root / "profiles"
PROFILE_REGISTRY = ProfileRegistry(str(_profiles_dir))
