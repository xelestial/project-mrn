# GPT Visual Replay And Playable Simulator Plan

## Goal
Turn the current CLI simulator into a visual game runtime that supports:

1. replaying completed games like a real online match screen
2. running live matches where human players and AI players can play together

This is not just a prettier log viewer.
The target is a maintainable visual runtime built on top of the existing engine and project rules.

## Final Product Target
The end state should support two modes on top of the same state/projection model.

### Mode A. Replay Viewer
- replay a finished game from stored artifacts
- show the game step by step like a real match
- support public-view replay and analysis-view replay

### Mode B. Live Playable Match
- start a live game session
- attach `human`, `gpt`, `claude`, or future agents as players
- render current game state continuously
- allow the human to make legal choices in real time

Important rule:
- replay mode and live mode must share the same projection and rendering contracts
- do not build a throwaway replay parser that cannot grow into live play

## Why A New Plan Is Needed
The earlier replay plan was good for "online-style replay".
The new requirement is bigger:

- the simulator should eventually become a playable visual game
- replay and live play should not diverge into separate architectures
- the renderer must expose all public information a real player needs
- the architecture must still obey the project's refactor direction:
  - DI-friendly boundaries
  - engine core separated from presentation
  - reusable policy/runtime adapters

So this plan treats replay as Phase 1 of the playable visual runtime, not as an isolated tool.

## Current State Assessment

### What We Already Have
- a working CLI simulator
- deterministic rerun path from seed
- `games.jsonl` and `summary.json` outputs
- some replay-oriented tooling such as:
  - `GPT/replay_first_bankrupt_samples.py`
- strong policy/runtime separation work already done:
  - helper/wrapper refactor
  - evaluator refactor
  - runtime bridge refactor

### What `/result` Can Do Today
`/result` currently contains:
- human-readable reports
- parsed sample logs
- replay-like forensic markdown

This is useful for review, but it is **not** an authoritative replay source for a real game viewer.

Reason:
- it is already post-processed
- fields are summarized rather than normalized
- step identity is not guaranteed
- hidden/public visibility boundaries are blurred
- animation-grade movement traces are not preserved

Conclusion:
- `/result/*.md` is useful as a review artifact
- `/result` is **not** sufficient as the primary data source for real replay or live play

### What `games.jsonl` Can Do Today
`games.jsonl` can be sufficient for Phase 1 replay **only if** the run is produced with enough raw event detail.

Current caveat:
- many runs are stored with `log_level none` or summary-only output
- those runs are not enough for full visual replay

Conclusion:
- Phase 1 replay should not depend on existing sparse runs
- replay-grade runs must use a richer raw event contract
- when possible, the most reliable source should be deterministic rerun plus explicit projection snapshots

## Authoritative Data Policy
For replay and live play, truth sources must be explicit.

Recommended priority:
1. explicit engine snapshot / projection event
2. deterministic reconstruction from seed and full event stream
3. raw summary fields from `games.jsonl`
4. human-readable `/result` reports

Working rule:
- markdown in `/result` is never the authoritative replay state
- replay correctness should come from engine-driven or rerun-driven structured data

## Feasibility Check Against Requested Public Information
The viewer must expose all publicly visible information and gameplay-critical state.

Below is the target matrix.

### 1. Money, shards, score, coins
Needed:
- cash
- shards
- hand score coins
- placed score coins
- current score / score breakdown if public

Current status:
- mostly available in summaries and rerun snapshots

Gap:
- not emitted as stable per-step public panel data today

Action:
- add per-step `PlayerPublicState`

### 2. Tile layout
Needed:
- tile color / block color
- owner
- placed score coin on tile
- purchase cost
- rent cost
- tile kind

Current status:
- reconstructable from engine state

Gap:
- current logs do not expose a stable renderer-facing board schema

Action:
- add `BoardPublicState.tiles[]`

### 3. Current player location
Needed:
- exact tile index
- active pawn position for each player

Current status:
- reconstructable from state and rerun

Gap:
- not consistently available as replay-step payload

Action:
- include pawn positions in every snapshot

### 4. Fortune / trick / weather effect state
Needed:
- current weather
- visible pending fortune impact if public
- public trick effects that remain active
- delayed or aura-like public modifiers

Current status:
- partially inferable

Gap:
- no stable "effect ledger" exists for the UI

Action:
- add `PublicEffectState`

