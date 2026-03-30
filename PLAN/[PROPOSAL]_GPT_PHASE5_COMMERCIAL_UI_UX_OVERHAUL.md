# GPT Phase 5 Commercial UI/UX Overhaul Proposal

Status: `ACTIVE`
Owner: `GPT`
Scope: `Phase 5 live + replay viewer user-facing UX`
Reviewed on: `2026-03-29`

## Why This Proposal Exists

The current Phase 5 viewer works, but it still behaves like an engine console with panels.

The new requirement is stronger:

- the match should feel readable at a glance like a commercial board game UI
- a human should be able to follow the full turn flow without mentally reconstructing engine events
- prompt timing should feel spatial and contextual, not like a floating form over the board
- replay and live play should present the same public story of the match

This proposal treats UI/UX quality as a first-class implementation track, not as polish to do at the very end.

## Product Goal

Turn the current Phase 5 viewer into a board-game-grade match presentation layer with:

1. clear turn theater
2. map-anchored interaction
3. persistent public action history
4. resource deltas with reasons
5. replay/live parity for the public match narrative

Target inspiration level:

- easy-to-read turn flow like `모두의 마블`
- contextual board feedback like modern digital board games
- low-cognitive-load action summaries during other players' turns

## Current Problems

### 1. Turn Flow Is Fragmented

The player currently sees:

- prompts
- side-panel status
- event feed
- overlays

but not one dominant "story" of the turn.

Result:
- players lose track of who acted
- movement and settlement can happen without a strong visual handoff
- other-player turns feel invisible unless the user watches multiple panels

### 2. Prompts Still Feel Like Engine Forms

Even after recent fixes:

- prompts can still feel detached from the board
- some choices expose engine-style context instead of player-facing explanations
- large decision lists still compete with the map rather than work with it

### 3. Public Consequences Are Not The Primary Visual Layer

The most important public consequences should always be obvious:

- where the pawn moved
- what tile it landed on
- whether rent was paid
- whether a purchase happened
- whether a fortune/weather effect changed resources
- what the current turn stage is

Right now, these are visible, but not yet staged as the main experience.

## Current Source Audit (2026-03-29)

Audit target:
- `GPT/viewer/renderers/play_html.py`
- `GPT/viewer/human_policy.py`
- `GPT/viewer/prompt_server.py`
- `GPT/viewer/live_server.py`
- `GPT/run_human_play.py`

### Audit Summary

The viewer now has meaningful Phase 5 foundations:
- prompt anchoring
- public action overlay
- story rail
- event feed scroll
- asset delta panel
- bankruptcy banner

However, the current user-play UX is still below "commercial board-game" quality in three critical areas.

### Critical Gaps

1. Text rendering/encoding quality is inconsistent in the live template.
- Several user-facing labels still appear as mojibake-like strings in source.
- This directly harms readability and trust in the UI.

2. Network/polling failure handling is console-only.
- `pollEvents` and `pollPrompt` currently fail with `console.warn(...)` but no in-UI recovery guidance.
- During local hiccups, users can mistake delay/failure for input bugs.

3. Accessibility and input resilience are incomplete.
- No keyboard-first decision navigation contract is defined yet.
- No ARIA/live-region strategy is documented for turn/alert changes.
- This is a practical UX issue for long sessions, not just compliance polish.

### Priority Backlog (Updated)

P0 (must do first):
- [DONE] Encoding normalization pass for live-viewer player-facing strings.
- [DONE] Turn theater v2:
  - dominant current-turn stage card
  - ordered public action lane
  - explicit actor handoff readability
- [DONE] Incident card layer near board (`incident-stack`):
  - purchase / rent / fortune / weather / landing
  - board-near presentation (not side-panel-only)

P1 (next):
- [DONE] Prompt guidance pack:
  - [DONE] concise "what changed" line before prompt opens
  - [DONE] prompt-family-specific actionable hint expansion
- [DONE] Failure UX:
  - reconnect/wait state on polling failures
  - stale-state indicator (`업데이트 지연 Ns`) for delayed backend heartbeat
- [DONE] Accessibility baseline:
  - keyboard selection flow
  - focus return policy
  - live-region notices for turn/bankruptcy/critical milestones

P2 (after stabilization):
- [DONE] Motion polish baseline:
  - staged movement animation (tile flash)
  - incident/activity/theater motion transitions
- [DONE] Live/replay wording parity hardening with shared phrase dictionary

### Implementation Progress Update (2026-03-29, Continued)

Completed in this slice:

- `탈출 노비` 선택 이동이 실제 사람 프롬프트(`runaway_step_choice`)로 연결됨
  - engine emits `runaway_choice` metadata on `dice_roll`
  - live prompt shows explicit `+1 이동` vs `정지` choices
  - replay/live event detail now exposes the actual chosen branch
- 보드 중앙 `incident-stack` 사건 카드 레이어 연결 완료
  - purchase / rent / weather / fortune / landing-resolved feed surfaced near board center
- 네트워크 실패 가시화 1차 완료
  - header `network-badge` added
  - `/events` and `/prompt` polling failures now surface as `연결 지연` / `재연결 중` UI state
  - stale-state badge now escalates to `업데이트 지연 Ns` when backend heartbeat is delayed
- 접근성/입력 회복력 1차 완료
  - decision overlay now includes dialog ARIA attributes
  - keyboard decision navigation added (arrow keys + enter/space)
  - `aria-live` announcement channel added for turn/prompt/bankruptcy milestones
  - focus-return policy added (decision close -> previous focus restore)
- 사용자 표기 정리 1차 완료
  - `play_html`의 핵심 이벤트/행동/자원 문구를 사람 친화 한국어로 교체
  - 턴 극장/자원 로그/이벤트 라벨의 `??` 형태 임시 표기를 대폭 제거

Closed in this follow-up:

- replay/live wording dictionary convergence is now wired to a shared source-of-truth module
  - `GPT/viewer/renderers/phrase_dict.py` now provides canonical Korean event and landing labels
  - replay renderers (`html_renderer.py`, `markdown_renderer.py`) consume the shared module
  - live renderer (`play_html.py`) now receives the same labels through injected JSON maps
  - regression tests now assert:
    - live HTML no longer ships unresolved phrase placeholders
    - replay phrase dictionary includes all current canonical event/landing keys

Verification:

- `python GPT/test_human_play.py` (PASS)
- `python GPT/test_live_server.py` (PASS)
- `python GPT/test_replay_viewer.py` (PASS)

### Implementation Progress Update (2026-03-29, Motion Polish Pass)

Completed in this pass:

- live viewer theater and incident cards now use staged motion transitions:
  - enter animation for `turn theater` cards
  - enter/fade transition for bottom activity overlay
  - enter transition for board-near incident stack cards
- move readability polish:
  - source/destination tile flash animation on `player_move`
- event label consistency in live view:
  - unified live label map override for user-facing event names

Verification:

- `python GPT/test_human_play.py` (PASS)
- `python GPT/test_live_server.py` (PASS)
- `python GPT/test_replay_viewer.py` (PASS)

### Implementation Progress Update (2026-03-29, Phase 5 Follow-up)

Completed in this follow-up:

- live decision labels now normalize common engine/English wording into human-readable Korean phrasing:
  - `Skip purchase` -> `구매 없이 턴 종료`
  - `Hide nothing` -> `이번에는 숨김 안 함`
  - `Skip (no trick)` -> `이번에는 사용 안 함`
  - `Use card(s)` -> `주사위 카드 사용`
- board tile kind labels now use player-facing text for special tiles:
  - `F1/F2` -> `종료 - 1 / 종료 - 2`
  - `S` -> `운수`
- turn theater now renders a dominant top card (`현재 턴 핵심`) before secondary rail cards.
- landing resolution event detail now summarizes public outcome more clearly, including
  `PURCHASE_SKIP_POLICY` -> `구매 없이 턴 종료`.

Verification:

- `python GPT/test_human_play.py` (PASS)
- `python GPT/test_live_server.py` (PASS)
- `python GPT/test_replay_viewer.py` (PASS)

### Implementation Progress Update (2026-03-29, Contract/Replay/Live Pass)

Completed in this pass:

- shared-contract payload sync on GPT engine side:
  - canonical fields added for `dice_roll`, `player_move`, `mark_resolved`, `marker_transferred`, `weather_reveal`, `game_end`, `round_start`
  - compatibility aliases kept so existing replay/live consumers remain stable
- replay fallback/compatibility cleanup:
  - replay projection now resolves `session_start`/`game_end` more robustly
  - replay renderers now prefer canonical payload names with alias fallback
  - marker/game-end wording fallback paths were tightened
- live Phase 5 readability improvements:
  - movement/event detail now reads canonical fields (`from_tile_index`, `to_tile_index`, `cards_used`, `total_move`)
  - event feed retention increased (`40 -> 200`) so longer turns can be reviewed without immediate truncation
  - board center end-time indicator now shows remaining end time (`15 - f_value`) instead of raw `f_value`
  - purchase prompt tile callout and tile meta wording were normalized into player-facing text (`구매 예정`, `통행료 N냥`)

