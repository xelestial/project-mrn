# [PLAN] 3D Interaction And Prompt Mapping

Status: ACTIVE_DRAFT  
Owner: Frontend / Runtime UI  
Updated: 2026-05-11

## Purpose

Define how Project-MRN backend-owned prompt choices map to clickable 3D scene targets.

The 3D scene is an input surface only. It must submit existing backend-provided `choice_id` values and must not invent gameplay decisions.

## Hard Rules

1. The backend prompt is the source of legal choices.
2. The 3D scene may only submit choices present in `view_state.prompt.active.choices` or its backend-owned prompt surface projection.
3. The 3D scene must not infer choice legality from Korean display text.
4. A 3D click without a matching active prompt target is inspection/focus only.
5. No implicit purchase, takeover, rent payment, score placement, or card use may happen from a raw 3D click.
6. Blocking prompts remain visible in the 2D prompt overlay even when 3D selection is available.
7. Stale prompt submissions must be prevented locally when possible and rejected by backend when not.

## Recommended Initial Interaction Mode

MVP default:

```ts
export const BOARD_3D_INTERACTION_DEFAULTS = {
  clickMode: "focus_then_confirm",
  hoverTooltips: true,
  submitOnSingleClick: false,
  requirePromptChoiceMatch: true,
  allowInspectWithoutPrompt: true,
  stalePromptGuard: true,
  showSelectablePulse: true,
  showDisabledDim: true,
} as const;
```

Meaning:

- First click on a valid 3D target focuses/highlights it.
- The 2D prompt overlay still provides the final confirm button.
- For very low-risk choices, a later version may allow single-click submit, but MVP does not.

## Prompt Choice Target Model

Recommended frontend adapter type:

```ts
export type PromptChoiceTarget =
  | {
      kind: "tile";
      tile_index: number;
      choice_id: string;
      request_id: string;
      request_type: string;
      label?: string;
    }
  | {
      kind: "player";
      player_id: number;
      choice_id: string;
      request_id: string;
      request_type: string;
      label?: string;
    }
  | {
      kind: "character";
      character_id: string;
      choice_id: string;
      request_id: string;
      request_type: string;
      label?: string;
    }
  | {
      kind: "card";
      deck_index: number;
      choice_id: string;
      request_id: string;
      request_type: string;
      label?: string;
    }
  | {
      kind: "button";
      choice_id: string;
      request_id: string;
      request_type: string;
      label?: string;
    };
```

Recommended map:

```ts
export type Prompt3DTargetMap = {
  byTileIndex: Map<number, PromptChoiceTarget[]>;
  byPlayerId: Map<number, PromptChoiceTarget[]>;
  byCharacterId: Map<string, PromptChoiceTarget[]>;
  byDeckIndex: Map<number, PromptChoiceTarget[]>;
  buttons: PromptChoiceTarget[];
};
```

## Request Type Mapping Defaults

| request_type | 3D target support | MVP behavior |
| --- | --- | --- |
| `purchase_tile` | tile | Highlight purchasable tile if `tile_index` is present in choice/surface. Click focuses tile; 2D confirm submits. |
| `coin_placement` | tile | Highlight owned eligible tiles. Click focuses tile; 2D confirm submits. |
| `trick_tile_target` | tile | Highlight valid target tiles. Click focuses tile; 2D confirm submits. |
| `mark_target` | character/player | Prefer 2D active-character strip. Optional 3D pawn target if backend provides `player_id`. |
| `movement` | button/card | Keep in 2D prompt overlay. 3D may show movement preview only after choice hover. |
| `lap_reward` | button | Keep in 2D prompt overlay. |
| `draft_card` | character/card | Keep in 2D draft UI. Do not use board click. |
| `final_character` | character/card | Keep in 2D draft UI. Do not use board click. |
| `trick_to_use` | card/button | Keep in 2D hand tray/prompt overlay. |
| `hidden_trick_card` | card/button | Keep in 2D hand tray/prompt overlay. |
| `specific_trick_reward` | card/button | Keep in 2D prompt overlay. |
| `burden_exchange` | card | Keep in 2D prompt overlay due to simultaneous response and private hand visibility. |
| `geo_bonus` | button | Keep in 2D prompt overlay. |
| `doctrine_relief` | player/button | Prefer 2D prompt overlay. Optional 3D pawn focus only. |
| `pabal_dice_mode` | button | Keep in 2D prompt overlay. |
| `runaway_step_choice` | tile/button | Optional tile highlight if backend provides target positions. Otherwise 2D only. |
| `active_flip` | character/button | Keep in 2D prompt overlay. |

## Required Backend/Selector Inputs

The 3D adapter should prefer backend-owned prompt `surface` fields when available.

Useful existing-style fields:

```ts
type PromptSurfaceTileOption = {
  choice_id: string;
  tile_index: number;
  title?: string;
  description?: string;
};
```

Examples:

- `surface.purchase_tile.options[].tile_index`
- `surface.coin_placement.options[].tile_index`
- `surface.trick_tile_target.options[].tile_index`
- `surface.runaway_step.bonus_target_pos`
- `surface.runaway_step.one_short_pos`

