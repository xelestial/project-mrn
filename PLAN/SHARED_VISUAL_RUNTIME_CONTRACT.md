# Shared Visual Runtime Contract

Status: `ACTIVE`
Role: `shared boundary specification for replay viewer and live playable runtime`

## Purpose
This document defines the shared contract that must be agreed before parallel implementation of:
- replay viewer
- live spectator
- human vs AI playable runtime

This contract is intentionally above implementation detail and below product planning.

It exists so:
- Claude can implement the lower event/state substrate
- GPT can implement session/projection/renderer/input runtime
- both sides stay compatible

## Why This Must Come First
If replay and live runtime are implemented without a fixed shared boundary, the project will drift in at least four places:
- event naming
- public state shape
- hidden/public visibility rules
- decision request/response payloads

So this document is the first implementation blocker for visualization work.

## Ownership Split

### Claude-owned implementation side
Claude should implement the lower substrate that produces authoritative public runtime data:
- structured replay/live event stream
- `PlayerPublicState`
- `BoardPublicState`
- `TilePublicState`
- `MovementTrace`
- `TurnEndSnapshot`

### GPT-owned implementation side
GPT should implement the upper visual runtime that consumes the shared contract:
- `RuntimeSession`
- `ReplayController`
- `GameSessionController`
- `PublicGameProjection`
- `AnalysisProjection`
- `Renderer`
- `HumanDecisionAdapter`
- `AIDecisionAdapter`

## Truth Source Policy

### Authoritative
Use these as truth:
1. live engine state
2. structured event stream
3. deterministic rerun with full logging

### Non-authoritative
Do not use these as truth:
- `/result/*.md`
- forensic markdown summaries
- summary-only aggregate reports

## Shared Contract Layers

### Layer 1. Replay / Runtime Events
These are append-only events that describe what happened.

Required event families:
- `session_start`
- `round_start`
- `weather_reveal`
- `draft_pick`
- `final_character_choice`
- `turn_start`
- `trick_window_open`
- `trick_window_closed`
- `dice_roll`
- `player_move`
- `landing_resolved`
- `rent_paid`
- `tile_purchased`
- `fortune_drawn`
- `fortune_resolved`
- `mark_resolved`
- `marker_transferred`
- `lap_reward_chosen`
- `f_value_change`
- `bankruptcy`
- `turn_end_snapshot`
- `game_end`

### Layer 2. Public Snapshot State
These are public-state payloads suitable for replay and rendering.

Required snapshot families:
- `PlayerPublicState`
- `BoardPublicState`
- `TilePublicState`
- `PublicEffectState`
- `TurnEndSnapshot`

### Layer 3. Decision Prompt Contract
These are request/response payloads for live playable runtime.

Required prompt families:
- `MovementDecisionRequest`
- `DraftChoiceRequest`
- `CharacterChoiceRequest`
- `MarkTargetRequest`
- `TrickWindowRequest`
- `PurchaseDecisionRequest`
- `LapRewardRequest`
- `CoinPlacementRequest`
- `DoctrineReliefRequest`
- `GeoBonusRequest`
- `SpecificTrickRewardRequest`

## Minimum Event Schema

Every event must include:
- `event_type`
- `session_id`
- `round_index`
- `turn_index`
- `step_index`
- `acting_player_id` or `null`
- `public_phase`
- `timestamp` or deterministic sequence id

### Event ordering rule
Events must be stable and replayable without relying on markdown parsing.

So every event stream must be:
- ordered
- append-only
- deterministic in sequence

## Public State Schemas

### PlayerPublicState
Must include:
- `player_id`
- `seat`
- `display_name`
- `alive`
- `character`
- `position`
- `cash`
- `shards`
- `hand_score_coins`
- `placed_score_coins`
- `owned_tile_count`
- `owned_tile_indices`
- `public_tricks`
- `hidden_trick_count`
- `mark_status`
- `pending_mark_source`
- `public_effects`
- `burden_summary`

### TilePublicState
Must include:
- `tile_index`
- `tile_kind`
- `block_id`
- `zone_color`
- `purchase_cost`
- `rent_cost`
- `owner_player_id`
- `score_coin_count`
- `pawn_player_ids`

### BoardPublicState
Must include:
- `tiles`
- `f_value`
- `marker_owner_player_id`
- `round_index`
- `turn_index`

## Movement Contract

### DiceRollEvent
Must include:
- `player_id`
- `dice_values`
- `cards_used`
- `total_move`
- `move_modifier_reason`

### MovementTrace
Must include:
- `player_id`
- `from_tile_index`
- `to_tile_index`
- `path`
- `crossed_start`
- `movement_source`

This is required for:
- board animation
- lap crossing visuals
- path highlights
- exact replay reconstruction

## Economy Contract

### RentPaidEvent
Must include:
- `payer_player_id`
- `owner_player_id`
- `tile_index`
- `base_amount`
- `final_amount`
- `modifiers`

### TilePurchasedEvent
Must include:
- `player_id`
- `tile_index`
- `cost`
- `purchase_source`

