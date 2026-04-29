# [PLAN] Tile Trait And Action Pipeline

Status: IMPLEMENTING  
Created: 2026-04-30

## Goal

Introduce one consistent rule pipeline for tile effects, purchase, rent, score-token placement, weather modifiers, trick modifiers, fortune follow-ups, and character effects.

The target shape is:

```text
arrival
-> build TileEffectContext
-> collect tile traits and active modifiers
-> produce queued actions or immediate atomic effects
-> execute one action boundary at a time
-> persist checkpoint to Redis
```

This keeps the engine from growing by scattered `if weather`, `if trick`, `if character`, and `if tile color` branches. A tile should describe what it is. Trait and modifier modules should decide what that means under the current state.

## Current Problem

The engine already has useful seams:

- `landing.unowned.resolve`
- `landing.own_tile.resolve`
- `rent.payment.resolve`
- `tile.purchase.attempt`
- `resolve_arrival`
- `request_purchase_tile`
- `resolve_landing_post_effects`

However, important rule branches still live inside large handlers and helper methods:

- purchase cost is mixed with purchase decision and purchase mutation
- free purchase effects are flags consumed inside purchase mutation
- rent amount is spread across base tile cost, weather/color, global rent flags, player flags, and trick waivers
- score-token placement happens as a helper rather than a resumable action family
- tile color, weather, character, fortune, and trick effects are all able to add one-off branches

This works for current rules but makes future effects easy to implement in a hardcoded way.

## Design Principles

1. Tile metadata describes the board.
2. Traits describe what a tile can do.
3. Modifiers alter a context, not the final state directly.
4. Actions mutate state and are resumable through Redis checkpoints.
5. Human decisions happen only at action boundaries.
6. One-shot flags are consumed only after the action succeeds.
7. Direct helper calls remain test/plugin compatibility paths, not runtime effect paths.

## Core Data Model

### TileEffectContext

Created whenever a player arrives on a tile.

```python
TileEffectContext(
    state: GameState,
    player: PlayerState,
    tile_index: int,
    tile: TileState,
    kind: CellKind,
    owner_id: int | None,
    block_id: int,
    zone_color: str | None,
    source_action_id: str,
    trigger: str,
)
```

It should be read-mostly. Mutations should happen through produced actions or explicit atomic handlers.

### TileTrait

A tile trait represents stable tile behavior.

Examples:

- `PurchasableLandTrait`
- `RentableLandTrait`
- `OwnTileTokenTrait`
- `FortuneTileTrait`
- `MaliciousTileTrait`
- `StartEndTileTrait`
- `ZoneChainTrait`

Suggested interface:

```python
class TileTrait(Protocol):
    trait_id: str

    def applies(self, context: TileEffectContext) -> bool:
        ...

    def produce(self, context: TileEffectContext) -> list[ActionEnvelope] | dict | None:
        ...
```

Traits may return:

- a queued action
- a small immediate result for simple atomic effects
- `None` when not applicable

### Modifier

A modifier changes a decision context before the final action runs.

Examples:

- `WeatherColorRentModifier`
- `GlobalRentHalfModifier`
- `PersonalRentHalfModifier`
- `RentWaiverModifier`
- `FreePurchaseModifier`
- `BuilderPurchaseModifier`
- `PurchaseBlockedModifier`
- `TokenCapacityModifier`

Suggested interface:

```python
class Modifier(Protocol):
    modifier_id: str
    priority: int

    def applies(self, context) -> bool:
        ...

    def apply(self, context) -> None:
        ...
```

Modifiers should not directly spend cash, transfer ownership, or place score tokens. They prepare the final context.

## Purchase Pipeline

### Context

```python
PurchaseContext(
    tile_context: TileEffectContext,
    base_cost: int,
    final_cost: int,
    can_purchase: bool,
    purchase_source: str,
    cost_breakdown: list[dict],
    one_shot_consumptions: list[dict],
)
```

### Flow

