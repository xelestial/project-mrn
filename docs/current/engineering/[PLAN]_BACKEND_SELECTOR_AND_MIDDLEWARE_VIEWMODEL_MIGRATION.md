# [PLAN] Backend Selector And Middleware ViewModel Migration

Status: ACTIVE  
Updated: 2026-04-09  
Owner: Codex

## Purpose

This plan exists to move gameplay-derived UI truth out of the web app and into a backend or middleware selector layer so the frontend can become a thin renderer.

The goal is not “move code for its own sake.”
The goal is to make the same canonical derived state reusable across:

- current web HUD
- future frontend rewrites
- Unity clients
- Unreal clients
- spectator / replay consumers
- native or alternate clients

## Why This Plan Exists Now

`docs/current/planning/PLAN_STATUS_INDEX.md` says broad architecture migration should not be reopened by default.

This document is an explicit exception because the user directly requested a backend/middleware selector migration and the current live-play bug pattern now clearly shows that too much truth still lives in web selectors.

This plan should therefore be treated as:

- a user-requested architecture plan
- a replacement for continued piecemeal selector drift in the web app
- a staged migration plan, not a single big-bang rewrite

## Ground Truth

The current web app is still doing too much state construction locally.

Today, the frontend derives major gameplay truths in:

- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/domain/selectors/promptSelectors.ts`
- `apps/web/src/App.tsx`

These selectors already reconstruct:

- current actor and turn stage
- active character slots
- mark-target candidates
- player ordering from marker owner and direction
- hand tray / burden tray visibility
- prompt liveness and prompt dedupe
- reveal/event ordering for HUD display

This creates three recurring problems:

1. frontend-specific truth drift  
Different surfaces can disagree because they rebuild state from raw messages independently.

2. replay/live contract instability  
A consumer must know web-specific selector logic to understand the stream correctly.

3. migration cost  
Any frontend rewrite inherits hidden game-logic reconstruction work instead of consuming canonical view models.

4. renderer lock-in  
If selector truth stays embedded in React selectors and component glue, a Unity or Unreal client must reverse-engineer gameplay semantics from web behavior instead of binding to a stable contract.

## Target Outcome

The server-side stack should expose canonical, UI-ready derived models while preserving raw stream events.

The target layering is:

1. engine emits canonical domain events
2. server runtime/stream middleware derives stable view selectors from those events
3. transport publishes both:
   - raw event stream
   - derived view-state payloads / projections
4. frontend renders those projections with minimal local interpretation

The frontend should still do:

- layout
- formatting
- local animations
- temporary input state
- presentational filtering that does not change gameplay truth

The frontend should stop doing:

- gameplay-derived ordering
- slot ownership reconstruction
- mark-target legality reconstruction
- prompt chain collapse rules
- board / player / hand truth assembly from raw stream deltas

## Compatibility Requirement

This migration must be strong enough that React can be replaced by Unity or Unreal without re-implementing gameplay-state interpretation.

The portability target is:

1. keep the selector and projector layer
2. swap the presentation layer
3. adapt only the client-side transport binding and rendering widgets
4. avoid rebuilding gameplay truth in the new client

That means the new backend or middleware selector layer must provide:

- renderer-agnostic selectors
- dependency-injected assembly boundaries
- transport-neutral view-state objects before serialization
- payload contracts stable enough for:
  - TypeScript web clients
  - C# Unity clients
  - Unreal-native adapters

## Non-Goals

This plan does not:

- replace the engine event model
- remove raw replay or raw stream access
- merge all runtime logic into one giant payload
- require immediate deletion of all web selectors in one pass
- redesign UI wording or board layout by itself

## Design Principles

### 1. Raw Events Remain Canonical

Derived selectors must be projections of the raw stream, not a second hidden game state.

The source of truth remains:

- engine domain state
- decision ordering
- emitted runtime events

### 2. Backend Selectors Must Be Reusable

Selectors must live in a domain or middleware module that is not tied to React, DOM shape, or current CSS layout.

They must also not depend on TypeScript-only selector semantics or React lifecycle assumptions.

### 3. Projection Contracts Must Be Stable

A future client should be able to render from derived payloads without re-implementing web-only selector behavior.

The contract should be stable enough that the same payload can be bound into:

- React props
- Unity DTOs
- Unreal adapter structs or objects

### 4. Dependency Injection Must Be First-Class

Selector assembly must be wired through injectable boundaries, not hidden imports or ad hoc component glue.

Required DI properties:

- selector modules are independently testable
- projector assembly can be swapped or decorated in tests
- transport adapters can consume the same selector outputs without forking logic

### 5. Migration Must Be Incremental

We should dual-run:

- existing web selectors
- backend-derived selectors

until each slice is verified and cut over.

## Proposed Module Boundary

Create a new server-side projection package.

Recommended location:

- `apps/server/src/domain/view_state/`

Recommended modules:

- `apps/server/src/domain/view_state/types.py`
- `apps/server/src/domain/view_state/snapshot_selector.py`
- `apps/server/src/domain/view_state/player_selector.py`
- `apps/server/src/domain/view_state/active_slots_selector.py`
- `apps/server/src/domain/view_state/mark_target_selector.py`
- `apps/server/src/domain/view_state/prompt_selector.py`
- `apps/server/src/domain/view_state/reveal_selector.py`
- `apps/server/src/domain/view_state/board_selector.py`
- `apps/server/src/domain/view_state/projector.py`

If the team prefers service ownership instead of domain ownership, the acceptable fallback is:

- `apps/server/src/services/view_state/`

but the first option is preferred because this is selector/projection logic, not request orchestration.

Recommended companion adapter layer:

- `apps/server/src/infra/view_state_adapters/`

Examples:

- `websocket_adapter.py`
- `replay_export_adapter.py`
- `runtime_status_adapter.py`

## Proposed Responsibilities

### `snapshot_selector.py`

Build the latest stable gameplay snapshot from runtime events.

Derived fields should include:

- round index
- turn index
- current actor player id
- marker owner
- marker draft direction
- live player resources
- pawn positions
- tile ownership
- score state

### `player_selector.py`

Build canonical player card ordering and derived player cards.

Required outputs:

- marker-ordered players
- current character face
- visible role text
- score / cash / shards / tile count / trick count
- current-turn ownership markers

### `active_slots_selector.py`

Build the current active-character strip from canonical visible state.

Required outputs:

- `#1 ~ #8` active face
- reverse-face / paired-face where applicable
- owning player if known
- current actor marker

