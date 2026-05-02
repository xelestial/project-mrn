from __future__ import annotations

from dataclasses import dataclass

from .contracts import Modifier, ModifierRegistryState


@dataclass(slots=True)
class ModifierRegistry:
    state: ModifierRegistryState

    def add(self, modifier: Modifier) -> None:
        self.state.modifiers = [
            existing for existing in self.state.modifiers if existing.modifier_id != modifier.modifier_id
        ]
        self.state.modifiers.append(modifier)
        self.state.modifiers.sort(key=lambda item: item.priority)

    def applicable(self, module_type: str, owner_player_id: int | None = None) -> list[Modifier]:
        result: list[Modifier] = []
        for modifier in self.state.modifiers:
            if modifier.consumed:
                continue
            if modifier.target_module_type != module_type and module_type not in modifier.propagation:
                continue
            if modifier.owner_player_id is not None and modifier.owner_player_id != owner_player_id:
                continue
            result.append(modifier)
        return sorted(result, key=lambda item: item.priority)

    def consume(self, modifier_id: str) -> Modifier | None:
        for modifier in self.state.modifiers:
            if modifier.modifier_id != modifier_id or modifier.consumed:
                continue
            if modifier.scope == "single_use":
                modifier.consumed = True
            return modifier
        return None

    def expire(self, expires_on: str) -> None:
        self.state.modifiers = [
            modifier for modifier in self.state.modifiers if modifier.expires_on != expires_on and not modifier.consumed
        ]
