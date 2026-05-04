# Runtime End-to-End Contract

## Authority

The engine is the source of legal game progression. Backend services, Redis persistence, WebSocket replay, and frontend selectors must reject or ignore states that contradict the engine runtime contract.

## Runtime Boundaries

- `RoundFrame`: setup, draft, turn scheduling, player-turn slots, round-end card flip, cleanup.
- `TurnFrame`: exactly one player's turn body.
- `SequenceFrame`: nested follow-up work created by an active turn module.
- `SimultaneousResolutionFrame`: all-required concurrent prompts and commits.

## Hard Rules

1. Draft prompts and draft events never mutate `turn_stage`.
2. Round-end card flip is legal only after every player turn module in the round frame is completed or skipped.
3. Resupply prompts use a simultaneous batch contract with `batch_id`.
4. Module prompt decisions must echo `resume_token`, `frame_id`, `module_id`, and `module_type`.
5. WebSocket replay may fill gaps only with projections compatible with the latest known runtime frame path.
6. Redis stores committed state atomically but does not replace backend semantic validation.
7. `final_character_choice` is draft-frame private data until the matching `turn_start`.
   Backend `view_state.player_cards` may show `selected_private` only to the
   choosing seat; spectators see the assignment only after `turn_start` changes
   it to `revealed`.
