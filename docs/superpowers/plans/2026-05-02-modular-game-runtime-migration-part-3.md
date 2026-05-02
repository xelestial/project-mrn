# Modular Game Runtime Migration Part 3 - Implementation Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` before implementing this migration. This document is Part 3 of 3 and defines concrete implementation slices. Read Part 1 for goals and Part 2 for module contracts.

**Goal:** Implement the module/frame runtime in safe, testable slices while keeping existing gameplay stable until the module runner is explicitly enabled for a session.

**Architecture:** Start with observability and projection on top of the legacy runner, then introduce module contracts, then enable round/turn/sequence execution behind persisted runner flags, then cut over after parity validation.

**Tech Stack:** Python tests with `pytest`, TypeScript tests with `vitest`, browser checks with Playwright where frontend behavior changes.

---

## 3-1. Implementation Principles

1. Do not big-bang rewrite `GPT/engine.py`.
2. Add compatibility metadata first, so every later failure is diagnosable by frame/module path.
3. Keep module runner and legacy runner mutually exclusive per session.
4. Port one boundary at a time: contracts, round modules, turn modules, sequence modules, prompts, stream, frontend.
5. Each slice must add tests before or with implementation.
6. Existing event names remain stable until a documented cleanup phase.
7. No frontend stage logic may be moved to raw localized text while module projection exists.

## 3-2. New Engine File Map

Create these files:

1. `GPT/runtime_modules/__init__.py`
2. `GPT/runtime_modules/contracts.py`
3. `GPT/runtime_modules/ids.py`
4. `GPT/runtime_modules/journal.py`
5. `GPT/runtime_modules/modifiers.py`
6. `GPT/runtime_modules/prompts.py`
7. `GPT/runtime_modules/queue.py`
8. `GPT/runtime_modules/runner.py`
9. `GPT/runtime_modules/legacy_metadata.py`
10. `GPT/runtime_modules/round_modules.py`
11. `GPT/runtime_modules/turn_modules.py`
12. `GPT/runtime_modules/sequence_modules.py`
13. `GPT/runtime_modules/adapters.py`

Modify these files:

1. `GPT/state.py`
2. `GPT/engine.py`
3. `GPT/effect_handlers.py` only when a module needs a stable existing handler path

Add tests:

1. `GPT/test_runtime_module_contracts.py`
2. `GPT/test_runtime_legacy_module_metadata.py`
3. `GPT/test_runtime_round_modules.py`
4. `GPT/test_runtime_turn_modules.py`
5. `GPT/test_runtime_sequence_modules.py`
6. `GPT/test_runtime_prompt_continuation.py`
7. `GPT/test_runtime_module_parity.py`

## 3-3. New Backend File Map

Modify these files:

1. `apps/server/src/services/runtime_service.py`
2. `apps/server/src/services/stream_service.py`
3. `apps/server/src/services/decision_gateway.py`
4. `apps/server/src/services/prompt_service.py`
5. `apps/server/src/routes/stream.py`
6. `apps/server/src/domain/view_state/projector.py`
7. `apps/server/src/domain/view_state/scene_selector.py`
8. `apps/server/src/domain/view_state/prompt_selector.py`

Create or extend tests:

1. `apps/server/tests/test_runtime_module_runner.py`
2. `apps/server/tests/test_runtime_runner_kind.py`
3. `apps/server/tests/test_stream_module_idempotency.py`
4. `apps/server/tests/test_stream_ws_resume_replay_only.py`
5. `apps/server/tests/test_view_state_runtime_projection.py`
6. `apps/server/tests/test_prompt_module_continuation.py`

## 3-4. New Frontend File Map

Modify these files:

1. `apps/web/src/domain/store/gameStreamReducer.ts`
2. `apps/web/src/domain/selectors/streamSelectors.ts`
3. `apps/web/src/domain/selectors/promptSelectors.ts`
4. `apps/web/src/infra/ws/StreamClient.ts`
5. `apps/web/src/features/prompt/PromptOverlay.tsx` only if selector output shape changes
6. `apps/web/src/App.tsx` only if top-level selector wiring needs runtime projection

