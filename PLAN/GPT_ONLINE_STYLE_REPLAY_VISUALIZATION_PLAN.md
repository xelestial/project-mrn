# GPT Online-Style Replay Visualization Plan

## Goal
Turn raw game logs into an online-game-style replay view that is readable by a human without inspecting raw JSON or markdown dumps.

The target is not just a text parser.
It should reconstruct the game as a sequence of visible states and events, closer to how a player would watch an online match.

## Why
Recent sample review showed that:
- the AI is making stranger choices than expected
- raw action rows are not enough to understand why
- even parsed reports still hide too much board context

To judge whether a play was bad, we need:
- who had priority
- where each player was
- what the board looked like
- what hidden/public trick state existed
- what happened off-turn
- what fortune/weather effects changed the board state

This means the next analysis layer must behave like a replay UI model.

## Product Definition
Input:
- raw game log or `games.jsonl` entry

Output:
- online-style replay data
- optionally rendered markdown, HTML, or future UI view

The replay should show the game in ordered steps with synchronized panels.

## Presentation Strategy
The replay should not look like a forensic log dump.
It should look like a game screen composed of synchronized panels.

Target layout:
- top progress strip
- left/right player panels
- center board panel
- bottom event feed

The reader should first understand:
- who is where
- who owns what
- what just happened

and only then drill into raw event details if needed.

## Delivery Modes
The replay system should support two separate delivery modes.

### Mode A. Offline Replay
Use case:
- post-game review
- suspicious-sample forensics
- sharing one finished game state with a human reader

Requirements:
- can be rendered without Javascript
- can be emitted as markdown or static HTML
- supports step-by-step replay from a finished log

This is the required first milestone.

### Mode B. Live Spectator
Use case:
- observing a running simulation
- watching turns unfold without manual refresh
- comparing AI behavior while the game is still running

Requirements:
- must update without page refresh
- should use a small client-side renderer
- should consume incremental replay state updates instead of rebuilding the whole page

Important rule:
- true live spectator mode will require Javascript or an equivalent client update mechanism
- do not pretend that static HTML alone is enough for live observation

## Core Replay Flow
For each round and turn, reconstruct this flow:

1. Turn start
2. Weather reveal
3. Draft
4. Priority / round order
5. Each player's turn execution
6. Fortune reveal if triggered
7. Marker flip if triggered
8. Off-turn reactions and deferred effects

The replay must preserve both:
- active-turn actions
- off-turn consequences

## Required Visualization Model

### A. Timeline Layer
The timeline is the spine of the replay.

It must represent:
- round boundaries
- turn boundaries
- substeps inside a turn
- off-turn interrupts
- delayed resolution events

Minimum event groups:
- `turn_start`
- `weather_reveal`
- `draft_phase_1`
- `draft_phase_2`
- `round_order_confirmed`
- `character_selected`
- `trick_used`
- `movement_declared`
- `movement_resolved`
- `landing_resolved`
- `fortune_revealed`
- `fortune_resolved`
- `marker_flip`
- `mark_attempt`
- `mark_resolved`
- `purchase_attempt`
- `purchase_resolved`
- `lap_reward`
- `offturn_effect`
- `bankruptcy`
- `turn_end`

### B. Player Panels
Each replay step must be able to render one panel per player.

Required fields:
- player id
- current character
- current cash
- owned tile list
- public tricks
- hidden trick count
- shards
- hand score coins
- placed score coins if useful
- current position
- drafted card pair if relevant
- mark source / mark target state
- pending mark state
- burden state
- alive / bankrupt state

Recommended fields:
- remaining dice cards
- current plan key if future intent-memory trace exists
- current survival stage / cleanup stage

### C. Central Board Panel
The board panel should behave like a compact online board view.

Required tile data per tile:
- tile number
- tile kind
- tile color / block color
- owner
- placed score coin count
- tile purchase cost
- tile rent cost
- special markers such as `S`, `F1`, `F2`, `MALICIOUS`
- player pawns currently on the tile

Required turn context:
- movement source position
- movement destination
- dice cards spent
- rolled dice if applicable
- whether start was crossed
- whether forced movement happened

## Board Rendering Plan
The board should be built in stages.
Do not start by chasing a decorative board.
Start with a precise board model and progressively improve the renderer.

### Stage 1. Index-Based Board Strip
The first renderer should display tiles in board order.

Each tile cell should show:
- tile index
- tile kind
- block color or block id
- owner
- placed score coins
- purchase cost
- rent cost
- pawn occupants

Why:
- fastest path to correctness
- directly traceable to raw log movement like `19 -> 24`
- easiest way to debug replay reconstruction

### Stage 2. Square Loop Board Layout
Once the board model is stable, map tile indices to loop coordinates.

Target approach:
- top edge
- right edge
- bottom edge
- left edge

This should preserve:
- start-crossing intuition
- near-end positioning
- relative spacing between players
- special tile placement awareness

Important rule:
- keep data index-based
- only the renderer converts index to screen position

### Stage 3. HTML Board Renderer
After the replay state is reliable, render the board as a proper local replay board.

