# Game-Rules Alignment Audit and Engine Fix Plan

Status: `ACTIVE`
Owner: `GPT`
Source of truth: `docs/Game-Rules.md`
Scope: `engine turn structure / round order / core rule sequencing / high-risk rule mismatches`

## Goal
Bring the current runtime back into alignment with `docs/Game-Rules.md`, prioritizing turn structure and ordering semantics first, because sequence errors invalidate downstream effects even when individual abilities are implemented.

---

## Audit Summary

The current runtime is only **partially aligned** with `docs/Game-Rules.md`.
The most critical divergence is not card numbers or balance values, but **phase ordering** and **round structure**.

### Critical mismatches found

1. **Round start order mismatch**
   - Current engine: `draft -> weather`
   - Rules doc: `weather reveal -> draft -> turn order`
   - Current code location: `GPT/engine.py::_start_new_round()`

2. **Doctrine / marker flip timing mismatch risk**
   - Rules doc states doctrine choice affects marker ownership and active-face switching at **round end**, with the next round using the resulting state.
   - Current runtime already does marker flip resolution at round start via `_resolve_marker_flip(state)` before draft, but this flow needs formal validation against exact doctrine acquisition timing and whether multiple card flips are currently constrained.

3. **Turn sequence mismatch risk**
   Rules doc turn order:
   - pending marks on me
   - character ability
   - trick card window
   - dice/movement
   - landing branch
   - round-end doctrine/marker handling after all players

   Current engine mostly follows:
   - resolve pending marks
   - apply character start
   - trick window
   - movement choice
   - movement resolve / landing resolve
   - marker management at end of player turn

   This is close, but marker / doctrine ownership changes and active-face switching must be validated to remain **round-end global effects**, not effectively per-turn effects.

4. **End-condition system mismatch**
   Rules doc win/end:
   - F/end timer reaches 0
   - one player monopolizes 3 zones
   - 2 players bankrupt

   Current runtime/summary vocabulary in recent runs includes:
   - `ALIVE_THRESHOLD`
   - `F_THRESHOLD`
   - `NINE_TILES`

   This is a direct source-of-truth mismatch and must be reconciled.

5. **Economy / lap reward model mismatch**
   Rules doc specifies point-budget-based initial choice and lap reward choice.
   Current runtime uses fixed reward values from config/rules.
   This is not a small data mismatch; it is a model mismatch.

---

## Priority Principles

### P0 — sequencing correctness first
Before touching card data tables, ensure the runtime obeys the correct order of:
- weather
- draft
- final character reveal/selection
- turn order
- mark resolution timing
- character skill timing
- trick timing
- movement
- landing
- doctrine marker transfer / active-face switching
- end evaluation

### P1 — end conditions next
The runtime must end games for the reasons described in `docs/Game-Rules.md`, or the balance layer becomes incomparable to the design document.

### P2 — economy / reward model
Initial PT allocation and lap reward PT allocation need explicit design decision:
- either migrate engine to PT-budget model
- or formally revise `docs/Game-Rules.md`

### P3 — card table exactness
After sequencing/end/economy alignment, audit detailed card text one by one.

---

## Concrete Findings by Engine Area

### 1. `engine.py::_start_new_round()`
Current sequence is effectively:
1. reset round flags
2. resolve marker flip
3. run draft
4. apply round weather
5. derive round order

Required rules sequence:
1. reveal weather
2. run draft
3. determine turn order by chosen character priority

### Required fix
Refactor `_start_new_round()` so that weather is revealed/applied before draft resolution, unless the design intentionally requires weather after draft. If intentional, `docs/Game-Rules.md` must be updated instead. Current plan assumes the document is authoritative.

---

### 2. `engine.py::_take_turn()`
Current sequence is:
1. skipped-turn short-circuit
2. resolve pending marks
3. apply weather extra dice
4. apply character start
5. trick window
6. choose movement
7. resolve movement / landing
8. marker management

### Assessment
This is broadly aligned with the document.
Main risk is whether marker management is doing anything that should only happen after **all** players finish the round.

### Required fix work
Audit `_apply_marker_management()` and event handlers behind `marker.management.apply` to ensure:
- doctrine ownership transfer timing matches rules
- active-face switching happens after all turns, not prematurely
- marker uniqueness constraints remain valid

---

### 3. End condition pipeline
Current end evaluation uses injected end rules and recent runtime outputs show non-document reasons.

### Required fix
Replace or reconfigure end evaluation so the runtime uses only:
- `F reaches 0`
- `three monopolized zones`
- `two bankrupt players`

Also verify winner resolution logic remains:
- tiles owned + placed score tokens
- tiebreak by cash

If current `state.total_score()` includes anything else, it must be audited.

---

### 4. Initial economy / lap rewards
Document requires:
- start cash 20
- additional start-resource PT allocation
- lap reward PT allocation
- finite reward pools

Current runtime has:
- fixed starting shards / cash / coins
- fixed lap reward values

