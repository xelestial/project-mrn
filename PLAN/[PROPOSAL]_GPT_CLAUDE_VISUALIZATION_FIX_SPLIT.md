# [PROPOSAL] GPT / CLAUDE Visualization Fix Split After PR22

Status: `PROPOSAL`
Reviewed against: `main`
Last reviewed on: `2026-03-29`

## Purpose
This document tracks the corrective visualization work that still matters on `main`.

It is not the top-level product plan.
It is the current split of:
- what GPT has already corrected
- what GPT still owns
- what CLAUDE still owns

Canonical references:
- product/runtime plan: `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- shared contract baseline: `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Current Main-Branch Read

### Confirmed baseline-complete
- Phase 1 visual substrate exists
- Phase 2 replay viewer exists
- Phase 3 live spectator exists
- Phase 4 baseline human-play loop exists

### Confirmed recently corrected by GPT
- human-play final-character crash
- Phase 4 false-positive test path
- `play_html.py` stale public-state field usage
- plan/status document alignment for current `main`

### Confirmed recently corrected by CLAUDE
- substrate legacy alias expansion
- event payload canonical field names
- public-state alias cleanup
- validator canonical refresh

### Confirmed still open
- replay/renderer compatibility still has smaller polish-level gaps
- CLAUDE substrate completeness for Phase 5 should still be verified end-to-end

## Ownership Rule

- GPT owns upper runtime correction:
  - prompt adapter
  - human-play flow
  - renderer behavior
  - application tests
  - plan/status document correction
- CLAUDE owns lower substrate correction:
  - event/schema stability
  - authoritative public-state naming
  - replay/live event completeness
  - renderer-neutral contract fidelity

Shared rule:
- no one should silently rename contract fields in implementation only
- contract changes must be reflected in `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## GPT Status

### GPT work already closed

#### G1. Human-play final-character crash
Status: `DONE`

Closed by:
- `GPT/viewer/human_policy.py`
- `GPT/test_human_play.py`

Result:
- final-character choice now resolves to the engine-valid character identifier family
- Phase 4 no longer crashes from legal final-character input

#### G2. Renderer/public-state field drift in human play
Status: `DONE`

Closed by:
- `GPT/viewer/renderers/play_html.py`

Result:
- human-play renderer now consumes canonical public-state names
- stale fields such as `marker_owner_id`, `trick_cards_visible`, `tiles_owned`, `score_coins_placed` are no longer the active human-play dependency

#### G3. Phase 4 test trustworthiness
Status: `DONE`

Closed by:
- `GPT/viewer/live_server.py`
- `GPT/viewer/prompt_server.py`
- `GPT/test_human_play.py`

Result:
- background game-thread errors are surfaced through status
- Phase 4 regression path now fails when the runtime dies internally

#### G5. Correct plan/status documents to match `main`
Status: `DONE`

Closed by:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- `PLAN/PLAN_STATUS_INDEX.md`
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

Opinion:
- this item was correctly open when the status drift existed
- it should no longer remain open now that `main` documents explicitly reflect Phase 1-4 baseline completion and current Phase 5 focus

### GPT work still open

#### G4. Normalize the prompt envelope at the GPT boundary
Priority: `P1`
Status: `DONE`

What is already done:
- `GPT/viewer/prompt_contract.py` exists
- `human_policy.py` emits `request_type`, `legal_choices`, `can_pass`, `timeout_ms`, `fallback_policy`, and `public_context`
- remove temporary legacy mirrors such as `type` and `options`
- stop flattening `public_context` onto the top-level prompt envelope
- make replay/live/human-play consume the canonical envelope only

Opinion:
- this strictness/cleanup work is now complete on the GPT boundary
- remaining replay polish should be tracked separately from prompt-envelope convergence

#### G6. Replay-side compatibility cleanup
Priority: `P2`
Status: `PARTIAL`

What is already done:
- replay projection exists
- replay HTML/Markdown rendering exists
- replay wording/layout is materially more human-readable than the original baseline
- within-turn replay ordering now follows gameplay comprehension more closely
- replay frame state now updates movement, lap reward, rent, tile ownership, and remaining dice cards more immediately

What still remains:
- remove smaller renderer/projection inconsistencies
- keep replay wording and event ordering aligned with real gameplay comprehension
- tighten remaining contract drift where replay still accepts broader fallback shapes than necessary

Opinion:
- this is no longer a blocker-sized item
- it should be treated as continuing viewer polish and contract tightening

## CLAUDE Status

### CLAUDE work already closed

#### C1. Close substrate drift against the shared contract
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29`

Result:
- canonical event payload names were refreshed on the substrate side
- validator coverage was updated around those canonical payloads

#### C2. Freeze authoritative public-state naming
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29`

Frozen canonical names:
- `public_tricks`
- `mark_status`
- `marker_owner_player_id`
- `owned_tile_count`
- `placed_score_coins`

#### C5. `remaining_dice_cards` CLAUDE public-state support
Priority: `P1`
Status: `DONE`
Closed: `2026-03-29`

Result:
- CLAUDE-side public state now matches GPT-side expectation for remaining dice-card visibility

#### C6. `public_effects.all_rent_waiver` convergence
Priority: `P2`
Status: `DONE`
Closed: `2026-03-29`

Result:
- CLAUDE-side public-effect ledger now matches the public label family consumed by GPT viewers

### CLAUDE work still open

#### C3. Verify Phase 5 substrate completeness
Priority: `P2`
Status: `PARTIAL`

What still matters:
- verify that movement, lap reward, weather, fortune, and effect-ledger payloads are complete enough for Phase 5 UI growth
- verify that no remaining renderer-facing gaps only become visible in richer live-play flows

Opinion:
- this should stay open as a verification item, not as a broad rewrite item

#### C4. Keep renderer-neutral transport discipline
Priority: `P2`
Status: `ASSESSED`

Opinion:
- no urgent violation is visible right now
- this remains a guardrail, not an implementation blocker

## Shared Coordination Items

### S1. Freeze prompt value semantics
Status: `PARTIAL`

Need agreement on:
- what label the user sees
- what value the engine receives
- which identifier family is authoritative for characters, tiles, tricks, and players

Opinion:
- the runtime is already workable
- what remains is contract hardening, not baseline enablement

### S2. Freeze seat / player-id semantics
Status: `PARTIAL`

Need agreement on:
- 0-based internal seat vs 1-based public `player_id`
- whether `seat`, `player_id`, and rendered order are distinct concepts

Opinion:
- this matters more now that multi-human-seat support is entering the runtime surface

## Practical Recommendation

Treat this proposal as:
- a corrective ownership memo
- not a replacement for the canonical product plan

Use it to drive only the remaining true cleanup work:
- GPT prompt-envelope strict cleanup
- GPT replay polish/contract tightening
- CLAUDE Phase 5 substrate completeness verification
