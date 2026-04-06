# [PLAN] Next Work Priority Reference

Status: ACTIVE  
Updated: 2026-04-05  
Owner: GPT

## Purpose

This is the daily execution board.

If multiple plans exist, this file decides:
- what is blocked now
- what is active now
- what should wait

Always read this after the mandatory principles document.

## P0. Immediate Execution

### P0-1. Unified Decision API Stability

Source plans:
- `PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md`
- `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`

Goal:
- keep one canonical decision flow for both AI and human seats

Must remain true:
- `decision_requested -> decision_resolved(or decision_timeout_fallback) -> domain events`
- prompt ownership is seat-correct
- replay/live ordering stays deterministic

Current focus:
- preserve ordering while refactoring prompt UI and locale architecture
- do not let UI-side wording changes reintroduce stale-prompt or wrong-seat regressions
- continue after the runtime-wrapper unification slice:
  - AI seats already emit canonical decision lifecycle events at the server boundary
  - timeout/ack stream paths now share canonical payload builders too
  - next step is engine-side `DecisionPort` migration and typed provider cleanup

### P0-2. Human Play Runtime Recovery

Source plan:
- `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`

Goal:
- make the React/FastAPI surface feel like a playable board game, not a replay inspector

Current focus:
- spectator continuity during other players' turns
- strong weather / movement / landing / purchase / rent visibility
- prompt UX that is obvious, blocking only when actually actionable, and readable on first glance
- protect against previously reported regressions

### P0-3. Game Rules Parity

Source plan:
- `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
- `docs/Game-Rules.md`

Goal:
- engine / server / web must reflect the latest rules document

Current focus:
- human prompt semantics
- visual timing for weather / fortune / flips / marks / lap reward
- no UI rendering that implies the wrong rule

### P0-4. String Resource / Encoding Stabilization

Source plans:
- `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
- `PLAN/[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`

Goal:
- remove fragile inline user-facing strings from active UI surfaces
- prevent mojibake regressions
- prepare clean KO/EN switching

Current focus:
- keep locale resources outside components
- reduce remaining `uiText.ts` compatibility-bridge ownership
- move selector-visible wording toward locale-aware boundaries

## P1. Stabilization

### P1-1. Human E2E Hardening
- `1 human + 3 AI` full-path confidence
- browser smoke and parity flows
- timeout/fallback visibility

### P1-2. Parameter-Driven Decoupling Follow-up
Source plan:
- `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`

Goal:
- prevent tile/rule/character/trick parameter changes from breaking web/runtime assumptions

### P1-3. Contract / Selector Cleanup
- reduce selector ownership of locale-specific sentences
- move toward key + params or canonical payload at selector boundaries

## P2. Secondary / Deferred

### P2-1. Broader React architecture/history documents
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

Status:
- reference-only unless a task explicitly needs them

### P2-2. Older audit / proposal / strategy records

Status:
- supporting context only
- do not use as the main task list

## Always-Read Order

1. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
3. `docs/Game-Rules.md`
4. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
5. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
6. `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
7. `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
8. `PLAN/[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`
9. `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
10. `PLAN/PLAN_STATUS_INDEX.md`

## Current Execution Order

Implement in this order unless a blocker forces a swap:

1. selector/resource locale detachment
2. prompt surface cleanup on top of the locale foundation
3. non-local turn theater continuity
4. rule-parity visual fixes
5. parameter/contract decoupling follow-up

## 2026-04-05 Concrete Next Steps

1. Keep `apps/web/src/i18n/` as the source of truth and remove new direct ownership from:
   - selectors
   - runtime-facing prompt helpers
   - theater/stage summary helpers
2. Continue prompt cleanup with the locale resource model:
   - movement
   - trick
   - purchase
   - mark
   - lap reward
3. Preserve non-local turn continuity so the match reads as:
   - actor start
   - movement
   - landing
   - purchase/rent/fortune
   - turn end
4. Only after the above, continue selector/key decoupling and parameter-driven follow-up.

### 2026-04-05 Progress Update

- `streamSelectors.ts` now accepts locale-aware text resources instead of forcing runtime rendering through the Korean compatibility bridge.
- `App.tsx` now passes current locale resources into:
  - timeline
  - theater
  - alert
  - situation
  - turn-stage selectors
- Therefore the next immediate implementation order is:
  1. keep trimming selector-owned phrase composition
  2. continue prompt/theater human-play cleanup
  3. only then return to lower-priority decoupling follow-up

### 2026-04-06 Progress Update

- Remote-turn board continuity now preserves and renders intermediate move-path tiles, not only move origin/destination.
- As a result, the next immediate P0-2 slice should stay focused on:
  1. theatrical fortune / purchase / rent staging after movement completes
  2. stronger pawn/path animation on top of the new path-step groundwork
  3. continued local prompt simplification on the locale-safe foundation

### 2026-04-06 Progress Update (current checkpoint)

- The board now also renders a transient ghost-pawn travel overlay between move start and move end.
- Prompt surface wording is now further detached from component ownership:
  - collapsed prompt chip text
  - prompt footer request-meta text
  - purchase prompt description text
  now come from locale resources.
- `DecisionGateway` now also centralizes repeated lifecycle publish paths for:
  - `decision_requested`
  - `decision_resolved`
  - `decision_timeout_fallback`
- Therefore the next immediate execution order is:
  1. continue prompt-surface cleanup until remaining live prompts feel game-native instead of inspector-like
  2. keep strengthening non-local turn scene payoff for fortune / purchase / rent
  3. continue reducing human/AI branch-local decision drift before later `DecisionPort` migration

### 2026-04-06 Progress Update (remaining generic prompt split)

- The remaining previously-generic prompt families:
  - `runaway_step_choice`
  - `coin_placement`
  - `doctrine_relief`
  - `geo_bonus`
  now render on dedicated emphasized live-choice surfaces instead of the generic fallback grid.
- Backend specialty coverage now also explicitly guards:
  - `doctrine_relief`
  - `burden_exchange`
- Therefore the next immediate execution order is:
  1. finish scene-grade payoff for fortune / purchase / rent so outcomes feel like events instead of feed entries
  2. continue trimming any still-rare generic prompt fallback surfaces
  3. after the above, move P0-1 from seam-coverage work toward typed provider cleanup / `DecisionPort` prep

### 2026-04-06 Progress Update (specialty coverage checkpoint)

- Specialty decision coverage now explicitly includes:
  - `runaway_step_choice`
  - `coin_placement`
  - `geo_bonus`
  in addition to the already-covered specialty paths.
- Scene payoff cards also now use a shared pulse treatment so purchase / rent / fortune outcomes stand out more clearly during live turns.
- Therefore the next immediate execution order is:
  1. continue true human-play UX work:
     - stronger fortune reveal staging
     - richer purchase/rent event transitions
     - remaining prompt-surface simplification
  2. keep reducing any residual generic fallback prompt usage
  3. only after that, return to typed provider cleanup and later `DecisionPort` migration

### 2026-04-06 Progress Update (locale persistence checkpoint)

- Locale restore is now explicitly guarded:
  - both `ko` and `en` survive reload
  - invalid stored values fall back to the default locale
  - locale buttons have stable ids and browser coverage
- Therefore the next immediate execution order remains:
  1. continue prompt-surface cleanup until remaining live prompts feel game-native instead of inspector-like
  2. keep strengthening non-local turn scene payoff for fortune / purchase / rent and turn-to-turn handoff
  3. continue reducing human/AI branch-local decision drift before later `DecisionPort` migration

### 2026-04-06 Progress Update (spectator journey + mark drift)

- Remote turns now also expose a dedicated spectator journey strip, not only payoff and spotlight cards.
- Prompt display order now keeps passive `none`/skip-style entries behind actionable options where applicable.
- AI-side canonical request coverage now explicitly includes `mark_target`.
- Therefore the next immediate execution order is:
  1. continue trimming prompt surfaces that still feel inspector-like
  2. continue scene-grade continuity for fortune / purchase / rent / turn handoff
  3. extend canonical decision coverage to remaining specialty methods before full `DecisionPort` migration

### 2026-04-06 Progress Update (spectator result + active flip)

- Prompt request-meta moved into the prompt head, reducing footer inspector feel.
- Remote turns now keep a dedicated spectator result card for the latest payoff beat.
- AI-side canonical request coverage now also explicitly includes `active_flip`.
- Therefore the next immediate execution order is:
  1. finish the remaining specialty prompt simplification slices
  2. continue scene-grade continuity for weather / fortune / purchase / rent handoff
  3. extend canonical decision coverage to the remaining specialty methods before full `DecisionPort` migration

### 2026-04-06 Progress Update (weather spotlight + specific reward)

- Remote-turn weather is now also promoted into the spectator spotlight strip.
- Remote-turn journey continuity now separates:
  - purchase
  - rent
  - fortune
  into their own beats when present.
- Specialty prompt layouts now also explicitly cover:
  - `active_flip`
  - `burden_exchange`
  - `specific_trick_reward`
- AI-side canonical request coverage now also explicitly includes `specific_trick_reward`.
- Therefore the next immediate execution order is:
  1. keep trimming the last remaining generic/inspector-feeling prompt states
  2. keep strengthening scene-grade continuity for fortune reveal and purchase/rent payoff transitions
  3. extend canonical decision coverage to the remaining specialty methods before full `DecisionPort` migration

### 2026-04-06 Progress Update (pabal seam fixed)

- `pabal_dice_mode` is now a real human prompt path, not an AI-only specialty branch.
- Prompt choice parsing now also recognizes `value.description`, reducing future specialty prompt drift.
- Therefore the next immediate execution order is:
  1. continue scene-grade continuity for fortune reveal / purchase / rent / turn handoff
  2. keep trimming the last remaining inspector-feeling prompt surfaces
  3. move P0-1 from “missing specialty seams” to typed-provider / `DecisionPort` cleanup
### 2026-04-06 Progress Update (prompt HUD + explicit payoff labels)

- Prompt overlays now use a compact HUD-style head instead of a debug-like request sentence.
- Turn-stage and spectator payoff cards now prefer explicit event labels for:
  - landing resolved
  - tile purchased
  - rent paid
  - fortune drawn
  - fortune resolved
- Therefore the next immediate execution order is:
  1. continue scene-grade continuity for true turn handoff and payoff animation
  2. keep trimming any still-generic prompt surface that does not yet feel game-native
  3. after the above, keep collapsing provider drift toward the typed `DecisionPort` boundary