### 5. Mark / marked state
Needed:
- who is marking
- who is marked
- whether mark is pending or resolved

Current status:
- partially logged, partially inferable

Gap:
- not normalized into one replay-friendly state object

Action:
- add `MarkPublicState`

### 6. Trick inventory
Needed:
- public tricks
- hidden trick count
- used trick history if relevant

Current status:
- available in player summaries and rerun

Gap:
- not guaranteed at every replay step

Action:
- track public trick visibility updates step-by-step

### 7. Dice / movement result
Needed:
- dice cards spent
- rolled values if any
- movement source
- movement destination
- special movement effect

Current status:
- destination often recoverable
- exact path and sub-events are incomplete

Gap:
- insufficient for online-style replay and animation

Action:
- add `MovementTrace`

### 8. Movement animation
Needed:
- path segments
- movement cause
- start-cross flag
- duration/sequence hints

Current status:
- not reliably present

Gap:
- current logs are not animation-grade

Action:
- emit movement segments, not just final location

### 9. Rent payment
Needed:
- payer
- receiver
- amount
- reason
- source tile

Current status:
- mostly available in events

Gap:
- not normalized for renderer timing

Action:
- add `PaymentEvent` and ledger panel integration

### 10. Anytime trick interaction
Needed:
- whether an instant-usable trick is available
- whether the player declined or used it
- legal timing window

Current status:
- this is a major gap

Important caveat:
- some current engine behavior treats "anytime" tricks in a simplified turn phase
- for true playable visual mode, the UI must know when the player is being asked

Action:
- add explicit prompt windows to the runtime session layer

### 11. Current scoreboard / status board
Needed:
- all player public panels
- round
- turn
- current actor
- alive/bankrupt
- end-condition pressure

Current status:
- reconstructable

Gap:
- no single normalized status board view model

Action:
- add `MatchStatusBoard`

### 12. F value
Needed:
- current F
- threshold if public

Current status:
- available in result summaries and state

Gap:
- not emitted as per-step board header state

Action:
- include F in every `ReplaySnapshot`

### 13. Lap reward choice
Needed:
- choice offered
- chosen reward
- immediate resource result

Current status:
- often inferable, not always step-normalized

Gap:
- not yet a formal replay-step event contract

Action:
- add `LapRewardEvent`

### Additional Public Information Required
The visual runtime should also surface:
- round order / current priority
- current character
- owned tiles list
- alive/bankrupt state
- recent event feed
- whether a player is waiting for input
- current phase
- end reason when game closes

## Core Design Decision
Do **not** build the visual layer from markdown reports.
Build it from a projection model.

Everything should flow through:
- engine/runtime
- normalized public event stream
- projection state
- renderer

## Proposed Architecture

### 1. Domain Core
Keep:
- `GameEngine`
- rules
- board config
- policy runtime

Rule:
- domain core should not know about HTML, animation, or UI widgets

### 2. Runtime Session Layer
Add a session/runtime controller above the engine.

Responsibilities:
- run the match
- drive turn progression
- expose wait states for human decisions
- emit normalized runtime events

Suggested types:
- `GameSessionController`
- `RuntimeCommand`
- `RuntimePrompt`
- `RuntimeEventStream`

### 3. Projection Layer
Build a public-view projection from runtime events.

Responsibilities:
- maintain replay/live public game state
- compute per-step player panels
- compute board panel
- maintain effect ledger
- build movement traces

Suggested types:
- `PublicGameProjection`
- `ReplayProjection`
- `PlayerPublicState`
- `BoardPublicState`
- `PublicEffectState`
- `MatchStatusBoard`

### 4. Renderer Layer
Render projection state, not raw engine state.

Renderer targets:
- offline markdown replay
- offline HTML replay
- live HTML viewer

### 5. Input Adapter Layer
For live play, player decisions should be adapters, not engine special cases.

Suggested adapters:
- `AiDecisionAdapter`
- `HumanDecisionAdapter`
- `ReplayDecisionAdapter` for deterministic playback

This is important for DI:
- engine depends on abstract policy/decision contracts
- session controller depends on adapter interfaces
- renderer depends on projection snapshots only

## DI / Maintainability Rules
This plan must follow the project's architecture direction.

### Rule 1. Engine Is Not The UI
- no HTML concerns inside `engine.py`
- no renderer logic inside `ai_policy.py`