If the prompt lacks a stable target field:

- Do not infer a 3D target.
- Render the choice only in the 2D prompt overlay.
- Add a TODO or diagnostic in development mode.

## Click Handling Contract

Recommended click algorithm:

```ts
function handleTileClick(tileIndex: number, context: SceneInteractionContext) {
  const activePrompt = context.activePrompt;
  const targets = context.promptTargetMap.byTileIndex.get(tileIndex) ?? [];

  if (!activePrompt || targets.length === 0) {
    context.inspectTile(tileIndex);
    return;
  }

  if (targets.length === 1) {
    context.focusPromptTarget(targets[0]);
    return;
  }

  context.openTargetDisambiguation(targets);
}
```

Submit algorithm:

```ts
function submitFocusedPromptTarget(context: SceneInteractionContext) {
  const target = context.focusedPromptTarget;
  const activePrompt = context.activePrompt;

  if (!target || !activePrompt) return;
  if (target.request_id !== activePrompt.request_id) return;
  if (!activePrompt.choices.some((choice) => choice.choice_id === target.choice_id)) return;

  context.submitDecision({
    request_id: activePrompt.request_id,
    request_type: activePrompt.request_type,
    player_id: activePrompt.player_id,
    choice_id: target.choice_id,
  });
}
```

## Hover Tooltip Defaults

Tile hover tooltip should show only viewer-visible data:

```ts
type TileTooltipView = {
  tile_index: number;
  label?: string;
  kind?: string;
  owner_label?: string;
  cost?: number;
  rent?: number;
  score_coin_count?: number;
  pawn_labels?: string[];
  selectable_reason?: string;
};
```

Default tooltip placement:

- Use 2D overlay anchored to projected screen position.
- Do not use dense 3D text.
- Hide tooltip while dragging/orbiting camera.

## Selection Visual Defaults

```ts
export const SELECTION_VISUAL_DEFAULTS = {
  selectableEmissiveIntensity: 0.28,
  focusedEmissiveIntensity: 0.55,
  disabledOpacity: 0.42,
  hoverScale: 1.035,
  focusedScale: 1.06,
  pulseMs: 1200,
} as const;
```

Rules:

- Selectable tiles pulse subtly.
- Focused tile is visibly stronger than hover.
- Disabled/non-selectable tiles may dim only during blocking tile prompts.
- Never hide non-selectable board state completely.

## Decision Submission Guard Defaults

```ts
export const DECISION_SUBMISSION_GUARD_DEFAULTS = {
  dedupeSameRequestId: true,
  blockWhilePendingAck: true,
  clearFocusOnNewCommitSeq: true,
  clearFocusOnPromptChange: true,
  clearFocusOnDecisionAck: true,
  rejectLocalIfChoiceMissing: true,
} as const;
```

Rules:

- The frontend must not submit the same `request_id + choice_id` twice while pending.
- A new `view_commit_seq` with a different active prompt clears focused target.
- A rejected/stale ack clears pending UI and rehydrates from latest `ViewCommit`.

## Inspection Mode Defaults

When there is no active matching prompt:

- Tile click opens inspection state only.
- Pawn click opens player summary only.
- Property marker click opens tile ownership summary only.
- No command is submitted.

Recommended inspection state:

```ts
type SceneInspectionState =
  | { kind: "none" }
  | { kind: "tile"; tile_index: number }
  | { kind: "player"; player_id: number }
  | { kind: "property"; tile_index: number };
```

Inspection state is local UI state and must not be persisted to backend.

## 3D Prompt Cause Display

3D may emphasize the target, but the cause explanation remains in 2D prompt/event UI.

Examples:

- Weather-caused prompt: 2D overlay must show weather name/effect context.
- Trick-caused prompt: 2D overlay must show trick name/effect context.
- Character-caused prompt: 2D overlay must show character/source context.

3D scene must not replace effect-cause readability.

## Accessibility Defaults

MVP must keep a non-3D fallback path:

- Existing 2D prompt buttons remain usable.
- Tile choices must be available through the prompt overlay or a 2D list even when 3D click fails.
- Keyboard focus must remain in the 2D prompt overlay for blocking decisions.

## Required Tests

Add tests for:

1. `purchase_tile` prompt with `tile_index` maps to one tile target.
2. `coin_placement` prompt with multiple tile options maps all eligible tile targets.
3. Unknown prompt type maps to no 3D target and stays 2D-only.
4. Tile click without matching prompt does not submit a decision.
5. Tile click with one matching prompt target focuses the target but does not submit in MVP mode.
6. Submit focused target sends backend-provided `choice_id` only.
7. Focus clears when `request_id` changes.
8. Focus clears when `commit_seq` changes and active prompt changes.
9. Duplicate pending decision is suppressed locally.
10. Stale/rejected ack returns UI to latest authoritative prompt state.

## Definition Of Done For MVP Interaction

- 3D tile clicks cannot create illegal decisions.
- All 3D submissions use backend-provided `choice_id`.
- Dense/card/private decisions remain safe in 2D UI.
- Clickable 3D targets are visible only when the active prompt supports them.
- 2D prompt overlay remains fully functional without 3D clicks.
