# Round Action Control Matrix

Each round may contain these action groups. Every group must be controlled from engine to frontend.

| Round action group | Engine owner | Backend/Redis authority | Frontend visibility rule |
| --- | --- | --- | --- |
| Round start | `RoundStartModule` in `RoundFrame` | publish only if `frame_type=round`, `module_type=RoundStartModule`, no active turn prompt | `runtime.round_stage=round_setup`, no `turn_stage` mutation |
| Weather | `WeatherModule` in `RoundFrame` | one weather event per round idempotency key | show weather in round/setup context; may be copied into later turn context as persisted weather only |
| Draft pick/final choice | `DraftModule` in `RoundFrame` | prompt and events must carry round context, no turn frame/module | active draft UI only; must not append to previous `turn_stage.progress_codes` |
| Turn scheduling | `TurnSchedulerModule` in `RoundFrame` | order generated once per round and persisted in checkpoint | show order/progress outside current turn body |
| Player turn | `PlayerTurnModule` in `RoundFrame`, child `TurnFrame`/`SequenceFrame` work | stream events must match active turn round/turn/actor or active child frame | only same round+turn events can mutate `turn_stage` |
| Marker immediate effects | `PendingMarkResolutionModule`/`ImmediateMarkerTransferModule` at start of target player's turn | may occur before card flip; must carry current turn frame | displayed as early turn progress, not round-end marker flip |
| Trick sequence | `Trick*Module` in `SequenceFrame` created by active turn module | prompt continuation must include `resume_token`, `frame_id`, `module_id`, `module_type`, sequence id | hand/trick UI active only when runtime active sequence is trick |
| Dice/move/arrival | `DiceRollModule`, `MapMoveModule`, `ArrivalTileModule` | event must match active actor round+turn | displayed in current turn only |
| Lap reward | `LapRewardModule` after movement lap detection | prompt continuation must resume `lap_reward:await_choice`; reward mutation happens inside the module, not during movement reconstruction | render reward prompt/current turn progress from backend `turn_stage`, not from inferred position changes |
| Fortune follow-up | `FortuneResolveModule` in turn/sequence | any inserted extra action must be queued through runtime module API | displayed in current turn/sequence only |
| Simultaneous response / resupply | `SimultaneousResolutionFrame` | all participant prompts share `batch_id`; commit only when all required responses exist or policy timeout default applies | simultaneous response surface; must not supersede unrelated single-player prompts |
| Turn end | `TurnEndSnapshotModule` in the active `TurnFrame` | backend/Redis must not promote `pending_turn_completion` into a sequence frame; turn completion cannot publish round-end card flip | closes current turn UI |
| Round-end card flip | `RoundEndCardFlipModule` in `RoundFrame` | allowed only after all `PlayerTurnModule`s completed/skipped | show as round-end stage, never as current turn progress |
| Cleanup/next round | `RoundCleanupAndNextRoundModule` | starts next round only after card flip/cleanup complete | clear stale prompt/turn stage before next draft |

## Implementation Module Inventory

This section is intentionally exhaustive and is checked by tests against `engine/runtime_modules/catalog.py`. If a module is added to the engine catalog, this matrix must be updated with its frame boundary and frontend/backend contract before the module can ship.

- RoundFrame modules: `RoundStartModule`, `InitialRewardModule`, `WeatherModule`, `DraftModule`, `TurnSchedulerModule`, `PlayerTurnModule`, `RoundEndCardFlipModule`, `RoundCleanupAndNextRoundModule`.
- TurnFrame modules: `TurnStartModule`, `ScheduledStartActionsModule`, `CharacterStartModule`, `ImmediateMarkerTransferModule`, `TargetJudicatorModule`, `TrickWindowModule`, `DiceRollModule`, `MovementResolveModule`, `LapRewardModule`, `PendingMarkResolutionModule`, `MapMoveModule`, `ArrivalTileModule`, `FortuneResolveModule`, `TurnEndSnapshotModule`.
- SequenceFrame trick modules: `TrickChoiceModule`, `TrickSkipModule`, `TrickResolveModule`, `TrickDiscardModule`, `TrickDeferredFollowupsModule`, `TrickVisibilitySyncModule`.
- SequenceFrame action modules: `LapRewardModule`, `PendingMarkResolutionModule`, `MapMoveModule`, `ArrivalTileModule`, `RentPaymentModule`, `PurchaseDecisionModule`, `PurchaseCommitModule`, `UnownedPostPurchaseModule`, `ScoreTokenPlacementPromptModule`, `ScoreTokenPlacementCommitModule`, `LandingPostEffectsModule`, `TrickTileRentModifierModule`, `FortuneResolveModule`.
- SimultaneousResolutionFrame modules: `SimultaneousProcessingModule`, `SimultaneousPromptBatchModule`, `ResupplyModule`, `SimultaneousCommitModule`, `CompleteSimultaneousResolutionModule`.
- Virtual effect modules: `CharacterModifierSeedModule`, `CharacterPassiveModifierSeedModule`, `ConcurrentResolutionSchedulerModule`. These are inventory-only module boundaries used to express modifier/scheduler ownership without allowing ad hoc backend branching.

