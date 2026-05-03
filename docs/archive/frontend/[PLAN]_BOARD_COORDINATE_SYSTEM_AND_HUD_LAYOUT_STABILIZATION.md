# [PLAN] Board Coordinate System And HUD Layout Stabilization

Status: CLOSED_MERGED  
Updated: 2026-04-15  
Owner: Codex

Merged into:
- `docs/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`

## Purpose

This plan exists to stabilize the live match layout around one explicit board coordinate system instead of the current mixed approach:

- viewport-based outer layout
- board-relative tile placement
- px-measured safe bounds
- fixed or absolute HUD overlays owned by `App.tsx`

The goal is not a cosmetic refresh.
The goal is to make the board and every non-board HUD layer stay readable and anchored across monitor resolutions, browser sizes, and future renderer migrations.

That includes inner scale, not just outer placement.

This plan therefore treats the following as part of the same problem:

- coordinate placement
- typography scale
- spacing and padding scale
- pill and badge density
- card minimum readable size

This plan also folds in two adjacent cleanup tasks requested by the user:

1. fix cases where the whole board is not fully visible after resolution changes
2. move the secondary “recent public action / extra info” panel into the debug log flow and make it accumulate newest-first instead of behaving like a one-off transient card

## Scope

This plan covers every live-match component that is positioned relative to the board except the central board tile ring or line itself.

In practice, the affected surfaces are:

- global match header behavior as it affects available viewport space
- in-board top HUD
  - weather card
  - P1~P4 player strip
  - active character strip
- in-board middle HUD
  - passive prompt card
  - waiting panel
  - actionable prompt overlay shell
- in-board bottom HUD
  - current trick hand tray
- public event layer
  - current-turn reveal stack
- turn banner / interrupt banner relationship to the board
- session info expansion behavior
- recent public action / extra information panel currently rendered below the board
- debug log presentation and ordering

The following scale primitives are also explicitly in scope:

- weather/player/prompt/hand card title sizes
- body/caption/stat sizes
- panel/card padding
- internal gaps
- pill/badge heights
- compact/tight density thresholds

Explicit non-goals for this document:

- changing game logic
- changing decision legality
- redesigning the board tile art system
- changing selector truth ownership already moved to backend middleware unless needed for new layout metadata

## Current Ground Truth

The current live match layout has three separate coordinate systems in play:

1. viewport layout
   - `apps/web/src/App.tsx`
   - global header, turn banner, event overlay fallback width, prompt shell placement

2. board grid layout
   - `apps/web/src/features/board/BoardPanel.tsx`
   - tile positions via `projectTilePosition(...)`
   - moving pawn animation already expressed in board-relative percentages

3. measured px overlay bounds
   - `BoardPanel.tsx` measures anchor tile DOM rects
   - computes `overlaySafeTop`, `overlaySafeBottomGap`, `overlaySafeLeft`, `overlaySafeRightGap`
   - emits `boardOverlayFrame.viewportLeft / viewportWidth`
   - `App.tsx` then reinterprets those into fixed overlay placement

This causes several instability patterns:

### A. Mixed coordinate ownership

`BoardPanel` knows where the board really is, but `App.tsx` owns several overlay placements.

That means:

- board-relative measurements are converted to viewport px
- then re-used by components that no longer live inside the same board container
- so resizing and prompt visibility changes can desynchronize them

### B. Resolution breakage

The board ring currently uses viewport-derived height with a hard minimum:

- `.board-ring-ring`
  - `height: min(calc(100vh - 210px), calc((100vw - 48px) * 0.58));`
  - `min-height: 760px;`

This can make the board exceed the actually available match viewport when:

- header grows
- top HUD grows
- prompt tray is visible
- the monitor height is reduced

### C. Overlay frame only solves width, not a full coordinate system

Current `boardOverlayFrame` contains only:

- `viewportLeft`
- `viewportWidth`

But the actual HUD problem needs a complete board-relative layout contract:

- left
- right
- top
- bottom
- width
- height
- safe lanes
- z-order and collision rules

### D. The recent-public-action surface still competes with the board

`CoreActionPanel` is still rendered as a regular layout sibling under the board in `App.tsx`.

That means:

