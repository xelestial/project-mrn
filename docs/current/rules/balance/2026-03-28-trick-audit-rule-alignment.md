# 2026-03-28 Trick Audit Rule Alignment

This note records trick-rule changes applied after manual audit.

## Scope
- `성물 수집가`
- `우대권`
- `강제 매각`
- `신의뜻`
- `마당발`
- `뇌절왕`

## Applied Runtime Changes

### 성물 수집가
- F tile shard reward now doubles on the current turn.
- `F1`: `1 -> 2`
- `F2`: `2 -> 4`
- lap reward shard gain is intentionally unchanged.

### 우대권
- Changed from `one rent waiver` semantics to `all toll payments this turn`.
- Added explicit turn flag:
  - `player.trick_all_rent_waiver_this_turn`
- This flag is consumed by normal rent payment handling only.
- It does **not** zero `사기꾼` takeover cost.

### 강제 매각
- No longer treated as held anytime runtime behavior.
- It must be used during the player's trick phase.
- Runtime now arms:
  - `player.trick_force_sale_landing_this_turn = True`
- Landing on an owned tile consumes the armed effect.

### 신의뜻
- Same-tile shard payment now uses the acting player's shard count.
- It no longer reads the target player's shard count for settlement amount.

### 마당발
- Extra adjacent purchase flag is now cleared even when the extra purchase fails.
- This matches the clarified `one purchase opportunity only` interpretation.

### 뇌절왕
- No longer treated as held anytime runtime behavior.
- It must be used before movement.
- Runtime still arms:
  - `player.trick_zone_chain_this_turn = True`
- Extra dice count now follows the number of dice actually rolled earlier in the same turn:
  - `player.rolled_dice_count_this_turn`

## Internal Data Changes
- Added to `PlayerState`:
  - `trick_all_rent_waiver_this_turn: bool`
  - `rolled_dice_count_this_turn: int`

## Notes
- These changes are rule-alignment fixes, not balance tuning in the narrow numeric sense.
- They change real gameplay semantics and therefore should be treated as a balance-history event.
