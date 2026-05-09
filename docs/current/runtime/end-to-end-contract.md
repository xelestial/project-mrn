# Runtime End-to-End Contract

## Authority

The engine is the source of legal game progression. RuntimeService is the single writer of live `ViewCommit` state. Backend services, Redis persistence, WebSocket delivery, and frontend selectors must reject or ignore states that contradict the engine runtime contract.

## Runtime Boundaries

- `RoundFrame`: setup, draft, turn scheduling, player-turn slots, round-end card flip, cleanup.
- `TurnFrame`: exactly one player's turn body.
- `SequenceFrame`: nested follow-up work created by an active turn module.
- `SimultaneousResolutionFrame`: all-required concurrent prompts and commits.

## Command Boundary Contract

A frontend command is identified by `session_id + player_id + prompt_id + request_id`.
The command lifecycle fields are `command_id`, `command_seq`, `request_id`,
`player_id`, `request_type`, `choice_id`, `status`, `started_at_ms`,
`finished_at_ms`, `final_commit_seq`, `boundary_reason`, `refusal_reason`,
`error_code`, and `module_trace`.

`module_trace` is diagnostic timing data. It is not the authoritative rendering
surface. Redis checkpoint and cached `ViewCommit` are committed only at the
terminal command boundary: `success`, `refused`, `failed`, `waiting_input`, or
`completed`.

## Hard Rules

1. Draft prompts and draft events never mutate `turn_stage`.
2. Round-end card flip is legal only after every player turn module in the round frame is completed or skipped.
3. Resupply prompts use a simultaneous batch contract with `batch_id`.
4. Module prompt decisions must echo `resume_token`, `frame_id`, `module_id`, and `module_type`.
5. Live WebSocket recovery uses the latest Redis-cached `ViewCommit` only. Replay projection is debug/archive data and must not fill live UI gaps.
6. Redis stores committed state atomically but does not replace backend semantic validation.
7. `final_character_choice` is draft-frame private data until the matching `turn_start`.
   Backend `view_state.player_cards` may show `selected_private` only to the
   choosing seat; spectators see the assignment only after `turn_start` changes
   it to `revealed`.
8. Effect-caused prompts must carry backend-projected `public_context.effect_context`
   into `view_state.prompt.active.effect_context`. The payload names the source
   family/name, player when known, intent, tone, attribution, and UI detail so
   clients never infer prompt causality from raw event history.
9. Known prompt-resuming actions must resolve to native runtime modules. An
   uncatalogued prompt boundary is rejected until it has an owner module,
   handler, and continuation contract.
10. Internal engine module transitions are not external commits. Tests that
    change module interfaces must update module expectation tests and, when a
    module-to-module connection changes, the corresponding boundary expectation
    tests. Redis/view-commit tests cover persistence and recovery only.
11. Frontend duplicate command submissions are protocol inputs. Same
    `request_id` is deduped or explicitly refused; a different `request_id` for
    the same active prompt while processing is `busy` or `conflict`; stale prompt
    submissions must not mutate state.

## Prompt Effect Context Contract

`effect_context` is optional for purely generic prompts, but required for every
prompt opened by a character, trick, movement reward, score placement, resupply,
or round-end effect. The current covered prompt families are:

- Character/mark effects: `mark_target`, `geo_bonus`, `pabal_dice_mode`,
  `runaway_step_choice`, `doctrine_relief`, and matchmaker `purchase_tile`.
- Trick effects: `trick_tile_target`, `specific_trick_reward`,
  `burden_exchange`.
- Movement/economy effects: `lap_reward`, landing `purchase_tile`,
  `coin_placement`.
- Round boundary effects: `active_flip`.

Frontend renderers consume this projection from `view_state.prompt.active` and
may localize display text, but must not reconstruct the source or intent from
older stream events.

## Prompt Decision Surface Inventory

These request types are the backend/frontend wire surface for resumable module
prompts:

- `mark_target`: `TargetJudicatorModule` resumes the active `TurnFrame`.
- `trick_to_use`: `TrickWindowModule` opens a child `TrickSequenceFrame`.
- `hidden_trick_card`: `TrickChoiceModule` resumes inside the child trick
  sequence.
- `specific_trick_reward`: `TrickResolveModule` resumes inside the child trick
  sequence.
- `movement`: `DiceRollModule`, `MapMoveModule`, or `ArrivalTileModule` resumes
  the current turn without creating a new turn.
- `lap_reward`: `LapRewardModule` resumes the movement-created action
  sequence.
- `purchase_tile`: `PurchaseDecisionModule` and `PurchaseCommitModule` resume
  the arrival action sequence.
- `coin_placement`: frontend/backend request type for score-token placement;
  engine ownership stays in `ScoreTokenPlacementPromptModule` and
  `ScoreTokenPlacementCommitModule`.
- `burden_exchange`: simultaneous response request type owned by
  `SimultaneousPromptBatchModule`, `ResupplyModule`, and
  `SimultaneousCommitModule`.
