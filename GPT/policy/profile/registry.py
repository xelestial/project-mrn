from __future__ import annotations

from typing import Iterable

from policy.profile.spec import PolicyProfileSpec


class PolicyProfileRegistry:
    def __init__(self, specs: Iterable[PolicyProfileSpec], default_profile_key: str = "balanced") -> None:
        self._specs: dict[str, PolicyProfileSpec] = {}
        self._profile_aliases: dict[str, str] = {"heuristic_v1": default_profile_key}
        self._character_mode_aliases: dict[str, str] = {"heuristic_v1": "heuristic_v1", "random": "random", "arena": "arena"}
        self._lap_mode_aliases: dict[str, str] = {
            "heuristic_v1": "heuristic_v1",
            "cash_focus": "cash_focus",
            "shard_focus": "shard_focus",
            "coin_focus": "coin_focus",
            "balanced": "balanced",
        }
        for spec in specs:
            self.register(spec)
        if default_profile_key not in self._specs:
            raise ValueError(f"Unknown default profile key: {default_profile_key}")
        self._default_profile_key = default_profile_key

    def register(self, spec: PolicyProfileSpec) -> None:
        self._specs[spec.key] = spec
        for mode in spec.supported_modes:
            self._profile_aliases[mode] = spec.key
            self._character_mode_aliases[mode] = spec.canonical_mode
            self._lap_mode_aliases[mode] = spec.canonical_mode

    def resolve_profile(self, mode: str | None = None) -> PolicyProfileSpec:
        return self._specs[self.resolve_profile_key(mode)]

    def resolve_profile_key(self, mode: str | None = None) -> str:
        lookup = mode or self._default_profile_key
        try:
            return self._profile_aliases[lookup]
        except KeyError as exc:
            raise ValueError(f"Unknown profile mode: {lookup}") from exc

    def canonicalize_character_mode(self, mode: str) -> str:
        try:
            return self._character_mode_aliases[mode]
        except KeyError as exc:
            raise ValueError(f"Unsupported character policy mode: {mode}") from exc

    def canonicalize_lap_mode(self, mode: str) -> str:
        try:
            return self._lap_mode_aliases[mode]
        except KeyError as exc:
            raise ValueError(f"Unsupported lap policy mode: {mode}") from exc

    def profile_keys(self) -> set[str]:
        return set(self._specs)

    def valid_character_modes(self) -> set[str]:
        return set(self._character_mode_aliases)

    def valid_lap_modes(self) -> set[str]:
        return set(self._lap_mode_aliases)

    @property
    def default_character_values(self) -> dict[str, float]:
        return dict(self.resolve_profile().character_values)

    @property
    def profile_weights(self) -> dict[str, dict[str, float]]:
        return {key: dict(spec.weights) for key, spec in self._specs.items()}