This module must own the “what is publicly visible right now?” rule, not the frontend.

### `mark_target_selector.py`

Build mark-target candidates from the same active-slot truth used by the strip.

Required outputs:

- acting slot
- acting character
- eligible target slots with higher priority than actor where required
- visible target labels
- optional “skip” metadata

This must replace web-side reconstruction from prompt choices.

### `prompt_selector.py`

Project actionable prompt state into a UI-ready contract.

Required outputs:

- active prompt
- prompt phase / task label
- stale prompt suppression
- prompt chain grouping
- derived controls and visible choice groups

This is where repeated burden prompts, repeated draft prompts, and similar chain behavior should be normalized.

### `reveal_selector.py`

Build turn reveal stack / public event theater projections.

Required outputs:

- current-turn reveal items
- stable canonical ordering
- display-ready reveal phases
- interrupt-worthiness / visibility flags

### `board_selector.py`

Build tile-level and board overlay view state.

Required outputs:

- tile highlight state
- landing / purchase / rent target emphasis
- score / ownership badges
- visible board overlays anchored to tile geometry identifiers

### `projector.py`

Single assembly entrypoint that composes the above selectors into one transport-ready view model.

Suggested outputs:

- `view_state.snapshot`
- `view_state.players`
- `view_state.active_slots`
- `view_state.mark_target`
- `view_state.prompt`
- `view_state.reveals`
- `view_state.board`

The projector should first build a transport-neutral object.

Transport adapters should then serialize that object for:

- websocket stream delivery
- replay export
- runtime status
- future SDK or client bindings

## Transport Strategy

Do not replace the existing raw stream immediately.

Instead, add a derived projection alongside raw events.

Recommended staged contract:

1. keep current raw `stream_service` payloads unchanged
2. publish a new derived payload channel or embed a `view_state` projection in:
   - replay export
   - runtime status
   - websocket stream snapshots
