# [PROPOSAL] CLAUDE Visualization Substrate Follow-up

Status: `PROPOSAL`
Owner: `CLAUDE`
Last reviewed on: `2026-03-29`

## Purpose
This document tracks the remaining CLAUDE-side substrate work after the initial viewer compatibility push.

It should no longer be read as:
- "add more aliases so GPT keeps working"

It should now be read as:
- "finish substrate and validator convergence toward the shared contract"

Primary references:
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- `PLAN/[PROPOSAL]_GPT_CLAUDE_VISUALIZATION_FIX_SPLIT.md`

## Status Summary

### Already materially done
- baseline replay/live substrate exists
- validator/compatibility path exists
- core event families used by GPT Phase 1-4 are present enough for replay/live/human-play baseline

### What changed in priority
The older focus on alias expansion is no longer the main goal.

Why:
- GPT now consumes canonical public-state names in the human-play renderer
- continuing to preserve every alias as a first-class contract risks freezing drift into the system

So the remaining CLAUDE work should prioritize:
- canonical naming
- contract-stable event/state payloads
- validator maintenance
- lower-layer bug fixes when verification reveals a real substrate gap

## CLAUDE Work Status

### C1. Contract-first audit of event emission
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29`

Closed scope:
- canonical dice, movement, purchase, rent, and snapshot field families were refreshed
- validator coverage was updated alongside the canonical event payloads

Opinion:
- this item should stay closed unless a new contract revision is explicitly proposed

### C2. Canonical public-state naming freeze
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29`

Frozen canonical names:
- `public_tricks`
- `mark_status`
- `marker_owner_player_id`
- `owned_tile_count`
- `placed_score_coins`

Opinion:
- alias preservation should not become the long-term contract strategy again

### C3. Validator refresh toward canonical contract
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29`

Result:
- validator checks now treat canonical names as primary
- canonical replay/live payloads are the expected path

### C4. Phase 5 substrate completeness review
Priority: `P2`
Status: `DONE`
Closed: `2026-03-29`

Result:
- `player_move.path`, `movement_source`, `crossed_start` verified sufficient
- `lap_reward_chosen` public payloads verified sufficient for Phase 5 renderer growth
- `public_effects`, weather, fortune verified complete under current Phase 5 expectations
- `trick_used` now emits to the visual stream with readable public detail
- `marker_flip` now emits to the visual stream with readable public detail
- `mark_resolved` now carries public summary detail across branches
- `CLAUDE/validate_gpt_viewer_compat.py` passes on representative seeds (`42`, `137`, `999`, `13`)

Opinion:
- all material Phase 5 substrate gaps are now closed

### C5. Renderer-neutral portability discipline
Priority: `P2`
Status: `ASSESSED`

Assessment:
- no urgent violation is visible right now
- `tile_kind` and `public_effects` remain acceptable transport-level values for current HTML/runtime work

Opinion:
- keep this as a rule-of-engagement item, not an active blocker

### C6. `remaining_dice_cards` CLAUDE public-state support
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29`

Result:
- CLAUDE public state now carries the same remaining dice-card concept expected by GPT viewers

### C7. `public_effects.all_rent_waiver` convergence
Priority: `P2`
Status: `DONE`
Closed: `2026-03-29`

Result:
- CLAUDE public-effect output now includes the effect-name family expected by GPT viewers

## What This Proposal Should No Longer Recommend
This proposal should no longer recommend the following as a primary direction:
- making legacy alias fields the stable long-term contract
- treating GPT viewer compatibility as the same thing as contract completion

Compatibility is useful.
Canonical convergence is more important now.

## Completion Standard
This proposal can be treated as closed when:
- canonical public-state naming remains frozen
- validators continue to treat canonical names as primary
- no remaining Phase 5 renderer expansion exposes missing substrate fields

Current opinion:
- most of the originally proposed CLAUDE corrective work is already closed
- Phase 5 completeness verification is also closed
- the remaining CLAUDE role is validator maintenance plus lower-layer bug-fix follow-up if future Phase 5 growth reveals a real payload gap
