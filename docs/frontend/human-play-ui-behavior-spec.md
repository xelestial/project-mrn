# Human Play UI Behavior Spec (React/FastAPI)

## Purpose
Define the target UI behavior for real human play, not stream debugging.

This spec freezes:
- how movement is visualized
- how other players' actions are continuously shown
- how prompts are rendered and submitted
- how turn-time interaction latency is reduced with a client turn orchestrator

## Canonical Round / Turn Flow (Game Theater Standard)

### Round Start
1. Round starts.
2. Weather reveal component opens immediately.
3. Weather panel must show:
   - weather name
   - weather effect text
4. Weather panel remains visible for the whole round (until next weather reveal), pinned at top-left match HUD.

### Draft Phase
1. First draft selection prompt:
   - "1차 드래프트 후보를 지정하세요" (4-card candidate selection)
2. Second draft selection:
   - no user choice UI
   - one card is randomly selected by rule
3. Final character choice prompt:
   - exactly two candidates:
     - card picked in first draft
     - random-selected card from second stage

### Turn Start (Per Player)
1. Bottom overlay: "`OO의 턴입니다`".
2. If actor is not local player:
   - show waiting spinner and "`내 턴이 아닙니다`" state.
3. Actor character reveal (center stage):
   - back-to-front flip transition (1.0s)
   - character name + character effect text.
4. Movement resolution:
   - movement animation phase (2.0s)
   - transition to destination tile
   - destination tile places actor pawn.
5. Trick usage (if used):
   - center card effect with trick name + trick effect text.
6. Land purchase (if purchased):
   - sparkle effect
   - tile color transition to owner color (1.5s).
7. Dice resolution:
   - central dice effect for roll
   - for dice-card usage, show card-shape with number (not cube dice).
8. Center stage persistence:
   - keep current turn artifacts visible:
     - character
     - trick (if used)
     - dice / dice-card.
9. Turn end:
   - show "`턴 종료`" for 2.0s
   - then proceed.
10. Next turn:
   - bottom overlay updates to next actor "`OO의 턴입니다`".

## Layout Model (Viewport First)
- Match screen consumes full viewport (`100vw`, `100vh`) with no fixed max width.
- Main regions:
  - Top command strip (collapsible): lobby controls, connection status, diagnostics.
  - Center stage: board + movement focus + prompt modal layer.
  - Right rail: current situation + players + turn summary.
  - Bottom theater: sequential action cards for all players.
- Raw debug messages remain available but hidden by default in match mode.

## Movement Visualization

### Board
- Every tile always shows:
  - tile number (high contrast)
  - type-aware title (`토지`, `운수`, `종료-1`, `종료-2`, etc.)
  - owner/rent/purchase summary where applicable
- `운수`/`종료` use distinct tile layout (not generic land layout).

### Pawn Rendering
- All active players' pawns are always visible.
- Pawn visual style:
  - high-contrast player color
  - large chess-pawn silhouette.
- Latest movement plays as:
  - source tile pulse (short)
  - destination tile highlight (strong)
  - pawn arrival pulse

### Movement Card Near Board
- For each move event, create a board-near event card:
  - `P2 이동 19 -> 26`
  - include dice/card breakdown when available.

## Other Players' Action Visibility

### Turn Theater (Persistent)
- Theater lane receives action cards for all players, not only local player.
- Required card categories:
  - turn start/end
  - movement
  - landing result
  - purchase / skip purchase
  - rent payment
  - weather reveal / fortune draw / fortune resolve
  - bankruptcy / game end
- No silent jump between other players' turns.

### Side Summary
- Right rail shows current actor and last 3 actions by actor.
- If local player is waiting, show "타 플레이어 진행 중" state with last visible action.

## Weather Persistence Rule (Turn-Scoped)
- Weather reveal is not a one-shot toast.
- After `weather_reveal`, the current round weather must remain visible until the next round weather is revealed.
- Required placements:
  - top status strip (`현재 날씨`)
  - situation panel (`라운드 날씨`)
  - theater card at reveal moment

## Prompt UX (Modal First)

### Prompt Placement
- Active prompt is rendered as modal overlay above board.
- Prompt can be minimized, but not silently moved below fold.
- While minimized, a compact sticky prompt chip remains visible.

### Click Model
- Entire choice card is clickable.
- On submit:
  - set local `SUBMITTING` state
  - disable all choices
  - show spinner and "처리 중" text
- Spinner appears only after user submit action.

### Prompt-Type Rendering Rules
- Hidden trick selection:
  - show all hand cards in one list
  - hidden-selected card is shown with a distinct muted style
- Trick use:
  - single unified option list
  - no duplicated "same options repeated below"
- Dice:
  - two-step UX: `주사위 굴리기` or `주사위 카드 사용`
  - card chips (`[1]...[6]`) for selection, max-card rule shown
  - dice-card visual uses card-shaped badge with fixed number
- Mark target:
  - option text in `대상 인물 / 플레이어` format
- Lap reward:
  - explicit reward breakdown (cash/shards/victory)
  - each option card must show exact resulting amount

## Turn Orchestrator (React Value Restoration)

## Problem
If every click causes full-screen blocking and hard reflow, React value is lost.

## Solution
Client turn orchestrator state machine:
- `IDLE`
- `PROMPT_OPEN`
- `INPUTTING`
- `SUBMITTING`
- `ACKED`
- `NEXT_PROMPT_PENDING`

Rules:
- Keep board and theater interactive while waiting ACK.
- Update local optimistic prompt state immediately.
- Do not re-layout whole page on each decision.
- Allow prompt chaining without losing visual continuity between decisions.

## Lap Reward Flow
- Local UI pre-renders all reward options with amounts.
- Single click submits selected reward; UI remains in modal with submitting indicator until ACK.
- After ACK, theater card shows final selected reward details.

## Contract and Selector Requirements
- Prompt selector must normalize both:
  - `choices`
  - `legal_choices`
- Event selector must normalize payload aliases for:
  - movement fields
  - landing result fields
  - lap reward amount fields
  - mark target fields

## Acceptance Criteria
- Human player can complete one full turn without scroll hunting or ambiguous state.
- Other players' turns are observable via theater cards and board highlights.
- Hidden trick, trick use, dice, mark target, lap reward prompts are all readable and non-duplicated.
- Local decision latency is visually masked by orchestrator states (no "did click work?" uncertainty).
- Round/draft/turn sequence follows the canonical theater order defined above.
