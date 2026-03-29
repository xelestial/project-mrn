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

The first implementation slice should do all of the following together:

- add a board-game-style public action rail
- strengthen the turn banner / spectator continuity layer
- keep the current bottom overlay as transient emphasis, but add a persistent action lane
- prepare the layout for later animation and richer event cards

This is the minimum slice that meaningfully shifts the viewer from "tool UI" toward "match UI".

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