## Action Module Inventory

Action sequence names must resolve to explicit module boundaries. Backend resume and frontend prompt routing must use these module names instead of inferring behavior from loose action strings.

| Action type | Runtime module |
| --- | --- |
| `resolve_mark` | `PendingMarkResolutionModule` |
| `apply_move` | `MapMoveModule` |
| `resolve_lap_reward` | `LapRewardModule` |
| `resolve_arrival` | `ArrivalTileModule` |
| `resolve_rent_payment` | `RentPaymentModule` |
| `request_purchase_tile` | `PurchaseDecisionModule` |
| `resolve_purchase_tile` | `PurchaseCommitModule` |
| `resolve_unowned_post_purchase` | `UnownedPostPurchaseModule` |
| `request_score_token_placement` | `ScoreTokenPlacementPromptModule` |
| `resolve_score_token_placement` | `ScoreTokenPlacementCommitModule` |
| `resolve_landing_post_effects` | `LandingPostEffectsModule` |
| `continue_after_trick_phase` | `TrickDeferredFollowupsModule` |
| `resolve_trick_tile_rent_modifier` | `TrickTileRentModifierModule` |
| `resolve_fortune_takeover_backward` | `FortuneResolveModule` |
| `resolve_fortune_subscription` | `FortuneResolveModule` |
| `resolve_fortune_land_thief` | `FortuneResolveModule` |
| `resolve_fortune_donation_angel` | `FortuneResolveModule` |
| `resolve_fortune_forced_trade` | `FortuneResolveModule` |
| `resolve_fortune_pious_marker` | `FortuneResolveModule` |
| unknown `resolve_fortune_*` action | rejected with `UnknownActionTypeError` until catalogued |
| unknown uncatalogued action | rejected with `UnknownActionTypeError` |

Prompt-resuming action coverage is tested as a native-module contract. `resolve_mark`,
`resolve_lap_reward`, `request_purchase_tile`, `resolve_purchase_tile`,
`request_score_token_placement`, `resolve_score_token_placement`, and
`resolve_trick_tile_rent_modifier` must resolve to the explicit modules above.

## Prompt/Decision Contract Matrix

Every player decision is owned by the active engine frame and module that opened
the prompt. The backend/Redis layer persists this identity; WebSocket forwards
it; the frontend returns it unchanged. The frontend does not invent request ids
or resume tokens.

Single-player prompt envelopes must carry `request_id`, `legacy_request_id`,
`public_request_id`, `public_prompt_instance_id`, `player_id`, `frame_id`,
`module_id`, `module_type`, and `module_cursor` once the prompt boundary is
created. `prompt_instance_id` remains a numeric compatibility lifecycle key;
the opaque `public_prompt_instance_id` is the protocol-facing companion.