### Rule 2. Projection Is A Read Model
- projection may lag one event behind
- projection is disposable and replayable
- engine remains authoritative for mutation

### Rule 3. Input Uses Interfaces
- human and AI both satisfy the same decision interface
- live session should not special-case "human" deep in the engine

### Rule 4. Visibility Is Explicit
- public replay and analysis replay must be separate modes
- hidden info should only appear in analysis mode with a clear flag

### Rule 5. Replay And Live Share Contracts
- do not build a replay-only schema and later invent a different live schema
- both should share:
  - event taxonomy
  - projection types
  - board model
  - player panel model

## Phase Plan

## Phase 1. Replay-Grade Structured Output
Goal:
- produce replay-quality structured logs and snapshots

Required work:
- define `ReplayEvent`
- define `ReplaySnapshot`
- define `PlayerPublicState`
- define `BoardPublicState`
- define `MovementTrace`
- define `PublicEffectState`

Success:
- one game can be replayed as a public match screen without rereading raw JSON manually

## Phase 2. Offline Replay Viewer
Goal:
- replay completed games like a visual online match

Deliverables:
- JSON replay artifact
- markdown replay artifact
- local HTML replay page

Important:
- HTML replay can use JS for controls
- offline replay does not require live networking

## Phase 3. Live Spectator Mode
Goal:
- observe a running simulation without refresh

Recommended transport:
1. polling
2. local HTTP
3. websocket if needed later

Important:
- use append-only event updates where possible

## Phase 4. Human Play Runtime
Goal:
- attach a human player to one or more seats

Required work:
- explicit prompt objects for:
  - movement choice
  - draft choice
  - final character
  - lap reward
  - mark target
  - active flip
  - hidden trick
  - burden exchange
  - geo bonus
  - anytime trick window when applicable

Success:
- a human can play one seat while AI controls the others

## Phase 5. Full Match UI
Goal:
- make it feel like a real playable game screen

Features:
- board animation
- current actor highlight
- event feed
- input prompts
- hover detail for tiles and effects
- pause / step / replay controls

## Current Data Sufficiency Verdict

### For Phase 1 Replay
Current data is **partially sufficient**.

Good enough if:
- we rerun from seed
- we instrument snapshots/events more explicitly
- we do not rely on sparse `log_level none` runs

Not good enough if:
- we try to reconstruct full replay only from `/result/*.md`
- we expect animation-grade movement from current sparse logs

### For Phase 2 Live Human Play
Current data is **not yet sufficient**.

Main blockers:
- no formal prompt/wait-state contract
- no replay/live shared projection schema
- no explicit anytime-trick decision window model for UI-facing play
- no live renderer transport yet

Conclusion:
- replay-first is still the right order
- but replay must be built with live-play contracts in mind

## Recommended Starting Point
Start here, in this exact order.

1. Define the shared event/projection schema
2. Instrument replay-grade structured output from deterministic rerun
3. Build one offline HTML replay for a single suspicious game
4. Confirm the UI can show all public information listed above
5. Add prompt objects and human decision adapter
6. Upgrade the same renderer into live spectator mode
7. Enable actual human-vs-AI play

## Minimum Schema To Implement First

### ReplayEvent
- `event_id`
- `step_id`
- `round_index`
- `turn_index`
- `phase`
- `event_type`
- `acting_player_id`
- `subject_player_ids`
- `summary`
- `is_offturn`
- `public_payload`

### ReplaySnapshot
- `step_id`
- `round_index`
- `turn_index`
- `phase`
- `current_actor`
- `players`
- `board`
- `status_board`
- `effects`
- `event_feed_tail`

### RuntimePrompt
- `prompt_id`
- `player_id`
- `decision_type`
- `choices`
- `deadline_mode`
- `public_context`

## Success Criteria
This plan is successful when:

1. a completed game can be replayed as a visual match screen
2. all public information is visible at each step
3. movement and payments are understandable without reading forensic logs
4. live spectator mode updates without full page refresh
5. at least one human player can play against AI through the same runtime contracts
6. the implementation respects DI and does not collapse UI concerns into the engine core

## Final Recommendation
Do not treat replay and play as separate products.
Treat replay as the first public runtime of the future playable visual simulator.

That is the safest path for:
- maintainability
- DI compliance
- visibility correctness
- future human-vs-AI play
