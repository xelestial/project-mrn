# [PLAN] Lane-Owned Board Redesign

Status: DRAFT  
Created: 2026-04-26  
Owner: frontend match board

## Problem

The current quarterview board fails the tile principles.

User-defined principles:

1. One lane's exterior outline must always be a straight line. It must not become stair-stepped.
2. All tiles must be fully connected. Tiles must not be hidden, clipped, or visually overlapped by HUD panels or other tiles.

The current implementation still renders forty independently positioned and transformed `.tile-card` elements. Even when the mathematical tile centers line up, the visible board can fail because each tile owns its own exterior, outline, shadow, antialiasing, hover behavior, and internal surface. That makes the board read as separate floating cards rather than one connected lane-based board.

## Failure Analysis

The last pass made the wrong architectural tradeoff.

- It tried to preserve the existing absolute-tile renderer and tune constants around it.
- It treated viewport containment as a sizing problem instead of a geometry ownership problem.
- It used visual patches, such as removing rounded corners and shrinking the board, but the visible exterior still belonged to each individual tile.
- It validated DOM count, build success, and rough viewport fit, but did not validate the stricter visual invariants.
- It placed HUD by viewport guesses, so weather and prompt panels could still intrude into the board-safe area.

The root mistake: the board's visible lane outline must be owned by the lane, not by each tile.

## Decision

Redesign the board renderer around lane-owned continuous geometry.

The visible board surface should be four continuous lane strips:

- top lane
- right lane
- bottom lane
- left lane

Each lane is a single transformed strip with one straight exterior edge. Tile cells are subdivisions inside that strip. Tile content, ownership stamp, price, and special markers live inside the lane cells, but they do not define the lane's exterior geometry.

This means the board should be rendered in two layers:

1. `board-lane-surface-layer`: owns the visible connected board.
2. `board-tile-interaction-layer`: optional invisible or minimally visible hit targets, focus rings, stage/reveal effects, and accessibility semantics.

The old approach, where every visible tile card is an independent board piece, should be removed for ring topology once the new renderer is stable.

## Non-Negotiable Invariants

### Geometry

- A lane exterior is one continuous straight line.
- A lane must not be assembled from visually offset tile boxes.
- Adjacent cells inside a lane may have internal dividers, but those dividers must not change the lane exterior.
- Four lane strips must meet at the corners without visible gaps.
- Corner/finish tiles must visually touch exactly the adjacent two lanes.
- No tile cell may overlap another cell in a way that hides information.
- No HUD may cover any tile or character standee.

### Information

Each normal tile must retain:

- tile index
- tile kind label
- purchase/rent value
- owner status
- score coin count when present
- owner stamp slot, including an empty reserved slot before ownership
- move/stage/reveal affordances

Each special tile must use the whole cell:

- fortune tile uses the entire cell for the fortune identity
- finish/end tile uses the entire cell for the finish/end identity
- special symbols are visual, but must not replace required gameplay state when relevant

### Responsiveness

- The board must stay inside the map container.
- The board must scale from available board-safe bounds, not from arbitrary viewport constants.
- HUD panels must consume reserved safe bands outside the board, not float over the board.
- If the viewport is too small, reduce board scale before allowing clipping or overlap.

## Target Architecture

### Data Flow

```text
snapshot / manifest tiles
        |
        v
board ring order
        |
        v
lane partition
        |
        v
lane geometry calculation
        |
        v
lane-owned visual cells
        |
        v
interaction/focus/standee overlays
```

### Lane Partition

Create a pure helper, likely in `apps/web/src/features/board/boardProjection.ts`.

```ts
export type QuarterviewLaneId = "top" | "right" | "bottom" | "left";

export type QuarterviewLaneCell = {
  tileIndex: number;
  lane: QuarterviewLaneId;
  laneIndex: number;
  laneCount: number;
  isCorner: boolean;
};

export type QuarterviewLaneModel = {
  lane: QuarterviewLaneId;
  cells: QuarterviewLaneCell[];
};
```

The helper must return lanes in visual order, not merely DOM tile order.

Important: corner/finish tiles are still logical tiles, but their visual treatment must be planned as corner cells that lock two lane ends together.

### Lane Geometry

Create a geometry helper that returns the board scene and each lane strip.

```ts
export type LaneOwnedBoardGeometry = {
  boardAspectRatio: number;
  boardWidthPercent: number;
  boardHeightPercent: number;
  laneAngleDeg: number;
  laneThicknessPercent: number;
  laneLengthPercent: number;
  cornerSizePercent: number;
};
```

Geometry rules:

- `laneAngleDeg` is derived from x/y spread, not hand-coded in CSS.
- `laneThicknessPercent` is shared by all lanes.
- `laneLengthPercent` is shared by all lanes.
- corner size is derived from lane thickness, not tuned separately unless a test proves it is necessary.

The lane surface should be positioned by four side centers, not by every tile center.

### Rendering Layers

#### 1. Lane Surface Layer

Add a new component inside `BoardPanel.tsx`, for example:

```tsx
<div className="board-lane-surface-layer" aria-hidden="true">
  {laneModels.map((lane) => (
    <div className={`board-lane-strip board-lane-strip-${lane.lane}`}>
      {lane.cells.map((cell) => (
        <div className="board-lane-cell">
          <TileCellContent tile={tileByIndex[cell.tileIndex]} />
        </div>
      ))}
    </div>
  ))}
</div>
```

The lane strip owns:

- straight exterior
- shared background/base
- side border
- side shadow
- corner miters

The lane cell owns:

- internal divider
- zone strip
- textual information
- reserved stamp slot

#### 2. Interaction Layer

The existing `.tile-card` articles can temporarily remain for semantics and event/focus overlays, but their visible background must be disabled once lane cells render the tile information.

Migration-safe interim rule:

```css
.board-ring-quarterview .tile-card {
  background: transparent;
  box-shadow: none;
  outline: none;
}

.board-ring-quarterview .tile-card .tile-content {
  opacity: 0;
  pointer-events: none;
}
```

Final rule:

- remove duplicated tile content from `.tile-card`
- use `.tile-card` only as hit/focus anchors, or replace it with lane cell semantic buttons/articles

#### 3. Standee Layer

Standee positions must derive from lane cell centers, not from the old independent tile card centers.

```ts
export type LaneCellAnchor = {
  tileIndex: number;
  xPercent: number;
  yPercent: number;
  zIndex: number;
  lane: QuarterviewLaneId;
};
```

Characters should stand on top of the cell center or a lane-specific foot anchor. They must not cover tile text by default; if a character is on a text-heavy cell, place the standee toward the lower visual edge of that cell.

## CSS Design

### Board Container

The board ring should be sized by board-safe bounds:

```css
.board-ring-quarterview {
  width: min(var(--board-safe-width), calc(var(--board-safe-height) * var(--board-qv-aspect-ratio)));
  height: min(var(--board-safe-height), calc(var(--board-safe-width) / var(--board-qv-aspect-ratio)));
}
```

`--board-safe-width` and `--board-safe-height` must come from the match layout, not from scattered viewport constants.

### Lane Strip

```css
.board-lane-strip {
  position: absolute;
  left: var(--lane-x);
  top: var(--lane-y);
  width: var(--lane-length);
  height: var(--lane-thickness);
  display: grid;
  grid-template-columns: repeat(var(--lane-cell-count), minmax(0, 1fr));
  overflow: hidden;
  transform: translate(-50%, -50%) rotate(var(--lane-angle));
}
```

The strip may use a miter clip path at the ends, but the clip belongs to the lane, not to the cells.

### Lane Cell

```css
.board-lane-cell {
  min-width: 0;
  height: 100%;
  display: grid;
  grid-template-rows: 34% minmax(0, 1fr);
  border-inline-start: 1px solid rgba(...);
}
```

No lane cell may have:

- external margin
- independent transform
- exterior shadow
- rounded exterior corner
- hover translate that changes the lane outline

Hover/focus should render a contained inset highlight.

### Tile Content

Normal tile layout:

```text
+--------------------------------+
| colored zone strip + name      |
| index | price/rent | stamp     |
| owner/score compact row        |
+--------------------------------+
```

Special tile layout:

```text
+--------------------------------+
| large symbol                   |
| Fortune / End label            |
+--------------------------------+
```

Lane-specific content rotation is allowed only inside the cell. It must not rotate or distort the lane surface.

## HUD Rules

HUD must be outside board-safe bounds.

Required layout slots:

- player cards: corner/side rail slots
- active character roster: left rail, independently scrollable if needed
- weather: top-left safe HUD slot outside the board bounding polygon
- prompt/waiting/action panel: top or side safe slot outside the board polygon
- hand tray: bottom safe band, not overlapping lower lane

Do not place HUD using arbitrary viewport guesses like `right: 18px` if that can enter the board polygon at another viewport size.

Preferred approach:

```ts
type BoardSafeFrame = {
  boardRect: DOMRect;
  tilePolygon: Array<{ x: number; y: number }>;
  safeTopBand: DOMRect;
  safeLeftRail: DOMRect;
  safeRightRail: DOMRect;
  safeBottomBand: DOMRect;
};
```