- it consumes page height directly
- it competes with the board for vertical space
- it behaves like a primary surface instead of an auxiliary diagnostic/history surface

The user explicitly wants this information moved into the debug log flow and accumulated newest-first.

### E. Internal density still behaves like fixed-size UI

Even when outer panel placement is approximately correct, the panel contents can still break if inner sizing does not follow the same parent system.

Typical symptoms:

- text remains too large after the board shrinks
- chips and stat pills wrap early
- card paddings stay oversized relative to the available slot
- scrollbars appear because content density is effectively fixed

This means coordinate stabilization alone is not enough.

The board HUD also needs one shared scale model for font, spacing, and density.

## Architecture Target

The live match screen should use a layered coordinate system with one clear responsibility boundary.

### Layer 1. Viewport shell

Owns:

- total available viewport
- global header
- optional turn banner
- page-safe padding

This layer decides:

- how much vertical space the board scene is allowed to occupy
- how much space remains for non-board global UI

It must not directly position board HUD internals.

### Layer 2. Board frame

Owns:

- actual rendered board rect
- tile DOM anchors
- normalized coordinate system
- board-relative safe lanes

This becomes the canonical coordinate root for:

- weather/player/active strip
- prompt dock
- hand tray
- public event lane
- board-relative overlays and future motion layers

### Layer 3. HUD layout model

Owns semantic board-relative layout, not CSS guesses.

The layout model should expose:

- board rect metrics
- anchor tile metrics
- normalized bounds
- board-safe lanes
- collision-free bands
- constraints for each surface

This layer must be renderer-agnostic enough that React, Unity, or Unreal could consume the same layout metadata pattern.

### Layer 3.5. HUD scale model

Layout bounds and internal density must be derived from the same board scene.

This scale model should expose:

- board scene scale factor
- semantic density mode
- typography tokens
- spacing tokens
- compactness hints per surface

Without this layer, bounds can become correct while inner content still overflows.

### Layer 4. Presentation

React should only:

- read the board HUD layout model
- map bounds into CSS custom properties or inline style
- render

React should stop:

- re-deriving overlay width in `App.tsx`
- mixing viewport fixed positioning with board-internal overlays
- manually compensating for other HUD elements with separate resize effects

## Coordinate System Design

### Principle

All non-board HUD surfaces should be anchored in board coordinates, not directly in viewport coordinates.

The viewport still matters, but only up to the board frame.

After that, the board frame becomes the parent coordinate system.

### Canonical units

The board layout model should produce both:

1. measured px values
2. normalized ratios relative to the board frame

Recommended normalized shape:

```ts
type BoardRect = {
  viewportLeft: number;
  viewportTop: number;
  width: number;
  height: number;
};

type BoardNormalizedRect = {
  x: number;      // 0..1
  y: number;      // 0..1
  width: number;  // 0..1
  height: number; // 0..1
};
```

Recommended layout payload:

```ts
type BoardHudLayout = {
  boardRect: BoardRect;
  safeLanes: {
    topBand: BoardNormalizedRect;
    middleBand: BoardNormalizedRect;
    bottomBand: BoardNormalizedRect;
    eventBand: BoardNormalizedRect;
  };
  anchors: {
    tile3Start: BoardNormalizedRect;
    tile9End: BoardNormalizedRect;
    tile32End: BoardNormalizedRect;
    tile40Start: BoardNormalizedRect;
  };
  surfaces: {
    weatherStrip: BoardNormalizedRect;
    playerStrip: BoardNormalizedRect;
    activeCharacterStrip: BoardNormalizedRect;
    promptDock: BoardNormalizedRect;
    handTray: BoardNormalizedRect;
    publicEventStack: BoardNormalizedRect;
  };
};
```

Recommended scale payload:

```ts
type BoardHudScale = {
  sceneScale: number;
  densityMode: "comfortable" | "compact" | "tight";
  typeScale: {
    title: number;
    body: number;
    caption: number;
    stat: number;
  };
  spaceScale: {
    panelPadding: number;
    cardPadding: number;
    gap: number;
    chipHeight: number;
    badgeHeight: number;
  };
};
```

### Why normalized coordinates are required

If only px values are stored, layout works only for the currently measured DOM state.

