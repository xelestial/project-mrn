# Modular Game Runtime Result#1

Status: Review recorded  
Date: 2026-05-02  
Reviewed inputs:

- `docs/superpowers/plans/2026-05-02-modular-game-runtime-draft-1.md`
- `docs/superpowers/plans/2026-05-02-modular-game-runtime-bug-1.md`

## 1. Review Question

Is Draft#1 structurally safe against the existing and expected bug set in Bug#1?

Short answer:

Draft#1 is structurally safe against the known first-turn, repeated-draft, mid-turn card-flip, trick-continuation, marker-transfer, prompt-resume, and frontend replay-display classes if implemented with the listed non-negotiable invariants. It is not automatically safe if the migration allows legacy pending flags and new module queues to both own gameplay order.

## 2. Safety Criteria

### CR-001: Next Work Is Explicit

Requirement:

- At any checkpoint, the next engine work item must be visible as `frame_stack[-1].module_queue[0]` or as an active suspended prompt.

Draft#1 result:

- Pass.

Reason:

- `RoundFrame`, `TurnFrame`, and `SequenceFrame` make next work explicit.
- This removes hidden inference from `pending_actions`, `pending_turn_completion`, and `turn_index`.

Residual risk:

- During migration, synthetic module metadata must not pretend safety while legacy flags still decide order.

### CR-002: Round Boundary Is Structurally Separated From Turn Internals

Requirement:

- Round-end card flip must be unreachable until all turn frames complete.

Draft#1 result:

- Pass.

Reason:

- `RoundEndCardFlipModule` is appended after every `PlayerTurnModule`.
- `PlayerTurnModule` cannot complete until child `TurnFrame` completes.
- `TurnFrame` cannot complete until `TurnEndSnapshotModule` completes.

Bug coverage:

- BUG-003
- BUG-004
- BUG-007
- BUG-013

### CR-003: Immediate Marker Transfer Is Not Card Flip

Requirement:

- Doctrine/researcher marker transfer happens immediately during the actor's turn.
- "Has marker" effects observe the new owner immediately.
- Card flip remains round-end-only.

Draft#1 result:

- Pass.

Reason:

- `ImmediateMarkerTransferModule` lives under `CharacterStartModule`.
- `RoundEndCardFlipModule` is the only legal card flip source.

Bug coverage:

- BUG-004

Required implementation check:

- Add a test where marker ownership changes inside character start, then the very next module checks "has marker."

### CR-004: Trick Is a Child Sequence

Requirement:

- Trick resolution must not be able to consume or skip the rest of the turn by ambiguous return value.

Draft#1 result:

- Pass.

Reason:

- `TrickWindowModule` spawns `TrickSequenceFrame`.
- The parent `TurnFrame` resumes after the child frame completes.
- Deferred trick work is frame-local or inserted through explicit queue operations.

Bug coverage:

- BUG-003
- BUG-005
- BUG-007

Residual risk:

- Existing trick effect handlers may still enqueue global actions until ported. The compatibility adapter must force every legacy trick follow-up into a child frame or an explicit parent-frame insertion.

### CR-005: Draft Is Round-Only and Idempotent

Requirement:

- Draft must run once per round and cannot appear mid-turn.

Draft#1 result:

- Pass.

Reason:

- `DraftModule` is only legal in `RoundFrame`.
- `DraftModule` uses stable idempotency key `round:{n}:draft`.
- Frontend draft UI depends on active prompt/module projection rather than old draft events.

Bug coverage:

- BUG-001
- BUG-002
- BUG-010
- BUG-011

### CR-006: Prompt Continuation Is Exact

Requirement:

- Decisions resume exactly the suspended module.
- Stale decisions are harmless.

Draft#1 result:

- Pass.

Reason:

- Prompt continuation contains `request_id`, `resume_token`, `frame_id`, and `module_id`.
- Backend validates before waking runtime.
- Engine refuses token/module mismatch.

Bug coverage:

- BUG-006
- BUG-012

Residual risk:

- All prompt-producing paths must be ported. A single legacy prompt without module continuation would reintroduce ambiguity.

### CR-007: Stream Replay Cannot Advance Gameplay

Requirement:

- WebSocket `resume` replays stream messages only.
- It cannot execute engine transitions.

Draft#1 result:

- Pass.

Reason:

- WebSocket route keeps `resume` as replay-only.
- Runtime wakeup is limited to accepted prompt decisions or explicit runtime lifecycle actions.