Suggested implementation:
- CSS grid or absolute-positioned loop layout
- owner color accents
- coin badges
- pawn overlays
- current movement path highlight

### Board Architecture Rule
Separate these layers:
- `BoardModel`
- `BoardLayout`
- `BoardRenderer`

Meaning:
- `BoardModel` stores tile truth
- `BoardLayout` maps tile index to visual coordinates
- `BoardRenderer` draws the current board

This is required if we want:
- markdown replay first
- HTML replay later
- future interactive playback without rewriting state logic

## Live Update Strategy
For live spectator mode, do not rebuild full reports on every change.

Use this flow:
1. raw log receives a new row
2. parser emits one or more `ReplayEvent`
3. `ReplayState.apply(event)` advances the state
4. a fresh `ReplaySnapshot` is emitted
5. the client rerenders only the affected panels

Recommended transport stages:
- Stage 1: periodic JSON polling from a local file or local endpoint
- Stage 2: local file-watch bridge or lightweight local server
- Stage 3: websocket push for smoother live playback

Important rule:
- renderer must consume replay snapshots
- renderer must not parse raw logs directly
- live update must be append-only where possible

## Architecture

### Phase 1. Replay State Model
Build a deterministic replay state structure that advances step by step.

Target artifacts:
- `ReplayState`
- `ReplayPlayerPanel`
- `ReplayTileView`
- `ReplayStep`
- `ReplayEvent`

Rule:
- replay state is derived from log plus deterministic reconstruction
- engine does not become the renderer

### Phase 2. Raw Log to Replay Events
Extend the existing parser layer so raw action rows become ordered replay events.

Target artifacts:
- `replay_event_parser.py`
- normalized event taxonomy

Required work:
- map raw engine events into user-facing event types
- preserve off-turn events
- preserve semantic relationships between cause and effect

### Phase 3. Snapshot Reconstruction
At each replay step, build synchronized player panels and board state.

Required work:
- reconstruct player resources
- reconstruct tile ownership and coin placement
- reconstruct public and hidden trick visibility
- reconstruct pawn positions
- reconstruct mark state and off-turn pending effects

Success criterion:
- any suspicious action can be judged from the replay step without manually reading raw rows

### Phase 4. Online-Style Renderer
Produce a readable view layer on top of replay state.

Initial renderer targets:
- markdown replay report
- structured JSON for future UI

Future renderer targets:
- HTML page
- local app panel
- timeline scrubber

Initial board renderer sequence:
1. markdown board strip
2. monospace square loop board
3. HTML square loop board

Renderer split:
- offline renderer: no-JS friendly
- live renderer: small JS client over replay JSON

Important rule:
- renderer consumes replay state
- renderer does not parse raw logs directly

### Phase 5. Decision Overlay
Add decision overlays so replay can explain why the AI likely chose something.

Optional overlay fields:
- chosen decision
- candidate alternatives
- policy debug reasons
- current plan key
- advantage rank before / after turn

This phase should build on:
- `GPT/action_log_parser.py`
- `GPT/turn_advantage.py`
- future intent-memory trace

## Data Contracts

### ReplayEvent
One visible event in the timeline.

Minimum fields:
- `event_type`
- `round_index`
- `turn_index`
- `acting_player`
- `subject_players`
- `summary`
- `raw_refs`
- `is_offturn`

### ReplayStep
One displayable moment.

Minimum fields:
- `step_id`
- `round_index`
- `turn_index`
- `phase`
- `headline`
- `events`
- `player_panels`
- `board_panel`

### ReplayPlayerPanel
Minimum fields:
- `player_id`
- `character`
- `cash`
- `shards`
- `hand_coins`
- `placed_score_coins`
- `position`
- `owned_tiles`
- `public_tricks`
- `hidden_trick_count`
- `pending_marks`
- `burden_cards`
- `alive`

### ReplayBoardPanel
Minimum fields:
- `tiles`
- `pawn_positions`
- `movement_trace`
- `round_order`
- `weather`
- `visible_fortune`

## Required Log Enrichment
The replay can start with current logs, but these additions would sharply improve quality:
- explicit turn-start snapshot row
- explicit turn-end snapshot row
- actual movement path segments
- actual dice roll values
- explicit fortune reveal row with card text
- explicit marker-flip reveal row
- explicit mark guess vs mark resolution row
- explicit public-trick visibility updates

These are recommended, not blockers, for the first visualization phase.

## Questions The Plan Must Answer
Before implementation expands too far, the replay system should explicitly answer:
- is this a developer/debug replay or a player-facing spectator replay?
- should hidden information stay hidden, or can analysis mode reveal it?
- what is the unit of playback: event, substep, turn, or round?
- what is the update transport for live mode: file polling, local HTTP, or websocket?
- what is the persistence format for snapshots: JSON-only or JSON plus rendered cache?
- how does a reader jump directly to a suspicious move without replaying the whole game?
- how are replay files versioned so old results still render after schema changes?
- which state is authoritative when raw logs and rerun reconstruction disagree?
- how should one replay compare two policies or two runs side by side?

