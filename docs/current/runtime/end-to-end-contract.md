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
8. Effect-caused prompts must carry backend-projected `public_context.effect_context`
   into `view_state.prompt.active.effect_context`. The payload names the source
   family/name, player when known, intent, tone, attribution, and UI detail so
   clients never infer prompt causality from raw event history.
9. Known prompt-resuming actions must resolve to native runtime modules. A
   prompt boundary that would resume through `LegacyActionAdapterModule` is a
   migration failure, not a tolerated compatibility path.

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
