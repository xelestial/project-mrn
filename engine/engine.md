# engine.py

`GameEngine` is the gameplay authority. It owns rule execution, runtime module progression, semantic event emission, and `GameResult` construction.

## Current Runtime Shape

- `prepare_run(initial_state=...)` prepares a hydrated state for transition execution.
- `run_next_transition(state)` advances one committed module/turn/round boundary.
- Module-runner sessions store progress in frame/module cursors and Redis checkpoints.
- Prompt-capable modules raise prompt boundaries only after the backend can persist continuation data.

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

## Observability

The engine emits semantic events and action-log entries so backend stream guards and debug-log audits can verify module ownership.