### Acceptance Delta Added

This proposal now additionally requires:
- no unreadable user-facing mojibake text in live viewer
- players can understand connection state without dev console
- each non-human turn is readable through one theater lane without scanning all panels

## UX Direction

### A. Turn Theater

Each turn should read as a short public sequence:

1. actor focus
2. movement choice / roll result
3. movement path + arrival
4. landing resolution
5. purchase / rent / fortune / reward consequences
6. end-of-turn settle

Implementation direction:

- keep a strong top turn banner
- add a public action rail that reads like a sequence of action cards
- ensure every major action has:
  - actor
  - action type
  - concise result
  - board context when relevant

### B. Map-Anchored Interaction

Prompts should appear where the decision matters.

Examples:

- purchase prompt near the target tile
- movement result near the destination
- mark / target prompts visually tied to the target player or tile
- public action callouts close to the affected area when possible

### C. Public Ledger + Spectator View

The viewer should support "I am waiting for my turn" as a first-class mode.

Needed:

- visible recent public actions
- scrollable history
- large summary cards for the latest important action
- a compact resource delta log explaining why cash changed

### D. Board Readability First

The board must remain readable without relying on side panels.

Needed:

- stronger tile ownership and target highlighting
- clearer pawn markers
- better special tile labeling
- less engine shorthand
- explicit tile callouts when a tile is the current interaction target

### E. Replay/Live Narrative Parity

Replay and live should tell the same public story:

- same action naming
- same event ordering semantics
- same public consequence wording
- same movement and settlement emphasis

## Phase 5 Overhaul Workstreams

### Workstream 1. Turn Theater Shell

Goal:
- create a dominant "current turn" presentation area

Deliverables:
- stronger turn banner
- current actor focus card
- public action rail
- clearer round / weather / stage presentation

### Workstream 2. Contextual Prompt System

Goal:
- make prompts feel attached to board state, not detached modal forms

Deliverables:
- prompt anchoring by tile / player / event type
- better prompt summaries
- better preview cards
- reduced engine-facing wording

### Workstream 3. Public Consequence Layer

Goal:
- make the result of every action instantly legible

Deliverables:
- movement reveal cards
- purchase callouts
- rent / reward / weather / fortune deltas
- clear "why money changed" surface

### Workstream 4. Spectator Continuity

Goal:
- keep the game understandable when it is not the user's turn

Deliverables:
- public action overlay
- scrollable event ledger
- event rail
- temporary spotlight cards for major actions

### Workstream 5. Replay/Live Unification

Goal:
- converge the public-facing action language and visual sequencing

Deliverables:
- shared wording standards
- shared action labels
- shared ordering expectations for movement -> landing -> purchase consequences

## Immediate Next Slice

The original first slice is now complete:

- board-game-style public action rail
- stronger turn banner / spectator continuity layer
- persistent action lane + transient bottom overlay
- motion-ready layout for richer event cards

Current next slice is now closed (`2026-03-31`):

- [DONE] long-session UX tuning (density/spacing at 1080p and below)
- [DONE] prompt-card simplification for large choice sets (compact-mode default with detail toggle)
- [DONE] replay/live wording parity hardening for additional event families (`trick_window_open/closed`, `mark_resolved`, `marker_flip`, `f_value_change`)

## Rule Clarification To Preserve During UX Work

`탈출 노비` one-short routing is a choice, not a forced automatic correction.

Clarified rule:

- when `탈출 노비` is exactly one step short of a valid `시작`, `종료`, or `운수` tile,
- the player `may` move into that tile
- this is optional, not mandatory

UI implication:

- if this rule is surfaced in a player-facing movement prompt,
- the prompt must present it as an explicit selectable branch, not a silent automatic redirect

## Non-Goals

This proposal does not ask for:

- a new frontend framework
- a React rewrite
- a Unity port now
- analysis-only overlays as the first priority

The goal is to make the current HTML runtime feel like a real game first.

## Ownership

### GPT

- live viewer UX architecture
- prompt presentation
- replay/live wording parity
- board-game-style public narrative

### CLAUDE

- keep lower-layer payloads sufficient for richer UI
- validate canonical contract stability
- fix lower-layer bugs discovered by UI growth

## Exit Criteria

This track is complete only when:

- a human can follow other-player turns without hunting across panels
- prompt placement feels contextual
- money/resource changes are attributable from the UI alone
- replay and live present the same public sequence language
- the viewer feels like a playable board game screen rather than a debug console