This can be implemented incrementally, but the document-level rule is: HUD cannot cover tiles.

## Implementation Plan

### Phase 1. Model and Tests

Files:

- `apps/web/src/features/board/boardProjection.ts`
- `apps/web/src/features/board/boardProjection.spec.ts`

Work:

- add lane partition helper
- add lane-owned geometry helper
- add tile anchor helper derived from lane cells
- test lane counts and visual order
- test lane strips share one angle/thickness/length
- test tile anchors stay inside board bounds

Acceptance:

- no rendering changes yet
- pure tests prove the new model can represent 40 tiles without relying on independent tile exterior geometry

### Phase 2. Lane Surface Renderer

Files:

- `apps/web/src/features/board/BoardPanel.tsx`
- `apps/web/src/styles.css`

Work:

- render `board-lane-surface-layer`
- render lane strips and cells from lane model
- move visible tile content into lane cells
- keep old tile cards only as invisible anchors

Acceptance:

- one lane's exterior is a single strip
- internal cell dividers do not alter the exterior
- all cells are connected inside their lane

### Phase 3. Corner and Special Tile Pass

Work:

- make finish/end/corner cells lock the adjacent lane ends visually
- ensure special tiles use the whole cell
- reserve empty owner stamp slots on normal cells

Acceptance:

- finish/end tile visually touches exactly two lane directions
- no special tile floats as an independent card

### Phase 4. Standee and Overlay Anchors

Work:

- derive standee anchors from lane cell centers
- move stage/focus/reveal effects to lane cell overlays
- keep focus effects inset so they do not change lane exterior

Acceptance:

- character sizes are consistent
- standees do not hide the tile's critical information by default
- move/reveal highlights do not break lane straightness

### Phase 5. HUD Safe Bounds

Work:

- move weather and prompt to board-safe slots
- remove viewport compensation constants that shrink the board arbitrarily
- keep full board visible before growing HUD

Acceptance:

- weather does not cover any tile
- prompt/waiting panel does not cover any tile
- board remains visible without right/bottom clipping

### Phase 6. Cleanup

Work:

- remove obsolete quarterview rail/visual lane experiments
- remove duplicated tile visual CSS blocks
- delete temporary hidden tile content paths after interaction layer is replaced

Acceptance:

- one rendering path owns visible ring topology
- CSS no longer depends on late `!important` override piles for board geometry

## Validation Plan

### Automated

Run:

```sh
cd apps/web && npm run test -- src/features/board/boardProjection.spec.ts
cd apps/web && npm run build
```

Add tests for:

- lane partition order
- lane cell counts
- lane angle/thickness derivation
- tile anchors remain bounded
- corner/finish anchors sit at lane junctions

### Browser

Use the in-app browser at `http://127.0.0.1:9000/#/match`.

Viewports:

- current desktop viewport
- 1280px wide
- 1180px wide
- 980px wide
- short-height desktop

States:

- waiting prompt
- actionable prompt
- no prompt
- visible weather
- active character roster with all 8 entries
- multiple standees on same tile

Visual pass criteria:

- no lane exterior is stair-stepped
- no tile is clipped by viewport
- no tile is covered by HUD
- no tile covers another tile's information
- board is not made tiny just to satisfy containment

## Acceptance Criteria

The redesign is complete only when all are true:

- The board is visibly one connected ring, not forty floating cards.
- Each of the four lanes has a straight exterior edge.
- Lane cells are fully connected with no gaps.
- Corner/finish tiles lock into the two adjacent directions.
- HUD does not overlap the board.
- Tile information volume is preserved.
- Text is readable enough at the supported desktop viewport.
- Browser screenshots confirm the criteria, not just tests/build.

## Rollback Criteria

Rollback or stop the pass if:

- lane cells require independent transforms to look connected
- HUD safe bounds cannot be expressed without arbitrary viewport hacks
- tile information becomes less complete than the current version
- the board must be shrunk so much that it loses primary visual status

Rollback path:

1. keep pure lane model helpers if tests are useful
2. disable lane surface renderer
3. restore previous stable top-view renderer
4. re-plan around canvas/SVG if CSS lane geometry remains too fragile

## Notes for Future Implementation

- Prefer SVG for the visible lane surface if CSS strip miters become hard to control. SVG can own the continuous path and still host HTML overlays for text.
- Do not use `scaleY()` on the whole board. It distorts text, standees, and hit areas.
- Do not add rails as a visual patch. Rails can hide discontinuity instead of solving it.
- Do not validate by DOM count alone. The visual invariants are the acceptance criteria.
