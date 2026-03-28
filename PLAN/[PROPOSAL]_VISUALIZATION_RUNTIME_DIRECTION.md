# [PROPOSAL] Visualization Runtime Direction

## Purpose
This document records the recommended direction for turning the current simulator into:
- a replayable visual match viewer
- a live playable game runtime

It is a proposal document, not the canonical implementation plan.

The canonical active plan remains:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

## Recommendation Summary
The best direction is a hybrid structure:

- use the GPT-side visualization/runtime plan as the top-level product architecture
- use the Claude-side event/state substrate ideas as the lower-layer data contract

In short:
- GPT owns the upper runtime architecture
- Claude-style substrate owns the lower public-state/event contract

This is the most stable, least coupled, and most portable approach.

## Recommended Ownership Split

### GPT-Owned Upper Layers
These layers should define how the visual system behaves as an application:
- `RuntimeSession`
- `GameSessionController`
- `ReplayController`
- `PublicGameProjection`
- `AnalysisProjection`
- `Renderer`
- `HumanDecisionAdapter`
- `AIDecisionAdapter`

These are the right layers for:
- DI-friendly composition
- replay/live convergence
- future web UI or desktop UI
- future Unity porting

### Claude-Informed Lower Layers
These layers should define the authoritative public data substrate:
- structured event stream
- replay-grade movement traces
- public player snapshot schema
- public board snapshot schema
- authoritative state transition logging

These are the right layers for:
- low ambiguity replay
- deterministic rerun validation
- animation-grade movement reconstruction
- future renderer independence

## Why This Direction Is Better

### 1. It matches the project's DI and separation rules
The engine should not know about:
- renderer
- UI widgets
- player input screens
- replay controls

The renderer should not infer game rules from markdown or ad hoc parsing.

So the architecture should be:
- engine
- structured public event/state substrate
- projection
- renderer
- input adapters

This keeps engine logic, policy logic, and visual runtime separate.

### 2. It keeps replay and live play on one architecture
Replay should not be a throwaway parser.

If replay and live use different models, maintenance cost will explode.

So both should share:
- the same projection schema
- the same public player model
- the same public board model
- the same effect/timeline model

Only the source changes:
- replay consumes stored event streams
- live mode consumes runtime events

### 3. It avoids `/result` becoming a fake source of truth
`/result/*.md` is useful for:
- reports
- summaries
- forensic notes

It is not good enough for:
- replay authority
- animation
- legal action prompts
- exact public-state reconstruction

The real truth source should be:
1. live engine state
2. structured event stream
3. deterministic rerun

`/result` should remain a review artifact only.

### 4. It is the most maintainable path to a real game
The next steps become natural:
- Phase 1: replay viewer
- Phase 2: live spectator
- Phase 3: human decision prompts
- Phase 4: real human-vs-AI match

This is much safer than building a UI-first mock game that later has to be rebuilt around engine truth.

## Required Public Information
The visual runtime must expose every publicly visible gameplay-critical field.

At minimum:
- money
- shards
- score coins in hand
- score coins placed
- tile ownership
- tile color / block / kind
- score coin placement on tiles
- player current position
- weather
- fortune/trick/effect state that is public
- mark source / marked target / pending mark status
- public trick cards
- hidden trick count
- dice values and final movement result
- movement path for animation
- rent payment events
- anytime trick prompt windows and outcomes
- current scoreboard panel
- F value
- lap reward choice and outcome
- marker owner / marker transfers
- bankruptcies and elimination reason if public

If a real online player can know it, the projection should carry it.

## Recommended Authoritative Data Policy

### Authoritative
Use these as truth:
1. engine state at runtime
2. replay-grade structured event stream
3. deterministic rerun with full logging

### Non-Authoritative
Do not use these as truth:
- `/result/*.md`
- summary-only game reports
- derived markdown timelines

## Stability Assessment

### Most Stable Technical Path
The most stable implementation path is:
- keep engine logic unchanged as much as possible
- enrich logging and public snapshot contracts
- build replay/live runtime on top of those contracts

This is safer than:
- putting UI logic into engine code
- making the renderer reconstruct hidden state heuristically
- using summary outputs as replay inputs

## Coupling Assessment
The lowest-coupling structure is:
- engine mutation authority
- public projection layer
- renderer layer
- decision adapter layer

This means:
- AI and human players can share the same decision request contract
- replay and live can share the same projection
- UI framework can change without changing engine rules

## Visualization Quality Recommendation
For the user-facing experience, the recommended screen model is:

- top: round / turn / phase / F / marker owner
- left and right: player panels
- center: board map
- bottom: event feed and prompt area

Player panel should show:
- name / seat / character
- alive state
- money
- shards
- hand score coins
- placed score coins
- owned tiles
- public tricks
- hidden trick count
- mark status
- burden/effect summary

Center board should show:
- tile kind
- tile color/block
- owner
- score coin placement
- purchase/rent values
- pawn positions
- movement trace
- transient highlights for:
  - rent
  - fortune
  - lap crossing
  - purchase
  - mark resolution

## Unity 3D Portability
If the project later becomes a Unity 3D game, this structure ports cleanly.

Mapping is straightforward:
- engine/domain stays domain
- public projection becomes view-model layer
- renderer becomes Unity scene/UI layer
- decision adapters become input/controller layer

That is much better than a log-viewer-style design.

So for future Unity work, the right target structure is:
- domain truth
- event/state substrate
- projection
- renderer
- input adapters

## Concrete Recommendation

### Adopt
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md` as the canonical top-level implementation plan

### Treat As Companion Reference
- `CLAUDE-MAIN:PLAN/VISUALIZATION_GAME_PLAN.md`
- `PLAN/[REFERENCE]_CLAUDE_VISUALIZATION_GAME_SUBSTRATE_PLAN.md`

### Do Not Do
- do not build replay directly from `/result/*.md`
- do not build a replay-only parser that cannot grow into live play
- do not bind UI directly to engine internals

## Final Opinion
The right path is not:
- "GPT plan or Claude plan"

The right path is:
- GPT upper architecture
- Claude-style lower substrate
- one shared public projection contract

That combination best satisfies:
- DI
- maintainability
- low coupling
- full public-information display
- stable real gameplay support
- future Unity portability
