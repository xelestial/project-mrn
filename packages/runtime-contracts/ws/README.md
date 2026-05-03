# WS Runtime Contract

This directory freezes v1 transport contracts for the online runtime.

## Layout

- `schemas/`: JSON Schema files by message type.
- `examples/`: canonical payload examples used for docs and tests.
  - Includes per-message fixtures and ordered sequence fixtures for decision lanes.
  - Includes selector/view-state fixtures shared by frontend, backend, and engine tests.

## Scope

Inbound (`server -> client`):

- `event`
- `prompt`
- `decision_ack`
- `error`
- `heartbeat`

Prompt payloads use canonical `legal_choices` as the primary choice list. A legacy `choices` field may still appear temporarily for compatibility, but frozen examples and new surfaces should prefer `legal_choices`.

Decision lifecycle examples now also freeze external-participant metadata on `decision_requested`, including:

- `legal_choices`
- `public_context.tile_index`
- `public_context.external_ai_worker_id`
- `public_context.external_ai_resolution_status`

Outbound (`client -> server`):

- `resume`
- `decision`

## Change Rules

1. Additive changes only by default.
2. Breaking changes require:
   - schema update
   - example update
   - API/interface spec update
   - compatibility note in `docs/current/runtime/end-to-end-contract.md`

## Ordered Sequence Fixtures

- `sequence.decision.accepted_then_domain.json`
  - `decision_requested -> decision_resolved -> player_move`
- `sequence.decision.timeout_then_domain.json`
  - `decision_requested -> decision_resolved -> decision_timeout_fallback -> turn_end_snapshot`

## Shared Selector Fixtures

- `selector.scene.turn_resolution.json`
  - shared fixture + metadata for:
    - backend `view_state.scene` projection tests
    - frontend scene selector tests
    - engine event-order regression tests
  - metadata currently includes:
    - `core_turn_resolution_order`
    - `engine_advance_resolution_order`
- `selector.player.mark_target_visibility.json`
  - shared fixture + metadata for:
    - backend `view_state.players / active_slots / mark_target` projection tests
    - frontend active-slot and mark-target selector tests
    - engine public mark-target visibility order checks
  - metadata currently includes:
    - `actor_player_id`
    - `actor_character`
    - `expected_visible_target_characters`
- `selector.board.live_tiles.json`
  - shared fixture + metadata for:
    - backend `view_state.board.tiles` projection tests
    - frontend live snapshot board-surface adapter tests
  - metadata currently includes:
    - `focus_tile_indices`
- `selector.prompt.lap_reward_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.lap_reward` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware reward-choice consistency checks
  - metadata currently includes:
    - `expected_choice_ids`
- `selector.prompt.burden_exchange_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.burden_exchange_batch` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware burden-context consistency checks
  - metadata currently includes:
    - `expected_current_target_deck_index`
    - `expected_card_names`
- `selector.prompt.mark_target_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.mark_target` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware mark-target choice consistency checks
  - metadata currently includes:
    - `expected_choice_ids`
    - `actor_name`
- `selector.prompt.active_flip_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.active_flip` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware active-flip choice consistency checks
  - metadata currently includes:
    - `expected_choice_ids`
    - `finish_choice_id`
- `selector.prompt.coin_placement_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.coin_placement` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware coin-placement choice consistency checks
  - metadata currently includes:
    - `expected_choice_ids`
    - `owned_tile_count`
- `selector.prompt.geo_bonus_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.geo_bonus` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware geo-bonus choice consistency checks
  - metadata currently includes:
    - `expected_choice_ids`
    - `actor_name`
- `selector.prompt.movement_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.movement` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware movement-choice consistency checks
  - metadata currently includes:
    - `expected_choice_ids`
    - `roll_choice_id`
    - `card_pool`
- `selector.prompt.hand_choice_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.hand_choice` projection tests
    - frontend prompt surface adapter tests
  - metadata currently includes:
    - `expected_choice_ids`
    - `pass_choice_id`
    - `mode`
- `selector.prompt.runaway_step_surface.json`
  - shared fixture + metadata for:
    - backend `view_state.prompt.active.surface.runaway_step` projection tests
    - frontend prompt surface adapter tests
    - engine/shared middleware runaway-step choice consistency checks
  - metadata currently includes:
    - `expected_choice_ids`
    - `bonus_choice_id`
    - `stay_choice_id`