Create or extend tests:

1. `apps/web/src/domain/selectors/runtimeProjectionSelectors.spec.ts`
2. `apps/web/src/domain/selectors/streamSelectors.spec.ts`
3. `apps/web/src/domain/selectors/promptSelectors.spec.ts`
4. `apps/web/src/domain/store/gameStreamReducer.spec.ts`
5. `apps/web/src/infra/ws/StreamClient.spec.ts`
6. `apps/web/e2e/human_play_runtime.spec.ts`

## 3-5. M0 Baseline Lock

Purpose:

1. Freeze current fixed behavior before adding metadata.
2. Guard the three original issues: first turn, repeated draft, mid-turn card flip.

Implementation:

1. Extend `GPT/test_rule_fixes.py` with named tests for:
   - first player turn executes after draft setup
   - trick use with no deferred continuation reaches movement
   - card flip comes after `turn_end_snapshot` for last actor
2. Add engine audit helper that scans `VisEventStream` for:
   - `draft_pick` after `turn_start` before round boundary
   - `marker_flip` before all turn-end snapshots
   - `turn_start` without `turn_end_snapshot` unless followed by `game_end`
3. Add backend regression test in `apps/server/tests/test_runtime_service.py` that confirms committed debug logs are written only after `StreamService.publish` advances `seq`.

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_rule_fixes.py apps/server/tests/test_runtime_service.py -q
```

## 3-6. M1 Legacy Module Metadata

Purpose:

1. Add read-only `runtime_module` metadata to legacy engine events.
2. Make current order observable without changing gameplay.

Implementation:

1. In `GPT/runtime_modules/legacy_metadata.py`, implement `legacy_runtime_module_for_event(state, event_type, phase, player_id, payload) -> dict`.
2. Map current events to synthetic modules:
   - `round_start` -> `RoundStartModule`
   - `weather_reveal` -> `WeatherModule`
   - `draft_pick`, `final_character_choice` -> `DraftModule`
   - `round_order` -> `TurnSchedulerModule`
   - `turn_start` -> `TurnStartModule`
   - `mark_resolved` -> `PendingMarkResolutionModule` or `CharacterStartModule` depending on payload source
   - `trick_window_open`, `trick_window_closed` -> `TrickWindowModule`
   - `trick_used` -> `TrickSequenceFrame/TrickResolveModule`
   - `dice_roll` -> `DiceRollModule`
   - `player_move`, `action_move` -> `MapMoveModule`
   - `landing_resolved` -> `ArrivalTileModule`
   - `lap_reward_chosen` -> `LapRewardModule`
   - fortune events -> `FortuneResolveModule`
   - `turn_end_snapshot` -> `TurnEndSnapshotModule`
   - card flip event -> `RoundEndCardFlipModule`
3. In `GPT/engine.py::_emit_vis`, attach metadata when `runtime.module_metadata_v1` is enabled or when tests request it.
4. Keep event payloads additive. Do not change event order.
5. Add `idempotency_key` generation in metadata, but leave current stream dedupe behavior unchanged in this slice.

Tests:

1. `GPT/test_runtime_legacy_module_metadata.py::test_draft_events_are_round_frame_only`
2. `GPT/test_runtime_legacy_module_metadata.py::test_trick_used_has_sequence_frame_path`
3. `GPT/test_runtime_legacy_module_metadata.py::test_card_flip_metadata_is_round_end_module`
4. `GPT/test_runtime_legacy_module_metadata.py::test_legacy_metadata_does_not_change_event_order`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_runtime_legacy_module_metadata.py GPT/test_rule_fixes.py -q
```

## 3-7. M2 Backend Runtime Projection

Purpose:

1. Add canonical runtime stage projection.
2. Stop backend/frontend from guessing active stage from localized event text.

Implementation:

1. In `apps/server/src/domain/view_state/projector.py`, include `runtime` projection object.
2. Add a selector helper that consumes the latest checkpoint active module when available, otherwise latest event `runtime_module`.
3. Project:
   - `runner_kind`
   - `latest_module_path`
   - `round_stage`
   - `turn_stage`
   - `active_sequence`
   - `active_prompt_request_id`
   - `draft_active`
   - `trick_sequence_active`
   - `card_flip_legal`
4. In `apps/server/src/services/runtime_service.py`, persist runner kind and checkpoint schema version in runtime status.
5. In `apps/server/src/services/stream_service.py`, ensure `view_state.runtime` is included in `publish` and `project_message_for_viewer`.

Tests:

1. `apps/server/tests/test_view_state_runtime_projection.py::test_projects_draft_active_only_for_draft_module_or_prompt`
2. `apps/server/tests/test_view_state_runtime_projection.py::test_projects_trick_sequence_from_sequence_metadata`
3. `apps/server/tests/test_view_state_runtime_projection.py::test_card_flip_requires_round_end_module`
4. `apps/server/tests/test_view_state_runtime_projection.py::test_projection_prefers_checkpoint_active_module_over_old_event`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest apps/server/tests/test_view_state_runtime_projection.py apps/server/tests/test_stream_api.py -q
```

## 3-8. M3 Frontend Projection-First Selectors

Purpose:

1. Prevent stale replayed draft/trick/card-flip events from reopening UI.
2. Make frontend follow backend runtime projection.

Implementation:

1. Add runtime projection parsing helpers in `apps/web/src/domain/selectors/streamSelectors.ts`.
2. Update prompt selector closing logic so `view_state.runtime` closes stale draft/trick prompts when active module is no longer compatible.
3. Update card flip surfaces so they require `RoundEndCardFlipModule` metadata or projected card flip legality.
4. Update draft display logic so old `draft_pick` events are display history, not active draft state.
5. Keep legacy fallback only when no `view_state.runtime` exists.

Tests:

1. `runtimeProjectionSelectors.spec.ts::prefers_view_state_runtime_over_event_history`
2. `promptSelectors.spec.ts::replayed_draft_pick_cannot_reopen_prompt_after_turn_stage_projection`
3. `promptSelectors.spec.ts::trick_prompt_closes_when_runtime_leaves_trick_sequence`
4. `streamSelectors.spec.ts::card_flip_surface_requires_round_end_module`
5. `gameStreamReducer.spec.ts::older_replay_projection_does_not_override_newer_runtime_stage`

Acceptance:

```bash
npm --prefix apps/web test -- runtimeProjectionSelectors.spec.ts streamSelectors.spec.ts promptSelectors.spec.ts gameStreamReducer.spec.ts
npm --prefix apps/web run build
```

## 3-9. M4 Engine Contracts And Runner Skeleton

Purpose:

1. Introduce explicit contracts without changing active gameplay.
2. Make queue, journal, prompt, and modifier validation testable in isolation.

Implementation:

1. In `GPT/runtime_modules/contracts.py`, implement dataclasses from Part 2:
   - `GameRuntimeState`
   - `FrameState`
   - `ModuleRef`
   - `ModuleResult`
   - `QueueOp`
   - `Modifier`
   - `PromptContinuation`
   - `SimultaneousPromptBatchContinuation`
   - `DomainEvent`
2. In `GPT/runtime_modules/ids.py`, implement stable id builders for round/turn/sequence/simultaneous modules.
3. In `GPT/runtime_modules/queue.py`, implement `FrameQueueApi.apply(queue_ops)`.
4. In `GPT/runtime_modules/journal.py`, implement append-only module journal entries.
5. In `GPT/runtime_modules/modifiers.py`, implement registry add/query/consume/expire behavior.
6. In `GPT/runtime_modules/prompts.py`, implement prompt continuation creation and resume validation.
7. In `GPT/runtime_modules/runner.py`, implement `ModuleRunner.advance_one(context)`.
8. In `GPT/state.py`, add optional checkpoint fields:
   - `runtime_runner_kind`
   - `runtime_checkpoint_schema_version`
   - `runtime_frame_stack`
   - `runtime_module_journal`
   - `runtime_active_prompt`
   - `runtime_active_prompt_batch`
   - `runtime_modifier_registry`
9. Extend `GameState.to_checkpoint_payload` and `from_checkpoint_payload` to round-trip those fields.

Tests:

1. `test_runtime_module_contracts.py::test_draft_module_rejected_in_turn_frame`
2. `test_runtime_module_contracts.py::test_completed_frame_rejects_queue_insertion`
3. `test_runtime_module_contracts.py::test_duplicate_module_id_is_idempotent_only_with_same_key`
4. `test_runtime_module_contracts.py::test_prompt_resume_token_mismatch_rejected`
5. `test_runtime_module_contracts.py::test_modifier_single_use_consumed_once`
6. `test_runtime_module_contracts.py::test_simultaneous_frame_rejects_turn_only_module`
7. `test_runtime_module_contracts.py::test_prompt_batch_partial_response_does_not_advance_parent`
8. `test_runtime_module_contracts.py::test_prompt_batch_completes_after_all_required_responses`
9. `test_runtime_module_contracts.py::test_checkpoint_round_trips_runtime_state`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_runtime_module_contracts.py -q
```