| request_type | Frame contract | Owner modules | Resume contract | Structural replay ban |
| --- | --- | --- | --- | --- |
| `mark_target` | `TurnFrame` | `CharacterStartModule`, `TargetJudicatorModule` | `PromptContinuation` | must not reopen `CharacterStartModule` |
| `trick_to_use` | `TrickSequenceFrame` | `TrickWindowModule`, `TrickChoiceModule` | `PromptContinuation` | must not reopen `TrickWindowModule` |
| `hidden_trick_card` | `TrickSequenceFrame` | `TrickChoiceModule`, `TrickResolveModule` | `PromptContinuation` | must not insert duplicate followup `TrickChoiceModule` |
| `specific_trick_reward` | `TrickSequenceFrame` | `TrickResolveModule`, `TrickDeferredFollowupsModule` | `PromptContinuation` with at least one legal choice | must not leave current `TrickSequenceFrame`; empty reward deck resolves in engine without opening a prompt |
| `movement` | `TurnFrame` | `DiceRollModule`, `MapMoveModule`, `ArrivalTileModule` | `PromptContinuation` | must not create a new `TurnFrame` |
| `lap_reward` | `ActionSequenceFrame` | `LapRewardModule` | `PromptContinuation` | must not rerun `MovementResolveModule` |
| `purchase_tile` | `ActionSequenceFrame` | `PurchaseDecisionModule`, `PurchaseCommitModule` | `PromptContinuation` | must not rerun `ArrivalTileModule` |
| `coin_placement` | `ActionSequenceFrame` | `ScoreTokenPlacementPromptModule`, `ScoreTokenPlacementCommitModule` | `PromptContinuation` | must not rerun `PurchaseCommitModule` |
| `burden_exchange` | `SimultaneousResolutionFrame` | `SimultaneousPromptBatchModule`, `ResupplyModule`, `SimultaneousCommitModule` | `SimultaneousPromptBatchContinuation` | must not recalculate eligible burden cards |

`coin_placement` is the backend/frontend wire request type for score-token
placement. The engine action/module names remain
`request_score_token_placement`, `resolve_score_token_placement`,
`ScoreTokenPlacementPromptModule`, and `ScoreTokenPlacementCommitModule`.

Single-player prompt rows must carry `request_id`, `request_type`, `player_id`,
`frame_id`, `module_id`, `module_type`, and `module_cursor`. Simultaneous
response rows additionally carry `batch_id`, `missing_player_ids`, and
`resume_tokens_by_player_id`.

## Trick/Mark Loop Structural Gates

- TrickWindowModule may suspend only into a child `TrickSequenceFrame`; it does not reopen the turn's character, target, dice, or movement modules.
- completed pre-trick modules must not replay after `TrickSequenceFrame` completion; the parent `TurnFrame` resumes at the suspended `TrickWindowModule` and then advances to the next queued turn module.
- 후속 잔꾀 선택은 `followup_choice_module_id`로 한 번만 삽입된다. Worker retry/recovery reuses that module id instead of appending another `TrickChoiceModule`.
- A mark prompt such as `mark_target` is consumed by `TargetJudicatorModule`; later trick prompts such as `trick_to_use`, `hidden_trick_card`, and `specific_trick_reward` stay inside the child `TrickSequenceFrame`.
- A same-turn trick follow-up may enqueue action modules, but it must not call the round turn scheduler or create a new `TurnFrame`.

## Action Classification

Action sequence names are closed-world. Known names map to the modules above;
new names fail until they are catalogued with an owner module and handler.

| Classification | Required behavior |
| --- | --- |
| Native actionized path | All known turn follow-up actions listed above must resolve to their explicit module type. |
| Native fortune path | All catalogued `resolve_fortune_*` actions listed above must resolve to `FortuneResolveModule`; any new fortune action must be added to `FORTUNE_ACTION_TYPE_TO_MODULE_TYPE` before use. |
| Simultaneous path | `resolve_supply_threshold` must never be built as a `SequenceFrame` action and must be promoted into `SimultaneousResolutionFrame` / `ResupplyModule`. |
| Unknown uncatalogued path | Any unmapped action now fails before action sequence construction with `UnknownActionTypeError`. The fix is to add a module boundary, handler, prompt continuation contract when needed, and matrix row. |
| Turn completion | `pending_turn_completion` may exist in `GameState` serialization, but module-runner sessions must attach it to the active `TurnFrame`'s `TurnEndSnapshotModule` payload in the same transition. Any orphan checkpoint or `SequenceFrame` containing `TurnEndSnapshotModule` is rejected. |

## Simultaneous Action Inventory

These actions are never valid inside a `SequenceFrame` action sequence. They
must be promoted by `ModuleRunner` into a `SimultaneousResolutionFrame` before
execution.

