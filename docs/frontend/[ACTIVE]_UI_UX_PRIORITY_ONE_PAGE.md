# [ACTIVE] UI/UX Priority One Page

Status: ACTIVE  
Updated: 2026-04-07  
Source: merged from Claude proposals + Codex review

## Purpose

This is the one-page execution priority for current UI/UX work.

## Current Diagnosis

The current failure is not lack of polish.
It is loss of readability:

1. the player cannot quickly tell whose turn it is
2. the player cannot easily tell why a prompt appeared
3. the board is visible but not dominant
4. remote turns still risk feeling like compressed logs instead of visible scenes

## Immediate Execution Priority

### P0. Fixes That Survive Redesign

1. current actor visibility everywhere
2. no-empty-state on my turn
3. decision labeling cleanup
4. prompt reason visibility

Why:
- these are foundational
- these improve playability immediately
- these remain useful even if a larger redesign happens later

### P1. Readability Layout Fixes

1. keep the board visually first-class
2. reduce duplicate turn/spectator/status surfaces
3. keep current actor resources always readable
4. keep the top line compact: weather + four-player status only
5. merge "preparing" copy into the main decision surface instead of showing a second waiting panel

### P2. Evidence-Driven Dramatic Layer

1. stronger spectator strip / current-turn narration
2. larger movement / landing / rent / purchase reveals
3. interrupt overlays only for truly important events

## Do Now vs Later

### Do Now

- actor emphasis
- my-turn waiting state
- prompt labeling cleanup
- prompt reason/context expansion
- board-first layout tuning
- duplicate panel reduction
- compact top rail with weather + P1-P4
- remove the right-side detail drawer from the main play view
- show dice result and movement as distinct visible beats

### Stage Later

- full panel unification
- full-screen draft/interrupt choreography
- heavy scene transitions
- full board-center redesign

### Reference Only Until Needed

- mobile-first full-screen commercial patterns
- heavy animation systems
- broad architecture replacement of every current panel

## Practical Order

1. fix actor visibility and my-turn blank state
2. fix prompt labeling and prompt reason visibility
3. reduce duplicate turn/spectator panels
4. enlarge and simplify board-first layout
5. run playtests
6. reopen heavier redesign items only if playtest evidence demands it

## File-Level Entry Points

Start here without reading other documents:

### 1. Actor visibility (P0)
- `apps/web/src/features/players/PlayersPanel.tsx`
  - missing: `currentActorPlayerId` prop — no visual indication of whose turn it is
  - fix: add prop, apply `.player-card-active` CSS class when `player.id === currentActorPlayerId`
- `apps/web/src/App.tsx`
  - missing: `currentActorId` not passed to `PlayersPanel`
  - fix: pass `currentActorId={currentActorId}` at the `<PlayersPanel>` call site
- `apps/web/src/styles.css`
  - missing: `.player-card-active` style
  - fix: add border/background highlight rule

### 2. My-turn blank state (P0)
- `apps/web/src/App.tsx`
  - condition: `isMyTurn && !actionablePrompt && !promptBusy`
  - currently: nothing renders in the action zone
  - fix: render a waiting indicator ("처리 중…" spinner) in this gap

### 3. Prompt labeling (P0)
- `apps/web/src/features/stage/TurnStagePanel.tsx` — line ~359
  - bug: `stageLine(turnStage.fields.trick, model.promptSummary)` — non-trick prompts shown under "잔꾀" label
  - fix: show `model.trickSummary` under "잔꾀"; show `model.promptSummary` under a separate `turnStage.fields.decision` label
  - trick-related types (keep under 잔꾀): `trick_to_use`, `hidden_trick_card`, `trick_tile_target`

### 4. Prompt reason visibility (P0)
- `apps/web/src/features/prompt/PromptOverlay.tsx`
  - currently: no explanation of why the prompt appeared
  - fix spec: `docs/frontend/[PROPOSAL]_UI_UX_COMMERCIAL_REDESIGN.md` — Zone D (PromptPanel) + `buildPromptContext()`

### 5. Duplicate panel reduction (P1)
- `apps/web/src/App.tsx`
  - bug: `TurnStagePanel` and `SpectatorTurnPanel` rendered simultaneously
  - fix: `isMyTurn ? <TurnStagePanel /> : <SpectatorTurnPanel />`
  - note: both panels are slated for full replacement in the commercial redesign — this is a minimal patch until then

### 6. Token input state bug (trivial)
- `apps/web/src/App.tsx` — `onUseSession` handler
  - bug: calls `setTokenInput("")` then immediately reads `tokenInput.trim()` (React async state)
  - fix: capture value before clearing — `const token = tokenInput.trim(); setTokenInput(""); ... buildMatchHash(id, token || undefined)`

### 7. "Select a session" oops text in active game (confirmed in live play)
- `apps/web/src/features/players/PlayersPanel.tsx`
  - bug: all player cards show "Select a session" subtitle even after characters are assigned
  - fix: clear this text when player is alive or has a character assigned

### 8. Raw `[효과]` / `[능력N]` / `[도치]` tags in card text (confirmed in live play)
- `apps/web/src/features/prompt/PromptOverlay.tsx` — card description render
  - bug: `[효과] 이번 턴 모든 통행료를 내지 않습니다` — marker tags shown as raw text
  - fix: `parseCardText()` util — replace `[TAG]` patterns with styled badges or `<strong>` tags

### 9. Timeline panel below the fold (confirmed in live play)
- `apps/web/src/App.tsx` — `TimelinePanel` placement
  - bug: "Recent Public Actions" requires scrolling to see; invisible during active play
  - fix: move into side column as scrollable EventFeed (see commercial redesign Zone F)

## Confirmed Non-Issues (revised from earlier analysis)

- **BUG-01 (tile costs)**: costs DO appear after draft completes. Only missing during Round 0 draft phase. Lower priority than originally assessed.

## Reference Documents

Use only when the above entry points are insufficient:

- `docs/frontend/[PROPOSAL]_UI_UX_ISSUE_FIX_PLAN.md` — full bug list with cause/fix/priority
- `docs/frontend/[PROPOSAL]_UI_UX_COMMERCIAL_REDESIGN.md` — full redesign spec (Zone A–I)
- `docs/frontend/[PROPOSAL]_UI_UX_DETAILED_SPEC.md` — pixel math and CSS specs