### LapRewardChosenEvent
Must include:
- `player_id`
- `choice`
- `amount`
- `resource_delta`

### FValueChangeEvent
Must include:
- `before`
- `after`
- `delta`
- `reason`

## Effect / Prompt Contract

### TrickWindowRequest
Must include:
- `player_id`
- `window_phase`
- `available_tricks`
- `can_pass`

### TrickWindowResolution
Must include:
- `player_id`
- `window_phase`
- `used_trick` or `null`

### FortuneDrawnEvent
Must include:
- `player_id`
- `card_name`
- `public_summary`

### MarkResolvedEvent
Must include:
- `source_player_id`
- `target_player_id`
- `success`
- `effect_type`
- `public_summary`

## Visibility Rules

### Public view
Public view may include only information available to a real player:
- public tricks
- hidden trick count only
- public effects
- public board state
- public resources

### Analysis view
Analysis view may include derived overlays:
- swing turns
- suspicious moves
- evaluator comments
- counterfactual hints

But it still must not silently mix hidden information into public-view payloads.

### Hard rule
The shared schema must separate:
- `public_payload`
- `analysis_payload`

The renderer chooses which one to show.

## Replay / Live Convergence Rule

Replay mode and live mode must share:
- event schema
- public snapshot schema
- prompt/response schema

Only the source differs:
- replay reads stored event stream
- live reads runtime event stream and prompt channel

## Serialization Rule
The contract must be serializable to:
- Python dataclasses or typed dicts
- JSON schema
- future Unity-safe transport objects

This is required so the same contract can survive:
- Python replay tooling
- browser renderer
- later Unity 3D port

## First Implementation Tasks

### Task 1. Freeze shared names
Before major implementation starts, freeze:
- event names
- field names
- prompt names
- snapshot names

### Task 2. Define JSON-serializable schema set
Create a schema package for:
- replay events
- public state
- decision prompts

### Task 3. Validate one replay path end-to-end
Prove the contract by running:
- one deterministic game
- full event output
- one replay projection
- one simple renderer

### Task 4. Validate one human prompt path end-to-end
Prove the contract by running one live prompt:
- engine emits request
- UI receives request
- human response returns
- engine continues legally

## Acceptance Criteria
The shared contract is ready when:
- Claude and GPT can implement against it independently
- one replay can be rendered without markdown parsing
- one live decision can round-trip through the prompt schema
- public view never leaks hidden information
- replay and live use the same core projection model

## Schema Freeze V1 Checklist

Before parallel implementation begins in earnest, freeze these items as `v1`:

### Event Names
Freeze the final names for:
- `session_start`
- `round_start`
- `weather_reveal`
- `draft_pick`
- `final_character_choice`
- `turn_start`
- `trick_window_open`
- `trick_window_closed`
- `dice_roll`
- `player_move`
- `landing_resolved`
- `rent_paid`
- `tile_purchased`
- `fortune_drawn`
- `fortune_resolved`
- `mark_resolved`
- `marker_transferred`
- `lap_reward_chosen`
- `f_value_change`
- `bankruptcy`
- `turn_end_snapshot`
- `game_end`

### Core Field Names
Freeze the final field names for:
- `session_id`
- `round_index`
- `turn_index`
- `step_index`
- `acting_player_id`
- `player_id`
- `source_player_id`
- `target_player_id`
- `tile_index`
- `from_tile_index`
- `to_tile_index`
- `choice`
- `public_phase`
- `public_payload`
- `analysis_payload`

### Public Phase Values
Freeze the allowed `public_phase` values.

Recommended initial set:
- `session_start`
- `weather`
- `draft`
- `character_select`
- `turn_start`
- `trick_window`
- `movement`
- `landing`
- `fortune`
- `mark`
- `economy`
- `lap_reward`
- `turn_end`
- `game_end`

### Prompt Envelope
Freeze the common prompt envelope fields:
- `request_type`
- `player_id`
- `legal_choices`
- `can_pass`
- `timeout_ms`
- `fallback_policy`
- `public_context`

### Visibility Boundary
Freeze the rule that:
- hidden information is never emitted in `public_payload`
- analysis-only overlays must stay in `analysis_payload`

## Schema Freeze V1 Sign-Off Table

Use this as the implementation-start checklist.

| Item | Scope | Owner | Status |
|------|------|------|--------|
| Event names frozen | replay/live shared events | Shared | pending |
| Core field names frozen | event and snapshot payloads | Shared | pending |
| `public_phase` values frozen | replay/live phase model | Shared | pending |
| Prompt envelope frozen | live decision request/response | Shared | pending |
| Visibility rules frozen | public vs analysis boundary | Shared | pending |
| Public state schema frozen | player/board/tile public state | Shared | pending |

Recommended rule:
- do not begin parallel implementation until every row is at least reviewed
- do not rename frozen fields casually once implementation starts

## Dependency Injection And Flexibility Guide

The goal is not "maximum abstraction everywhere".
The goal is stable seams where different implementations can evolve independently.

