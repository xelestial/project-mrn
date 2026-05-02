# Modular Game Runtime Bug#1

Status: Drafted  
Date: 2026-05-02  
Scope: Existing and expected failure modes for engine, backend runtime, WebSocket stream, and frontend rendering.

## 1. Root Cause Summary

The current runtime is structurally vulnerable because next-step control is split across:

- `state.pending_actions`
- `state.pending_turn_completion`
- `state.current_round_order`
- `state.turn_index`
- prompt sequence state
- stream replay/dedupe behavior
- frontend selectors that infer stage from event history

That means "what should happen next" is not always a single explicit object in the checkpoint. Draft#1 addresses this by making the next work item an explicit module in a persisted frame queue.

## 2. Bug Set

### BUG-001: First Turn Does Not Execute After Round Setup

Observed/suspected symptom:

- Round setup events appear.
- Draft or prompt events appear.
- The first scheduled player turn is missing, delayed, or displaced.

Likely structural causes:

- Round setup and first turn are separated by implicit `current_round_order` and `turn_index` checks.
- Prompt/replay identity can make setup appear duplicated or resumed at the wrong boundary.
- No persisted `RoundFrame` says: "Draft completed; next module is PlayerTurnModule(Px)."

Draft#1 guard:

- `TurnSchedulerModule` appends concrete `PlayerTurnModule` entries.
- The checkpoint stores the next module path.
- `DraftModule` cannot complete without producing turn schedule.

Required tests:

- New session advances through `RoundStartModule -> WeatherModule -> DraftModule -> TurnSchedulerModule -> first PlayerTurnModule`.
- Hydrating immediately after draft resumes first player turn, not draft.

### BUG-002: Draft Runs Multiple Times Mid-Turn

Observed/suspected symptom:

- Draft events recur after a turn has already begun.
- Frontend shows draft-like state while turn execution should be active.

Likely structural causes:

- Round setup replay and runtime transition replay are not represented as completed modules.
- Duplicate visual events can be logged/published without a stable module idempotency key.
- Frontend may treat latest prompt/projection as a live draft if prompt closure metadata is stale.

Draft#1 guard:

- `DraftModule` is legal only in `RoundFrame`.
- It has stable idempotency key `round:{n}:draft`.
- Backend stream dedupes by idempotency key.
- Frontend draft UI uses `view_state.round_stage` and prompt continuation status, not merely latest `draft_pick` text.

Required tests:

- Replay of `draft_pick` does not reopen draft prompt.
- A `DraftModule` cannot be inserted into `TurnFrame`.

### BUG-003: Card Flip Happens Mid-Turn

Observed/suspected symptom:

- Card flip/marker flip event appears before the current player's turn has fully ended.
- This can look like "턴 중간 카드 뒤집기."

Likely structural causes:

- Turn completion is tracked by a flag rather than a child frame boundary.
- Trick or deferred action can return control to the top-level dispatcher before the turn's final snapshot is complete.
- Round-ending logic can run after `_take_turn` returns if the engine believes there are no pending turn actions.

Draft#1 guard:

- `RoundEndCardFlipModule` is appended after all `PlayerTurnModule`s.
- `PlayerTurnModule` completes only after its child `TurnFrame` completes.
- `TurnFrame` completes only after `TurnEndSnapshotModule`.

Required tests:

- If trick spawns deferred work, card flip remains impossible until the turn frame completes.
- Card flip event's `module_type` must be `RoundEndCardFlipModule`.

### BUG-004: Immediate Marker Transfer Is Confused With Round-End Card Flip

Observed/suspected symptom:

- Doctrine/researcher marker transfer is treated like round-end marker/card processing.
- "Has marker" effects start too late or too early.

Likely structural causes:

- Marker movement, marker management, and marker/card flip events share similar naming and phases.
- Current flow does not expose an explicit `ImmediateMarkerTransferModule`.

Draft#1 guard:

- Doctrine/researcher marker transfer occurs inside `CharacterStartModule` via `ImmediateMarkerTransferModule`.
- New marker owner is updated immediately before later turn modules run.
- Card flip remains isolated to `RoundEndCardFlipModule`.

Required tests:

- After immediate marker transfer, the next module's "has marker" condition sees the new owner.
- Immediate marker transfer never emits card flip.

### BUG-005: Trick Sequence Has No Structural Boundary

Observed/suspected symptom:

- Trick use may skip movement.
- Deferred trick work may make the runtime think the turn is done.
- Logs cannot distinguish "inside trick" from "after trick."

Likely structural causes:

- Trick flow is represented by function return value and global pending actions.
- The return value can conflate "a trick was used" with "the rest of the turn is deferred."

Draft#1 guard:

- `TrickWindowModule` spawns `TrickSequenceFrame`.
- Parent `TurnFrame` is suspended while trick child frame runs.
- After trick child completion, parent resumes at the next module.

Required tests:

- Trick used with no deferred follow-up continues to dice/movement.
- Trick used with deferred follow-up resumes parent after child sequence completion.

### BUG-006: Prompt Resume Can Target the Wrong Continuation

Observed/suspected symptom:

- A human decision is accepted but the next transition advances the wrong phase.
- Reconnect/retry sends a stale decision that affects a later prompt.

Likely structural causes:

- Prompt identity is not tied tightly enough to `frame_id` and `module_id`.
- Backend prompt service stores request identity, but the engine resume point is still represented by ambient state.

Draft#1 guard:

- Every prompt stores `resume_token`, `frame_id`, `module_id`, and `module_type`.
- Engine resumes only the suspended module matching the token.
- Stale decisions are acknowledged as rejected and do not wake the runtime.

Required tests:

- Duplicate decision for an already-resolved prompt is rejected.
- Decision with valid request id but stale resume token is rejected.

### BUG-007: Global Pending Actions Cross Round/Turn Boundaries

Observed/suspected symptom:

- A follow-up action runs after the turn or round boundary that created it.
- A queued action changes the wrong actor or stale phase.

Likely structural causes:

- `pending_actions` is global and untyped by frame ownership.
- Action order is based on list position, not parent frame semantics.

Draft#1 guard:

- Follow-ups are inserted into a specific frame or child sequence.
- `QueueOp` records target frame id.
- Runner rejects queue operations targeting completed frames.

Required tests:

- Arrival follow-up cannot run after `TurnFrame` completion.
- Round-end module cannot run while a child sequence frame is active.

### BUG-008: Modifiers Do Not Have Clear Scope or Propagation

Observed/suspected symptom:

- Dice/movement/tile/lap effects leak into later modules or fail to reach child modules.
- Pabal/guesthouse-style effects need manual special cases.

Likely structural causes:

- Modifiers are stored as ad hoc player/state fields.
- Propagation is implicit in each function.

Draft#1 guard:

- `ModifierRegistry` defines target module type, scope, priority, propagation, and expiry.
- Modules consume applicable modifiers through the context.

Required tests:

- Single-use modifier is consumed once.
- Movement modifier propagates to arrival/lap only when declared.

### BUG-009: Stream Dedupe Can Suppress or Duplicate the Wrong Event

Observed/suspected symptom:

- Backend debug log shows duplicates.
- Frontend receives duplicate-looking draft/setup events.
- Valid repeated domain events may be suppressed by broad heuristics.

Likely structural causes:

- Stream dedupe is heuristic rather than module idempotency based.
- Debug logging can observe attempted publish rather than committed stream sequence.

Draft#1 guard:

- Every domain event has stable `idempotency_key`.
- `StreamService.publish` dedupes against idempotency key.
- Debug logging records only committed new sequence numbers.

Required tests:

- Same idempotency key is published once.
- Two valid repeated events with different module ids are both published.

### BUG-010: Frontend Infers Runtime Stage From Event History

Observed/suspected symptom:

- UI displays draft/flip/trick state that is no longer active.
- Replayed messages change visible phase incorrectly.

Likely structural causes:

- Selectors scan latest events and fall back to text or raw event type.
- There is no canonical `active_sequence` or `module_path` projection.

Draft#1 guard:

- Backend projects `round_stage`, `turn_stage`, and `active_sequence`.
- Frontend uses projected module path first.
- Event text is presentation only.

Required tests:

- Replayed older draft event cannot override newer `view_state.turn_stage`.
- Card flip UI requires `module_type=RoundEndCardFlipModule`.

### BUG-011: WebSocket Resume Interleaves Replay and Live Events

Observed/suspected symptom:

- Client sees out-of-order apparent stages after reconnect.
- Live event arrives while replay is filling gaps.

Likely structural causes:

- Replay and live subscriber stream are both active.
- Frontend reducer has to fast-forward using projected messages when gaps exist.

Draft#1 guard:

- Reducer keeps latest projection and module path.
- Replay messages and live messages share seq ordering and idempotency keys.
- Heartbeat exposes latest module path to help diagnose stream state.

Required tests:

- Out-of-order replay/live delivery converges to latest view state.
- Resume does not produce duplicate active prompt.

### BUG-012: Backend Runtime Status Lags Prompt State

Observed/suspected symptom:

- Runtime says running while prompt is pending.
- Watchdog or recovery starts a transition while waiting input.

Likely structural causes:

- Prompt pending state and engine suspended module are stored separately.
- Runtime loop exits on prompt service state, not on frame suspension state.

Draft#1 guard:

- Engine checkpoint owns `active_prompt`.
- Backend runtime status mirrors checkpoint suspension.
- Prompt service is an index over the active prompt, not the source of truth.

Required tests:

- When engine returns prompt suspension, checkpoint and prompt service agree.
- Recovery from checkpoint restores `waiting_input` without advancing.

### BUG-013: End-of-Turn Snapshot Can Be Missing on Exceptional Paths

Observed/suspected symptom:

- `turn_start` has no matching `turn_end_snapshot`.
- Frontend remains in an active turn after actor dies or skips.

Likely structural causes:

- Some early returns bypass the common turn-end path.
- Death during trick/payment can exit before snapshot.

Draft#1 guard:

- `TurnFrame` has explicit `TurnEndSnapshotModule`.
- Exceptional modules insert or route to `TurnEndSnapshotModule` unless the game has ended.

Required tests:

- Actor death during trick still produces turn closure event or explicit game-end event.
- Skipped turn passes through the same close path.

### BUG-014: Backend Projection Recomputes From History Without Frame Semantics

Observed/suspected symptom:

- Projection chooses a plausible but wrong active stage.
- Long sessions make projection slower and harder to reason about.

Likely structural causes:

- Selectors derive state from raw event history.
- Events lack explicit frame/module causality.

Draft#1 guard:

- Projection reads module metadata and checkpoint-derived active module state.
- Incremental projection can be added later because causality is explicit.

Required tests:

- Projection picks active sequence from module metadata even if event names repeat.
- Repeated event types in different modules project differently.

### BUG-015: Mixed Old/New Runtime During Migration Creates Two Sources of Truth

Expected migration risk:

- Legacy `pending_actions` and new module queue both try to schedule work.
- Some events have module metadata and some do not.

Draft#1 guard:

- Migration starts with read-only synthetic module metadata.
- New module runner runs behind one runtime flag.
- Compatibility adapter maps legacy pending actions into module-shaped events without allowing both runners to execute gameplay in one session.

Required tests:

- A session is either legacy-runner or module-runner from start to finish.
- Mixed metadata does not change gameplay behavior.

## 3. Highest-Risk Areas

1. Trick and deferred actions: they currently touch turn continuation, pending actions, visibility sync, and prompt decisions.
2. Prompt continuation: it crosses engine/backend/WebSocket/frontend.
3. Marker transfer vs card flip: names are similar but timing is different.
4. Migration: half-converted queue ownership would be worse than the current code.

## 4. Minimum Safety Test Suite

The first implementation slice must include these tests before broad porting:

- First turn executes after draft.
- Draft cannot run inside a turn frame.
- Trick with no deferred action continues to movement.
- Trick with deferred action returns to parent turn after child sequence.
- Immediate marker transfer activates "has marker" effects before next turn module.
- Card flip cannot occur before all player turn frames finish.
- Prompt resume token mismatch is rejected.
- WebSocket resume does not advance engine.
- Frontend replayed draft cannot reopen draft UI after turn stage projection exists.