If normalized board-relative coordinates are stored, we gain:

- resize stability
- renderer portability
- testable layout contracts
- one conversion path from board metrics to UI bounds

The same rule applies to inner scale:

- if font and spacing stay as isolated px values, panels can still break after bounds are corrected
- if font and spacing are derived from the board scene, internal density remains proportional to the same parent system

### Board scene scale

HUD internals should not scale from raw viewport width alone.

They should scale from the resolved board frame.

Recommended reference model:

```ts
sceneScale = min(boardFrame.width / 1600, boardFrame.height / 900)
sceneScale = clamp(sceneScale, 0.72, 1.08)
```

Every HUD surface then consumes tokens derived from `sceneScale`.

### Density modes

Continuous scale is not enough by itself.

We should define semantic density breakpoints:

- `comfortable`
- `compact`
- `tight`

These modes should influence:

- typography
- spacing
- wrapping rules
- secondary text visibility
- chip and badge size

The density mode must be computed from the same board scene, not by ad hoc per-component heuristics.

### Anchor rule set

The layout system should compute its main horizontal and vertical boundaries from tile anchors, not from hardcoded numbers.

Required anchor semantics:

- horizontal left boundary:
  - start of tile 3
- horizontal right boundary:
  - end of tile 9
- top safe entry:
  - start height of tile 40
- bottom safe exit:
  - end height of tile 32

These are already close to the user’s intended mental model and should remain the canonical layout references.

## Required Refactor

## 1. Replace `boardOverlayFrame` with full board HUD metrics

Current:

- `BoardPanel` emits only width and left in viewport px

Target:

- `BoardPanel` emits a `BoardHudLayout` object
- or a dedicated selector/hook returns it to `App.tsx`
- preferably the layout model stays local to the board scene and the parent only consumes semantic slots

Recommendation:

- add a dedicated module:
  - `apps/web/src/features/board/boardHudLayout.ts`
- add a dedicated hook:
  - `apps/web/src/features/board/useBoardHudLayout.ts`
- add a dedicated scale module:
  - `apps/web/src/features/board/boardHudScale.ts`

This module should:

- read board scroll rect
- read anchor tile rects
- normalize them into board coordinates
- compute named surface slots
- emit stable equality-friendly objects

The scale module should:

- derive `sceneScale` from the resolved board frame
- derive semantic density mode
- expose shared typography and spacing tokens

## 2. Move board-internal overlays out of `App.tsx` layout ownership

Current board HUD composition is created in `App.tsx` via `overlayContent`.

That keeps too much positioning and collision behavior in the page root.

Target:

- `BoardPanel` should own the overlay container and its board-relative layout slots
- `App.tsx` should provide content models, not ad hoc placement styles

Recommended split:

- `App.tsx`
  - computes data
  - passes semantic models
- `BoardPanel.tsx`
  - reads `BoardHudLayout`
  - renders top / middle / bottom / event layers

## 3. Remove fixed viewport-bounded event overlay layout

Current:

- `eventOverlayLayout.bottom` and `eventOverlayLayout.maxHeight` are computed from `handTrayDockRef`
- event overlay is fixed relative to viewport

Target:

- public events become just another board-relative band
- their size is capped by board-safe remaining height
- they do not rely on viewport-fixed compensation math

## 4. Fix board visibility across monitor resolutions

The board must remain fully visible inside the match scene at all supported resolutions.

Required changes:

- remove rigid `min-height` assumptions that force overflow at medium heights
- define a board scene height budget from the viewport shell
- allow the board frame to shrink proportionally before HUD layers begin overlapping
- ensure the board scene uses a bounded aspect strategy rather than a hard minimum that exceeds the viewport

### Proposed sizing rule

Instead of:

- board width from viewport
- board height from viewport
- plus a large `min-height`

Use:

- `MatchViewportScene`
  - `height = viewportHeight - globalHeader - turnBanner - pagePadding`
- `BoardFrame`
  - `height = min(sceneHeight, sceneWidth * boardAspectRatio)`
  - `width = min(sceneWidth, sceneHeight / boardAspectRatio)`
- board tile ring scales inside that frame

The board should be shrunk before page overflow is allowed.