| Action type | Runtime frame/module |
| --- | --- |
| `resolve_supply_threshold` | `SimultaneousResolutionFrame` / `ResupplyModule` |

## Effect Boundary Inventory

Each effect is owned by a producer module and consumed only by declared runtime boundary modules. This is the structural replacement for one-off backend comparisons such as "if this character then block that target"; the character/trick/fortune effect must seed a modifier, prompt, or sequence module, and downstream modules consume that declared boundary.

| Effect id | Source | Producer | Consumer/runtime boundary |
| --- | --- | --- | --- |
| `character:assassin:mark_target` | 자객 | `CharacterStartModule` | `TargetJudicatorModule`, `ImmediateMarkerTransferModule` |
| `character:bandit:mark_target` | 산적 | `CharacterStartModule` | `TargetJudicatorModule`, `PendingMarkResolutionModule` |
| `character:chuno:mark_target` | 추노꾼 | `CharacterStartModule` | `TargetJudicatorModule`, `PendingMarkResolutionModule` |
| `character:baksu:mark_target` | 박수 | `CharacterStartModule` | `TargetJudicatorModule`, `PendingMarkResolutionModule` |
| `character:mansin:mark_target` | 만신 | `CharacterStartModule` | `TargetJudicatorModule`, `PendingMarkResolutionModule` |
| `character:eosa:suppress_muroe` | 어사 | `CharacterModifierSeedModule` | `CharacterStartModule`, `TargetJudicatorModule` |
| `character:tamgwanori:dice_tribute` | 탐관오리 | `CharacterPassiveModifierSeedModule` | `DiceRollModule` |
| `character:runaway_slave:special_step` | 탈출 노비 | `DiceRollModule` | `DiceRollModule`, `MapMoveModule`, `ArrivalTileModule` |
| `character:pabalggun:dice_modifier` | 파발꾼 | `CharacterStartModule` | `DiceRollModule` |
| `character:ajeon:arrival_rent_waiver` | 아전 | `CharacterStartModule` | `ArrivalTileModule`, `RentPaymentModule`, `LandingPostEffectsModule` |
| `character:doctrine_researcher:burden_relief` | 교리 연구관 | `CharacterStartModule` | `CharacterStartModule` |
| `character:doctrine_researcher:marker_management` | 교리 연구관 | `RoundEndCardFlipModule` | `RoundEndCardFlipModule` |
| `character:doctrine_supervisor:burden_relief` | 교리 감독관 | `CharacterStartModule` | `CharacterStartModule` |
| `character:doctrine_supervisor:marker_management` | 교리 감독관 | `RoundEndCardFlipModule` | `RoundEndCardFlipModule` |
| `character:gakju:arrival_lap_modifiers` | 객주 | `CharacterStartModule` | `ArrivalTileModule`, `LapRewardModule` |
| `character:matchmaker:adjacent_purchase` | 중매꾼 | `ArrivalTileModule` | `PurchaseDecisionModule`, `PurchaseCommitModule` |
| `character:builder:free_purchase` | 건설업자 | `CharacterStartModule` | `PurchaseDecisionModule`, `PurchaseCommitModule` |
| `character:swindler:takeover` | 사기꾼 | `ArrivalTileModule` | `ArrivalTileModule`, `RentPaymentModule`, `LandingPostEffectsModule` |
| `trick:sequence` | 잔꾀 | `TrickWindowModule` | `TrickChoiceModule`, `TrickResolveModule` |
| `trick:specific_reward` | 잔꾀 보상 | `TrickResolveModule` | `TrickResolveModule` |
| `fortune:extra_arrival` | 운수 | `FortuneResolveModule` | `MapMoveModule`, `ArrivalTileModule` |
| `simultaneous:resupply` | 재보급 | `ConcurrentResolutionSchedulerModule` | `SimultaneousProcessingModule`, `SimultaneousPromptBatchModule`, `ResupplyModule`, `SimultaneousCommitModule`, `CompleteSimultaneousResolutionModule` |

## Replay/Retry Invariants

