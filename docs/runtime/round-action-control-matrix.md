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