### High-DI Zones
These should be explicitly injected behind interfaces/contracts.

#### 1. Session / Runtime Control
- `RuntimeSession`
- `ReplayController`
- `GameSessionController`
- `DecisionAdapter`
- `EventSourceAdapter`

Reason:
- live and replay must be swappable
- human and AI players must be swappable
- transport or UI framework should not affect engine behavior

#### 2. Projection
- `PublicGameProjection`
- `AnalysisProjection`
- projection reducers / projectors

Reason:
- web, desktop, tests, and future Unity should be able to consume the same projected state

#### 3. Rendering
- `Renderer`
- board renderer
- panel renderer
- timeline renderer

Reason:
- HTML/SVG renderer today should be replaceable with Canvas or Unity later

#### 4. Prompt Handling
- `HumanDecisionAdapter`
- `AIDecisionAdapter`
- `PromptTransport`

Reason:
- queue, websocket, local loopback, or future network runtime may differ

### Moderate-DI Zones
These should be modular and replaceable, but do not need excessive abstraction on day one.

#### 1. Animation Policy
- movement animation timing
- event highlight timing
- transition presets

Reason:
- should be configurable
- does not need a deep plugin system initially

#### 2. UI Layout Policy
- compact vs expanded player panels
- public vs analysis layout
- mobile vs desktop layout rules

Reason:
- should be configurable by renderer/view mode
- can start as configuration instead of full interface hierarchy

#### 3. Replay Storage Adapter
- file-backed event source
- deterministic rerun-backed source

Reason:
- source must be swappable
- but likely only a few concrete implementations are needed early

### Low-DI Zones
These should stay simple and concrete unless a real need appears.

#### 1. Schema Value Objects
- `PlayerPublicState`
- `TilePublicState`
- `BoardPublicState`
- event payload structs

Reason:
- these are contracts, not strategy objects
- over-abstracting them increases ambiguity

#### 2. Field-Level Formatting Rules
- numeric formatting
- label text mapping
- simple icon/color lookup

Reason:
- these can be simple tables/config first

#### 3. Deterministic Contract Validators
- schema validation helpers
- required-field checks

Reason:
- these should be boring and fixed

## Flexibility Range

### What Must Stay Flexible
- renderer technology
- replay source implementation
- prompt transport
- human vs AI input source
- public vs analysis visualization mode
- future Unity port

### What Should Be Frozen Early
- event names
- public snapshot shape
- prompt envelope shape
- visibility rules
- authoritative truth-source policy

### What Should Not Be Rebuilt Repeatedly
- engine rule logic
- event naming conventions
- public-state contract naming
- replay/live core projection model

## Responsibility Matrix

This matrix is the recommended ownership split for the first implementation wave.

| Area | Primary Owner | Notes |
|------|---------------|------|
| structured event emission | Claude | lower substrate |
| public board/player snapshot emission | Claude | lower substrate |
| movement trace emission | Claude | required for animation |
| replay event schema package | Shared | agreed names and fields |
| prompt/request schema package | Shared | agreed names and fields |
| replay session/controller | GPT | upper runtime |
| live session/controller | GPT | upper runtime |
| public projection | GPT | consumes shared substrate |
| analysis projection | GPT | consumes shared substrate |
| renderer | GPT | SVG/HTML first is acceptable |
| prompt transport bridge | GPT | queue/websocket adapter layer |
| human input handling | GPT | uses shared prompt schema |
| deterministic replay validation | Shared | one agreed replay proof path |
| hidden/public visibility review | Shared | must be checked before shipping |

## First Integration Scenarios

These are the first end-to-end scenarios that should be proven before expanding the system.

### Scenario 1. Single Replay Proof
- run one deterministic game with replay-grade event logging
- reconstruct one replay stream without markdown parsing
- render one public replay view

Success criteria:
- board state matches event stream
- player panels update correctly
- no hidden information leaks into public view

### Scenario 2. Movement Animation Proof
- capture one `dice_roll`
- capture one `player_move` with full path
- animate pawn movement over the path

Success criteria:
- path is exact
- start crossing is visible
- final tile matches snapshot

### Scenario 3. Economy Proof
- capture one `rent_paid`
- capture one `tile_purchased`
- capture one `lap_reward_chosen`

Success criteria:
- panel cash changes correctly
- board ownership changes correctly
- lap reward result is visible in UI

### Scenario 4. Human Prompt Round-Trip Proof
- engine emits one live prompt request
- UI receives it
- human response returns through the prompt contract
- engine continues legally

Success criteria:
- no engine/UI deadlock
- legal choices only
- fallback path is defined

### Scenario 5. Public vs Analysis View Proof
- render the same turn in both modes

Success criteria:
- public mode exposes only public information
- analysis mode can add overlays without polluting public payloads

## Current Recommendation
This document should be treated as the immediate cross-implementation contract baseline for visualization work.

The implementation order should be:
1. agree this contract
2. freeze schema names and prompt envelope as `v1`
3. emit substrate events and snapshots
4. build replay projection
5. build renderer
6. build human prompt loop