- `TrickResolveModule` may insert a follow-up `TrickChoiceModule` only once. The inserted module id is stored as `followup_choice_module_id`; worker retry must reuse that module instead of appending another prompt.
- `RoundEndCardFlipModule` requires all `PlayerTurnModule` entries to be completed or skipped and also requires no active child `TurnFrame`, `SequenceFrame`, or `SimultaneousResolutionFrame`.
- `resolve_supply_threshold` remains outside action sequences; retry/recovery must resume the stored `SimultaneousResolutionFrame` and its `ResupplyModule` eligible snapshot without recreating processing/prompt-batch modules.
- `TurnEndSnapshotModule` is turn-owned only. A module-runner replay must not create a `SequenceFrame` from `pending_turn_completion`; the backend semantic guard rejects that invalid shape before publish/recovery can continue.
- All catalogued `resolve_fortune_*` actions remain native `FortuneResolveModule` work and may chain `MapMoveModule`/`ArrivalTileModule` without creating a new turn.
- Unknown action types must fail before runtime execution. Frontend/backend logs may mention the failed action type, but the engine must not create module work for it.
- Engine execution validates every action payload against its owning module before dispatch. A recovered checkpoint whose payload says `apply_move` but whose module says `ArrivalTileModule` fails inside the runner, not only at the backend WebSocket guard. Actionized `continue_after_trick_phase` is likewise executed as native `TrickDeferredFollowupsModule` work and transfers any pending turn completion into the active `TurnEndSnapshotModule` before follow-up actions are promoted.
- Redis prompt-boundary resume coverage includes target adjudication, fortune target choice, rent payment, score-token placement, purchase, trick, and lap reward prompts. Each resumes from saved `runtime_active_prompt` frame/module/cursor data and must not call prompt seed reconstruction.

## Backend/Redis Boundary

Backend and Redis do not own game-rule branching. They persist and validate the engine-issued frame/module checkpoint, active prompt, active prompt batch, idempotency keys, and stream ordering only.

- Prompt resume decisions must match `runtime_active_prompt` or `runtime_active_prompt_batch` by `resume_token`, `frame_id`, `module_id`, `module_type`, `module_cursor`, and when present `batch_id`.
- Active prompt projections must carry `effect_context` when the prompt was
  opened by a character, trick, movement/economy, simultaneous, or round-end
  effect. Frontend selectors consume that field as the source-of-truth prompt
  cause and only adapt it for presentation.
- Character suppression, trick follow-up insertion, movement, arrival, fortune chaining, turn end, and simultaneous resupply are engine module responsibilities.
- Redis may expose checkpoint visibility fields such as `has_pending_turn_completion`, but module-runner execution treats orphan `pending_turn_completion` as invalid unless it has already been consumed into `TurnEndSnapshotModule.payload.turn_completion`.
- WebSocket payloads are accepted only when their runtime module placement matches the catalog. This prevents impossible engine states from being republished as frontend progress.
- Backend `view_state` is the client projection source for `player_cards`, `active_by_card`, and `turn_stage`; frontend selectors consume those fields before reconstructing from raw prompt/event history, including backend-only `prompt_active` checkpoints.

## Latest Play Log Revalidation

The May 2 playtest logs under `.log/20260502-150332-272298-p1/` and
`.log/20260502-150334-677119-p1/` were rechecked after the module runtime
retry/idempotency work.

| Finding | Evidence | Structural expectation |
| --- | --- | --- |
| Duplicate burden exchange request was a frontend resend loop. | `frontend.jsonl` sent `sess_KyskL_9wzGLkZyyQyNlS3Dxu:r1:t3:p1:burden_exchange:3` 173 times with no `decision_suppressed_duplicate` events in that run. | Current frontend request ledger suppresses same-stream duplicate `requestId`s before network send. |
| Backend accepted the duplicated request only once. | `backend.jsonl` recorded 216 receives for the same request id: 1 `accepted`, 215 `stale/already_resolved`. | Redis prompt state remains the authoritative continuation gate; duplicate decisions must not enqueue duplicate engine commands. |
| No active-turn card flip violation was present in the rechecked engine logs. | Both engine logs had 0 `marker_flip` events and 0 `RoundEndCardFlipModule` runtime modules. | Card flip remains a `RoundFrame` module and is invalid while any active child frame exists. |