## 3-10. M5 RoundFrame Modules

Purpose:

1. Execute round setup and scheduling as explicit modules behind `runtime.module_runner_round_v1`.
2. Keep turn execution legacy-compatible until M6.

Implementation:

1. In `GPT/runtime_modules/round_modules.py`, implement:
   - `RoundStartModule`
   - `WeatherModule`
   - `DraftModule`
   - `TurnSchedulerModule`
   - `PlayerTurnModule`
   - `RoundEndCardFlipModule`
   - `RoundCleanupAndNextRoundModule`
2. Move round reset logic from `_start_new_round` into `RoundStartModule` helper functions, leaving `_start_new_round` as legacy path.
3. Make `WeatherModule` call existing `_apply_round_weather` or extracted weather helper.
4. Make `DraftModule` call extracted draft helpers from `_run_draft`, preserving prompts.
5. Make `TurnSchedulerModule` append `PlayerTurnModule` refs and emit `round_order`.
6. In module-runner sessions, `GameEngine.run_next_transition` delegates to `ModuleRunner.advance_one`.
7. `PlayerTurnModule` initially delegates to legacy `_take_turn` and completes only when legacy pending turn completion is done; M6 replaces this.
8. `RoundEndCardFlipModule` asserts every player turn module is complete before calling marker/card flip helper.

Tests:

1. `test_runtime_round_modules.py::test_round_frame_order_weather_draft_scheduler_turns_flip_cleanup`
2. `test_runtime_round_modules.py::test_draft_module_idempotency_per_round`
3. `test_runtime_round_modules.py::test_first_player_turn_module_exists_after_scheduler`
4. `test_runtime_round_modules.py::test_round_end_card_flip_rejects_incomplete_player_turns`
5. `test_runtime_round_modules.py::test_module_runner_session_does_not_use_legacy_round_start`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_runtime_module_contracts.py GPT/test_runtime_round_modules.py GPT/test_rule_fixes.py -q
```

## 3-11. M6 TurnFrame And Core Sequence Modules

Purpose:

1. Replace legacy `_take_turn` control flow with explicit `TurnFrame`.
2. Convert trick flow into child `TrickSequenceFrame`.

Implementation:

1. In `GPT/runtime_modules/turn_modules.py`, implement:
   - `TurnStartModule`
   - `ScheduledStartActionsModule`
   - `PendingMarkResolutionModule`
   - `CharacterStartModule`
   - `ImmediateMarkerTransferModule`
   - `TargetJudicatorModule`
   - `TrickWindowModule`
   - `DiceRollModule`
   - `MovementResolveModule`
   - `MapMoveModule`
   - `ArrivalTileModule`
   - `LapRewardModule`
   - `FortuneResolveModule`
   - `TurnEndSnapshotModule`
2. In `GPT/runtime_modules/sequence_modules.py`, implement:
   - `TrickChoiceModule`
   - `TrickSkipModule`
   - `TrickResolveModule`
   - `TrickDiscardModule`
   - `TrickDeferredFollowupsModule`
   - `TrickVisibilitySyncModule`
   - `RollAndArriveSequenceFrame` builder
   - `PurchaseRentPaymentSequenceFrame` builder
3. Extract pure helpers from `_finish_turn_after_trick_phase`, `_resolve_move`, `_enqueue_standard_move_action`, `_apply_move_action`, `_resolve_landing`, `_apply_lap_reward`, and fortune resolution functions.
4. Convert legacy `pending_actions` generated by trick, mark, landing, and fortune into sequence modules for module sessions.
5. Keep `pending_actions` compatibility only inside legacy adapter tests.
6. Ensure skipped/dead actor paths route to `TurnEndSnapshotModule` or game-end terminal status.

Tests:

1. `test_runtime_turn_modules.py::test_turn_frame_default_order`
2. `test_runtime_turn_modules.py::test_skipped_turn_still_emits_turn_end_snapshot`
3. `test_runtime_turn_modules.py::test_dead_actor_during_mark_resolution_closes_turn_or_game`
4. `test_runtime_turn_modules.py::test_immediate_marker_transfer_affects_next_module`
5. `test_runtime_turn_modules.py::test_card_flip_not_reachable_while_turn_frame_running`
6. `test_runtime_sequence_modules.py::test_trick_used_without_deferred_work_resumes_to_dice`
7. `test_runtime_sequence_modules.py::test_trick_deferred_followup_completes_before_parent_resumes`
8. `test_runtime_sequence_modules.py::test_fortune_extra_roll_is_sequence_not_new_turn`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_runtime_turn_modules.py GPT/test_runtime_sequence_modules.py GPT/test_rule_fixes.py -q
```

## 3-12. M7 Prompt Continuation Migration

Purpose:

1. Make prompts true module suspension.
2. Remove ambient prompt replay heuristics from module sessions.

Implementation:

1. In engine `PromptApi`, create `PromptContinuation` for every human decision:
   - draft card
   - final character
   - hidden trick card
   - mark target
   - trick to use
   - movement
   - lap reward
   - purchase/coin placement
   - fortune/trick special choices
2. In engine `PromptApi`, create `SimultaneousPromptBatchContinuation` for synchronized multi-player decisions such as resupply.
3. In `apps/server/src/services/decision_gateway.py`, include `resume_token`, `frame_id`, `module_id`, `module_type`, and optional `batch_id` in prompt payload.
4. In `apps/server/src/services/prompt_service.py`, store continuation fields and reject decisions missing required fields for module-runner sessions.
5. For batch prompts, accept partial participant responses, persist `missing_player_ids`, and wake gameplay advancement only when the batch is complete or a default policy closes it.
6. In `runtime_service.py`, wake module runner only after decision command is accepted.
7. Keep `_prompt_sequence_seed_for_transition` only for legacy runner.
8. Add backend `decision_ack` rejection codes:
   - `STALE_PROMPT`
   - `TOKEN_MISMATCH`
   - `MODULE_MISMATCH`
   - `CHOICE_NOT_LEGAL`
   - `PLAYER_NOT_OWNER`
   - `BATCH_NOT_ACTIVE`
   - `BATCH_PARTICIPANT_MISMATCH`

Tests:

1. `GPT/test_runtime_prompt_continuation.py::test_prompt_suspends_current_module`
2. `GPT/test_runtime_prompt_continuation.py::test_valid_decision_resumes_same_module`
3. `GPT/test_runtime_prompt_continuation.py::test_stale_resume_token_rejected`
4. `apps/server/tests/test_prompt_module_continuation.py::test_prompt_payload_contains_module_continuation`
5. `apps/server/tests/test_prompt_module_continuation.py::test_duplicate_decision_ack_rejected_without_runtime_wake`
6. `apps/server/tests/test_prompt_module_continuation.py::test_runtime_status_waiting_input_mirrors_checkpoint_active_prompt`
7. `apps/server/tests/test_prompt_module_continuation.py::test_batch_prompt_payload_contains_batch_and_module_ids`
8. `apps/server/tests/test_prompt_module_continuation.py::test_partial_batch_response_keeps_runtime_waiting`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_runtime_prompt_continuation.py apps/server/tests/test_prompt_module_continuation.py apps/server/tests/test_runtime_service.py -q
```

## 3-12A. M7A Simultaneous Resolution And Resupply

Purpose:

1. Add the special synchronized processing path for rules that require multiple players to respond at the same time.
2. Move resupply/burden exchange out of sequential turn prompts.
3. Keep the module runtime free of untyped pending actions while still supporting all-player prompt batches.

Implementation:

1. In `GPT/runtime_modules/simultaneous.py`, implement:
   - `SimultaneousProcessingModule`
   - `SimultaneousPromptBatchModule`
   - `ResupplyModule`
   - `SimultaneousCommitModule`
   - `CompleteSimultaneousResolutionModule`
2. In `FrameQueueApi`, allow `SimultaneousProcessingModule` to spawn only `SimultaneousResolutionFrame`.
3. Add `PromptApi.create_batch(...)` and `PromptApi.record_batch_response(...)` for `SimultaneousPromptBatchContinuation`.
4. When the end value matches the configured multiple and the rule requires burden/resupply processing, enqueue `SimultaneousProcessingModule` with `trigger_reason=end_value_multiple_resupply`.
5. `ResupplyModule` captures participant ids and each player's eligible burden/resupply options before opening prompts.
6. AI seats use the same legality validator as human decisions and may auto-fill deterministic responses.
7. Human responses are accepted independently, but no burden removal/payment/draw mutation occurs until all required responses/defaults are present.
8. The commit step applies choices once in deterministic player-id order for logs while preserving simultaneous rule semantics.
9. Backend mirrors `runtime_active_prompt_batch` into PromptService and `view_state.runtime`.
10. Frontend prompt selectors show the local player's batch prompt, then a waiting state after that player responds while other participants are still missing.

Tests:

1. `GPT/test_runtime_simultaneous_modules.py::test_resupply_batch_waits_for_all_required_players`
2. `GPT/test_runtime_simultaneous_modules.py::test_partial_resupply_response_does_not_mutate_burdens`
3. `GPT/test_runtime_simultaneous_modules.py::test_resupply_commit_uses_start_snapshot`
4. `GPT/test_runtime_simultaneous_modules.py::test_stale_resupply_batch_response_rejected`
5. `apps/server/tests/test_prompt_module_continuation.py::test_batch_prompt_payload_contains_batch_and_module_ids`
6. `apps/server/tests/test_runtime_service.py::test_partial_batch_response_returns_waiting_input`
7. `apps/web/src/domain/selectors/promptSelectors.spec.ts::resupply_batch_prompt_uses_active_batch_projection`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_runtime_simultaneous_modules.py GPT/test_runtime_prompt_continuation.py apps/server/tests/test_prompt_module_continuation.py apps/server/tests/test_runtime_service.py -q
npm --prefix apps/web test -- promptSelectors.spec.ts streamSelectors.spec.ts
```

## 3-13. M8 Stream And WebSocket Hardening

Purpose:

1. Make stream dedupe module-aware.
2. Guarantee WebSocket replay cannot advance gameplay.

Implementation:

1. In `apps/server/src/services/stream_service.py`, add idempotency-key index per session.
2. Prefer top-level `payload.idempotency_key`, then `payload.runtime_module.idempotency_key`.
3. Return existing message for duplicate key.
4. Preserve current duplicate request and round setup dedupe as legacy fallback while M1-M3 events still exist.
5. In `apps/server/src/routes/stream.py`, assert `resume` calls only `replay_from`/projection paths.
6. Add heartbeat payload fields for runner kind and active module.
7. In frontend `StreamClient.ts`, keep `resume` as transport message only; no decision or runtime command is sent during reconnect.

