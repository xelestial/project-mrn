from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping


def _freeze_mapping(values: Mapping[str, float]) -> Mapping[str, float]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class PolicyProfileSpec:
    key: str
    canonical_mode: str
    aliases: tuple[str, ...] = ()
    weights: Mapping[str, float] = field(default_factory=dict)
    character_values: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "aliases", tuple(dict.fromkeys(self.aliases)))
        object.__setattr__(self, "weights", _freeze_mapping(self.weights))
        object.__setattr__(self, "character_values", _freeze_mapping(self.character_values))

    @property
    def supported_modes(self) -> tuple[str, ...]:
        return (self.key, self.canonical_mode, *self.aliases)
