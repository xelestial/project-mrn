# 1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE

Status: ACTIVE  
Audience: Human readers  
Updated: 2026-04-12

## Why This File Exists

This is the first document to read before touching the runtime, selectors, HUD, prompt flow, or gameplay-facing contracts.

It does two jobs:

1. summarize the current architecture and reading order
2. define the stabilization work that is still required

## Read In This Order

1. `docs/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md`
2. `docs/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
3. `docs/engineering/[PLAN]_BACKEND_SELECTOR_AND_MIDDLEWARE_VIEWMODEL_MIGRATION.md`
4. `docs/backend/online-game-interface-spec.md`
5. `docs/backend/turn-structure-and-order-source-map.md`
6. `docs/api/online-game-api-spec.md`

## Current Architecture Summary

- Engine gameplay truth originates in `GPT/engine.py` and related runtime modules under `GPT/`.
- Backend routes and runtime orchestration live under `apps/server/src/`.
- Derived UI truth is partially projected in backend view-state selectors under `apps/server/src/domain/view_state/`.
- The web app still contains important selector logic in:
  - `apps/web/src/domain/selectors/streamSelectors.ts`
  - `apps/web/src/domain/selectors/promptSelectors.ts`
  - `apps/web/src/App.tsx`

## What Must Still Be Stabilized

### 1. Identifier-driven gameplay rules

We still have gameplay conditions that depend on:

- Korean character names
- card-face names
- localized tile labels
- prompt labels instead of canonical ids

Target direction:

- rule evaluation should use stable ids such as `card_no`, `character_slot`, `tile_kind`, `effect_id`, `prompt_type`
- human-readable names should be injected at rendering or presentation boundaries only

### 2. Hardcoded rule reconstruction

Some logic is still reconstructed in frontend or selector glue using:

- display text
- fallback prompt titles
- inferred names from labels
- frontend-only pairing maps

Target direction:

- move canonical rule decisions into engine or backend selectors
- keep frontend as a renderer, formatter, and animation host

### 3. Dead-code and obsolete-path cleanup

We also need a disciplined dead-code pass.

Current evidence collected on 2026-04-12:

- Frontend export audit:
  - `npx ts-prune` in `apps/web` returned no unused exported symbol list
- Backend/Python candidate audit:
  - `vulture apps/server/src GPT --min-confidence 80` produced candidate findings, mostly in `GPT/ai_policy.py`
  - these are candidates, not confirmed removals
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
  - intentionally retained compatibility path

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
