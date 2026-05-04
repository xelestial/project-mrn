from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from config import CellKind
from policy.character_traits import is_builder
from runtime_modules.modifiers import builder_purchase_modifier
from state import GameState, PlayerState, TileState
from weather_cards import COLOR_RENT_DOUBLE_WEATHERS


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


@dataclass(slots=True)
class RentContext:
    tile_context: TileEffectContext
    owner_player_id: int
    base_rent: int
    final_rent: int
    rent_source: str = "landing_rent"
    rent_breakdown: list[dict] = field(default_factory=list)
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
            "owner_player_id": self.owner_player_id,
            "base_rent": self.base_rent,
            "final_rent": self.final_rent,
            "rent_source": self.rent_source,
            "rent_breakdown": [dict(item) for item in self.rent_breakdown],
            "one_shot_consumptions": list(self.one_shot_consumptions),
        }


@dataclass(slots=True)
class ScoreTokenPlacementContext:
    tile_context: TileEffectContext
    source: str
    requested_limit: int
    tile_capacity: int
    tile_tokens_before: int
    hand_tokens_before: int
    amount: int
    can_place: bool
    blocked_reason: str = ""

    @property
    def tile_index(self) -> int:
        return self.tile_context.tile_index

    @property
    def tile_kind(self) -> CellKind:
        return self.tile_context.kind

    @property
    def tile_room_before(self) -> int:
        return max(0, self.tile_capacity - self.tile_tokens_before)

    def to_payload(self) -> dict:
        return {
            "tile_index": self.tile_index,
            "tile_kind": self.tile_kind.name,
            "source": self.source,
            "requested_limit": self.requested_limit,
            "tile_capacity": self.tile_capacity,
            "tile_tokens_before": self.tile_tokens_before,
            "tile_room_before": self.tile_room_before,
            "hand_tokens_before": self.hand_tokens_before,
            "amount": self.amount,
            "can_place": self.can_place,
            "blocked_reason": self.blocked_reason,
        }


class PurchaseModifier(Protocol):
    modifier_id: str
    priority: int

    def applies(self, context: PurchaseContext) -> bool:
        ...

    def apply(self, context: PurchaseContext) -> None:
        ...


class RentModifier(Protocol):
    modifier_id: str
    priority: int

    def applies(self, context: RentContext) -> bool:
        ...

    def apply(self, context: RentContext) -> None:
        ...


class BuilderFreePurchaseModifier:
    modifier_id = "builder_free_purchase"
    priority = 10

    def applies(self, context: PurchaseContext) -> bool:
        if context.final_cost <= 0:
            return False
        state = context.tile_context.state
        player = context.tile_context.player
        return builder_purchase_modifier(state, player_id=player.player_id) is not None

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


class TileRentModifier:
    modifier_id = "tile_rent_modifier"
    priority = 10

    def applies(self, context: RentContext) -> bool:
        return context.tile_context.state.tile_rent_modifiers_this_turn.get(context.tile_index, 1) != 1

    def apply(self, context: RentContext) -> None:
        modifier = context.tile_context.state.tile_rent_modifiers_this_turn.get(context.tile_index, 1)
        before = context.final_rent
        context.final_rent *= modifier
        context.rent_breakdown.append(
            {
                "modifier": self.modifier_id,
                "factor": modifier,
                "before": before,
                "after": context.final_rent,
            }
        )


class ColorWeatherRentDoubleModifier:
    modifier_id = "color_weather_rent_double"
    priority = 20

    def applies(self, context: RentContext) -> bool:
        if context.final_rent <= 0 or context.tile_context.zone_color is None:
            return False
        return any(
            COLOR_RENT_DOUBLE_WEATHERS.get(name) == context.tile_context.zone_color
            for name in context.tile_context.state.current_weather_effects
        )

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent *= 2
        context.rent_breakdown.append({"modifier": self.modifier_id, "before": before, "after": context.final_rent})


class GlobalRentDoublePermanentModifier:
    modifier_id = "global_rent_double_permanent"
    priority = 30

    def applies(self, context: RentContext) -> bool:
        return context.final_rent > 0 and context.tile_context.state.global_rent_double_permanent

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent *= 2
        context.rent_breakdown.append({"modifier": self.modifier_id, "before": before, "after": context.final_rent})


class GlobalRentDoubleTurnModifier:
    modifier_id = "global_rent_double_this_turn"
    priority = 40

    def applies(self, context: RentContext) -> bool:
        return context.final_rent > 0 and context.tile_context.state.global_rent_double_this_turn

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent *= 2
        context.rent_breakdown.append({"modifier": self.modifier_id, "before": before, "after": context.final_rent})


class GlobalRentHalfTurnModifier:
    modifier_id = "global_rent_half_this_turn"
    priority = 50

    def applies(self, context: RentContext) -> bool:
        return context.final_rent > 0 and context.tile_context.state.global_rent_half_this_turn

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent = math.ceil(context.final_rent / 2)
        context.rent_breakdown.append({"modifier": self.modifier_id, "before": before, "after": context.final_rent})