Tests:

1. `apps/server/tests/test_stream_module_idempotency.py::test_same_idempotency_key_returns_existing_message`
2. `apps/server/tests/test_stream_module_idempotency.py::test_same_event_type_different_module_id_publishes_twice`
3. `apps/server/tests/test_stream_ws_resume_replay_only.py::test_resume_does_not_call_runtime_transition`
4. `apps/server/tests/test_stream_ws_resume_replay_only.py::test_resume_does_not_duplicate_active_prompt`
5. `apps/web/src/infra/ws/StreamClient.spec.ts::sends_resume_without_decision_payload`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest apps/server/tests/test_stream_module_idempotency.py apps/server/tests/test_stream_ws_resume_replay_only.py -q
npm --prefix apps/web test -- StreamClient.spec.ts gameStreamReducer.spec.ts
```

## 3-14. M9 Deterministic Parity Validation

Purpose:

1. Prove module runner preserves gameplay outcomes.
2. Find semantic drift before default cutover.

Implementation:

1. Add `GPT/test_runtime_module_parity.py`.
2. Build deterministic AI fixtures for 10 seeds and at least these scenarios:
   - no human prompts
   - draft choices with marker direction changes
   - trick used and skipped
   - trick with deferred follow-up
   - mark success and miss
   - fortune extra movement
   - purchase/rent/payment/bankruptcy
   - doctrine/researcher marker ownership
   - round-end card flip
3. Run the same seed once with legacy runner and once with module runner.
4. Compare:
   - winners/end reason
   - final player cash/position/tiles/score
   - active card faces
   - marker owner/direction
   - event type order at rule-critical boundaries
5. Allow metadata differences and known formatting differences only through explicit comparator fields.

Tests:

1. `test_runtime_module_parity.py::test_module_runner_matches_legacy_for_seed_matrix`
2. `test_runtime_module_parity.py::test_module_runner_preserves_rule_critical_event_order`

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_runtime_module_parity.py -q
```

## 3-15. M10 Cutover And Legacy Cleanup

Purpose:

1. Make module runner default for new sessions.
2. Remove old implicit scheduling ownership after parity is stable.

Implementation:

1. Change session runtime default to `runner_kind=module` when all module flags are enabled.
2. Keep legacy runner available for old checkpoints until they finish or are explicitly migrated through a supported path.
3. Remove module-session dependencies on:
   - `state.pending_actions` as order owner
   - `state.pending_turn_completion` as turn owner
   - prompt replay sequence heuristics
4. Keep `ActionEnvelope` only for legacy compatibility or convert it to a module adapter type.
5. Remove frontend fallback branches that can override `view_state.runtime`; keep display-only fallbacks.
6. Update docs:
   - `docs/backend/turn-structure-and-order-source-map.md`
   - `docs/engineering/1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE.md`
   - `packages/runtime-contracts/ws/README.md`

Tests:

1. Full engine rule suite.
2. Full backend runtime/stream suite.
3. Full frontend selector/build suite.
4. Browser runtime smoke for human prompt session.