Current recommended answers:
- first target is developer/debug replay
- default spectator mode should show only public information
- analysis mode may optionally reveal hidden information with a clear badge
- playback unit should be `ReplayStep`
- first live transport should be polling, not websocket

## Additional Requirements To Track
These are easy to miss and should be tracked now.

### 1. Public vs Analysis Visibility
Need two visibility modes:
- `public_view`
- `analysis_view`

Reason:
- some screens should behave like a real spectator
- others should help debug policy mistakes with hidden knowledge available

### 2. Step Identity And Stable References
Each replay step needs a stable id so:
- a client can seek to a step
- annotations can point to a step
- a suspicious decision can be linked directly

### 3. Incremental Snapshot Cost
Full-board rerender for every micro-event may become noisy or expensive.

Need:
- coarse snapshot boundaries
- lightweight event feed between snapshots

Recommended rule:
- keep one snapshot per visible step, not per raw event row

### 4. Movement Trace Fidelity
Many suspicious plays depend on path, not just destination.

Need:
- start position
- intermediate forced movement if any
- end position
- crossed-start flag
- card spend vs base move vs trick move

### 5. Off-Turn Event Grouping
Deaths and payments often happen off-turn.

Need:
- a way to visually group off-turn events under the active turn that caused them

### 6. Annotation Hooks
Future overlays should be attachable without changing the renderer core.

Need:
- optional badges such as `plan mismatch`, `wasteful move`, `cleanup risk`, `guess miss`

### 7. Replay Controls And Navigation
The replay must be navigable like a viewer, not just readable like a report.

Need:
- next / previous step
- next / previous turn
- next / previous round
- jump to player turn
- jump to bankruptcy / fortune / lap / mark events
- stable deep-link target for a specific suspicious step

Recommended rule:
- all renderers should share the same stable `step_id` and `turn_key`
- offline markdown should still emit these ids even if it cannot provide buttons

### 8. Suspicious-Step Bookmarks
The replay should support first-class bookmarks for obviously strange or high-impact steps.

Examples:
- wasteful premium movement
- impossible-feeling mark guess
- off-turn death
- lap-engine mismatch
- cleanup warning ignored

Need:
- `bookmark_type`
- optional severity
- optional linked analysis note

Reason:
- users will often review only the bad parts of a game, not every step

### 9. Authoritative State And Reconstruction Policy
Some fields may come from raw logs, some from deterministic rerun reconstruction.

Need:
- a clear priority order for truth sources
- a flag when a field is reconstructed instead of directly logged
- a mismatch report when replay inference and rerun snapshot disagree

Recommended order:
1. explicit raw log field
2. deterministic state reconstruction
3. best-effort inference with warning badge

### 10. Schema Versioning
Replay artifacts will evolve.

Need:
- replay schema version
- renderer compatibility target
- migration note when a stored replay was built under an older contract

Reason:
- result files and replay JSON will otherwise become brittle across refactors

### 11. Comparison Mode
This system will likely be used to compare GPT vs Claude behavior.

Need:
- one replay can expose policy id and profile id per player
- future support for side-by-side comparison between two runs or two players
- normalized event labels so different policy implementations remain comparable

This does not need to ship in the first renderer, but the schema should not block it.

## Initial GPT Implementation Scope
Start with:
- replay event parser
- replay state reconstruction from one game log
- markdown renderer for suspicious sample games

Do not start yet with:
- full GUI
- animation
- browser app
- bidirectional playback controls
- side-by-side replay comparison
- multi-game stitched timeline

## Success Criteria
Phase 1 is successful if:
- one `games.jsonl` entry can be turned into ordered replay steps

Phase 2 is successful if:
- player panels and board panel stay synchronized through the whole game

Phase 3 is successful if:
- suspicious actions like bad trick timing, wasteful movement, or impossible-feeling mark guesses can be understood from one replay step

Phase 4 is successful if:
- a user can read a replay like an online match log instead of a forensic dump
- the board panel makes movement, ownership, and danger zones visually obvious

Mode B live spectator is successful if:
- new turns appear without manual refresh
- player panels and board panel stay synchronized during incremental updates
- off-turn events are visible in the step stream instead of appearing out of nowhere

## Immediate Next Actions
1. Define `ReplayEvent`, `ReplayStep`, `ReplayPlayerPanel`, and `ReplayBoardPanel`.
2. Build a parser that maps raw action rows into replay events.
3. Define `BoardModel`, `BoardLayout`, and `BoardRenderer` boundaries.
4. Reuse the replay seed/rerun path from `GPT/replay_first_bankrupt_samples.py` where direct reconstruction is easier than raw inference.
5. Generate one markdown replay for a suspicious sample turn with player panels and board panel.
6. Add required-log-gap notes where the current logs are still too weak for a true online-style reconstruction.
7. Split the renderer contract into `offline no-JS replay` and `live JS spectator`.
8. Add stable step ids, bookmark hooks, and replay schema version to the first data contract.
9. Decide and document the authoritative source order between raw log values and rerun reconstruction.

## Working Rule
If a replay artifact still requires the reader to infer:
- where the players were
- what the board looked like
- what public information existed
- what off-turn event actually killed someone

then it is still a forensic dump, not an online-style replay.
