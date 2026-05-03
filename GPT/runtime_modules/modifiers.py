from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import Modifier, ModifierRegistryState

MUROE_SKILL_SUPPRESSION_KIND = "suppress_character_skill"
MUROE_SKILL_SUPPRESSION_REASON = "muroe_blocked_by_eosa"
PABAL_DICE_MODIFIER_KIND = "pabalggun_dice_delta"
BUILDER_FREE_PURCHASE_KIND = "builder_free_purchase"


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


def seed_character_start_modifiers(state: Any, *, source_module_id: str = "CharacterModifierSeedModule") -> None:
    registry = ModifierRegistry(state.runtime_modifier_registry)
    eosa_players = [
        player
        for player in getattr(state, "players", [])
        if getattr(player, "alive", True) and str(getattr(player, "current_character", "") or "") == "어사"
    ]
    if not eosa_players:
        return
    round_index = int(getattr(state, "rounds_completed", 0) or 0) + 1
    for eosa in eosa_players:
        eosa_player_id = int(getattr(eosa, "player_id", 0) or 0)
        for target in getattr(state, "players", []):
            target_player_id = int(getattr(target, "player_id", 0) or 0)
            if target_player_id == eosa_player_id:
                continue
            if not getattr(target, "alive", True):
                continue
            if str(getattr(target, "attribute", "") or "") != "무뢰":
                continue
            registry.add(
                Modifier(
                    modifier_id=(
                        f"modifier:round:{round_index}:eosa:{eosa_player_id}:"
                        f"suppress_muroe_character_skill:{target_player_id}"
                    ),
                    source_module_id=source_module_id,
                    target_module_type="CharacterStartModule",
                    scope="round",
                    owner_player_id=target_player_id,
                    priority=0,
                    payload={
                        "kind": MUROE_SKILL_SUPPRESSION_KIND,
                        "reason": MUROE_SKILL_SUPPRESSION_REASON,
                        "source_player_id": eosa_player_id,
                        "target_player_id": target_player_id,
                    },
                    propagation=[
                        "TargetJudicatorModule",
                        "DiceRollModule",
                        "MovementResolveModule",
                        "MapMoveModule",
                        "ArrivalTileModule",
                        "LapRewardModule",
                        "FortuneResolveModule",
                    ],
                    expires_on="round_completed",
                )
            )


def character_skill_suppression_modifier(state: Any, player_id: int) -> Modifier | None:
    registry = ModifierRegistry(state.runtime_modifier_registry)
    for modifier in registry.applicable("CharacterStartModule", owner_player_id=player_id):
        if modifier.payload.get("kind") != MUROE_SKILL_SUPPRESSION_KIND:
            continue
        return registry.consume(modifier.modifier_id)
    return None


def seed_pabal_dice_modifier(
    state: Any,
    *,
    player_id: int,
    dice_mode: str,
    source_module_id: str,
) -> Modifier:
    dice_delta = -1 if dice_mode == "minus_one" else 1
    round_index = int(getattr(state, "rounds_completed", 0) or 0) + 1
    modifier = Modifier(
        modifier_id=f"modifier:round:{round_index}:pabalggun:{player_id}:dice_delta",
        source_module_id=source_module_id,
        target_module_type="DiceRollModule",
        scope="single_use",
        owner_player_id=player_id,
        priority=10,
        payload={
            "kind": PABAL_DICE_MODIFIER_KIND,
            "dice_mode": dice_mode,
            "dice_delta": dice_delta,
            "source_player_id": player_id,
        },
        propagation=[],
        expires_on="turn_completed",
    )
    ModifierRegistry(state.runtime_modifier_registry).add(modifier)
    return modifier


def seed_builder_purchase_modifier(state: Any, *, player_id: int, source_module_id: str) -> Modifier:
    round_index = int(getattr(state, "rounds_completed", 0) or 0) + 1
    modifier = Modifier(
        modifier_id=f"modifier:round:{round_index}:builder:{player_id}:free_purchase",
        source_module_id=source_module_id,
        target_module_type="PurchaseDecisionModule",
        scope="turn",
        owner_player_id=player_id,
        priority=10,
        payload={
            "kind": BUILDER_FREE_PURCHASE_KIND,
            "source_player_id": player_id,
        },
        propagation=["PurchaseCommitModule", "ArrivalTileModule"],
        expires_on="turn_completed",
    )
    ModifierRegistry(state.runtime_modifier_registry).add(modifier)
    return modifier


def consume_pabal_dice_modifier(state: Any, *, player_id: int) -> Modifier | None:
    registry_state = getattr(state, "runtime_modifier_registry", None)
    if registry_state is None:
        return None
    registry = ModifierRegistry(registry_state)
    for modifier in registry.applicable("DiceRollModule", owner_player_id=player_id):
        if modifier.payload.get("kind") != PABAL_DICE_MODIFIER_KIND:
            continue
        return registry.consume(modifier.modifier_id)
    return None