3. let the web app dual-read raw + derived state during migration
4. cut over one surface at a time

Possible integration points:

- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/stream_service.py`
- `apps/server/src/routes/stream.py`

## DI And Client Adapter Contract

The new selector package should expose a narrow injectable interface rather than direct concrete coupling.

Recommended pattern:

- `ViewStateSelectorSet`
- `ViewStateProjector`
- `ViewStateTransportAdapter`

Responsibilities:

- selector set:
  - owns canonical derived-state assembly
- projector:
  - combines selector outputs into one immutable projection
- transport adapter:
  - serializes the projection for websocket, replay, REST, or future client SDKs

This is the seam that should let React, Unity, and Unreal all bind to the same backend truth without duplicating rule interpretation.

## Suggested Data Contract Shape

This is a shape guideline, not a frozen schema.

```json
{
  "view_state": {
    "snapshot_version": 1,
    "round_index": 2,
    "turn_index": 5,
    "marker_owner_player_id": 3,
    "marker_draft_direction": "clockwise",
    "players": [],
    "active_slots": [],
    "prompt": {},
    "mark_target": {},
    "reveals": [],
    "board": {}
  }
}
```

Rules:

- include enough identity for replay and diffing
- prefer explicit fields over UI-implied meaning
- do not embed React-specific grouping
- keep string ownership shared or localized at presentation layer when possible
- keep field naming stable enough for generated or hand-written non-web client DTOs
- separate semantic fields from layout-only hints

## API Documentation Tracking Requirement

Any transport contract change made during this migration must update the relevant API and runtime docs in the same implementation slice.

Minimum documentation targets:

- `docs/current/api/online-game-api-spec.md`
- `docs/current/api/README.md`
- `packages/runtime-contracts/ws/examples/`
- any schema or example files that define websocket, replay, or request/response payloads

Rules:

1. if websocket payloads gain `view_state`, document it
2. if replay export shape changes, document it
3. if runtime-status shape changes, document it
4. if prompt or decision payload contracts change, update examples and schemas together

No phase is complete if code landed but the corresponding contract docs were left behind.

## Migration Slices

### Phase 0. Inventory And Mapping

Before implementation, map every current web selector to a future backend selector owner.

Minimum mapping table:

- `selectTurnStage` -> backend prompt/reveal projector
- `selectCurrentTurnRevealItems` -> backend reveal selector
- `selectDerivedPlayers` -> backend player selector
- `selectActiveCharacterSlots` -> backend active slot selector
- `selectMarkTargetCharacterSlots` -> backend mark-target selector
- `selectMarkerOrderedPlayers` -> backend player selector
- `selectCurrentHandTrayCards` -> backend prompt / hand selector

Exit criteria:

- no major web selector remains “ownerless” in the migration table

### Phase 1. Canonical Snapshot And Player Projection

Build server-side:

- live snapshot projection
- marker-based player ordering
- canonical player cards

Frontend cutover target:

- top player strip

Exit criteria:

- player strip no longer computes ordering locally
- web only renders backend-provided ordered players
- any changed transport payload is documented in the API/runtime docs

### Phase 2. Active Slots And Mark Targets

Build server-side:

- active-character strip
- mark-target candidate projection

Frontend cutover targets:

- active slot strip
- mark-target prompt candidate list

Exit criteria:

- active strip and mark-target prompt read the same backend selector source
- no prompt-specific fallback reconstruction remains in web for this path
- any changed prompt or stream payload shape is documented

### Phase 3. Prompt Surface Projection

Build server-side:

- active prompt
- prompt chain grouping
- stale prompt suppression
- derived choice groups

Frontend cutover targets:

- prompt overlay root
- burden exchange batching
- draft/final-character stale prompt handling

Exit criteria:

- prompt dedupe and prompt chain behavior no longer live in App-level ad hoc state
- prompt transport examples and schemas are updated if the contract changed

### Phase 4. Reveal And Event Theater

Build server-side:

- reveal stack
- canonical display order
- interrupt classification

Frontend cutover targets:

- public event overlay
- turn-stage banner interplay

Exit criteria:

- web no longer re-sorts public event cards locally
- replay / websocket docs are updated if reveal projections changed transport shape

### Phase 5. Board And Hand View State

Build server-side:

- hand tray / burden tray canonical view state
- tile highlight / landing / purchase / rent emphasis

Frontend cutover targets:

- hand tray
- burden tray
- tile emphasis

Exit criteria:

- board overlays and trays stop rebuilding gameplay truth from raw prompt data
- transport docs are updated if tray or board projection fields become public API

### Phase 6. Web Selector De-Sugaring

After each slice is cut over:

- delete duplicated web selector logic
- leave only presentational helpers
- keep lightweight formatting selectors where useful

Exit criteria:

- web selectors are presentation adapters, not gameplay truth assemblers

## Required Mapping Table

During implementation, maintain a live mapping section in this doc or a follow-on task file.

Minimum columns:

- current web selector / logic path
- new backend selector owner
- transport field
- frontend consumer
- cutover status

## Validation Strategy

### Server Unit Tests

Add focused tests for each new selector module.

Minimum cases:

- marker owner and direction ordering
- active slot visibility across round start / turn start / flips
- mark-target candidate generation
- stale prompt suppression
- reveal ordering
- burden chain grouping

### Runtime Integration Tests

Add runtime-service level projection tests asserting the derived payload matches raw event history.

Primary area:

- `apps/server/tests/test_runtime_service.py`

### Stream / Replay Contract Tests

Add tests for:

- websocket snapshot payloads
- replay export payloads
- projection consistency across reconnect/replay windows
- backward-compatible field presence for alternate clients where required

Primary area:

- `apps/server/tests/test_stream_api.py`

### Web Contract Tests

The web should add tests only for:

- rendering derived payloads correctly
- not re-deriving backend-owned truth

The web should stop being the first place gameplay truth is validated.

### Client Compatibility Fixtures

Add at least one fixture or contract example that is explicitly written as if consumed by a non-web client.

Minimum expectation:

- a documented `view_state` example that a Unity or Unreal adapter could deserialize without reading React source

### Live Play Validation

Re-run mixed-seat playtests after each major phase:

- human + local AI
- human + external AI
- spectator + seat socket
- replay export after a real session

## Risks

### 1. Dual Truth During Migration

For a period, raw-event web selectors and backend view selectors may disagree.

Mitigation:

- cut over one surface at a time
- add side-by-side assertions in tests

### 2. Projection Drift From Engine Semantics

If selector modules begin interpreting rules instead of projecting them, a second rules engine will emerge.

Mitigation:

- keep projections declarative
- preserve raw event identity and source fields

### 3. Payload Bloat

Overeager view-state payloads can make the stream noisy or heavy.

Mitigation:

- prefer structured projections over repeated verbose duplicates
- measure payload size before broad rollout

### 4. Hidden String Ownership Drift

Server selectors might start owning presentation wording.

Mitigation:

- selectors should expose stable semantic fields
- wording should remain in shared text resources or be intentionally scoped

## Open Questions

1. Should `view_state` be embedded in every stream message snapshot, or only on selected message types plus runtime/replay endpoints?
2. Should the projection layer materialize per-message or per-session snapshot checkpoints?
3. Should prompt grouping live entirely on the server, or is there a small local optimistic layer we still want in the web app?

These should be resolved before implementation Phase 2 begins.

## Exit Criteria

This migration is complete when:

- top player strip reads backend-derived ordering and player cards
- active slot strip reads backend-derived active slots
- mark-target prompt reads backend-derived candidates
- prompt overlay reads backend-derived prompt grouping and stale-prompt rules
- public event theater reads backend-derived reveal ordering
- hand and burden trays read backend-derived tray state
- major gameplay truth no longer depends on React selectors interpreting raw stream history
- selector and projector contracts are DI-friendly and transport-neutral
- a replacement client can bind to the documented contract without reverse-engineering React logic
- all changed API/runtime docs were updated together with the code

## Immediate Next Step

Do not begin broad code movement blindly.

First implementation task should be:

1. create the server-side `view_state` package skeleton
2. migrate player ordering and canonical player card projection first
3. dual-wire the web player strip to that backend selector
4. validate with runtime + replay + web tests before moving to active slots
