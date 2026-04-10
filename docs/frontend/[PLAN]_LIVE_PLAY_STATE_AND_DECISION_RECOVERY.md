# [PLAN] Live Play State And Decision Recovery

Status: ACTIVE  
Updated: 2026-04-09  
Owner: Codex

## Purpose

This plan exists to recover three things that are still breaking real play:

1. logic correctness in draft / mark / purchase / trick resolution
2. single-source state propagation through selectors
3. board-first HUD readability

This is not a broad redesign document.
It is an execution plan for the concrete bugs repeatedly reproduced in live play.

## Ground Truth

The current product is still failing in three ways:

1. draft / final-character / mark-target / purchase logic can become inconsistent with what the player sees
2. player cards, active-character strip, hand, and board can show different truths because they do not all read the same derived state
3. decision surfaces and hand trays still fight the board for space instead of behaving like attached board HUD layers

## Execution Order

### P0. Decision Logic Recovery

These must be fixed before more visual polish.

#### 1. Draft state machine audit

Fix:

- first draft pick
- second draft pick
- final character choice
- active-flip carry-over into the next round
- prompt progression when the player should receive control next

Required outcome:

- the chosen candidate does not disappear and reappear under a different face
- final-character options always match what the player actually owns
- current turn ownership stays aligned with the acting priority slot

Primary files:

- `GPT/engine.py`
- `apps/server/src/services/decision_gateway.py`
- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/features/prompt/PromptOverlay.tsx`

#### 2. Mark target candidate generation

Fix:

- mark-target must show every currently active character with lower priority than the acting character
- it must not collapse to only the characters currently assigned to live players

Required outcome:

- mark prompts behave like deduction prompts over active priority cards, not over current player avatars

Primary files:

- `GPT/engine.py`
- `apps/server/src/services/decision_gateway.py`
- `apps/web/src/features/prompt/PromptOverlay.tsx`

#### 3. Matchmaker, arrival, and purchase safety

Fix:

- adjacent purchase candidates must include only legal targets
- arrival / purchase / follow-up purchase must resolve in the right order
- spend changes must not appear before the confirmed outcome

Required outcome:

- no invalid owned-tile purchase prompts
- no “money changed before resolution” confusion

Primary files:

- `GPT/engine.py`
- `apps/server/src/services/decision_gateway.py`
- `apps/web/src/domain/selectors/streamSelectors.ts`

#### 4. Card identity safety

Fix:

- every trick card decision should use a stable card instance id / deck index for validation and resolution
- burden cleanup, hidden trick, active flip, and trick use must all resolve against the same stable identity

Required outcome:

- no accidental duplicate-choice ambiguity
- no “same name card” confusion during burden cleanup or trick use

Primary files:

- `GPT/engine.py`
- `apps/server/src/services/decision_gateway.py`
- `apps/web/src/domain/selectors/promptSelectors.ts`
- `apps/web/src/features/prompt/PromptOverlay.tsx`

### P1. Single-Source State Propagation

#### 1. Derived player state selector

Create one selector path that every visible player status component uses.

It must combine:

- latest snapshot
- active round order
- active-by-card state
- current-turn live delta
- resolved hand state
- current pawn position
- marker ownership

Visible fields:

- current character face
- cash
- shards
- owned tiles
- trick count
- hand score
- placed score
- total score
- pawn position
- marker ownership

Required outcome:

- top player strip, board badges, active-character strip, and hand tray all update from the same source

Primary files:

- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/App.tsx`
- `apps/web/src/features/board/BoardPanel.tsx`

#### 2. Active-character strip truth

Fix:

- `#1 ~ #8` must show the active face for each priority slot
- it must update immediately after flip / round setup / draft resolution
- it must not show placeholder text when a face is already known

Required outcome:

- the strip is a live reference for the real active card map, not a guess

Primary files:

- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/App.tsx`

#### 3. Hand tray truth

Fix:

- used cards must disappear immediately when resolved
- hidden/private state must be derived from the same card identity path
- burden cleanup must operate on the persistent tray, not on transient button counts

Required outcome:

- the bottom hand tray becomes the canonical visible hand state

Primary files:

- `apps/web/src/App.tsx`
- `apps/web/src/features/prompt/PromptOverlay.tsx`
- `apps/web/src/domain/selectors/promptSelectors.ts`

#### 4. Tile-level derived state

Fix:

- board ownership
- pawn position
- placed-score markers
- target highlights

must all consume the same derived selector path as the top cards

Required outcome:

- tile UI no longer lags behind the top HUD

Primary files:

- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/features/board/BoardPanel.tsx`

### P2. Board-First HUD Recovery

#### 1. Decision panels must attach to the board

Fix:

- decision overlays use viewport-safe widths
- hand tray stays attached to the bottom inner board edge
- prompt choice cards use horizontal, boardgame-like card rows when space allows
- no floating side columns or orphan trays

Required outcome:

- the board remains fully legible while decision surfaces read like attached table HUD layers

Primary files:

- `apps/web/src/App.tsx`
- `apps/web/src/styles.css`

#### 2. Weather and active-card HUD

Fix:

- top line: weather + P1~P4
- weather card shows real effect text, not category placeholders
- active-character strip remains compact and horizontally aligned

Required outcome:

- the player can read the current weather and active priority faces in one glance

Primary files:

- `apps/web/src/App.tsx`
- `apps/web/src/i18n/locales/ko.ts`
- `apps/web/src/i18n/locales/en.ts`
- `apps/web/src/styles.css`

#### 3. Event reveal overlays

Fix:

- fortune reveal
- fortune effect
- weather reveal
- dice result
- movement value
- movement path
- landing outcome

Required outcome:

- major public effects are visible in order and do not silently resolve underneath later prompts

Primary files:

- `apps/server/src/services/runtime_service.py`
- `apps/web/src/features/board/BoardPanel.tsx`
- `docs/frontend/[PLAN]_PAWN_MOVEMENT_AND_EVENT_ANIMATION.md`

## Validation Gates

No item above counts as complete unless all three are true:

1. unit / selector regression updated
2. build passes
3. live-play evidence no longer reproduces the reported failure

## Immediate Do-Next Slice

Do these first, in order:

1. draft / final-character / current-turn state machine audit
2. active-character strip sourced only from active card state
3. mark-target candidate generation against active priority slots
4. stable trick-card identity for hidden trick, burden cleanup, and trick use
5. unified player/tile selector path
6. board-attached decision tray and hand tray cleanup
