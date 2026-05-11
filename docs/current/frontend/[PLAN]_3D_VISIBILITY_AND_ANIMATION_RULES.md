# [PLAN] 3D Visibility And Animation Rules

Status: ACTIVE_DRAFT  
Owner: Frontend / Runtime UI  
Updated: 2026-05-11

## Purpose

Define how 3D board rendering protects viewer-specific visibility and how cosmetic animation follows authoritative backend state.

This document prevents three classes of 3D regressions:

1. leaking private game information through 3D objects
2. letting animation become gameplay authority
3. making reconnect/recovery show stale or misleading motion

## Hard Rules

1. The 3D scene renders only the current viewer's `ViewCommit.view_state`.
2. The 3D scene must not use replay data to fill live state gaps.
3. The 3D scene must not reveal private draft, character, trick, burden, or hand state.
4. Animation is cosmetic only.
5. The latest authoritative `ViewCommit` wins over any in-flight animation.
6. Reconnect recovery renders static authoritative state first.
7. 3D effects must not delay blocking prompts or decision submission.
8. 3D effects must not replace 2D cause/effect explanations.

## Recommended Visibility Model

```ts
export type VisibilityMode =
  | "public"
  | "private_to_viewer"
  | "hidden"
  | "revealed";

export type RenderableSecretPolicy = {
  characterFace: VisibilityMode;
  draftCandidate: VisibilityMode;
  hiddenTrickCard: VisibilityMode;
  burdenCard: VisibilityMode;
  finalCharacterBeforeTurnStart: VisibilityMode;
};
```

Recommended default policy:

```ts
export const RENDERABLE_SECRET_POLICY_DEFAULTS = {
  characterFace: "public",
  draftCandidate: "private_to_viewer",
  hiddenTrickCard: "private_to_viewer",
  burdenCard: "private_to_viewer",
  finalCharacterBeforeTurnStart: "private_to_viewer",
} as const;
```

Interpretation:

- If the viewer's `view_state` includes a private item, it may be rendered for that viewer.
- If the viewer's `view_state` does not include the item, 3D must not reconstruct it.
- Spectators get only public/revealed information.

## 3D Representation Of Private Information

MVP rule:

- Do not represent hidden trick cards as 3D card objects on the board.
- Do not represent unrevealed final characters as pawn models or icons.
- Do not render draft candidates in the 3D scene.
- Keep private card/draft UI in the existing 2D prompt/hand surface.

Allowed:

- A player's pawn may exist on the board because position is public.
- A current actor highlight may exist if `is_current_actor` is visible in view_state.
- A marker owner indicator may exist if `marker_owner_player_id` is visible in view_state.
- A generic unrevealed badge may exist if backend explicitly provides unrevealed state for that viewer.

Not allowed:

- Guessing character identity from turn order, Korean labels, card art, or prior raw events.
- Showing a character-specific model before the backend marks that character as revealed for the current viewer.
- Showing hidden card art in 3D if the current viewer cannot see it.

## Viewer Mode Defaults

```ts
export type SceneViewerMode = "seat" | "spectator" | "debug";

export const VIEWER_MODE_DEFAULTS = {
  seat: {
    showOwnPrivatePromptData: true,
    showOtherPrivatePromptData: false,
    showDebugIds: false,
  },
  spectator: {
    showOwnPrivatePromptData: false,
    showOtherPrivatePromptData: false,
    showDebugIds: false,
  },
  debug: {
    showOwnPrivatePromptData: true,
    showOtherPrivatePromptData: false,
    showDebugIds: true,
  },
} as const;
```

Debug mode rule:

- Debug mode may show IDs and diagnostics.
- Debug mode still must not reveal private state absent from the current viewer's `ViewCommit`.

## Animation Authority Defaults

```ts
export const ANIMATION_AUTHORITY_DEFAULTS = {
  animationIsCosmetic: true,
  blockPromptForAnimation: false,
  blockCommitForAnimation: false,
  authoritativeCommitWins: true,
  reconnectReplaysAnimation: false,
  snapOnLargeDivergence: true,
  largeDivergenceTileDistance: 2,
  maxAnimationDelayMs: 700,
} as const;
```

Meaning:

- UI may animate movement for readability.
- Backend does not wait for animation.
- If a new commit conflicts with an animation, stop or blend to authoritative state.
- Reconnected clients show the latest static state first and do not replay old movement by default.

## Recommended Animation Durations

```ts
export const BOARD_ANIMATION_DEFAULTS = {
  pawnStepMs: 180,
  pawnStepMaxMs: 260,
  pawnHopHeight: 0.18,
  pawnSettleMs: 120,
  purchaseFlashMs: 450,
  rentTransferMs: 550,
  scoreCoinPlaceMs: 360,
  weatherRevealMs: 700,
  fortuneRevealMs: 650,
  hostileRegionConvertMs: 650,
  focusTileMs: 220,
  cameraFocusMs: 350,
  maxQueuedVisualEvents: 6,
} as const;
```

Animation timing rule:

- Movement may take `pawnStepMs * path length`, but visual delay should not block prompts.
- If prompt appears while movement is still animating, the prompt appears immediately.
- If the animation queue exceeds `maxQueuedVisualEvents`, drop old cosmetic events and render the latest state.

## Movement Animation Contract

Input:

```ts
type LastMoveView = {
  player_id: number;
  from_tile_index: number;
  to_tile_index: number;
  path_tile_indices: number[];
};
```

Recommended behavior:

1. If `path_tile_indices` is empty, snap pawn to `to_tile_index`.
2. If the player pawn is not currently rendered, spawn it at `to_tile_index`.
3. If the current commit is a reconnect hydration commit, do not animate; snap to final state.
4. If the previous commit already animated the same `player_id + to_tile_index + path`, do not replay it.
5. If a new commit arrives with a different pawn position, stop current animation and reconcile.

Recommended animation key:

```ts
type MovementAnimationKey = `${number}:${number}:${number}:${string}`;
// player_id:from_tile_index:to_tile_index:path_tile_indices.join("-")
```

## Reconciliation Defaults

```ts
export const ANIMATION_RECONCILIATION_DEFAULTS = {
  sameCommitSeq: "ignore",
  newerCommitSeq: "reconcile",
  missingPawn: "snap_to_authoritative",
  staleAnimation: "cancel",
  pathMismatch: "cancel_and_snap",
  promptAppeared: "continue_visual_only",
  gameCompleted: "snap_all_and_stop",
} as const;
```

Rules:

- `commit_seq` is the main freshness indicator.
- A newer commit never waits for older visual work.
- Game-over state cancels all board animations and renders final state.

## Visual Event Defaults

Recommended low-risk visual events:

| Event | 3D behavior | 2D explanation required |
| --- | --- | --- |
| pawn movement | animate pawn along path | yes, if caused by trick/fortune/character |
| property purchase | owner rail appears with flash | yes |
| rent payment | small coin trail or resource pulse | yes |
| score coin placement | coin drops onto tile | yes |
| weather reveal | board-wide subtle tint/banner | yes |
| fortune reveal | fortune tile pulse | yes |
| bankruptcy | player panel danger state + hostile tile conversion | yes |
| hostile region | cracked/danger rail on tile | yes |

MVP rule:

- If the cause is not available in `view_state` / effect context, do not invent it in 3D.
- Use generic animation only and rely on 2D feed for exact explanation.

## Camera And Animation Interaction

Defaults:

```ts
export const CAMERA_ANIMATION_DEFAULTS = {
  autoFocusActivePawn: false,
  autoFocusMovement: false,
  autoFocusBlockingPromptTarget: true,
  userCameraOverrideMs: 8000,
  promptFocusPadding: 1.4,
} as const;
```

Rules:

- Do not constantly move camera during AI turns.
- If user manually controls camera, suppress automatic focus for `userCameraOverrideMs`.
- Blocking tile prompt may focus the relevant tile area once.
- Camera motion must not obscure the 2D prompt overlay.

## Reconnect And Resume Defaults

Reconnect behavior:

```ts
export const RECONNECT_RENDER_DEFAULTS = {
  firstCommitRendersStatic: true,
  replayLastMoveOnReconnect: false,
  clearAnimationQueueOnReconnect: true,
  clearFocusedPromptTargetOnReconnect: true,
  preserveLocalCameraIfSameSession: true,
} as const;
```

Rules:

- First commit after WebSocket reconnect renders authoritative snapshot.
- Do not replay old `last_move` merely because it exists in snapshot.
- If the active prompt is present after reconnect, render prompt immediately.

## Prompt Visibility Rules

- A prompt visible to the current viewer may highlight related 3D targets.
- A prompt not visible to the current viewer must not produce 3D target highlights.
- Spectator mode may show public pending actor state, but not private choice surfaces.
- Simultaneous private prompts are never visualized as other players' 3D choices.

## Stale Visual State Cleanup

Clear local 3D state when any of these changes:

```ts
export const SCENE_STATE_CLEANUP_TRIGGERS = {
  sessionIdChanged: true,
  viewerChanged: true,
  activePromptRequestIdChanged: true,
  activePromptCleared: true,
  decisionAckReceived: true,
  gameStatusCompleted: true,
  manifestHashChanged: true,
} as const;
```

Cleanup rules:

- Focused prompt target clears on prompt change.
- Hover state clears on board topology/manifest change.
- Animation queue clears on session/viewer change.
- Cached board projection clears on manifest hash change.

## 3D Asset Visibility Policy

MVP allowed assets:

- generic pawn per player
- generic tile meshes
- generic score coin mesh
- generic ownership rail/marker
- generic weather overlay
- generic fortune pulse

MVP disallowed assets:

- character-specific pawn models before reveal policy is fully wired
- card-art 3D meshes for hidden/private cards
- per-character skill VFX that imply unrevealed identity
- heavy GLB scenes that block runtime responsiveness

## Asset Loading Defaults

```ts
export const ASSET_LOADING_DEFAULTS = {
  usePrimitiveMeshesFirst: true,
  allowGLBInMvp: false,
  maxInitial3DAssetBudgetMb: 3,
  lazyLoadDecorativeAssets: true,
  fallbackToPrimitiveOnLoadError: true,
} as const;
```

Rules:

- MVP should not depend on GLB assets.
- Decorative assets must fail gracefully.
- Board gameplay readability must survive asset loading failure.

## Required Tests

Add tests for:

1. private final character state is not rendered for spectator before reveal.
2. hidden trick card is not represented as a 3D card for other players.
3. own private prompt can highlight own valid targets.
4. spectator receives no private 3D target highlights.
5. new `commit_seq` cancels stale animation.
6. reconnect first commit renders static final pawn positions.
7. movement animation does not block prompt rendering.
8. game completed state clears animation queue.
9. manifest hash change clears projection cache.
10. missing effect cause does not create fake 3D cause labels.

## Definition Of Done For MVP Visibility And Animation

- 3D scene leaks no private information beyond the current viewer's `view_state`.
- Reconnect shows correct static authoritative state without replay confusion.
- Movement animation works but never controls game progression.
- Prompt visibility and 3D target highlights match backend-owned prompt visibility.
- 3D scene remains understandable when animations are skipped or cancelled.
