# [PLAN] 3D Board Rendering Contract

Status: ACTIVE_DRAFT  
Owner: Frontend / Runtime UI  
Updated: 2026-05-11

## Purpose

Define how backend-owned Project-MRN `ViewCommit.view_state` is rendered as a 3D board scene.

This document is a rendering contract only. It does not define game rules.

## Hard Rules

1. The 3D scene is not gameplay authority.
2. The 3D scene consumes backend-owned `ViewCommit.view_state` only.
3. The 3D scene must not infer rules from Korean display labels.
4. Korean labels are presentation text only.
5. Animation is cosmetic and must yield to authoritative `ViewCommit` state.
6. Private information must not be represented as a 3D object unless visible to the current viewer.
7. The existing 2D HUD, prompt overlay, and event feed remain the source for dense text and decision explanations.
8. 3D rendering must be feature-flagged until it passes runtime browser checks.

## Recommended Initial Feature Flag

```bash
MRN_ENABLE_3D_BOARD=true
```

Default behavior:

- `false` or unset: keep current 2D board.
- `true`: render 3D board while preserving current HUD, prompt overlay, player panels, and event feed.

## Recommended Initial Stack

Frontend packages:

```bash
npm install three @react-three/fiber @react-three/drei
npm install -D @types/three
```

Recommended directory:

```text
apps/web/src/features/scene3d/
  GameCanvas3D.tsx
  BoardScene.tsx
  BoardCamera.tsx
  BoardLights.tsx
  BoardTile3D.tsx
  PlayerPawn3D.tsx
  PropertyMarker3D.tsx
  ScoreCoin3D.tsx
  MovementPath3D.tsx
  TileSelectionLayer3D.tsx
  SceneHudBridge.tsx
  boardLayout3d.ts
  sceneTypes.ts
```

## Coordinate System

Recommended initial coordinate system:

```ts
const SCENE_COORDINATE_SYSTEM = {
  upAxis: "y",
  boardPlane: "x-z",
  boardCenter: [0, 0, 0],
  tileTopY: 0.08,
} as const;
```

Meaning:

- `x`: board left/right
- `z`: board front/back
- `y`: height
- board center is world origin
- tile objects sit on the X/Z plane

## Recommended MVP Board Defaults

```ts
export const BOARD_3D_DEFAULTS = {
  topology: "ring",
  tileCount: 40,
  sideTileCount: 10,
  tile: {
    width: 1.0,
    depth: 1.0,
    height: 0.16,
    gap: 0.08,
    bevelRadius: 0.04,
  },
  table: {
    padding: 1.0,
    height: 0.18,
    y: -0.16,
  },
  pawn: {
    radius: 0.13,
    height: 0.42,
    baseHeight: 0.06,
    yOffset: 0.28,
  },
  scoreCoin: {
    radius: 0.12,
    height: 0.04,
    yOffset: 0.22,
    maxVisiblePerTile: 3,
  },
  propertyMarker: {
    width: 0.72,
    height: 0.08,
    depth: 0.08,
    yOffset: 0.14,
  },
} as const;
```

## Ring Tile Mapping

For the default 40-tile ring board:

- Tile `0` is the start tile.
- Tile `0` is placed at the front-left corner from the default camera perspective.
- Movement proceeds clockwise around the board.
- Corner indices are `0`, `10`, `20`, `30`.
- Tile `39` is immediately before returning to tile `0`.

Recommended projection behavior:

```ts
export type BoardTopology = "ring" | "line";

export type Tile3DTransform = {
  tileIndex: number;
  position: [number, number, number];
  rotationY: number;
  side: "front" | "right" | "back" | "left";
};
```

Recommended initial mapping:

```ts
export function projectTileTo3DPosition(
  tileIndex: number,
  tileCount = 40,
): Tile3DTransform {
  if (tileCount !== 40) {
    throw new Error("3D MVP supports tileCount=40 only until generalized.");
  }

  const sideTileCount = 10;
  const step = BOARD_3D_DEFAULTS.tile.width + BOARD_3D_DEFAULTS.tile.gap;
  const half = ((sideTileCount - 1) * step) / 2;
  const y = BOARD_3D_DEFAULTS.tile.height / 2;

  if (tileIndex >= 0 && tileIndex <= 9) {
    return {
      tileIndex,
      position: [-half + tileIndex * step, y, half],
      rotationY: 0,
      side: "front",
    };
  }

  if (tileIndex >= 10 && tileIndex <= 19) {
    const offset = tileIndex - 10;
    return {
      tileIndex,
      position: [half, y, half - offset * step],
      rotationY: -Math.PI / 2,
      side: "right",
    };
  }

  if (tileIndex >= 20 && tileIndex <= 29) {
    const offset = tileIndex - 20;
    return {
      tileIndex,
      position: [half - offset * step, y, -half],
      rotationY: Math.PI,
      side: "back",
    };
  }

  if (tileIndex >= 30 && tileIndex <= 39) {
    const offset = tileIndex - 30;
    return {
      tileIndex,
      position: [-half, y, -half + offset * step],
      rotationY: Math.PI / 2,
      side: "left",
    };
  }

  throw new Error(`Invalid tileIndex: ${tileIndex}`);
}
```

Generalization rule:

- The MVP may hard-fail on non-40 tile boards.
- Generalized topology support must be introduced in a separate change with tests.
- Do not silently approximate unknown topology in live play.

## Pawn Slot Defaults

One tile may contain up to four pawns.

Recommended local tile offsets:

```ts
export const PAWN_SLOT_OFFSETS = [
  [-0.24, 0.00,  0.24],
  [ 0.24, 0.00,  0.24],
  [-0.24, 0.00, -0.24],
  [ 0.24, 0.00, -0.24],
] as const;
```

Rules:

- Slot order follows ascending `player_id` unless backend later provides explicit slot order.
- Pawn local offsets are applied relative to the tile transform.
- If more than four pawns are present, render the first four and show a `+N` 2D overlay badge from the HUD bridge.

## Score Coin Slot Defaults

Recommended local tile offsets:

```ts
export const SCORE_COIN_SLOT_OFFSETS = [
  [ 0.00, 0.00, -0.36],
  [-0.18, 0.00, -0.36],
  [ 0.18, 0.00, -0.36],
] as const;
```

Rules:

- Display at most three coins per tile in the MVP.
- If `score_coin_count > 3`, render three coins and show the exact count in the tile tooltip.
- Coin count is derived from `view_state.board.tiles[].score_coin_count`.

## Ownership Marker Defaults

Recommended behavior:

- Property owner is shown as a colored front rail on the tile.
- Owner color maps from `owner_player_id` to stable player colors.
- No owner means no rail.
- Hostile region uses a dark danger rail and cracked-tile overlay.

Recommended player colors:

```ts
export const PLAYER_COLOR_DEFAULTS = {
  1: "#ef476f",
  2: "#118ab2",
  3: "#06d6a0",
  4: "#ffd166",
} as const;
```

Recommended special tile colors:

```ts
export const TILE_KIND_COLOR_DEFAULTS = {
  start: "#f8fafc",
  end_time: "#f97316",
  fortune: "#8b5cf6",
  property_black: "#111827",
  property_red: "#dc2626",
  property_yellow: "#eab308",
  property_blue: "#2563eb",
  property_white: "#e5e7eb",
  property_green: "#16a34a",
  hostile: "#7f1d1d",
  unknown: "#64748b",
} as const;
```

## Camera Defaults

Use an orthographic camera for MVP to avoid perspective distortion and preserve board readability.

Recommended camera preset:

```ts
export const DEFAULT_BOARD_CAMERA = {
  type: "orthographic",
  position: [7.5, 9.0, 7.5],
  target: [0, 0, 0],
  zoom: 62,
  near: 0.1,
  far: 100,
  minZoom: 42,
  maxZoom: 110,
  enableRotate: true,
  enablePan: true,
  enableZoom: true,
  minPolarAngle: Math.PI / 5,
  maxPolarAngle: Math.PI / 2.7,
  resetTransitionMs: 350,
} as const;
```

Camera behavior:

- Default view must show the whole board.
- Reset camera returns to `DEFAULT_BOARD_CAMERA`.
- Camera controls are local UI state only.
- Camera state must not affect gameplay commands.
- Do not auto-rotate the camera during blocking prompts.

## Lighting Defaults

```ts
export const BOARD_LIGHTING_DEFAULTS = {
  background: "#0f172a",
  ambientIntensity: 0.65,
  directional: {
    position: [4, 8, 5],
    intensity: 0.9,
    castShadow: false,
  },
  hemisphere: {
    intensity: 0.35,
  },
} as const;
```

MVP rule:

- Prefer readability over cinematic lighting.
- Shadows are disabled by default until performance is measured.

## 3D Label Policy

Default:

- Do not render dense tile names as 3D text.
- Use hover tooltip / 2D HUD bridge for tile names, cost, rent, owner, and effects.
- Only use very short 3D icons or abbreviations for START, FORTUNE, and END_TIME tiles.

Reason:

- Project-MRN has long Korean labels and rule explanations.
- Dense text in 3D will reduce readability and accessibility.

## Minimum View State Inputs

The 3D board renderer must be able to render from these fields:

```ts
type Board3DViewInput = {
  commitSeq: number;
  board: {
    topology?: "ring" | "line";
    tiles: Array<{
      tile_index: number;
      tile_kind?: string;
      tile_label?: string;
      tile_color?: string;
      owner_player_id?: number | null;
      pawn_player_ids?: number[];
      score_coin_count?: number;
      is_hostile?: boolean;
    }>;
    last_move?: {
      player_id: number;
      from_tile_index: number;
      to_tile_index: number;
      path_tile_indices: number[];
    } | null;
  };
  players: {
    ordered_player_ids: number[];
    marker_owner_player_id?: number | null;
    items?: Array<{
      player_id: number;
      display_name?: string;
      cash?: number;
      shards?: number;
      is_current_actor?: boolean;
      is_marker_owner?: boolean;
    }>;
  };
  prompt?: {
    active?: unknown;
  };
};
```

If a field is missing:

- Render a safe fallback.
- Never invent gameplay state.
- Show diagnostics in development mode only.

## Performance Defaults

Initial limits:

```ts
export const BOARD_PERFORMANCE_DEFAULTS = {
  maxTilesWithoutInstancing: 80,
  maxPawns: 4,
  maxVisibleCoinsPerTile: 3,
  useShadows: false,
  usePostProcessing: false,
  usePhysics: false,
  preferMemoizedGeometry: true,
} as const;
```

MVP rule:

- No physics engine.
- No post-processing.
- No heavy GLB assets.
- No per-frame gameplay selectors.
- Convert `view_state` into render models only when `commit_seq` changes.

## Required Tests

Add tests for:

1. `projectTileTo3DPosition(0)` is front-left corner.
2. `projectTileTo3DPosition(10)` is front-right corner.
3. `projectTileTo3DPosition(20)` is back-right corner.
4. `projectTileTo3DPosition(30)` is back-left corner.
5. `projectTileTo3DPosition(39)` is adjacent to tile `0` on the left side path.
6. pawn slot ordering is stable by `player_id`.
7. score coin render count is capped but exact count remains available to tooltip.
8. unknown topology fails loudly in 3D MVP mode.

## Definition Of Done For MVP Rendering

- The 3D board renders from live `view_state`.
- The whole 40-tile board is visible in default camera view.
- Pawns, ownership markers, score coins, active actor, and marker owner are visible.
- Missing optional fields do not crash the scene.
- No gameplay state is inferred from display text.
- 2D HUD and prompt overlay remain readable above or beside the 3D canvas.
