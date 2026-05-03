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
| Fortune follow-up | `FortuneResolveModule` in turn/sequence | any inserted extra action must be queued through runtime module API | displayed in current turn/sequence only |
| Concurrent resupply | `SimultaneousResolutionFrame` | all participant prompts share `batch_id`; commit only when all required responses exist or policy timeout default applies | simultaneous response surface; must not supersede unrelated single-player prompts |
| Turn end | `TurnEndSnapshotModule` in active turn completion contract | turn completion cannot publish round-end card flip | closes current turn UI |
| Round-end card flip | `RoundEndCardFlipModule` in `RoundFrame` | allowed only after all `PlayerTurnModule`s completed/skipped | show as round-end stage, never as current turn progress |
| Cleanup/next round | `RoundCleanupAndNextRoundModule` | starts next round only after card flip/cleanup complete | clear stale prompt/turn stage before next draft |

## Implementation Module Inventory

This section is intentionally exhaustive and is checked by tests against `GPT/runtime_modules/catalog.py`. If a module is added to the engine catalog, this matrix must be updated with its frame boundary and frontend/backend contract before the module can ship.

- RoundFrame modules: `RoundStartModule`, `WeatherModule`, `DraftModule`, `TurnSchedulerModule`, `PlayerTurnModule`, `RoundEndCardFlipModule`, `RoundCleanupAndNextRoundModule`.
- TurnFrame modules: `TurnStartModule`, `ScheduledStartActionsModule`, `CharacterStartModule`, `ImmediateMarkerTransferModule`, `TargetJudicatorModule`, `TrickWindowModule`, `DiceRollModule`, `MovementResolveModule`, `LapRewardModule`, `PendingMarkResolutionModule`, `MapMoveModule`, `ArrivalTileModule`, `FortuneResolveModule`, `TurnEndSnapshotModule`.
- SequenceFrame trick modules: `TrickChoiceModule`, `TrickSkipModule`, `TrickResolveModule`, `TrickDiscardModule`, `TrickDeferredFollowupsModule`, `TrickVisibilitySyncModule`.
- SequenceFrame action modules: `PendingMarkResolutionModule`, `MapMoveModule`, `ArrivalTileModule`, `RentPaymentModule`, `PurchaseDecisionModule`, `PurchaseCommitModule`, `UnownedPostPurchaseModule`, `ScoreTokenPlacementPromptModule`, `ScoreTokenPlacementCommitModule`, `LandingPostEffectsModule`, `TrickTileRentModifierModule`, `FortuneResolveModule`, `LegacyActionAdapterModule`.
- SimultaneousResolutionFrame modules: `SimultaneousProcessingModule`, `SimultaneousPromptBatchModule`, `ResupplyModule`, `SimultaneousCommitModule`, `CompleteSimultaneousResolutionModule`.
- Virtual effect modules: `CharacterModifierSeedModule`, `CharacterPassiveModifierSeedModule`, `ConcurrentResolutionSchedulerModule`. These are inventory-only module boundaries used to express modifier/scheduler ownership without allowing ad hoc backend branching.

## Action Adapter Inventory

Action sequence names must resolve to explicit module boundaries. Backend resume and frontend prompt routing must use these module names instead of inferring behavior from loose action strings.

| Action type | Runtime module |
| --- | --- |
| `resolve_mark` | `PendingMarkResolutionModule` |
| `apply_move` | `MapMoveModule` |
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
| unknown `resolve_fortune_*` action | `LegacyActionAdapterModule` until catalogued |
| unknown legacy action | `LegacyActionAdapterModule` |

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
| `fortune:extra_arrival` | 운수 | `FortuneResolveModule` | `MapMoveModule`, `ArrivalTileModule` |
| `simultaneous:resupply` | 재보급 | `ConcurrentResolutionSchedulerModule` | `ResupplyModule` |