class PayerPersonalRentHalfModifier:
    modifier_id = "payer_personal_rent_half_this_turn"
    priority = 60

    def applies(self, context: RentContext) -> bool:
        return context.final_rent > 0 and context.tile_context.player.trick_personal_rent_half_this_turn

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent //= 2
        context.rent_breakdown.append({"modifier": self.modifier_id, "before": before, "after": context.final_rent})


class OwnerPersonalRentHalfModifier:
    modifier_id = "owner_personal_rent_half_this_turn"
    priority = 70

    def applies(self, context: RentContext) -> bool:
        if context.final_rent <= 0:
            return False
        owner = context.tile_context.state.players[context.owner_player_id]
        return owner.trick_personal_rent_half_this_turn

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent //= 2
        context.rent_breakdown.append({"modifier": self.modifier_id, "before": before, "after": context.final_rent})


class RentWaiverAllTurnModifier:
    modifier_id = "rent_waiver_all_turn"
    priority = 80

    def applies(self, context: RentContext) -> bool:
        return context.final_rent > 0 and context.tile_context.player.trick_all_rent_waiver_this_turn

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent = 0
        context.rent_breakdown.append({"modifier": self.modifier_id, "before": before, "after": context.final_rent})


class RentWaiverCountModifier:
    modifier_id = "rent_waiver_count_this_turn"
    priority = 90

    def applies(self, context: RentContext) -> bool:
        return context.final_rent > 0 and context.tile_context.player.rent_waiver_count_this_turn > 0

    def apply(self, context: RentContext) -> None:
        before = context.final_rent
        context.final_rent = 0
        context.one_shot_consumptions.append("rent_waiver_count_this_turn")
        context.rent_breakdown.append(
            {
                "modifier": self.modifier_id,
                "before": before,
                "after": context.final_rent,
                "consume_on_success": list(context.one_shot_consumptions),
            }
        )


RENT_MODIFIERS: tuple[RentModifier, ...] = (
    TileRentModifier(),
    ColorWeatherRentDoubleModifier(),
    GlobalRentDoublePermanentModifier(),
    GlobalRentDoubleTurnModifier(),
    GlobalRentHalfTurnModifier(),
    PayerPersonalRentHalfModifier(),
    OwnerPersonalRentHalfModifier(),
    RentWaiverAllTurnModifier(),
    RentWaiverCountModifier(),
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


def build_rent_context(
    state: GameState,
    payer: PlayerState,
    tile_index: int,
    owner_player_id: int,
    *,
    source: str = "landing_rent",
    include_waivers: bool = True,
) -> RentContext:
    base_rent = state.config.rules.economy.rent_cost_for(state, tile_index)
    tile_context = build_tile_effect_context(state, payer, tile_index, trigger=source)
    context = RentContext(
        tile_context=tile_context,
        owner_player_id=owner_player_id,
        base_rent=base_rent,
        final_rent=base_rent,
        rent_source=source,
        rent_breakdown=[
            {
                "modifier": "base_rent_cost",
                "amount": base_rent,
                "tile_kind": tile_context.kind.name,
            }
        ],
    )
    for modifier in sorted(RENT_MODIFIERS, key=lambda item: item.priority):
        if not include_waivers and modifier.modifier_id in {"rent_waiver_all_turn", "rent_waiver_count_this_turn"}:
            continue
        if modifier.applies(context):
            modifier.apply(context)
    context.final_rent = max(0, context.final_rent)
    return context


def build_score_token_placement_context(
    state: GameState,
    player: PlayerState,
    tile_index: int,
    *,
    max_place: int | None = None,
    source: str = "visit",
) -> ScoreTokenPlacementContext:
    tile_capacity = state.config.rules.token.tile_capacity(state, tile_index)
    tile_tokens_before = state.tile_coins[tile_index]
    hand_tokens_before = player.hand_coins
    requested_limit = state.config.rules.token.max_place_per_visit if max_place is None else max_place
    room = max(0, tile_capacity - tile_tokens_before)
    amount = min(hand_tokens_before, room, requested_limit)
    blocked_reason = ""
    if hand_tokens_before <= 0:
        blocked_reason = "no_hand_tokens"
    elif room <= 0:
        blocked_reason = "tile_full"
    elif requested_limit <= 0:
        blocked_reason = "placement_limit_zero"
    elif amount <= 0:
        blocked_reason = "no_placeable_amount"
    return ScoreTokenPlacementContext(
        tile_context=build_tile_effect_context(state, player, tile_index, trigger=source),
        source=source,
        requested_limit=requested_limit,
        tile_capacity=tile_capacity,
        tile_tokens_before=tile_tokens_before,
        hand_tokens_before=hand_tokens_before,
        amount=max(0, amount),
        can_place=amount > 0,
        blocked_reason=blocked_reason,
    )


def consume_purchase_one_shots(player: PlayerState, consumptions: list[str]) -> None:
    for item in consumptions:
        if item == "free_purchase_this_turn":
            player.free_purchase_this_turn = False
        elif item == "trick_free_purchase_this_turn":
            player.trick_free_purchase_this_turn = False


def consume_rent_one_shots(player: PlayerState, consumptions: list[str]) -> None:
    for item in consumptions:
        if item == "rent_waiver_count_this_turn" and player.rent_waiver_count_this_turn > 0:
            player.rent_waiver_count_this_turn -= 1
