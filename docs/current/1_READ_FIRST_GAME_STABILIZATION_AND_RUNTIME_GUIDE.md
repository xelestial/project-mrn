# 1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE

Status: ACTIVE  
Audience: Human readers  
Updated: 2026-05-03

## Why This File Exists

This is the first document to read before touching the runtime, selectors, HUD, prompt flow, or gameplay-facing contracts.

It does two jobs:

1. summarize the current architecture and reading order
2. define the stabilization work that is still required

## Read In This Order

1. `docs/current/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
2. `docs/current/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
3. `docs/current/runtime/end-to-end-contract.md`
4. `docs/current/runtime/round-action-control-matrix.md`
5. `docs/current/backend/online-game-interface-spec.md`
6. `docs/current/backend/turn-structure-and-order-source-map.md`
7. `docs/current/api/online-game-api-spec.md`

## Current Architecture Summary

- Engine gameplay truth originates in `engine/engine.py` and related runtime modules under `engine/`.
- Backend routes and runtime orchestration live under `apps/server/src/`.
- Derived UI truth is partially projected in backend view-state selectors under `apps/server/src/domain/view_state/`.
- The web app still contains important selector logic in:
  - `apps/web/src/domain/selectors/streamSelectors.ts`
  - `apps/web/src/domain/selectors/promptSelectors.ts`
  - `apps/web/src/App.tsx`

## Standard Local Runtime Ports

- Backend standard port: `9090`
- Frontend standard dev port: `9000`
- Frontend Vite proxy now defaults to backend `127.0.0.1:9090`

Override patterns:

- `MRN_WEB_API_PORT=8011 npm run dev -- --host 127.0.0.1 --port 9000`
- `MRN_WEB_API_TARGET=http://127.0.0.1:18001 npm run dev -- --host 127.0.0.1 --port 9000`

This exists specifically to prevent the stale-backend problem where the browser silently talks to an older local server on a different port.

## Browser Full-Game Timing Rule

Do not fail a browser full-game check because total game duration exceeds an arbitrary wall-clock cap. A game can legitimately take longer depending on rules, seed, AI choices, and prompt timing.

The automated screen test failure rule is:

- prompt/decision timeout stays a rule/runtime setting, currently 30 seconds by default.
- browser full-game validation has no total-duration limit.
- while the automated browser test process is running, the visible screen signature must update within 60 seconds.
- `ViewCommit.commit_seq` is sampled for diagnostics, but it does not reset the visible-screen stall timer.
- if the visible signature does not update for 60 seconds, classify the run as `screen_update_stalled`.
- time spent manually inspecting code with no browser-test process running is outside the measurement window.

## What Must Still Be Stabilized

### Latest browser gate result: REDIS-UI-10

As of 2026-05-01, `REDIS-UI-10` is resolved. The current lesson summary is
`docs/current/engineering/[LESSONS]_REDIS_RUNTIME_UI_PLAYTEST.md`.

The latest Docker Redis/browser retest proved that the game can boot, keep Redis-backed gameplay moving, render a readable board without console errors, and expose stable effect/spectator evidence:

- `npm --prefix apps/web run e2e:human-runtime` passed 18 of 18 checks.
- Targeted browser parity checks passed for `긴장감 조성` trick-target progression and `극심한 분리불안` trick-picker closure.
- Stable spectator/effect selectors are present again for `spectator-turn-panel`, `spectator-turn-weather`, `spectator-turn-worker`, `core-action-*`, and `board-event-reveal-*`.
- Character selection no longer overflows the desktop document.

Future effect-display work should keep the same closure rule. Do not close a similar regression until either:

- `npm run e2e:human-runtime` is green, or
- selector coverage is intentionally migrated to stable selectors with equivalent coverage for weather, worker provenance, rent/payoff, fortune, trick, and passive-bonus effects.

### 1. Identifier-driven gameplay rules

We still have gameplay conditions that depend on:

- Korean character names
- card-face names
- localized tile labels
- prompt labels instead of canonical ids

Target direction:

- rule evaluation should use stable ids such as `card_no`, `character_slot`, `tile_kind`, `effect_id`, `prompt_type`
- human-readable names should be injected at rendering or presentation boundaries only

Enforcement rule:

- `tools/gameplay_literal_gate.py` is the policy gate for this workstream
- runtime/domain files must not add new Korean gameplay-name comparisons
- the only current runtime exceptions are:
  - fortune alias normalization in `engine/policy/environment_traits.py`
  - the `"어사"` reason string in engine logs
- if a future change needs a new exception, it must be documented here first

### 2. Hardcoded rule reconstruction

Some logic is still reconstructed in frontend or selector glue using:

- display text
- fallback prompt titles
- inferred names from labels
- frontend-only pairing maps

Target direction:

- move canonical rule decisions into engine or backend selectors
- keep frontend as a renderer, formatter, and animation host

### 3. Dead-code and closed-path cleanup

We also need a disciplined dead-code pass.

Current evidence collected on 2026-04-12:

- Frontend export audit:
  - `npx ts-prune` in `apps/web` returned no unused exported symbol list
- Backend/Python candidate audit:
  - `vulture apps/server/src engine --min-confidence 80` produced candidate findings, mostly in `engine/ai_policy.py`
  - these are candidates, not confirmed removals
- Event-bus convergence audit:
  - `weather.round.apply` used to exist in both `engine/engine.py` and `engine/effect_handlers.py`
  - that duplication has now been removed from `engine/engine.py`
  - round weather is now applied through the event bus only
  - current scan shows the remaining default effect-handler registrations are referenced by engine `emit_first_non_none(...)` calls
- Non-code junk:
  - `docs/.DS_Store` was present and should not be treated as meaningful project content

Rule for cleanup:

- only remove code after confirming that it is unreachable, unused, or superseded
- document candidate dead code separately from confirmed removals

## Execution Plan

### Phase A. Canonical identifier migration

- Replace name-based rule conditions with canonical ids.
- Prioritize:
  - trick effects
  - weather effects
  - fortune effects
  - character effects
  - mark-target and active-face rules

### Phase B. Backend selector hardening

- Ensure backend selectors expose canonical derived data without requiring frontend name parsing.
- Expand view-state contracts so clients can render from ids plus labels.

### Phase C. Frontend simplification

- Remove frontend logic that guesses gameplay truth from localized strings.
- Keep only:
  - layout
  - animation
  - formatting
  - temporary input state

### Phase D. Dead-code triage

- Mark each candidate as one of:
  - confirmed dead
  - test-only artifact
  - false positive
  - intentionally retained public API surface
- Current confirmed cleanup:
  - weather application no longer has a dead duplicate implementation
  - engine wrapper remains, but actual logic lives in the event handler path
  - policy runtime helpers now resolve character/fortune logic through shared ids and catalogs rather than direct Korean-name branching

### Phase E. Contract documentation

- Keep engine -> backend -> frontend flow documented in one human-readable reference.
- Keep API and selector contracts aligned with test coverage.

## Deliverables

- canonical id migration plan and implementation notes
- human-readable runtime pipeline reference
- dead-code candidate appendix with evidence
- updated backend/frontend/api README entry points

## Definition Of Done For This Workstream

- no gameplay rule depends on localized Korean display text
- active slot, mark-target, weather, fortune, trick, and prompt flows are driven by ids and injected labels
- backend selectors are the primary source of UI truth
- docs identify where logic lives and how it is tested
- dead-code candidates are explicitly triaged
- browser runtime effect-display closure is proven by a green `npm run e2e:human-runtime` run or an explicitly documented equivalent selector migration