Bug coverage:

- BUG-009
- BUG-011

Required implementation check:

- Add a test asserting `resume` does not call runtime transition methods.

### CR-008: Frontend Is Projection-Driven

Requirement:

- Frontend must not infer gameplay truth from localized labels or stale event order.

Draft#1 result:

- Pass.

Reason:

- Selector priority is backend `view_state`, then canonical module metadata, then raw structured fields, then text for display only.
- Animation consumes event timeline but does not advance truth.

Bug coverage:

- BUG-002
- BUG-003
- BUG-010
- BUG-011

Residual risk:

- Existing fallback branches should remain only as compatibility paths and must be tested so they do not override newer projection.

## 3. Bug-by-Bug Verdict

| Bug | Draft#1 verdict | Why |
| --- | --- | --- |
| BUG-001 first turn not executed | Safe | Turn schedule produces concrete `PlayerTurnModule`s and checkpoint exposes next module. |
| BUG-002 draft repeats mid-turn | Safe | Draft is round-only and idempotent. |
| BUG-003 card flip mid-turn | Safe | Card flip is round-end-only after all turn frames complete. |
| BUG-004 marker transfer/card flip confusion | Safe | Immediate marker transfer and round-end card flip are different modules. |
| BUG-005 trick lacks boundary | Safe | Trick is a child `SequenceFrame`. |
| BUG-006 prompt resumes wrong place | Safe | Resume token binds decision to frame/module. |
| BUG-007 global pending action leakage | Safe if fully ported | Queue ops target a frame; legacy global actions must be adapted. |
| BUG-008 modifier leakage | Safe if registry enforced | Modifier scope/expiry/propagation are explicit. |
| BUG-009 stream duplicate/suppression | Safe if idempotency key required | Dedupe moves from heuristic to stable module id. |
| BUG-010 frontend wrong stage inference | Safe if projection-first rule enforced | UI uses module projection first. |
| BUG-011 replay/live interleaving | Mostly safe | Seq ordering plus latest projection converges; visual animation may still skip noncritical events. |
| BUG-012 runtime status lags prompt | Safe | Checkpoint-owned active prompt is source of truth. |
| BUG-013 missing turn end snapshot | Safe if exceptional paths route to close module | Turn end is an explicit module. |
| BUG-014 projection lacks causality | Safe | Module metadata gives causality. |
| BUG-015 mixed migration truth | Not safe unless migration flag is strict | A session must not mix legacy and module runners. |

## 4. Structural Safety Conclusion

Draft#1 is the right architecture for the game rules described by the user:

- Round work belongs to a first-layer queue.
- Player turn work belongs to a second-layer queue.
- Trick/fortune/purchase/zone-chain work belongs to child sequence frames.
- Targeting inserts modules or modifiers through frame APIs.
- Immediate marker transfer happens inside the current turn.
- Card flip happens only after every player turn module completes.

The design directly prevents the three concrete classes that triggered this review:

1. First turn not running after setup.
2. Draft appearing multiple times mid-turn.
3. Card flip appearing mid-turn.

## 5. Mandatory Implementation Constraints

These constraints must be treated as blockers, not preferences:

1. A module runner session and a legacy pending-action session cannot both advance gameplay.
2. Every prompt must have `resume_token`, `frame_id`, and `module_id`.
3. Every stream event from the engine must have `idempotency_key`.
4. `RoundEndCardFlipModule` must assert all `PlayerTurnModule`s are complete before running.
5. `PlayerTurnModule` must assert its child `TurnFrame` has completed before completing.
6. `ImmediateMarkerTransferModule` must never emit card flip.
7. Frontend card flip UI must require `module_type=RoundEndCardFlipModule`.
8. Frontend draft UI must require an active draft prompt/module, not just old draft events.

## 6. Recommended First Slice

The safest first implementation slice is not the full rewrite. It is:

1. Add module metadata to legacy events.
2. Add backend projection fields for `latest_module_path`, `round_stage`, `turn_stage`, and `active_sequence`.
3. Add frontend projection-first selectors for draft/trick/card-flip visibility.
4. Add engine tests for first-turn, trick continuation, and card flip order.
5. Only then introduce real `RoundFrame`/`TurnFrame` execution behind a runtime flag.

This gives immediate diagnostic value while keeping gameplay behavior stable during the transition.