```text
unowned land arrival
-> build PurchaseContext
-> apply PurchaseEligibilityModifier[]
-> apply PurchaseCostModifier[]
-> if can_purchase:
     queue request_purchase_tile
     queue resolve_purchase_tile
     queue resolve_unowned_post_purchase
```

### Free Purchase Example

The free purchase trick should not be a special branch inside purchase mutation.

Preferred shape:

```text
FreePurchaseModifier
  applies when player.trick_free_purchase_this_turn is true
  sets final_cost = 0
  appends one-shot consumption: trick_free_purchase_this_turn

resolve_purchase_tile
  asks/uses decision
  pays final_cost
  transfers ownership
  consumes one-shot flags only after success
```

This also covers builder-style free construction, weather discounts, future coupons, and event discounts.

### Purchase Action Split

Target action shape:

```text
resolve_arrival
-> request_purchase_tile
-> resolve_purchase_tile
-> resolve_unowned_post_purchase
```

Current implementation already has `request_purchase_tile` and `resolve_unowned_post_purchase`. The next migration should separate the final mutation into an explicit `resolve_purchase_tile` action or make `request_purchase_tile` own both prompt and mutation only until the modifier context is introduced.

## Rent Pipeline

### Context

```python
RentContext(
    tile_context: TileEffectContext,
    owner_id: int,
    base_rent: int,
    final_rent: int,
    payer_id: int,
    rent_breakdown: list[dict],
    one_shot_consumptions: list[dict],
)
```

### Flow

```text
owned land arrival
-> build RentContext
-> apply TileRentModifier[]
-> apply WeatherRentModifier[]
-> apply CharacterRentModifier[]
-> apply TrickRentModifier[]
-> queue/pay rent
-> queue post-rent landing effects
```

### Modifier Order

Suggested deterministic order:

1. base tile rent
2. tile-local modifiers
3. weather/color modifiers
4. global rent modifiers
5. owner/payer character modifiers
6. trick modifiers
7. floor/clamp
8. one-shot consumption

The order must be documented and tested because players will notice rent math.

### Weather/Color Example

Instead of:

```text
if weather doubles color:
    rent *= 2
```

Use:

```text
WeatherColorRentModifier
  applies when current weather targets context.zone_color
  appends breakdown item
  multiplies final_rent
```

This makes tile color a trait/metadata input rather than hardcoded rent logic.

## Score Token Pipeline

### Context

```python
ScoreTokenContext(
    tile_context: TileEffectContext,
    target_tile_index: int,
    base_amount: int,
    final_amount: int,
    capacity_remaining: int,
    placement_source: str,
)
```

### Flow

```text
own tile visit or purchase completion
-> build ScoreTokenContext
-> apply TokenGainModifier[]
-> apply TokenCapacityModifier[]
-> if human/AI target choice needed:
     queue request_score_token_placement
     queue place_score_token
-> else:
     queue/place_score_token
```

Score-token placement should become an action so it can be checkpointed separately from rent, purchase, or own-tile visit effects.

## Fortune And Trick Integration

Fortune and trick effects should use the same patterns:

- movement effects produce `apply_move` actions
- target-selection effects produce `resolve_fortune_*` or `resolve_trick_*` actions
- purchase/rent/token changes produce context modifiers or queued domain actions

Examples:

- a trick that makes the next purchase free becomes `FreePurchaseModifier`
- a trick that doubles rent becomes `RentModifier`
- a fortune that grants an empty tile becomes `resolve_fortune_*` action using purchase/ownership helpers
- a fortune that moves to another tile becomes `apply_move -> resolve_arrival`

## Redis And Recovery Contract

Every meaningful mutation must be recoverable from Redis:

- pending actions are serialized in `GameState.pending_actions`
- action payloads must include enough context to resume after restart
- one-shot flags are consumed only inside the successful action
- decision prompts must leave the current action queued on interruption

Modifier contexts do not need to be persisted as live Python objects. They should be rebuilt deterministically from Redis-owned state when the action resumes.

If a modifier context includes a value that must not be recalculated after a prompt, store the resolved value in the action payload:

```json
{
  "type": "resolve_purchase_tile",
  "payload": {
    "tile_index": 12,
    "base_cost": 4,
    "final_cost": 0,
    "cost_breakdown": [
      {"modifier": "free_purchase_trick", "delta": -4}
    ],
    "one_shot_consumptions": ["trick_free_purchase_this_turn"]
  }
}
```

## Anti-Hardcoding Rules

New tile/economy effects should not:

- directly inspect weather names inside purchase/rent mutation
- directly consume trick flags before a decision succeeds
- directly move players from a tile/fortune/trick handler
- directly place score tokens as a side effect of unrelated actions
- create new one-off rent/purchase calculations outside the modifier pipeline

New effects should:

- add a trait when the tile category changes behavior
- add a modifier when cost/rent/token math changes
- add an action when state mutation or human choice is involved
- add a breakdown entry so logs and UI can explain the result

## Migration Plan

### Phase 1. Context Skeleton

- Add `tile_effects.py` or `rules/tile_effects.py`.
- Define `TileEffectContext`, `PurchaseContext`, `RentContext`, and `ScoreTokenContext`.
- Add builders that read from `GameState` and `TileState`.
- Keep current behavior unchanged.

### Phase 2. Purchase Cost Modifiers

- Move purchase cost calculation into `PurchaseContext`.
- Add `FreePurchaseModifier`.
- Add breakdown metadata to purchase prompt context and purchase result.
- Keep existing `request_purchase_tile` behavior until tests prove parity.

### Phase 3. Purchase Action Split

- Introduce `resolve_purchase_tile`.
- Ensure prompt interruption leaves the purchase action queued.
- Consume one-shot purchase flags only after successful mutation.

### Phase 4. Rent Modifiers

- Move `_effective_rent()` internals into `RentContext` modifiers.
- Preserve current result payload shape.
- Add rent breakdown metadata for logs and frontend reveal surfaces.

### Phase 5. Score Token Actions

- Introduce `request_score_token_placement` and `place_score_token`.
- Move own-tile visit placement and purchase placement through the same action family.

### Phase 6. Trait Registry

- Replace landing dispatch conditionals with a trait registry.
- Keep event hooks as extension points around trait production.
- Make tile behavior additions data-driven by metadata plus trait mapping.

## Test Strategy

Unit tests:

- purchase context builds base/final cost
- free purchase modifier reduces cost to zero and consumes only on success
- rent modifiers apply in documented order
- weather/color rent modifier produces a visible breakdown entry
- score-token capacity clamps final placement

Integration tests:

- purchase prompt interruption preserves one-shot free purchase flag
- resumed purchase consumes the flag exactly once
- rent after restart uses the same final rent and breakdown
- own-tile score token placement resumes from pending action

Contract tests:

- production effect modules do not call immediate movement compatibility helpers
- new rent/purchase calculations go through modifier builders
- action payloads for human decisions include enough context to resume

## First Implementation Slice

Recommended first commit:

1. Add context dataclasses and purchase modifier interfaces.
2. Build `PurchaseContext` from current purchase helper.
3. Move `trick_free_purchase_this_turn` into `FreePurchaseModifier`.
4. Add tests for prompt interruption and successful resume.
5. Do not change rent/token code in the same slice.

This gives the architecture a real foothold while keeping the blast radius small.

## Implementation Notes

### 2026-04-30 Purchase Context Seed

Implemented:

- `GPT/tile_effects.py` defines `TileEffectContext`, `PurchaseContext`, and `PurchaseModifier`.
- Purchase cost calculation now builds a deterministic context before the purchase decision.
- `BuilderFreePurchaseModifier` applies innate builder free construction without consuming one-shot purchase flags.
- `FreePurchaseModifier` applies `free_purchase_this_turn` and `trick_free_purchase_this_turn` as one-shot cost modifiers.
- One-shot free purchase flags are consumed only after successful ownership mutation.
- Purchase results include `base_cost` and `purchase_context` payloads for logs, prompts, and later UI explanation.

Still pending:

- split final purchase mutation into a separate `resolve_purchase_tile` action
- migrate rent calculation into `RentContext`
- migrate score-token placement into resumable actions