### Required fix decision
This requires a product-level decision:
1. implement PT allocation and finite global pools in runtime
2. or explicitly revise the rules document to the current fixed-value model

Because the user identified `docs/Game-Rules.md` as the authoritative full rules reference, the current plan assumes **runtime should move toward the doc**.

---

## Current Progress Snapshot

### Completed analysis work
- Read the latest `docs/Game-Rules.md` as the authoritative rules source.
- Audited the current runtime sequence in `GPT/engine.py`.
- Audited rule-side handlers in `GPT/effect_handlers.py`.
- Confirmed the highest-risk sequencing mismatches:
  - round start currently runs `marker flip -> draft -> weather`
  - marker/doctrine ownership currently changes at the end of each player turn, not clearly at round end
- Confirmed that turn-internal sequencing is **mostly** aligned:
  - pending marks on victim turn start
  - character start ability
  - trick window
  - movement
  - landing resolution

### Newly confirmed data-level mismatch signals
- `effect_handlers.py` still contains weather-name handling that does not match the latest rules wording one-to-one.
  - examples seen in code: `공개 잔꾀`, `재활용의 날`, `산불의 날`
  - latest source-of-truth document instead uses updated terminology/card set such as `잔꾀 부리기`, `모든 것을 자원으로`, `긴급 피난`
- Smoke execution after preliminary sequencing edits still surfaced removed/outdated weather entries such as `배신의 징표` in runtime history, which strongly suggests that the current runtime data tables are not yet fully synchronized to the latest rules document.

### Preliminary execution result
- A 5-game smoke run was completed successfully after local P0 sequencing edits.
- This confirmed that the engine does not immediately crash when weather/draft ordering is adjusted.
- However, the run also confirmed that **data-table alignment is still incomplete**, so a successful smoke run does **not** yet imply rules alignment success.

### Important status note
- Sequencing analysis is complete.
- A local prototype patch for P0 sequencing was explored and smoke-tested.
- The branch currently contains the PLAN and collection tooling work, but the full verified runtime alignment patch has **not** yet been pushed as a completed/validated engine fix.
- The user requested: patch first, then verify with 100 games, then push.
- Therefore the engine-alignment work remains **in progress** until:
  1. sequencing patch is finalized,
  2. card/weather/trick/fortune data mismatches are reconciled,
  3. 100-game validation succeeds,
  4. then the code patch is pushed.

---

## Implementation Plan

### Phase A — sequencing correction (P0)
1. Audit and patch `_start_new_round()` ordering
   - weather before draft
   - preserve marker flip timing only if consistent with round-end doctrine ownership semantics
2. Audit `_apply_marker_management()` / marker event handlers
3. Add regression tests for exact round order event sequence

#### Deliverables
- engine patch
- event log assertions
- tests for `weather -> draft -> final character -> round order`

---

### Phase B — turn-order correctness tests (P0)
Add focused tests covering:
- pending mark resolution on victim turn start
- assassin skip/reveal timing
- hunter pull landing processed before movement choice
- baksu/manshin trigger timing on target turn
- trick timing strictly after character skill and before movement

#### Deliverables
- test suite additions in `test_rule_fixes.py` or new targeted test module

---

### Phase C — end-condition replacement (P1)
1. Audit current end-rule injection path
2. Remove/disable non-document end reasons from default ruleset
3. Rewire default end evaluation to document conditions only
4. Revalidate winner tie-break ordering

#### Deliverables
- config/ruleset/end-rule patch
- regression tests for all three end conditions

---

### Phase D — economy model alignment (P2)
1. Introduce start-resource PT choice model
2. Introduce lap reward PT choice model
3. Introduce finite global reward pools
4. Validate 객주 bonus interactions against PT selection model

#### Deliverables
- runtime changes
- policy changes for start/lap choices
- tests for pool depletion and 객주 bonuses

---

### Phase E — card-by-card audit (P3)
Audit and patch, in order:
1. doctrine cards
2. pabal/ajeon/chuno/escape slave
3. baksu/manshin
4. matchmaker/builder/swindler/gakju
5. trick cards
6. fortune cards
7. weather cards

#### Deliverables
- mismatch matrix
- implementation fixes
- card-text regression tests

---

## Immediate Next Actions

1. Finalize and re-apply the sequencing patch in committed engine code.
2. Build a mismatch table for `characters / tricks / fortune / weather` against `docs/Game-Rules.md`.
3. Patch weather/trick/fortune naming and behavior drift before claiming alignment.
4. Patch end conditions to document-default behavior.
5. Only then proceed to economy/PT model alignment.
6. Run a 100-game validation after the sequencing + data-table patch set is in place.

---

## Notes
- `배신의 징표` removal is acknowledged; it should not be treated as a current mismatch if absent from the latest source-of-truth document.
- Any conflict between older changelog/runtime experiments and `docs/Game-Rules.md` should be resolved in favor of `docs/Game-Rules.md` unless the document is intentionally revised.
- A smoke run succeeding is necessary but not sufficient; the real acceptance gate is rules alignment plus a successful 100-game validation run.
