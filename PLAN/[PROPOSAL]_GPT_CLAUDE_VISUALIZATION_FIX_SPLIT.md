# [PROPOSAL] GPT / CLAUDE Visualization Fix Split After PR22

Status: `PROPOSAL`
Reviewed against: `main`
Reviewed on: `2026-03-29`

## Purpose
This document records the corrective work that should happen after the `main`-branch visualization review following PR22.

It does not replace the canonical runtime plan.
It exists to answer one narrower question:

- what must be corrected now
- which part belongs to GPT
- which part belongs to Claude

The canonical top-level plan remains:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

The shared boundary baseline remains:
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Why This Proposal Is Needed
The current `main` state is usable, but not yet cleanly aligned with the intended Phase 4 and Phase 5 target.

The review found four concrete issues:
- human-play final character selection can crash the live game thread
- human-play HTML reads stale or mismatched public-state field names
- plan documents overstate what is complete and point to files that do not exist on `main`
- the runtime still drifts from the shared prompt/event contract

So the next work should not be treated as "new feature expansion".
It is primarily corrective alignment work.

## Re-review After PR25

Reviewed again against `origin/main` after PR #25 merged.

Verification used:
- `python CLAUDE\\validate_gpt_viewer_compat.py` → pass
- `python GPT\\test_human_play.py` → still prints `[human-game] ERROR: 8` and ends with `KeyError: 8`, while the test runner still reports `Phase 4: ALL TESTS PASSED`

Updated interpretation:

- several smaller GPT-side issues have already landed on `main`
  - human-seat 1-indexing in `play_html.py`
  - player color indexing normalization in `play_html.py`
  - `submit_response()` lock scope hardening in `human_policy.py`
  - prompt `player_id` values normalized to 1-indexed
- Claude PR #25 successfully strengthened the legacy GPT-viewer compatibility validator
- however, the primary blockers in this proposal remain unresolved:
  - Phase 4 human play can still crash on final character selection
  - `play_html.py` still consumes stale alias/public-state field names
  - Phase 4 tests are still false-positive
  - plan/status documents still overstate Phase 4 maturity

Net result:
- Claude follow-up has moved from "expand compatibility checks" to "converge on canonical contract names"
- GPT still owns the immediate blocking work

## Main-Branch Review Summary

### Confirmed Good
- Phase 1 visual substrate exists and tests pass
- Phase 2 replay viewer exists and tests pass
- Phase 3 live spectator exists at MVP level
- Phase 4 browser-driven human input round-trip exists in baseline form
- several smaller Phase 4 UI/runtime bugs have already been fixed on `main`

### Confirmed Problems
- `GPT/viewer/human_policy.py` final-character response can hand back a raw choice token that later becomes an invalid `current_character`
- `GPT/viewer/renderers/play_html.py` expects several public-state field names that no longer match `GPT/viewer/public_state.py`
- `GPT\test_human_play.py` can report success while a background game thread crashes
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md` and `PLAN/PLAN_STATUS_INDEX.md` describe a file/runtime shape that is ahead of actual `main`
- `GPT/viewer/events.py` and `GPT/viewer/human_policy.py` are not yet fully converged with `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- `CLAUDE/validate_gpt_viewer_compat.py` now passes, but it still validates several legacy alias names that should not become the long-term canonical contract

## Ownership Rule
Use this split:

- GPT owns upper runtime correction:
  - renderer
  - prompt adapter
  - human-play flow
  - plan/status document correction
  - application-level tests
- Claude owns lower substrate correction:
  - event schema stability
  - public-state fidelity
  - replay/live event completeness
  - contract-first field consistency below the renderer boundary

Shared rule:
- no side should silently rename contract fields on its own
- contract changes must be reflected in `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md` first or in the same change set

## GPT-Owned Corrective Work

### G1. Fix the human-play final-character crash
Priority: `P1`

Required correction:
- make final-character prompt responses resolve to the engine-valid character identifier, not a raw UI option token
- ensure `choose_final_character()` returns the same identifier family that `engine.py` expects for `current_character`

Minimum acceptance:
- no `KeyError` or equivalent crash occurs from legal human final-character selection
- `GPT\test_human_play.py` fails if the game thread throws

Affected area:
- `GPT/viewer/human_policy.py`
- `GPT/viewer/prompt_server.py`
- `GPT/engine.py`
- `GPT/test_human_play.py`

### G2. Fix renderer/public-state field drift
Priority: `P1`

Required correction:
- update the HTML renderer to consume the actual `PlayerPublicState` and `BoardPublicState` names on `main`
- stop relying on stale names such as:
  - `marker_owner_id`
  - `immune_to_marks`
  - `is_marked`
  - `trick_cards_visible`
  - `tiles_owned`
  - `score_coins_placed`

Expected canonical names should come from the actual public-state model or from the shared contract, not from renderer-local assumptions.

Minimum acceptance:
- marker owner
- mark status
- public tricks
- owned tile count
- placed score coins

These must all render from the authoritative public-state snapshot.

Affected area:
- `GPT/viewer/renderers/play_html.py`
- `GPT/viewer/public_state.py`
- renderer tests that cover human-play panels

### G3. Make Phase 4 tests trustworthy
Priority: `P1`

Required correction:
- background-thread exceptions must fail the test run
- human-play test should assert that the underlying game loop completes without hidden runtime exceptions
- add a direct regression test for final-character selection

