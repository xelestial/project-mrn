# Turn Structure & Order Source Map

Status: `ACTIVE`
Updated: `2026-05-04`
Scope: module-runner gameplay order from engine through backend/Redis/WebSocket/frontend

## Purpose

This document fixes the canonical turn order used by the migrated module runtime. The production module-runner contract is the structured frame stack below; direct non-module helpers are not allowed to own production gameplay order.

## 1. Top-Level Runtime

Canonical execution is `ModuleRunner.advance_engine(engine, state, decision_resume=None)`.

1. Reject orphan turn-completion checkpoints. `pending_turn_completion` is valid only while being consumed inside the current transition and must be attached to `TurnEndSnapshotModule` before the checkpoint is persisted.
2. Promote queued native follow-up work:
   - `resolve_supply_threshold` becomes a `SimultaneousResolutionFrame` / `ResupplyModule`.
   - Other catalogued action envelopes become an `ActionSequenceFrame` with explicit native modules.
3. Advance the deepest active frame first:
   - `SimultaneousResolutionFrame`
   - `SequenceFrame`
   - `TurnFrame`
   - `RoundFrame`
4. Persist the new `runtime_frame_stack`, module journal, active prompt or prompt batch, and stream payload metadata.

Backend and Redis do not decide game rules. They validate frame/module placement, idempotency, prompt continuation identity, and publish order.

## 2. RoundFrame Structure

`RoundFrame` owns work that happens once per round.

1. `RoundStartModule`: initializes round stage.
2. `WeatherModule`: reveals/applies weather and moves used weather as engine state.
3. `DraftModule`: owns draft prompt/final character decisions.
4. `TurnSchedulerModule`: materializes `PlayerTurnModule` entries in drafted turn order.
5. `PlayerTurnModule`: creates one child `TurnFrame` for the player and remains suspended until that child is completed.
6. `RoundEndCardFlipModule`: runs only after every `PlayerTurnModule` is completed/skipped and no child frame is active.
7. `RoundCleanupAndNextRoundModule`: cleans round-local state and prepares the next round.

Card/marker flip is round-owned. It is invalid in an active turn or child sequence context.

## 3. TurnFrame Structure

`PlayerTurnModule` creates a `TurnFrame`; it does not call `_take_turn`.

1. `TurnStartModule`: captures `finisher_before` and `disruption_before`, increments turns taken, and handles skipped turns.
2. `ScheduledStartActionsModule`: materializes scheduled turn-start actions as child sequence frames.
3. `PendingMarkResolutionModule`: resolves marks that apply immediately at the start of this player's turn.
4. `CharacterStartModule`: applies/seeds character-start effects and modifiers.
5. `TargetJudicatorModule`: validates mark targets and inserts `ImmediateMarkerTransferModule` when the card's rules require immediate transfer.
6. `ImmediateMarkerTransferModule`: executes immediate marker transfer inserted by the target adjudicator.
7. `TrickWindowModule`: opens the trick window once and creates a child `TrickSequenceFrame`.
8. `DiceRollModule`: consumes dice modifiers, calls the engine movement resolver, and captures `pending_turn_completion` into the existing turn-owned `TurnEndSnapshotModule`.
9. `MovementResolveModule`, `MapMoveModule`, `ArrivalTileModule`, `LapRewardModule`, `FortuneResolveModule`: native turn boundary slots. `LapRewardModule` owns lap-reward prompt/mutation after movement detects lap traversal and before arrival/post-arrival work continues; recovery resumes from `lap_reward:await_choice`. Follow-up actions may be executed as child `SequenceFrame`s when queued.
10. `TurnEndSnapshotModule`: emits `turn_end_snapshot`, applies control-finisher bookkeeping, checks game end, advances `turn_index`, and completes the child `TurnFrame` plus parent `PlayerTurnModule`.

The important ownership rule: turn completion is not a sequence. A sequence-owned `TurnEndSnapshotModule` or orphan `pending_turn_completion` checkpoint is rejected.

## 4. SequenceFrame Structure

`SequenceFrame` is nested work created by an active module. It never restarts the parent turn body.

- Trick sequence: `TrickChoiceModule`, `TrickSkipModule`, `TrickResolveModule`, `TrickDiscardModule`, `TrickDeferredFollowupsModule`, `TrickVisibilitySyncModule`.
- Native action sequence: `PendingMarkResolutionModule`, `MapMoveModule`, `ArrivalTileModule`, `RentPaymentModule`, `PurchaseDecisionModule`, `PurchaseCommitModule`, `UnownedPostPurchaseModule`, `ScoreTokenPlacementPromptModule`, `ScoreTokenPlacementCommitModule`, `LandingPostEffectsModule`, `TrickTileRentModifierModule`, `FortuneResolveModule`.
- Forbidden shapes: action payloads without native module handlers and `TurnEndSnapshotModule` in a sequence frame.

Examples:

- 잔꾀 follow-up stays inside the trick sequence. `TrickResolveModule` stores `followup_choice_module_id` so retry reuses the inserted `TrickChoiceModule`.
- 운수 follow-up movement stays in `FortuneResolveModule -> MapMoveModule -> ArrivalTileModule` and does not create a new turn.
- Rent and purchase follow-ups are native sequence modules, so repeated backend wakeups cannot re-run arrival/movement by inference.

## 5. SimultaneousResolutionFrame Structure

Simultaneous work handles prompts where multiple players respond to the same batch.

1. `ResupplyModule` initializes eligible burden-card snapshots.
2. `SimultaneousPromptBatchContinuation` stores one `batch_id`, per-player prompt identity, legal choices, and missing-player set.
3. Responses are committed only when all required players respond or policy defaults fill non-human/timeout decisions.
4. Completed responses update the stored processed snapshot before the module advances.

`resolve_supply_threshold` is never valid inside an action `SequenceFrame`.

## 6. Backend/Redis/WebSocket Contracts

Backend and Redis persist the engine checkpoint; they do not synthesize next gameplay.

- Runtime service resumes exactly one engine command against the saved checkpoint and stores the resulting checkpoint atomically.
- Redis prompt state is authoritative for `request_id`, `resume_token`, `frame_id`, `module_id`, `module_type`, `module_cursor`, and `batch_id`.
- WebSocket publishes the runtime module projection attached to each prompt/event. The semantic guard rejects impossible placements before they reach clients.
- Backend `view_state.player_cards`, `view_state.active_by_card`, and `view_state.turn_stage` are frontend-consumable projections. If a prompt event arrives late or replay skips raw history, the frontend still renders the current card strip and prompt-active beat from those fields.
- Frontend request IDs are not gameplay authority. The frontend preserves backend-issued continuation fields and uses a local ledger only to suppress duplicate sends.

## 7. Logging Map

Engine visual events are emitted by the module that owns the boundary.

- Round: `round_start`, `weather_reveal`, `draft_pick`, `final_character_choice`, `round_order`, `marker_flip`, `active_flip`.
- Turn: `turn_start`, `trick_window_open`, `dice_roll`, `turn_end_snapshot`.
- Sequence: `trick_used`, `player_move`, `landing_resolved`, `tile_purchased`, `rent_paid`, fortune follow-up events.
- Simultaneous: `burden_exchange` prompt batch and final `trick_supply` runtime log.

When diagnosing logs, compare each event's `runtime_module.frame_type/module_type` with the lists above. A mismatch is a structural bug, not a frontend display issue.
