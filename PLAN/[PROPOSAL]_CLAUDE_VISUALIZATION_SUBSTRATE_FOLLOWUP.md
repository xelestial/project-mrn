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
- Phase 5 completeness checks

## Open CLAUDE Work

### C1. Contract-first audit of event emission
Priority: `P1`
Status: `OPEN`

Need to verify against `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`:
- required event families exist where expected
- event payloads are contract-shaped rather than implementation-shaped
- replay/live emission is sufficiently stable for renderer consumption

Important examples:
- `fortune_drawn`
- `fortune_resolved`
- `bankruptcy`
- `trick_window_open`
- `trick_window_closed`
- `turn_end_snapshot`

### C2. Canonical public-state naming freeze
Priority: `P1`
Status: `OPEN`

Canonical names should be treated as authoritative:
- `public_tricks`
- `mark_status`
- `marker_owner_player_id`
- `owned_tile_count`
- `placed_score_coins`

What should change:
- CLAUDE-side docs, validators, and follow-up notes should stop presenting legacy alias names as primary
- if aliases remain temporarily for compatibility, they should be documented as transitional only

### C3. Validator refresh toward canonical contract
Priority: `P1`
Status: `OPEN`

Current need:
- `validate_gpt_viewer_compat.py` should increasingly validate canonical contract coverage, not just legacy compatibility

Practical goal:
- keep enough compatibility checking to avoid regressions
- but make canonical shared-contract names the first-class validation target

### C4. Phase 5 substrate completeness review
Priority: `P2`
Status: `OPEN`

Need explicit readiness review for:
- movement trace completeness
- dice detail completeness
- landing resolution detail
- rent transfer detail
- lap reward detail
- public effect lifetime continuity

Goal:
- Phase 5 UI should not need renderer heuristics to guess public game state

### C5. Renderer-neutral portability discipline
Priority: `P2`
Status: `OPEN`

Need to preserve:
- browser-friendly payloads now
- Unity-portable structure later

Rule:
- renderer-only convenience fields should not silently become core contract requirements

## What This Proposal Should No Longer Recommend
This proposal should no longer recommend the following as a primary direction:
- making legacy alias fields the stable long-term contract
- treating GPT viewer compatibility as the same thing as contract completion

Compatibility is useful.
Canonical convergence is more important now.

## Completion Standard
This proposal can be treated as closed when:
- canonical public-state naming is explicitly frozen
- validators treat canonical names as primary
- remaining critical event families are contract-audited
- Phase 5 substrate completeness is reviewed and documented
