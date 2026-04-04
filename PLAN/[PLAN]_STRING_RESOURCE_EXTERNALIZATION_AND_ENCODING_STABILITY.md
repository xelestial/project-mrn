# [PLAN] String Resource Externalization And Encoding Stability

Status: ACTIVE  
Updated: 2026-04-05  
Owner: GPT

## Purpose

React/FastAPI live viewer and related runtime surfaces still carry too many inline UI strings inside components.
That makes the project vulnerable to:

- repeated mojibake / broken UTF-8 recovery
- inconsistent wording between replay, live play, prompt UI, and system alerts
- accidental regression when component files are refactored or regenerated
- low reuse across web / server / future Unity-facing adapters

This plan moves user-facing strings into centralized, typed resource catalogs and defines the migration order.

## Problem Statement

Current symptoms observed in active work:

1. Component-local strings were repeatedly reintroduced in:
   - `apps/web/src/App.tsx`
   - `apps/web/src/features/theater/*`
   - `apps/web/src/features/stage/*`
   - prompt and lobby components
2. Mixed local editing paths increased risk of corrupted literals.
3. The same semantic phrase exists in multiple places with slightly different wording.
4. Human-play UX regressions can return even when logic is unchanged, simply because strings are retyped per component.

## Goals

1. Eliminate ad-hoc inline user-facing strings from critical React match flow.
2. Centralize all visible copy into typed resource modules.
3. Separate:
   - rule/event labels
   - prompt labels/helpers
   - theater/live narration strings
   - layout/system status strings
4. Make selector/component rendering consume resource keys instead of freeform literals where practical.
5. Add tests so broken/missing string resources fail before UI review.

## Non-Goals

- Full i18n framework adoption in this phase.
- Multi-language support in this phase.
- Rewriting every historical Python viewer phrase immediately.

This phase is about stability, single-source wording, and encoding safety.

## Target Architecture

### A. Resource Layers

1. `apps/web/src/domain/labels/*`
- canonical event labels
- prompt type labels
- helper text
- actor/theater/status phrases

2. `apps/web/src/domain/text/*` or adjacent dedicated resource files
- match layout chrome text
- waiting/passive prompt text
- section headings
- lane titles / subtitles
- system warning copy

3. optional shared package follow-up
- if web/server/runtime need identical human-readable phrase keys, move stable catalogs to `packages/runtime-contracts` or a new shared package

### B. Usage Rule

- Components should import resource helpers/constants, not embed large user-facing strings inline.
- Selectors may still compose dynamic summaries, but phrase templates should come from resource helpers.
- Any new user-facing text added to runtime/web must first be placed in a resource catalog.

## Migration Scope

### P0 Scope

1. Web match surface
- `apps/web/src/App.tsx`
- `apps/web/src/features/theater/CoreActionPanel.tsx`
- `apps/web/src/features/theater/IncidentCardStack.tsx`
- `apps/web/src/features/stage/TurnStagePanel.tsx`
- `apps/web/src/features/prompt/PromptOverlay.tsx`
- `apps/web/src/features/lobby/LobbyView.tsx`

2. Existing label catalogs
- normalize and extend:
  - `eventLabelCatalog.ts`
  - `promptTypeCatalog.ts`
  - `promptHelperCatalog.ts`

3. Runtime/system UI copy
- waiting text
- connection/runtime status labels
- prompt passive-observer text
- top command strip labels

### P1 Scope

1. Selector-generated summaries
- `streamSelectors.ts`
- `promptSelectors.ts`

2. Server/client transport-visible error message normalization
- websocket status text
- reconnect / stalled / recovery warnings

### P2 Scope

1. Shared contract-adjacent phrase keys
2. Replay/live/common wording convergence
3. Unity portability review for phrase ownership

## Detailed Execution Plan

### Step 1. Catalog Inventory

Create or expand a catalog map for these groups:

- `layoutText`
- `matchStatusText`
- `theaterText`
- `turnStageText`
- `promptChromeText`
- `lobbyText`

Each group should be typed and exported from a stable module.

### Step 2. Remove Inline Strings From P0 Components

Replace hardcoded UI literals with imported resources in:

- `App.tsx`
- `CoreActionPanel.tsx`
- `IncidentCardStack.tsx`
- `TurnStagePanel.tsx`
- `PromptOverlay.tsx`
- `LobbyView.tsx`

### Step 3. Dynamic Phrase Helpers

For phrases with interpolation, create helper functions such as:

- `waitingForPlayer(playerId)`
- `passivePromptSummary(playerId, requestType, secondsLeft)`
- `turnBanner(actor, character)`
- `laneSubtitle(lane)`

### Step 4. Encoding/Regression Guard

Add tests and checks for:

- required key presence
- no empty string values in critical catalogs
- selector/component tests using canonical text helpers
- existing encoding gate remains mandatory

### Step 5. Documentation And Usage Policy

Update mandatory principles so future work must:

- define new user-facing strings in resource catalogs first
- record string-surface changes in worklog
- avoid direct inline literals in core runtime components unless trivial and temporary

## Tests

### Required

1. Label/catalog unit tests
2. Prompt/render selector tests referencing canonical text resources
3. Build verification:
- `npm run build` in `apps/web`

### Recommended

1. Snapshot test for match-shell chrome text
2. Theater panel rendering test with canonical strings
3. Prompt overlay rendering test for key request types

## Risks

1. Partial migration can create mixed sources of truth.
2. Over-centralization without grouping can make catalogs hard to navigate.
3. Selector-generated free text can still bypass catalogs if not reviewed carefully.

## Mitigations

1. Migrate by UI surface, not by individual string.
2. Keep catalogs grouped by feature/surface.
3. Add policy note to mandatory doc and priority reference.
4. Track closure in worklog and parity plan.

## Definition Of Done

- Critical React match-flow components no longer own large inline user-facing strings.
- Theater/stage/prompt/lobby wording is sourced from centralized resource modules.
- String regressions are covered by tests and existing encoding gate.
- Future UI edits can reuse stable text helpers without retyping phrases.

## Immediate Priority Order

1. P0: extract live match chrome + theater/stage strings
2. P0: extract prompt/lobby strings
3. P1: normalize selector-generated summaries
4. P1: normalize runtime/server/client warning text
5. P2: evaluate shared phrase ownership for future Unity frontend
