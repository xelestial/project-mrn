from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from config import CellKind
from policy.character_traits import is_builder
from state import GameState, PlayerState, TileState


@dataclass(slots=True)
class TileEffectContext:
    state: GameState
    player: PlayerState
    tile_index: int
    tile: TileState
    kind: CellKind
    owner_id: int | None
    block_id: int
    zone_color: str | None
    trigger: str = ""
    source_action_id: str = ""


@dataclass(slots=True)
class PurchaseContext:
    tile_context: TileEffectContext
    base_cost: int
    final_cost: int
    can_purchase: bool = True
    purchase_source: str = "landing_purchase"
    shard_cost: int = 0
    cost_breakdown: list[dict] = field(default_factory=list)
    one_shot_consumptions: list[str] = field(default_factory=list)

    @property
    def tile_index(self) -> int:
        return self.tile_context.tile_index

    @property
    def tile_kind(self) -> CellKind:
        return self.tile_context.kind

    def to_payload(self) -> dict:
        return {
            "tile_index": self.tile_index,
            "tile_kind": self.tile_kind.name,
            "base_cost": self.base_cost,
            "final_cost": self.final_cost,
            "shard_cost": self.shard_cost,
            "can_purchase": self.can_purchase,
            "purchase_source": self.purchase_source,
            "cost_breakdown": [dict(item) for item in self.cost_breakdown],
            "one_shot_consumptions": list(self.one_shot_consumptions),
        }


class PurchaseModifier(Protocol):
    modifier_id: str
    priority: int

    def applies(self, context: PurchaseContext) -> bool:
        ...

    def apply(self, context: PurchaseContext) -> None:
        ...


class BuilderFreePurchaseModifier:
    modifier_id = "builder_free_purchase"
    priority = 10

    def applies(self, context: PurchaseContext) -> bool:
        return context.final_cost > 0 and is_builder(context.tile_context.player.current_character)

    def apply(self, context: PurchaseContext) -> None:
        before = context.final_cost
        context.final_cost = 0
        context.cost_breakdown.append(
            {
                "modifier": self.modifier_id,
                "before": before,
                "after": context.final_cost,
                "delta": -before,
            }
        )


class FreePurchaseModifier:
    modifier_id = "free_purchase_once"
    priority = 20

    def applies(self, context: PurchaseContext) -> bool:
        player = context.tile_context.player
        return context.final_cost > 0 and (player.free_purchase_this_turn or player.trick_free_purchase_this_turn)

    def apply(self, context: PurchaseContext) -> None:
        player = context.tile_context.player
        before = context.final_cost
        context.final_cost = 0
        if player.free_purchase_this_turn:
            context.one_shot_consumptions.append("free_purchase_this_turn")
        if player.trick_free_purchase_this_turn:
            context.one_shot_consumptions.append("trick_free_purchase_this_turn")
        context.cost_breakdown.append(
            {
                "modifier": self.modifier_id,
                "before": before,
                "after": context.final_cost,
                "delta": -before,
                "consume_on_success": list(context.one_shot_consumptions),
            }
        )


PURCHASE_MODIFIERS: tuple[PurchaseModifier, ...] = (
    BuilderFreePurchaseModifier(),
    FreePurchaseModifier(),
)


def build_tile_effect_context(
    state: GameState,
    player: PlayerState,
    tile_index: int,
    *,
    trigger: str = "",
    source_action_id: str = "",
) -> TileEffectContext:
    tile = state.tile_at(tile_index)
    return TileEffectContext(
        state=state,
        player=player,
        tile_index=tile_index,
        tile=tile,
        kind=tile.kind,
        owner_id=tile.owner_id,
        block_id=tile.block_id,
        zone_color=tile.zone_color,
        trigger=trigger,
        source_action_id=source_action_id,
    )


def build_purchase_context(
    state: GameState,
    player: PlayerState,
    tile_index: int,
    cell: CellKind,
    *,
    source: str,
) -> PurchaseContext:
    base_cost = state.config.rules.economy.purchase_cost_for(state, tile_index)
    context = PurchaseContext(
        tile_context=build_tile_effect_context(state, player, tile_index, trigger=source),
        base_cost=base_cost,
        final_cost=base_cost,
        purchase_source=source,
        cost_breakdown=[
            {
                "modifier": "base_purchase_cost",
                "amount": base_cost,
                "tile_kind": cell.name,
            }
        ],
    )
    for modifier in sorted(PURCHASE_MODIFIERS, key=lambda item: item.priority):
        if modifier.applies(context):
            modifier.apply(context)
    return context


def consume_purchase_one_shots(player: PlayerState, consumptions: list[str]) -> None:
    for item in consumptions:
        if item == "free_purchase_this_turn":
            player.free_purchase_this_turn = False
        elif item == "trick_free_purchase_this_turn":
            player.trick_free_purchase_this_turn = False
