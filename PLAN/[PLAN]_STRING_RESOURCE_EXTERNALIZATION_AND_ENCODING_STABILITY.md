# [PLAN] String Resource Externalization And Encoding Stability

Status: ACTIVE  
Updated: 2026-04-05  
Owner: GPT

## Progress Snapshot

### Done

1. Added centralized typed text catalogs in:
- `apps/web/src/domain/text/uiText.ts`

2. Migrated major React surface strings to catalogs:
- `apps/web/src/App.tsx`
- `apps/web/src/features/lobby/LobbyView.tsx`
- `apps/web/src/features/prompt/PromptOverlay.tsx`
- `apps/web/src/features/theater/CoreActionPanel.tsx`
- `apps/web/src/features/theater/IncidentCardStack.tsx`
- `apps/web/src/features/stage/TurnStagePanel.tsx`
- `apps/web/src/features/board/BoardPanel.tsx`
- `apps/web/src/features/status/ConnectionPanel.tsx`

3. Recovered/normalized label catalogs and label tests:
- `eventLabelCatalog.ts`
- `promptTypeCatalog.ts`
- `promptHelperCatalog.ts`

4. Expanded auxiliary/prompt text ownership:
- `PLAYERS_TEXT`
- `TIMELINE_TEXT`
- `PROMPT_TYPE_TEXT`
- `PROMPT_HELPER_TEXT`
- `promptTypeCatalog.ts` and `promptHelperCatalog.ts` now read from shared text resources instead of owning visible Korean strings
- `PlayersPanel.tsx` and `TimelinePanel.tsx` now render from catalog text

4. Validation completed:
- `npm run build` passed in `apps/web`
- `npm run test -- --run src/domain/labels` passed

5. Locale foundation is now active in implementation:
- `apps/web/src/i18n/`
- `I18nProvider`
- `useI18n`
- `ko/en` locale bundles

6. Hook-based locale usage has already reached major match surfaces:
- `App.tsx`
- `LobbyView.tsx`
- `ConnectionPanel.tsx`
- `PlayersPanel.tsx`
- `TimelinePanel.tsx`
- `SituationPanel.tsx`
- `TurnStagePanel.tsx`
- `SpectatorTurnPanel.tsx`
- `CoreActionPanel.tsx`
- `IncidentCardStack.tsx`
- `BoardPanel.tsx`
- `PromptOverlay.tsx`

### In Progress

1. Selector/domain-generated phrasing is still partially embedded in:
- `apps/web/src/domain/selectors/streamSelectors.ts`
- action classification heuristics in theater components
- zone-color mapping literals in `BoardPanel.tsx`

   Current note:
   - `streamSelectors.ts` now has a locale-aware text injection path and no longer has to rely on the Korean bridge at runtime when called from `App.tsx`
   - remaining work is to keep shrinking selector-owned phrasing, not to rebuild the injection path itself

2. `uiText.ts` still exists as a Korean compatibility bridge and should shrink over time instead of regaining ownership.
3. Some non-UI/internal fallback strings still remain in runtime-facing handlers and should be normalized next.
4. Leftover centralized mappings are being folded into locale bundles instead of staying in per-component helpers.

### Next

1. Finish moving selector-generated visible summaries behind locale-aware phrase helpers/catalog keys.
2. Reduce `uiText.ts` to a temporary compatibility bridge only.
3. Add resource-focused tests for selector-resource coupling and locale switching.
4. Continue P0-2 live human-play UI recovery on top of the locale foundation.
5. Treat any newly discovered inline Korean/English display string as a regression and move it into catalog ownership before further UI layering.

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

## 2026-04-05 Additional Progress Update

- Restored the main React UI text catalog in clean UTF-8 and re-covered it with tests.
- Recovered corrupted selector/label specs so string regressions now fail earlier in domain tests instead of surfacing only in the browser.
- Moved event/non-event labels into shared text ownership via `EVENT_LABEL_TEXT`.
- Remaining work on this plan is now narrower:
  1. finish splitting the large `uiText.ts` catalog into smaller feature catalogs if navigation starts to degrade
  2. continue removing any leftover inline user-visible phrases from runtime-oriented components
  3. keep validating that selector-generated summaries read from canonical text helpers