Acceptance:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT apps/server/tests -q
npm --prefix apps/web test
npm --prefix apps/web run build
npm --prefix apps/web run e2e:human-runtime
```

## 3-16. Backend Implementation Details

`runtime_service.py` changes:

1. Load `runner_kind` from session resolved runtime config.
2. Persist `runner_kind` and checkpoint schema in runtime status.
3. On hydrate, reject mismatched runner kind.
4. For legacy runner, keep current `_prepare_state_for_transition_replay`.
5. For module runner, call `engine.advance_one_module_transition(state, command)`.
6. Mirror `state.runtime_active_prompt` into `PromptService`.
7. Return `waiting_input` based on checkpoint active prompt, not only prompt service query.

`stream_service.py` changes:

1. Add idempotency lookup before assigning a new `seq`.
2. Store committed idempotency key with the stream message.
3. Keep projection call after duplicate check for new messages.
4. For duplicate returns, do not notify subscribers again.

`stream.py` changes:

1. Keep `resume` path limited to replay.
2. Add test hook/mocking seam proving runtime service is not called by resume.
3. Include active module diagnostics in heartbeat.

## 3-17. Frontend Implementation Details

Reducer:

1. Preserve current `seq` ordering.
2. Do not let heartbeat-only messages suppress same-seq projected events.
3. Keep latest state-bearing projection visible when replay gaps exist.
4. Add runtime projection to the set of state-bearing payloads.

Selectors:

1. Parse `view_state.runtime` once in a helper.
2. Use helper for draft prompt surface, trick hand/window, card flip display, scene headline, and active turn summary.
3. Make old event-based closures weaker than projected runtime closure.
4. Keep legacy event fallback only when projection is absent.

UI:

1. Do not create new text-heavy status panels.
2. Existing prompts render from selector models.
3. Animation remains event-history driven but cannot alter active prompt/stage state.

## 3-18. Rule-Specific Implementation Notes

Marker and card flip:

1. `ImmediateMarkerTransferModule` updates owner/direction immediately.
2. It emits `marker_transferred` with immediate module metadata.
3. `RoundEndCardFlipModule` is the only card face flip source.
4. Frontend card flip UI requires round-end module metadata.

Trick:

1. Trick sequence owns trick prompt, resolution, discard, deferred follow-ups, and visibility sync.
2. Parent turn frame resumes at dice after trick sequence completion.
3. A trick that queues extra actions creates typed modules, not untyped pending actions.

Draft:

1. `DraftModule` owns draft prompts and final character prompts.
2. `TurnSchedulerModule` alone creates player turn modules.
3. Replay of draft events never runs draft logic.

Fortune:

1. Fortune extra movement creates `RollAndArriveSequenceFrame`.
2. That sequence does not emit a new `turn_start`.
3. Arrival effects from fortune movement use the same arrival/purchase/rent modules.

## 3-19. Migration Stop Conditions

Stop and fix before continuing if any of these occurs:

1. A module-runner session writes or consumes legacy `pending_actions` as the next work owner.
2. A prompt payload lacks frame/module continuation in a module session.
3. A simultaneous prompt response mutates gameplay before the batch is complete.
4. Resupply runs as sequential player-turn prompts instead of a `SimultaneousResolutionFrame`.
5. `RoundEndCardFlipModule` can run while any player turn module or simultaneous frame is incomplete.
6. WebSocket `resume` calls runtime transition code.
7. Frontend shows draft, card flip, or resupply UI from an old replayed event while projection says turn/dice/movement or batch closed.
8. Legacy and module parity diverges on final state for deterministic no-human seeds.

## 3-20. Final Verification Bundle

Run this before claiming migration complete:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest GPT/test_rule_fixes.py GPT/test_runtime_module_contracts.py GPT/test_runtime_legacy_module_metadata.py GPT/test_runtime_round_modules.py GPT/test_runtime_turn_modules.py GPT/test_runtime_sequence_modules.py GPT/test_runtime_prompt_continuation.py GPT/test_runtime_simultaneous_modules.py GPT/test_runtime_module_parity.py -q
PYTHONPATH=$PWD .venv/bin/python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_runtime_module_runner.py apps/server/tests/test_runtime_runner_kind.py apps/server/tests/test_stream_module_idempotency.py apps/server/tests/test_stream_ws_resume_replay_only.py apps/server/tests/test_view_state_runtime_projection.py apps/server/tests/test_prompt_module_continuation.py -q
npm --prefix apps/web test
npm --prefix apps/web run build
npm --prefix apps/web run e2e:human-runtime
```

Documentation verification:

```bash
rg -n "T[B]D|T[O]DO|place[ ]holder|fill[ ]in" docs/superpowers/plans/2026-05-02-modular-game-runtime-migration-part-*.md
```

Expected documentation result: no matches.
