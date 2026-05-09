# engine.py

`GameEngine` is the gameplay authority. It owns rule execution, runtime module progression, and semantic event emission.

## Current Runtime Shape

- `prepare_run(initial_state=...)` prepares a hydrated state for transition execution.
- `run_next_transition(state)` advances one committed module/turn/round boundary.
- Module-runner sessions store progress in frame/module cursors and Redis checkpoints.
- Prompt-capable modules raise prompt boundaries only after the backend can persist continuation data.

## Split Boundaries

- `engine.py` owns transition orchestration only.
- `result.py` owns `GameResult`.
- `decision_port.py` owns policy decision request/resume contracts.
- `runtime_modules/contracts.py` owns runtime module DTOs.
- `runtime_modules/runner.py` owns committed module execution.
- `module_interface_manager.py` lists engine module interfaces that other modules may depend on.
- `backend_connection_manager.py` lists backend-to-engine entrypoints.

Changing a module boundary without updating its manager catalog and matching test expectations is invalid. Backend/engine connection changes must update both the manager entry and the test expectation in the same patch.

## Module-Owned Work

- Round setup schedules weather, draft, turn order, player turns, simultaneous work, and round-end flip.
- Player turns are owned by `PlayerTurnModule` and child frames.
- Trick follow-ups stay in `TrickSequenceFrame`.
- Movement, arrival, rent, purchase, LAP reward, and fortune follow-ups stay in action sequence modules.
- Simultaneous responses stay in `SimultaneousResolutionFrame`.

## Action Pipeline

Queued action envelopes split recoverable work into explicit module steps:

- `apply_move`
- `resolve_lap_reward`
- `resolve_arrival`
- `resolve_rent_payment`
- `request_purchase_tile`
- `resolve_purchase_tile`
- `resolve_score_token_placement`
- `resolve_landing_post_effects`
- `resolve_fortune_*`
- `resolve_trick_tile_rent_modifier`

Completed modules must not be re-run when a child sequence resumes.

## Rule Boundaries

Rule data flows through `GameRules`, tile metadata, modifier registries, and module contexts. Frontend code renders decisions and events; it does not reconstruct gameplay rules.

Hidden trick selection is also routed through the engine decision boundary so a persisted runtime can resume the round setup step from the same canonical state instead of asking policy code directly.

Start resource metadata is owned by `GameRules.start_reward`. At game start, the engine runs the same allocation-style decision boundary as LAP reward before weather reveal and draft, then consumes the start reward pools.

## Observability

The engine emits semantic events and action-log entries so backend stream guards and debug-log audits can verify module ownership.
