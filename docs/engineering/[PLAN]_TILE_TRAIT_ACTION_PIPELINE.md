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

Implemented migration:

- `request_purchase_tile` performs purchase prechecks, builds `PurchaseContext`, asks the purchase decision, and queues `resolve_purchase_tile` only when the player chooses to buy.
- `resolve_purchase_tile` performs the final mutation: resource payment, ownership transfer, first-purchase token placement, one-shot purchase flag consumption, AI decision logging, and `tile_purchased` visualization.
- `resolve_unowned_post_purchase` remains the landing follow-up boundary and now reads the final purchase result written by `resolve_purchase_tile`.

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

- split rent payment itself into a queued action if animation/recovery needs a payment boundary

### 2026-04-30 Purchase Resolution Action Split

Implemented:

- `request_purchase_tile` no longer mutates ownership on an affirmative decision.
- Affirmative purchase decisions insert `resolve_purchase_tile` at the front of `GameState.pending_actions`, preserving the existing follow-up order.
- Prompt interruption still leaves the original `request_purchase_tile` action queued and preserves one-shot purchase flags.
- Skip/fail decisions do not queue `resolve_purchase_tile`; they write the landing purchase result directly for post-purchase follow-up handling.
- Successful `resolve_purchase_tile` consumes one-shot free-purchase flags exactly once after the ownership mutation.

Validation:

- `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_tile_effects.py -k 'purchase or prompt_action'`
- `./.venv/bin/python -m pytest GPT/test_rule_fixes.py -k 'purchase or matchmaker or madangbal or same_tile'`

Next:

- split rent payment itself into a queued action if animation/recovery needs a payment boundary

### 2026-04-30 Rent Context Seed

Implemented:

- `GPT/tile_effects.py` defines `RentContext`, `RentModifier`, and ordered rent modifiers.
- Normal rent calculation now records a deterministic breakdown for:
  - base rent
  - tile-specific rent modifier
  - color/weather rent doubling
  - global rent double/half modifiers
  - payer/owner personal rent half modifiers
  - normal-rent waiver flags
- `handle_rent_payment()` uses `RentContext.final_rent` and consumes normal-rent waiver counts from the context.
- `_effective_rent()` uses the same builder with `include_waivers=False`, preserving swindler/derived-cost behavior where "rent-like amount" is used as a price but normal rent waivers must not apply.
- Rent events now include `base_rent` and `rent_context` payloads.

Validation:

- `./.venv/bin/python -m pytest GPT/test_tile_effects.py GPT/test_rule_fixes.py -k 'rent or weather_color or trade_pass or purchase or matchmaker or same_tile'`
- `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'queued_arrival_on_rent or purchase or prompt_action'`

### 2026-04-30 Score Token Placement Context Seed

Implemented:

- `GPT/tile_effects.py` defines `ScoreTokenPlacementContext`.
- `_place_hand_coins_on_tile()` now builds the placement context before mutating:
  - `state.tile_coins`
  - `player.hand_coins`
  - `player.score_coins_placed`
  - strategy `coins_placed`
- Placement results now include `placement_context` payloads for future logs/UI explanation.
- The context records tile capacity, current tile tokens, available room, player hand tokens, rule/request limit, final placement amount, and blocked reason.

Validation:

- `./.venv/bin/python -m pytest GPT/test_tile_effects.py GPT/test_rule_fixes.py -k 'score_token or coin or purchase_places or rent or trade_pass'`
- `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'purchase or queued_arrival_on_rent or prompt_action'`

Next:

- introduce `request_score_token_placement` for policy-selected own-tile visit placement

### 2026-04-30 Purchase Score Token Placement Action

Implemented:

- Added `resolve_score_token_placement` as a queued action handler.
- `resolve_purchase_tile` no longer mutates first-purchase score tokens inline.
- When a newly purchased tile can receive a score token, `resolve_purchase_tile` queues `resolve_score_token_placement` before `resolve_unowned_post_purchase`.
- `resolve_score_token_placement` updates the pending purchase result's `placed` payload before post-purchase landing effects are finalized.
- The buying path with placeable score tokens is now:

```text
resolve_arrival
-> request_purchase_tile
-> resolve_purchase_tile
-> resolve_score_token_placement
-> resolve_unowned_post_purchase
```

Validation:

- `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'purchase or score_token or prompt_action'`
- `./.venv/bin/python -m pytest GPT/test_rule_fixes.py GPT/test_tile_effects.py -k 'purchase_places or score_token or coin or rent or trade_pass'`

Still pending:

- rent payment still mutates inside `rent.payment.resolve`; split it only when a separate payment animation/recovery boundary is required

### 2026-04-30 Own Tile Score Token Request Split

Implemented:

- Added `request_score_token_placement` as the decision-bearing score-token action.
- Own-tile visit no longer opens `choose_coin_placement_tile` inside `resolve_arrival` on the queued path.
- The queued own-tile visit path is now:

```text
resolve_arrival
-> request_score_token_placement
-> resolve_score_token_placement
```

- Prompt interruption reinserts `request_score_token_placement`, preserving the already committed own-tile coin gain and leaving tile tokens unchanged until resolution.
- `resolve_score_token_placement` records the final landing result when it is carrying an own-tile base event.

Validation:

- `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'own_tile or score_token or purchase or prompt_action'`
- `./.venv/bin/python -m pytest GPT/test_rule_fixes.py GPT/test_tile_effects.py -k 'coin or score_token or purchase_places or rent or trade_pass'`

Next:

- audit remaining inline economic mutations and only split additional actions where there is a real decision, animation, or recovery boundary

## Inline Economic Mutation Audit

### Boundary Rule

Do not split every cash/shard/token mutation just because it mutates state. Split only when at least one condition is true:

- a human or AI decision can interrupt the flow
- the client needs a distinct animation/presentation beat
- Redis recovery needs to persist between "decision accepted" and "state mutated"
- the mutation is reused by multiple rule sources and needs a shared context/modifier contract

Keep an effect inline when it is atomic, deterministic, and has no independent prompt or presentation boundary.

### Current Classification

Already split:

- normal purchase prompt: `request_purchase_tile`
- purchase mutation: `resolve_purchase_tile`
- first-purchase score-token placement: `resolve_score_token_placement`
- own-tile score-token prompt: `request_score_token_placement`
- own-tile score-token mutation: `resolve_score_token_placement`
- queued movement and arrival: `apply_move -> resolve_arrival`
- mark effects with target-player timing: scheduled `resolve_mark`
- decision-bearing fortune target effects: `resolve_fortune_*`

Context/modifier calculation in place:

- purchase cost: `PurchaseContext`
- rent amount: `RentContext`
- score-token placement amount: `ScoreTokenPlacementContext`

Intentionally inline for now:

- weather round effects that immediately grant/pay resources
- F/MALICIOUS/S tile atomic payouts or payments
- same-tile bonus cash/shard effects after a landing result
- direct rent payment inside `rent.payment.resolve`
- trick-card immediate resource effects
- force sale / takeover helpers that are already single atomic ownership transactions

Watch list:

- rent payment can become `resolve_rent_payment` if the UI needs a payment animation checkpoint separate from landing post-effects
- force sale / takeover can become actionized if future cards add target-selection prompts or multi-step animations around ownership transfer
- global all-player payments can get a `resolve_global_payment` action if recovery needs to resume after each payer

### Guardrail

`GPT/test_action_pipeline_contract.py` now prevents default landing effect handlers from reopening purchase or score-token placement prompts inline. New runtime purchase/token decisions should be represented as queued request/resolve actions.
