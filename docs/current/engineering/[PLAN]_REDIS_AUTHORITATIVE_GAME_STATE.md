# Redis-Authoritative Runtime State

Status: ACTIVE
Updated: 2026-05-09

## 1. Purpose

Redis is the authoritative runtime checkpoint for online games. The engine owns game rules and module execution; the backend stores checkpoints, validates continuations, publishes stream events, and resumes work from the exact saved external boundary.

The backend must never infer game progress from frontend state, stream history, local process memory, or convenience tokens.

## 2. Authoritative Continuation Boundary

Prompt boundaries and user-command terminal boundaries are commit boundaries. Internal module transitions are not Redis or `view_commit` boundaries.

Before a prompt is published, the backend stores:

- canonical `GameState`
- runtime frame stack and module cursor
- active prompt or simultaneous prompt batch
- stream sequence watermark
- accepted command sequence

When a frontend command is accepted, the backend records the command lifecycle as `processing` and runs validators/resolvers in memory until one terminal boundary is reached: `success`, `refused`, `failed`, `waiting_input`, or `completed`. Only that terminal boundary writes the authoritative checkpoint, cached `view_commit`, stream event, and command status.

Worker 재실행은 Redis checkpoint rehydration, not a parent turn replay. A restarted worker loads the last authoritative checkpoint and continues from the stored external boundary. It does not rebuild a parent turn, re-run completed modules from frontend state, or accept reconstructed UI state as authority.

The runtime ignores prompt replay aids, raw resume tokens, frontend-created request id values, and stale local payloads. A mismatched continuation must not mutate canonical game state.

Internal `module_trace` is timing/debug evidence only. It is not an authoritative frontend render source and must not be used as a substitute for the final cached `view_commit`.

Runtime status persistence follows the same command boundary. During an internal non-terminal command loop, the backend may stage runner status in process, but it must not write Redis runtime status for each module transition. External status writes represent command acceptance or a terminal boundary, not every validator/resolver hop.

## 2.1. Irreversible Inputs vs Internal Progress

Redis persistence is required for external recovery boundaries and irreversible inputs, not for every internal module step.

Persist irreversible inputs when they are chosen or consumed:

- Dice rolls selected by the backend/engine, because replay must not roll again.
- Fortune/weather/deck draws, because ordered deck consumption must behave like a queue and cannot duplicate after restart.
- LAP reward choices or grants once accepted, because they are player-visible outcomes and may affect inventory, money, or score.
- Any random seed, shuffled order, card draw, or one-time token that cannot be recomputed safely from the previous checkpoint and command payload.

Do not create Redis checkpoints or `view_commit` records only because an internal module pointer changed:

- Turn pointer is authoritative at the prompt/command boundary. During one command loop, the active frame stack and module cursor in memory already define which turn/module is executing.
- Hidden-trick availability is a validator contract. If a trick cannot be used, the adjudicator returns `refused` or continues without mutating state; it does not need an intermediate external commit.
- Movement, purchase, arrival, rent, and follow-up modules may pass through many validators/resolvers. Their intermediate state is `module_trace`, not frontend authority.

If an internal module needs a value that cannot be recomputed deterministically, record that value in the command payload or terminal checkpoint before using it as an irreversible input. Do not solve nondeterminism by committing every module transition.

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
- Persist one command terminal boundary per accepted user command; do not write Redis checkpoints or authoritative `view_commit` records for each internal module transition.
- Rehydrate from Redis on worker restart.
- Reject duplicate or stale decisions without mutating state.
- Treat duplicate `request_id` submissions as idempotency hits or explicit stale/refused results, never as new engine commands.
- Reject a different `request_id` for the same active prompt while a command is already `processing` as `busy` or `conflict`.
- Reject uncatalogued action types until a native module handler and continuation contract exist.

## 6. Verification

Required checks:

- prompt continuation mismatch test
- duplicate frontend command test
- command-boundary single checkpoint/view_commit test
- command-boundary internal transition test that proves Redis runtime status is not written before terminal boundary
- irreversible input checkpoint test for RNG state, ordered decks, and reward pools
- duplicate `request_id` idempotency test
- same-prompt busy/conflict test
- worker restart/resume test
- simultaneous response resume test
- `FortuneResolveModule`, `MapMoveModule`, `ArrivalTileModule` follow-up test
- `RentPaymentModule` and `resolve_rent_payment` test
- stream semantic guard test
