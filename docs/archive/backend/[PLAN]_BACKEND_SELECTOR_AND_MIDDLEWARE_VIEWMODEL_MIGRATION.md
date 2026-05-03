# [PLAN] Backend Selector And Middleware ViewModel Migration

Status: ACTIVE  
Updated: 2026-04-09  
Owner: Codex  
Scope: engine / server / stream middleware / web contracts

## Why This Plan Exists

The web client is currently doing too much interpretation work over the raw stream.

Today the frontend is responsible for:

- reconstructing live snapshot state from mixed `event` / `prompt` messages
- deriving current actor / public faces / marker ownership / marker direction
- re-ordering players for HUD display
- rebuilding decision-specific candidate lists such as mark targets
- deciding when older prompt/snapshot state should be considered stale

That has caused repeated regressions:

- stale professions leaking across turns
- active-character strip and decision prompt disagreeing
- player strip order changing for the wrong reason
- prompt UIs needing frontend-only repair logic to stay playable

This plan moves selector ownership to backend/middleware layers so the frontend becomes a mostly thin renderer over canonical view models.

## Intent

Move from:

- `raw stream + heavy web selectors + UI-local repair logic`

To:

- `raw domain stream + server-side derived view stream + thin web projection`

The frontend should still own:

- presentation layout
- local focus / collapse / animation state
- purely visual grouping and density choices

The frontend should stop owning:

- game-state reconstruction
- prompt-candidate legality reconstruction
- marker-direction ordering reconstruction
- stale-state cleanup logic

## Non-Goals

This plan does not:

- redesign the full websocket protocol from scratch
- remove raw event replay
- change engine rules by itself
- merge all UI text into the backend

The goal is selector/view-model migration, not protocol replacement.

## Current Problem Map

### 1. Web Selectors Are Acting Like A State Engine

`apps/web/src/domain/selectors/streamSelectors.ts` currently rebuilds:

- live snapshot
- player strip state
- active-character strip state
- marker ownership and now marker direction
- mark-target candidates
- current-turn reveal ordering

This is effectively middleware logic living in the client.

### 2. Prompt Semantics Depend On Frontend Repair

`apps/web/src/features/prompt/PromptOverlay.tsx` and `App.tsx` currently contain special repair behavior for:

- burden batch progression
- active flip batch progression
- lap reward normalization
- mark-target candidate filtering

The UI is compensating for transport shape instead of simply rendering server intent.

### 3. Different UI Areas Still Read Different Truths

Even after recent fixes, these areas can still drift:

- player strip
- active-character strip
- prompt candidate lists
- hand tray
- public event stack

That is a boundary problem, not just a rendering bug.

## Target Architecture

### Layer 1. Domain Event Stream

Keep the raw engine/event stream as the canonical replay source.

This layer remains:

- append-only
- order-preserving
- minimally interpreted

Primary files:

- `GPT/engine.py`
- `apps/server/src/services/stream_service.py`
- `apps/server/src/routes/stream.py`

### Layer 2. Server Selector / Reducer Layer

Add a server-owned selector module that can consume raw stream messages and build canonical derived state.

Proposed location:

- `apps/server/src/services/view_state_reducer.py`
- `apps/server/src/services/view_selectors.py`

Responsibilities:

- reduce raw stream into a session-scoped derived state snapshot
- apply turn / round boundary resets
- derive active faces by priority slot
- derive player HUD ordering from marker owner + direction
- derive decision candidate lists from canonical public state
- expose prompt-scoped public view models
- expose board/HUD/event-stack view models

This layer becomes the single implementation of selector logic.

### Layer 3. Stream Middleware / Projection Layer

Add a middleware service that publishes derived view payloads beside raw events.

Proposed location:

- `apps/server/src/services/view_projection_service.py`

Responsibilities:

- subscribe to raw stream publication points
- update session-local reduced view state
- emit lightweight derived payload messages, for example:
  - `view_snapshot`
  - `view_prompt`
  - `view_turn_stage`
  - `view_public_events`

This layer is where transport shaping happens.

### Layer 4. Thin Web Adapters

Web selectors become simple payload readers.

The web should mostly do:

- pick latest `view_*` payload
- render
- retain local-only UX state

Anything beyond that should be considered exceptional.

## Migration Principle

Do not cut over everything at once.

The migration should proceed as:

1. build server selectors
2. publish derived view payloads in parallel with raw stream
3. convert web readers feature-by-feature
4. remove duplicated frontend selector logic only after parity is proven

This keeps replay compatibility and reduces rollout risk.

## Canonical Derived Models To Introduce

### A. `DerivedSessionView`

Purpose:

- top-level session HUD state

Fields:

- `session_id`
- `round_index`
- `turn_index`
- `marker_owner_player_id`
- `marker_draft_direction`
- `current_actor_player_id`
- `current_actor_character`
- `weather_name`
- `weather_effect`
- `f_value`
- `end_time_remaining`

### B. `DerivedPlayerStripView`

Purpose:

- top player HUD cards

Fields per player:

- `player_id`
- `display_name`
- `ordered_index`
- `is_marker_owner`
- `is_current_actor`
- `is_local_candidate` if needed
- `public_character_face`
- `cash`
- `shards`
- `owned_tile_count`
- `hand_score`
- `placed_score`
- `total_score`
- `trick_count`

Important:

- order must be derived from marker owner and marker direction, not character priority

### C. `DerivedActiveCharacterStripView`

Purpose:

- authoritative priority-slot strip

Fields per slot:

- `slot`
- `active_character`
- `inactive_character`
- `holder_player_id`
- `is_revealed`
- `is_current_actor_slot`

This is the canonical source for:

- active-character HUD
- mark-target public candidate derivation
- flip/draft public reasoning

### D. `DerivedPromptView`

Purpose:

- render-ready prompt contract

Fields:

- `request_id`
- `request_type`
- `player_id`
- `prompt_title`
- `prompt_help`
- `timeout_ms`
- `public_context`
- `display_choices`
- `focus_tiles`
- `visibility_policy`
- `batch_mode`
- `followup_policy`

Important:

- `display_choices` must already be canonical
- frontend should not re-filter mark targets, burden progression, or active-flip candidate logic

### E. `DerivedPublicEventStackView`

Purpose:

- current public event stack

Fields per item:

- `step`
- `event_code`
- `label`
- `detail`
- `tone`
- `focus_tile_index`

Important:

- sequence must reflect engine order
- numbering shown to UI must come from derived order, not raw seq ids

### F. `DerivedBoardOverlayView`

Purpose:

- board-level support data

Fields:

- `focus_tiles`
- `move_path`
- `purchase_target_tile`
- `rent_target_tile`
- `lap_reward_focus`
- `decision_overlay_frame_hint`

This is optional in phase 1, but should exist before removing the last UI-local focus selector logic.

## Server Selector Modules

### 1. `view_state_reducer.py`

Role:

- consume raw messages in order
- maintain reduced canonical session view state

Should own:

- round boundary resets
- turn boundary resets
- marker owner / direction updates
- active face updates
- public prompt context hydration

### 2. `view_selectors.py`

Role:

- derive render-ready slices from reduced canonical state

Should own:

- player strip ordering
- active-character strip
- mark-target candidate list
- event stack order
- current turn stage
- current actionable prompt projection

### 3. `view_projection_service.py`

Role:

- bridge reducer/selectors to stream transport

Should own:

- when to emit `view_snapshot`
- when to emit `view_prompt`
- when to emit `view_public_events`
- when to emit updated projection after raw event publish

## Contract Strategy

### Raw Stream Must Stay

Keep existing raw messages for:

- replay fidelity
- debugging
- compatibility during migration

### New Derived Messages Should Be Additive

Additive message types:

- `view_snapshot`
- `view_prompt`
- `view_turn_stage`
- `view_public_events`

or one consolidated type:

- `view_state`

Recommendation:

- use one consolidated `view_state` first for lower transport churn
- split later only if payload size or update frequency becomes a problem

### Suggested `view_state` Shape

```json
{
  "type": "view_state",
  "payload": {
    "session": {},
    "players": [],
    "active_slots": [],
    "prompt": null,
    "public_events": [],
    "board_overlay": {},
    "version": 1
  }
}
```

This gives the frontend one canonical source to read.

## Migration Plan

### Phase 0. Inventory And Freeze

Before moving logic:

- inventory every web selector currently doing state reconstruction
- tag each as:
  - `presentation-only`
  - `projection`
  - `rule reconstruction`
- freeze new frontend selector growth except bugfixes

Primary files to inventory:

- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/domain/selectors/promptSelectors.ts`
- `apps/web/src/App.tsx`
- `apps/web/src/features/prompt/PromptOverlay.tsx`

Deliverable:

- a migration checklist section in this plan or a follow-up task table

### Phase 1. Build Canonical Reducer On Server

Implement:

- raw message reducer in `view_state_reducer.py`
- test fixtures using real mixed `event` / `prompt` sequences

Must cover first:

- marker owner and direction
- active-by-card
- player public face
- turn stage
- prompt lifecycle

Validation:

- parity tests against currently reproduced regressions

### Phase 2. Move Prompt Candidate Logic

Move all prompt-specific selector logic server-side:

- mark target
- active flip
- burden exchange
- lap reward
- draft / final character
- purchase_tile canonical focus

Frontend after phase 2:

- no candidate filtering
- no batch progression repair decisions
- only dispatch selected choice ids

### Phase 3. Move Player / HUD Ordering Logic

Move:

- player strip ordering
- marker-driven ordering
- active-character strip model
- public event stack model

Frontend after phase 3:

- reads pre-ordered player array
- reads precomputed event stack
- no longer computes marker-based sort locally

### Phase 4. Move Board-Focus Logic

Move:

- focus tile derivation
- path/highlight derivation
- purchase/rent/fortune target focus

Frontend after phase 4:

- only paints highlights from derived model

### Phase 5. Remove Duplicated Web Reducers

Delete or collapse:

- live snapshot rebuild logic in web selectors
- active-by-card repair logic in web selectors
- prompt-specific legality repair logic in `PromptOverlay`

This phase should be done only after:

- replay/live parity tests pass
- real playtest confirms no regression

## Frontend End State

### Web Should Keep

- locale formatting
- layout grouping
- collapsed/expanded UI state
- animation timing
- keyboard focus behavior

### Web Should Lose

- stream reduction over raw events
- state healing over stale snapshots
- public candidate derivation
- marker-direction ordering derivation
- burden follow-up semantics
- active-slot reconstruction

## Testing Strategy

### Server Tests

Add selector/reducer tests in:

- `apps/server/tests/test_view_state_reducer.py`
- `apps/server/tests/test_view_selectors.py`

Cover:

- round boundary reset
- turn boundary reset
- marker transfer + direction changes
- draft/final-character visibility
- mark-target candidate derivation
- burden batch progression
- event ordering

### Contract Tests

Add transport tests in:

- `apps/server/tests/test_stream_api.py`
- `apps/server/tests/test_runtime_service.py`

Cover:

- derived payload emitted with raw payload
- actionable prompt visibility
- seat-only prompt privacy still preserved

### Web Tests

Web tests should shrink in logic depth over time.

Target:

- selector tests become payload-reader tests
- component tests verify rendering only

## Rollout Strategy

### Step 1. Parallel Read

Ship derived server payloads while frontend still uses old selectors behind a debug flag comparison path.

### Step 2. Shadow Compare

During development and playtests:

- compare old web-derived model and server-derived model
- log diffs for:
  - player order
  - active slots
  - prompt candidates
  - event stack

### Step 3. Cut Over Per Surface

Recommended order:

1. player strip
2. active-character strip
3. mark-target / draft / active-flip prompts
4. burden exchange / lap reward prompts
5. public event stack
6. board focus and highlights

### Step 4. Delete Old Logic

Only after each surface has:

- server tests
- web render tests
- live mixed-seat check

## Risks

### R1. Dual Truth During Migration

Mitigation:

- additive payloads
- explicit feature flags
- shadow comparisons

### R2. Replay Compatibility Drift

Mitigation:

- raw stream remains untouched
- derived layer rebuilds entirely from raw stream

### R3. Hidden Rule Changes By Accident

Mitigation:

- server selector layer must not invent new legality
- only move existing canonical interpretation logic from frontend into middleware/server

### R4. Payload Growth

Mitigation:

- start with one `view_state`
- split only if profiling says it is necessary

## Concrete File Plan

### New Files

- `apps/server/src/services/view_state_reducer.py`
- `apps/server/src/services/view_selectors.py`
- `apps/server/src/services/view_projection_service.py`
- `apps/server/tests/test_view_state_reducer.py`
- `apps/server/tests/test_view_selectors.py`

### Major Edits

- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/stream_service.py`
- `apps/server/src/routes/stream.py`
- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/domain/selectors/promptSelectors.ts`
- `apps/web/src/App.tsx`
- `apps/web/src/features/prompt/PromptOverlay.tsx`
- `apps/web/src/features/board/BoardPanel.tsx`

## First Execution Slice

The first implementation slice should not attempt the whole migration.

Do this first:

1. create `view_state_reducer.py`
2. move marker owner / direction, active-by-card, current actor, and player strip ordering into it
3. emit one additive `view_state` payload with:
   - session summary
   - ordered player strip
   - active-character strip
4. cut web player strip and active-character strip over to that payload

Why first:

- it removes the most unstable selector logic
- it gives immediate value without redesigning every prompt at once

## Success Criteria

This migration is successful when:

- frontend no longer reconstructs canonical gameplay state from raw mixed messages
- player strip, active-character strip, prompts, and event stack read the same server-derived truth
- prompt components are mostly dumb renderers
- real playtest bugs stop being “selector disagreement” bugs

## Decision

This architecture migration is explicitly reopened because the current real-play bug class is caused by boundary ownership, not by isolated UI mistakes.

The repo should treat this as a controlled boundary refactor, not as a cosmetic frontend cleanup.