## 2026-04-05 Browser Parity Follow-up

- The string/resource work is now strong enough to support browser-level human-play smoke coverage.
- Added a Playwright quick-start parity scenario that verifies:
  1. lobby quick start creates a `1 human + 3 AI` session
  2. the human seat joins
  3. the host starts the session
  4. the match view opens
  5. the first human prompt renders using the restored text catalogs
- Existing parity tests were also updated to follow the current Korean UI wording (`참가 좌석`, `Raw 보기`, etc.).
- This plan is not fully complete yet.
- Remaining work on this plan is now:
  1. split `uiText.ts` into smaller feature catalogs once navigation/readability starts to suffer
  2. keep eliminating leftover inline literals from runtime-oriented React components
  3. extend browser assertions so prompt/theater/stage UI is checked with canonical resource text instead of ad-hoc raw strings

## 2026-04-05 Prompt Decision Surface Follow-up

- Prompt-surface browser coverage now extends past quick-start shell validation and into real request types:
  1. `movement` prompt with runtime-contract `dice_*` choices
  2. `purchase_tile` prompt
  3. `mark_target` prompt
- This reduces the risk that selector/resource cleanup accidentally regresses live human-play decision wording while preserving superficially similar layouts.
- Remaining string-plan follow-up is now mostly structural:
  1. split `uiText.ts` into smaller feature catalogs when file navigation starts slowing implementation
  2. continue removing any leftover inline visible strings from prompt/stage/theater helpers
  3. keep browser assertions tied to canonical text ownership instead of ad-hoc component literals

## 2026-04-05 Beat/Board Summary Follow-up

- Added new canonical text ownership for public economic/effect summaries:
  - `rent_paid`
  - `fortune_drawn`
  - `fortune_resolved`
- This was driven by live-play continuity work, because blank selector summaries immediately break the theater/board coupling effect.
- Result:
  - stage summaries, board focus summaries, and selector tests now read from the same shared text catalog for these beats
- Remaining string-plan follow-up remains:
  1. continue extracting any leftover inline visible phrases from stage/theater/board helpers
  2. split `uiText.ts` by feature once navigation cost starts slowing implementation
  3. keep browser/selectors/tests tied to canonical resource ownership so mojibake or wording drift cannot quietly return

## 2026-04-06 Prompt Locale-Boundary Follow-up

- Prompt chrome moved one step further away from component-owned wording:
  - collapsed prompt chip text now comes from locale resources
  - footer request-meta text now comes from locale resources
- Purchase prompt description text also now comes from locale resources instead of a component-local fallback sentence.
- English prompt resource wording was also normalized so the current default English mode no longer exposes mojibake separators in these prompt surfaces.
- This plan is still not complete.
- Remaining follow-up remains:
  1. continue extracting any leftover inline visible phrases from prompt/stage/theater helpers
  2. split `uiText.ts` by feature once navigation cost starts slowing implementation
  3. add broader locale-focused browser assertions once more prompt surfaces are fully resource-owned

## 2026-04-06 English Locale Recovery Follow-up

- The English locale file contained an old corrupted fragment in:
  - board zone-color fallback keys
  - weather fallback name keys
- That fragment is now treated as an active regression class, not harmless dead text, because:
  - Vite/dev build can fail on it
  - browser parity can stall before any human-play UI renders
- Current stabilization outcome:
  - English movement prompt wording was normalized again
  - English purchase / rent / fortune scene wording was normalized again
  - the broken legacy board-locale fragment was removed so build/e2e return to a stable baseline
- Remaining follow-up remains:
  1. keep eliminating any legacy mojibake fragments from locale files even when they appear outside currently visible UI
  2. keep browser smoke coverage on human-play flows so locale corruption fails early
  3. continue moving prompt/stage/theater wording out of component assembly and into locale-owned resources

## 2026-04-06 Locale Restore Validation

- Locale persistence is now part of the guarded string-stability surface:
  - `ko` must restore after reload
  - `en` must restore after reload
  - invalid stored values must safely fall back to the default locale
- This is now covered through a direct unit seam (`resolveLocaleFromStoredValue(...)`) instead of relying only on manual browser verification.