Reason:
- Phase 4 cannot be treated as complete while the test suite can pass with a dead game thread

Affected area:
- `GPT/test_human_play.py`
- any helper used by `prompt_server` or live human-play harness

### G4. Normalize the prompt envelope at the GPT boundary
Priority: `P2`

Required correction:
- stop growing new ad-hoc prompt dictionaries in `human_policy.py`
- introduce a stable adapter that maps engine-side decision requests into the shared prompt contract fields
- renderer/UI code should depend on a single prompt envelope shape

Minimum target:
- `request_type`
- `legal_choices`
- `can_pass`
- `public_context`
- response shape that distinguishes display labels from returned values

This can be implemented as an adapter layer even if the engine internals are not fully rewritten.

### G5. Correct plan/status documents to match `main`
Priority: `P2`

Required correction:
- mark Phase 4 as `PARTIAL` rather than effectively complete
- reflect the actual runtime shape now present on `main`
- stop naming non-existent `main` files as if they are the active implementation

At minimum update:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- `PLAN/PLAN_STATUS_INDEX.md`

## CLAUDE-Owned Corrective Work

### C1. Close remaining substrate drift against the shared contract
Priority: `P1`

Required correction:
- audit replay/live event emission against `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- identify where the current substrate still emits implementation-shaped data instead of contract-shaped data
- remove ambiguity around public field names before Phase 5 UI layering grows further

Minimum acceptance:
- event names
- required event families
- field names used by `PlayerPublicState`, `BoardPublicState`, and tile snapshots

These should be contract-stable and renderer-agnostic.

### C2. Freeze authoritative public-state naming
Priority: `P1`

Required correction:
- define which public-state names are authoritative and keep them stable
- do not allow renderer-facing names to drift by branch or by implementation convenience
- add contract tests where useful so field-name drift is caught before integration

This is specifically important for:
- marker ownership
- mark status
- public trick exposure
- placed score coin counts
- owned tile counts

### C3. Verify replay/live event completeness for Phase 5 needs
Priority: `P2`

Required correction:
- confirm that the lower substrate exposes enough public information for the intended visual runtime without renderer heuristics
- identify any remaining gaps in:
  - movement traces
  - dice result detail
  - landing resolution detail
  - rent transfers
  - lap reward resolution
  - public effect lifetimes

This is a substrate responsibility because Phase 5 should consume authoritative data, not infer it in HTML.

Status update after PR25:
- legacy GPT-viewer compatibility validation is now in place and passing
- the remaining work here should focus on canonical completeness, not more alias expansion

### C4. Keep future portability constraints explicit
Priority: `P2`

Required correction:
- maintain a renderer-neutral event/state shape that can be consumed by browser HTML now and Unity later
- if a field is only useful for a specific renderer implementation, keep it outside the core contract or clearly label it as optional view metadata

The goal is to preserve low coupling for a future Unity transport and 3D client.

## Shared Coordination Items

### S1. Freeze value semantics for prompt choices
Both sides must agree on:
- what the user sees as a label
- what the engine receives as a returned value
- which identifier family is authoritative for characters, tiles, tricks, and players

This is the direct guardrail against the final-character crash class.

### S2. Freeze public seat and player-id semantics
Both sides must agree on:
- 0-based vs 1-based seat numbering
- whether `seat`, `player_id`, and rendered order are distinct concepts
- which one is canonical in the contract

### S3. Do not let the renderer invent rules
Renderer code may format and visualize.
It should not reconstruct rule meaning from missing or renamed fields.

If the renderer needs to guess, the substrate or contract is still incomplete.

## Recommended Execution Order
Execute in this order:

1. GPT fixes `G1` and `G3`
2. GPT fixes `G2`
3. GPT updates `G5`
4. Claude freezes `C1` and `C2` around canonical contract names
5. GPT applies `G4` using the stabilized contract boundary
6. Claude completes `C4` as Phase 5 readiness work

Reason:
- Phase 4 must stop crashing first
- renderer drift should be corrected before more UI polish is added
- document/status drift should be corrected before Phase 4 is treated as stable
- contract stabilization should happen before wider prompt/view expansion

## Final Opinion

After PR #25, the immediate owner is still `GPT`.

Reason:
- the user-visible and test-visible blockers that still reproduce now are all on the GPT side
- Claude-side follow-up succeeded in strengthening compatibility validation, but that line of work should now narrow to canonical contract convergence rather than more viewer-specific alias support

Practical takeaway:
- use this proposal as the current corrective backlog
- treat `PLAN/[PROPOSAL]_GPT_VISUALIZATION_BUG_FIXES.md` as a smaller renderer bug note
- treat `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_SUBSTRATE_FOLLOWUP.md` as a mostly historical Phase 2-S follow-up with one remaining contract-convergence role

## Completion Standard
This corrective proposal can be treated as complete only when all of the following are true:

- legal human final-character play no longer crashes runtime
- human-play tests fail on hidden game-thread exceptions
- HTML renderer uses current authoritative public-state names
- plan documents no longer overstate `main`
- prompt/event/public-state boundaries are explicitly aligned with `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Non-Goals
This proposal does not itself schedule:
- full trick UI support
- full animation polish
- large engine rewrite
- Unity implementation

Those should happen after the corrective alignment above is closed.
