# Tile Trait Action Pipeline

Status: ACTIVE
Updated: 2026-05-05

## 1. Purpose

Tile effects are runtime actions owned by modules. Landing on a tile may enqueue prompt, payment, movement, purchase, score-token, or simultaneous-response work, but every follow-up must stay inside the active frame and module cursor.

## 2. Core Flow

`MapMoveModule` moves the player and records pass-through facts such as LAP crossings.

`ArrivalTileModule` reads the destination tile and emits catalogued actions.

Native sequence modules resolve those actions:

- `RentPaymentModule`
- `PurchaseDecisionModule`
- `PurchaseCommitModule`
- `UnownedPostPurchaseModule`
- `ScoreTokenPlacementPromptModule`
- `ScoreTokenPlacementCommitModule`
- `LandingPostEffectsModule`
- `TrickTileRentModifierModule`

Unknown tile actions fail with `UnknownActionTypeError` until added to the action catalog and module inventory.

## 3. Rent

rent payment is now actionized.

The canonical action is `resolve_rent_payment`; the owner module is `RentPaymentModule`.

The module receives the payer, owner, tile id, amount, and modifier context. It applies payment, emits payment events, and returns to the parent `SequenceFrame` without restarting movement or arrival.

## 4. Purchase

Unowned purchasable tiles emit a purchase decision prompt owned by `PurchaseDecisionModule`.

Accepted decisions resume into `PurchaseCommitModule`, then `UnownedPostPurchaseModule` handles post-purchase effects such as score-token placement.

## 5. LAP Reward

LAP crossings are detected during movement and resolved by a LAP reward module boundary. Prompt exposure comes from the backend only after the engine has committed the module checkpoint.

## 6. Modifiers

Character, trick, fortune, and tile effects write modifier facts to module context. Consumer modules read the facts at their own boundary:

- dice modifiers affect dice/movement modules
- map movement modifiers affect `MapMoveModule`
- arrival modifiers affect `ArrivalTileModule`
- rent modifiers affect `RentPaymentModule`
- purchase modifiers affect purchase modules

## 7. Verification

Coverage must prove:

- rent resolves through `resolve_rent_payment` and `RentPaymentModule`
- movement restart does not repeat arrival
- purchase prompts resume by stored continuation
- LAP reward prompts are engine-owned
- uncatalogued actions are rejected before mutation
