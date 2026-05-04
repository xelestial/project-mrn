# Redis-Authoritative Runtime State

Status: ACTIVE
Updated: 2026-05-05

## 1. Purpose

Redis is the authoritative runtime checkpoint for online games. The engine owns game rules and module execution; the backend stores checkpoints, validates continuations, publishes stream events, and resumes work from the exact saved module boundary.

The backend must never infer game progress from frontend state, stream history, local process memory, or convenience tokens.

## 2. Authoritative Continuation Boundary

Prompt boundaries are commit boundaries.

Before a prompt is published, the backend stores:

- canonical `GameState`
- runtime frame stack and module cursor
- active prompt or simultaneous prompt batch
- stream sequence watermark
- accepted command sequence

Worker 재실행은 Redis checkpoint rehydration, not a parent turn replay. A restarted worker loads the checkpoint and continues the active module cursor. It does not rebuild a parent turn, re-run completed modules, or accept reconstructed UI state as authority.

The runtime ignores prompt replay aids, raw resume tokens, frontend-created request id values, and stale local payloads. A mismatched continuation must not mutate canonical game state.

## 3. Stored Contracts

`PromptContinuation` stores a single-player decision boundary:

- `request_id`
- `request_type`
- `player_id`
- `frame_id`
- `module_id`
- `module_type`
- `module_cursor`
- `choice_id`

`SimultaneousPromptBatchContinuation` stores a simultaneous response boundary:

- `batch_id`
- `request_type`
- `frame_id`
- `module_id`
- `module_type`
- `module_cursor`
- `missing_player_ids`
- `resume_tokens_by_player_id`

Every accepted decision must match the stored continuation before the engine advances.

## 4. Runtime Ownership

Runtime progress is module-owned:

- `RoundSetupModule` owns weather, draft, turn order, and round-end scheduling.
- `PlayerTurnModule` owns turn-local child frames.
- `SequenceFrame` owns trick, movement, arrival, rent, purchase, LAP reward, and fortune follow-up work.
- `SimultaneousResolutionFrame` owns all-player prompts such as resupply.

Rent payment is now actionized through `resolve_rent_payment` and `RentPaymentModule`.

Fortune and movement follow-up work stays inside `FortuneResolveModule -> MapMoveModule -> ArrivalTileModule`.

test/plugin-only surfaces guarded by contract tests may call narrow helpers, but production progress still requires catalogued modules and stored continuations.

## 5. Backend Rules

- Accept only commands that match the active Redis checkpoint.
- Publish stream events after semantic validation against the active frame/module.
- Persist every prompt boundary before exposing it to clients.
- Rehydrate from Redis on worker restart.
- Reject duplicate or stale decisions without mutating state.
- Reject uncatalogued action types until a native module handler and continuation contract exist.

## 6. Verification

Required checks:

- prompt continuation mismatch test
- duplicate frontend command test
- worker restart/resume test
- simultaneous response resume test
- `FortuneResolveModule`, `MapMoveModule`, `ArrivalTileModule` follow-up test
- `RentPaymentModule` and `resolve_rent_payment` test
- stream semantic guard test