Page overflow should become a fallback, not the default.

This phase must also define the first version of scene-scale-driven typography and spacing tokens so reduced board size does not leave oversized HUD content.

## 5. Move recent public action / extra info to debug log

The current `CoreActionPanel` should stop consuming page space under the board during normal match play.

The user wants the secondary info panel moved to the debug log side.

### Required behavior

- debug log accumulates items
- newest item appears first
- the panel is not one-shot or replaced by the latest only
- it keeps updating while the match progresses

### Recommended implementation

Create a selector-backed debug feed model:

- `apps/web/src/domain/selectors/debugLogSelectors.ts`

Inputs:

- raw stream messages
- current-turn reveal items
- core action feed items
- session meta / connection state if needed

Outputs:

- accumulated diagnostic sections
- newest-first ordering
- stable keys and timestamps
- optional grouping by:
  - public action
  - prompt
  - runtime status
  - raw transport event

Then:

- remove `CoreActionPanel` from the main match page flow
- enrich the debug popup content with:
  - previous raw log
  - accumulated recent public actions
  - secondary info cards currently shown outside the board

### Required UX rule

Debug log content must be additive, not replace-the-latest.

Newest items appear at the top.

Older entries remain visible until the user closes the window or the session changes.

## 6. Session info compaction

The match header currently expands session info inline and steals space from the board scene.

The user already asked for this information to be less intrusive.

Required direction:

- keep the default collapsed
- move secondary operational details into the debug log popup
- header line stays single-line and compact

This directly supports the board visibility goal because every persistent global vertical pixel matters.

## Affected Files

Primary implementation files:

- `apps/web/src/App.tsx`
- `apps/web/src/features/board/BoardPanel.tsx`
- `apps/web/src/features/theater/CoreActionPanel.tsx`
- `apps/web/src/styles.css`

Recommended new modules:

- `apps/web/src/features/board/boardHudLayout.ts`
- `apps/web/src/features/board/useBoardHudLayout.ts`
- `apps/web/src/features/board/boardHudScale.ts`
- `apps/web/src/domain/selectors/debugLogSelectors.ts`
- `apps/web/src/features/debug/DebugLogWindow.tsx`

Likely touched selector/i18n files:

- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/i18n/locales/ko.ts`
- `apps/web/src/i18n/locales/en.ts`

Potential contract additions if we later promote layout hints beyond React:

- `apps/server/src/domain/view_state/board_selector.py`
- `docs/api/online-game-api-spec.md`

## Data Model And Ownership

### Board layout ownership

Board-relative layout should be computed closest to the board renderer, not at the page root.

Recommended ownership:

- board measurements
  - `BoardPanel`
- normalized HUD layout assembly
  - `boardHudLayout.ts`
- board scene scale assembly
  - `boardHudScale.ts`
- data selectors for weather, players, active cards, prompt, hand tray, reveal items
  - existing selectors / middleware-derived models
- render-only composition
  - board HUD slot components

### Debug log ownership

Debug log should become a derived accumulated view model, not a side effect of raw popup string rendering.

Recommended ownership:

- selector:
  - `debugLogSelectors.ts`
- popup renderer:
  - `DebugLogWindow.tsx`
- `App.tsx` only toggles visibility

## Execution Plan

### Phase 0. Measurement Inventory And Freeze

Before changing layout behavior, inventory every place currently using:

- viewport px compensation
- `getBoundingClientRect()`
- fixed prompt/event offsets
- board height `min-height` assumptions
- hardcoded widths that ignore board parent bounds

Deliverables:

- documented list of current board/HUD coordinate calculations
- documented list of current board/HUD fixed-size typography and spacing hotspots
- unit test baselines for current anchor extraction

### Phase 1. Board Scene Height Recovery

Fix the issue where the full board is not visible after resolution changes.

Tasks:

- introduce a viewport-scene height budget
- remove or reduce rigid board `min-height`
- keep board aspect ratio bounded inside available scene height
- ensure board scroll becomes fallback-only for the ring topology
- define the first board-scene scale factor
- define initial typography/spacing token ranges tied to that scale

Required outcome:

- the full board remains visible at typical desktop resolutions without vertical clipping
- inner HUD content also compacts with the board scene instead of overflowing independently

### Phase 2. Canonical Board HUD Layout Model

Build the reusable coordinate system.

Tasks:

- create `boardHudLayout.ts`
- create `boardHudScale.ts`
- produce named anchors from tile rects
- normalize to board-relative coordinates
- expose semantic slots:
  - top band
  - prompt band
  - hand tray band
  - event band
- expose shared scale tokens:
  - typography
  - spacing
  - density mode

Required outcome:

- every overlaying HUD surface can read one shared layout model
- every overlaying HUD surface can read one shared scale model

### Phase 3. Move Overlay Placement Into Board Ownership

Tasks:

- stop passing viewport-bounded overlay placement from `App.tsx`
- make `BoardPanel` render top/middle/bottom/event overlay lanes internally
- replace ad hoc `boardBoundedFixedStyle` and `eventOverlayLayout`

Required outcome:

- overlays stop mixing viewport-fixed and board-absolute placement
- overlays stop mixing board-relative bounds with independently hardcoded inner densities

### Phase 4. Slot-Based HUD Refactor

Tasks:

- top slot:
  - weather
  - player strip
  - active character strip
- middle slot:
  - passive prompt
  - waiting panel
  - actionable prompt
- bottom slot:
  - trick hand tray
- event slot:
  - public event stack
- apply shared board-scene scale tokens to:
  - weather bar
  - player cards
  - active-character cards
  - prompt overlay internals
  - hand tray internals
  - event cards

Required outcome:

- all board HUD elements use the same coordinate parent and collision rules
- all board HUD elements use the same scale parent and density rules

### Bottom hand tray card-count rule

The bottom trick hand tray should be designed around the gameplay maximum, not around the currently common count.

Required rule:

- if the tray uses a fixed grid mental model, its primary desktop layout should be based on 5 card slots, because the visible maximum is 5 cards
- it must not default to a 4-column grid that breaks or reflows awkwardly when the fifth card appears
- when fewer than 5 cards are present, the layout may either:
  - preserve a 5-slot rhythm visually, or
  - collapse responsively while still guaranteeing that the 5-card case remains the primary supported board-state layout

Implementation expectation:

- treat 5-card occupancy as the baseline acceptance case for the bottom tray
- derive card width, typography, and padding tokens from the 5-card scenario first, then loosen for 4/3/2/1 cards

### Phase 5. Debug Log Migration

Tasks:

- move `CoreActionPanel` content into the debug log system
- create accumulated newest-first debug feed selector
- move session extra info / auxiliary public info into the same popup
- keep the board page free of that secondary surface

Required outcome:

- no extra info panel under the board in normal match layout
- debug view becomes the home for accumulated diagnostics and public history

### Phase 6. Contract And Test Hardening

Tasks:

- add tests for board HUD layout slot calculations
- add viewport/resolution regression cases
- add debug-log accumulation selector tests
- if layout hints become contract data, update API docs and shared fixture examples

Required outcome:

- layout survives resolution changes and prompt combinations without silent regressions

## Testing Strategy

### Unit tests

Add tests for:

- board anchor extraction
- normalized rect calculation
- slot collision rules
- board-scene scale factor calculation
- density mode switching
- typography and spacing token output for representative board sizes
- debug log accumulation order
- newest-first insertion

Recommended files:

- `apps/web/src/features/board/boardHudLayout.spec.ts`
- `apps/web/src/features/board/boardHudScale.spec.ts`
- `apps/web/src/domain/selectors/debugLogSelectors.spec.ts`

### Browser or integration tests

Add resolution-sensitive coverage for:

- standard desktop
- shorter-height desktop
- compact-density mode
- prompt + hand tray + event stack all visible

Must verify:

- full board remains visible
- prompt does not cover the top HUD
- event stack does not cover the hand tray
- hand tray bottom aligns to the board safe lane
- typography and padding compact together with the board scene
- stat pills and badges stay aligned instead of wrapping unpredictably
- hand tray still renders cleanly in the 5-card case without falling back to awkward overflow or unintended 4-column wrapping

### Manual acceptance scenarios

Minimum scenarios:

1. no prompt, no hand tray, event stack visible
2. actionable prompt only
3. prompt + hand tray
4. prompt + hand tray + public event stack
5. resolution change while the above are open
6. debug log popup open while actions continue
7. short-height desktop where inner typography must compact with the board scene
8. bottom trick tray showing the full 5-card maximum

## Risks

### 1. Half-migrated coordinate ownership

If some overlays still use viewport-fixed placement while others use board-relative layout, the result will be worse than the current state.

Mitigation:

- cut over by overlay lane, not by individual card

### 2. Board shrink can make tiles unreadable

If board visibility is solved only by shrinking aggressively, tile content can become too small.

Mitigation:

- define a minimum readable tile density threshold
- below that threshold, switch specific HUD text to compact mode before shrinking further

### 2.5. Bounds can stabilize before inner density does

Even if the panel bounds are correct, fixed-size typography and padding can still cause clipping and premature scrollbars.

Mitigation:

- make `sceneScale` and `densityMode` first-class outputs of the board HUD system
- avoid ad hoc per-component font scaling for board HUD surfaces

### 3. Debug popup can become an unstructured dump

Moving public actions into debug should not mean losing readability.

Mitigation:

- use structured sections
- newest-first ordering
- clear group labels
- separate raw transport log from derived public-action history

### 4. Future renderer portability can be lost again

If the board layout model becomes React-hook-only glue, Unity/Unreal portability drops.

Mitigation:

- keep the normalized slot calculation in a plain data module
- keep DOM measurement in a thin adapter layer only

## Definition Of Done

This plan is complete when all of the following are true:

1. the full board remains visible at supported desktop resolutions without unintended clipping
2. all non-board HUD surfaces are positioned from one board-relative coordinate system
3. all non-board HUD surfaces consume one board-scene scale system for font, spacing, and density
4. `App.tsx` no longer owns ad hoc viewport compensation for board-internal HUD placement
5. recent public action / extra info is removed from the normal board page and available through accumulated newest-first debug log output
6. session info defaults to compact and no longer steals core board space
7. layout tests exist for anchors, slots, scale tokens, and debug accumulation behavior
8. any changed transport or layout contracts are documented
9. the bottom trick tray is validated against the 5-card maximum layout case

## Immediate Next Step

Start with Phase 0 and Phase 1 together:

- inventory current coordinate usage
- define the board scene height budget
- remove the current board visibility failure before refactoring the overlay slot system

That ordering is important because the coordinate-system work will be much easier once the board frame itself stops changing unpredictably under resolution stress.

## Revised Implementation Order

The current screenshot review changes the first implementation slice.

The main problem is no longer just outer placement.
It is the mismatch between:

- board-safe bounds
- vertical budget per HUD band
- inner typography and control scaling
- 5-card tray expectations

The implementation must therefore proceed in the following order.

### Step 1. Shared HUD scale contract

Add or tighten shared tokens for:

- top card minimum heights
- active character slot minimum heights
- prompt max height
- prompt choice minimum width and height
- current hand tray max height
- current hand card minimum height
- control height for buttons and chips

This step must reduce the number of fixed pixel values still embedded in the HUD CSS.

### Step 2. Bottom tray first-class 5-card layout

The current hand tray must be treated as a 5-slot grid surface.

Rules:

- if shown as a grid, use 5 columns as the canonical desktop layout
- do not silently collapse to a 4-column layout
- use scale tokens before falling back to structural wrapping
- tray height must be capped by the board-safe vertical budget

### Step 3. Middle prompt vertical budget

The centered decision prompt must stop competing with the top strip and bottom tray as if it had infinite height.

Rules:

- prompt shell height comes from board HUD scale, not from viewport-only guesses
- prompt inner body scrolls before the shell forces collisions
- prompt cards compact with the same typography/padding tokens used by the rest of the HUD

### Step 4. Safe-band ownership cleanup

Once scale and vertical budgets are stable, move remaining viewport-owned compensations out of `App.tsx` and into board-owned layout metadata.

That includes:

- prompt shell anchoring
- public event lane placement
- hand tray safe-bottom alignment

### Step 5. Final board visibility pass

Only after the HUD bands stabilize should the board ring height and shell budget be tuned again.

This avoids chasing false regressions caused by oversized prompt and tray content.
