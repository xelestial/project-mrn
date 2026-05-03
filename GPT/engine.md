# engine.py

## 0.7.62 note
Mark-target resolution now has a safe character-name fallback for test and tooling contexts where the public future-order view is not initialized.

## 2026-04-29 Redis checkpoint transition note
- `GameEngine.run()` now delegates execution to `prepare_run()` and `run_next_transition()`.
- `prepare_run(initial_state=...)` resets per-run trackers and can reuse a hydrated Redis checkpoint state.
- `run_next_transition(state)` advances one committed turn/round boundary and returns a small status payload, allowing server recovery code to persist the updated checkpoint after one transition.
- `prepare_run()` records `_last_prepared_state` so a server-side prompt boundary raised during initial round setup can still commit the canonical checkpoint.
- If `GameState.pending_actions` is non-empty, `run_next_transition(state)` drains exactly one queued action before normal turn advancement. This lets Redis persist intermediate movement/arrival boundaries.

## 2026-04-29 action pipeline seed note
- Movement/arrival refactoring has started with serializable `ActionEnvelope` execution helpers.
- The first migrated path is target movement: `apply_move` can optionally schedule `resolve_arrival`.
- Arrival resolution must not roll dice or calculate movement. Dice/fixed/target movement sources run before `resolve_arrival`; `resolve_arrival` only resolves the current tile.
- Fortune arrival/move-only effects and hunter forced landing now use the shared target-move helper, preserving `no_lap_credit` behavior while making the move/arrival boundary explicit.
- Visual contract note: queued `apply_move` emits `action_move` when a movement event is requested. The regular `player_move` event remains reserved for the normal turn movement that is paired with `dice_roll`; this keeps stream validation and replay projections from treating follow-up/forced movement as an extra dice move.
- Queue note: queued `apply_move` actions schedule `resolve_arrival` as a follow-up action instead of resolving landing inline; direct compatibility calls still execute inline until their callers are migrated.
- Step-move note: queued `apply_move` also accepts `move_value` for forward movement. In that mode it computes path and lap rewards during the move action, then leaves tile effects to the queued `resolve_arrival` action.
- Adapter note: `_build_standard_move_action()` / `_enqueue_standard_move_action()` convert resolved normal movement into a queued `apply_move` action. The adapter now mirrors obstacle slowdown, encounter boost, and zone-chain follow-up movement for parity tests. The default `_take_turn()` path now schedules normal movement through the queued `apply_move -> resolve_arrival` path and stores turn-end work in `pending_turn_completion` until the queued movement finishes.
- Log note: queued standard movement now stores an in-progress turn log aggregate in `GameState.pending_action_log`; final `resolve_arrival` emits a legacy-compatible `turn` log row when the movement chain completes.
- Turn-completion note: `run_next_transition()` drains pending actions before advancing the turn cursor. When `pending_turn_completion` exists, it emits `turn_end_snapshot`, applies delayed control-finisher bookkeeping, checks game end, and then advances the turn/round cursor.
- Scheduled-action note: `GameState.scheduled_actions` now stores phase-targeted actions such as turn-start marks. `run_next_transition()` materializes matching `turn_start` actions into `pending_actions` before incrementing the target player's turn, so mark effects can resolve through the same iterator.
- Mark-action note: queued marks now schedule `resolve_mark` for the target player's `turn_start`. Immediate mark effects such as bandit tax resolve inside that action; hunter pull produces follow-up `apply_move -> resolve_arrival` actions instead of nesting the movement inline.
- Fortune-producer note: fortune tile resolution now uses `_produce_fortune_card_actions()` for built-in fortune cards. Movement fortune cards enqueue follow-up `apply_move` actions and report queued movement results, while direct compatibility helpers such as `_apply_fortune_arrival()` still execute immediately for legacy tests and extension hooks.
- Trick-movement note: target-movement trick effects use the same queued target-move primitive. `극심한 분리불안` now queues `apply_move -> resolve_arrival` rather than moving the player during trick-card resolution.
- Trick-continuation note: when a regular trick effect queues follow-up actions, `_use_trick_phase()` appends `continue_after_trick_phase` behind those newly queued actions. The continuation token resumes the same turn after movement, arrival, purchase, or landing follow-ups finish, so a player with another usable trick card does not re-enter the trick-selection window after resolving `극심한 분리불안`.
- Compatibility-helper note: `_advance_player()`, `_apply_fortune_arrival()`, and `_apply_fortune_move_only()` are retained as immediate compatibility helpers. Production effect modules are guarded by `test_action_pipeline_contract.py` so new runtime movement call sites use queued actions.
- Fortune hook note: custom extensions can register `fortune.card.produce` and return `{"type": "QUEUE_TARGET_MOVE", ...}` to have the engine convert the result into the same queued `apply_move` primitive used by built-in fortune movement.
- Fortune takeover note: backward takeover fortune effects now split into `apply_move` followed by `resolve_fortune_takeover_backward`, so the movement and ownership mutation are recoverable as separate Redis transitions.
- Prompt-action note: `request_purchase_tile` is the first decision-bearing action. `_run_next_action_transition()` reinserts the popped action if decision handling raises a prompt boundary or other interruption, so Redis can checkpoint and retry the same action after the decision is submitted. The action now owns only the prompt/precheck boundary; on an affirmative decision it queues `resolve_purchase_tile` ahead of any post-purchase follow-up.
- Purchase-context note: purchase cost calculation now flows through `tile_effects.PurchaseContext` and purchase modifiers. `FreePurchaseModifier` and `BuilderFreePurchaseModifier` prepare final cost/breakdown data before the purchase decision; one-shot free-purchase flags are consumed only after successful ownership mutation.
- Purchase-resolution note: `resolve_purchase_tile` owns cash/shard payment, ownership transfer, one-shot free-purchase flag consumption, AI decision logging, and `tile_purchased` visualization. First-purchase score-token placement is now queued as `resolve_score_token_placement`, so purchase mutation and token placement have separate Redis checkpoints.
- Arrival purchase note: queued `resolve_arrival` no longer calls the purchase prompt inline when the actor lands on an unowned land tile. It emits a `QUEUED_PURCHASE` landing, then flows as `request_purchase_tile -> resolve_purchase_tile -> resolve_score_token_placement -> resolve_unowned_post_purchase` when the player buys and can place a token, or skips the token-placement action when no token can be placed. Purchase decisions, prompt interruption, ownership mutation, token placement, adjacent-buy follow-ups, and same-tile bonuses are each resumable action steps.
- Rent-context note: normal rent calculation now flows through `tile_effects.RentContext` and rent modifiers. The context records base rent, final rent, weather/color doubling, global rent modifiers, personal rent modifiers, and normal-rent waiver consumptions. `_effective_rent()` uses the same context with normal waivers excluded so non-rent costs such as swindler takeover pricing do not accidentally consume or apply rent waivers.
- Score-token context note: score-token placement now builds `tile_effects.ScoreTokenPlacementContext` before mutating `hand_coins`, `tile_coins`, and `score_coins_placed`. First-purchase automatic placement uses the queued `resolve_score_token_placement` action. Policy-selected own-tile visit placement now uses `request_score_token_placement -> resolve_score_token_placement`, so the `choose_coin_placement_tile` prompt is also replay-safe.
- Rent landing note: queued rent landings now run as `resolve_arrival -> resolve_rent_payment -> resolve_landing_post_effects`. Direct `_resolve_landing()` compatibility remains inline, but the action pipeline can checkpoint before rent mutation and again before adjacent-buy/same-tile follow-up work.
- Fortune decision-action note: subscription, land thief, donation angel, forced trade, and pious marker gain now produce `resolve_fortune_*` actions on the queued fortune path. Those actions own target selection and later mutation, so target-selection prompts can be checkpointed instead of nesting inside fortune draw resolution. Non-target global effects such as all-player payment still resolve immediately inside the fortune handler until they need a replay boundary.
- Trick tile-rent action note: `재뿌리기` and `긴장감 조성` now queue `resolve_trick_tile_rent_modifier`. The action owns `choose_trick_tile_target` and the final per-tile rent modifier mutation, so Redis recovery can pause before target selection without losing the already-used trick-card state.

`GameEngine` orchestrates turns, emits semantic events, and builds `GameResult`.

As of v0.7.51, the engine also attaches an event-bus trace layer so emitted
semantic events are recorded into `action_log` with summarized arguments and
results when logging is enabled. This improves observability without changing
effect behavior.


## Metadata/log registry note
- For cross-cutting metadata, log schema, and board spec documentation, read `METADATA_REGISTRY.md`, `ACTION_LOG_SCHEMA.md`, and `BOARD_LAYOUT_SCHEMA.md` alongside this module.


## 0.7.57 token placement helpers
- `_place_hand_coins_on_tile(...)` is the low-level placement helper.
- purchase placement uses the purchased tile directly with `max_place=1`.
- revisit placement still goes through policy-chosen tile placement with normal per-visit cap.


## Rule injection stage 1
Engine orchestration now delegates token placement limits, takeover blocking, force-sale behavior, and end-condition evaluation through `state.config.rules`.


## 0.7.60 note
Engine cost, dice-card, and special-tile calculations increasingly prefer injected `GameRules` over legacy config mirrors.


## 2026 forensic logging patch
- 게임 결과에 `bankruptcy_events`가 포함된다. 각 이벤트는 `cash_before_death`, `required_cost`, `cash_shortfall`, `cause_hint`, `last_semantic_event`, `is_offturn_death`, `receiver_player_id` 등을 담는다.
- 각 `player_summary` 행에도 `bankruptcy_info`가 들어가서 요약 로그만으로도 해당 플레이어의 파산 원인 힌트를 볼 수 있다.
- 시뮬레이션 로그에는 `run_id`, `root_seed`, `chunk_seed`, `chunk_id`, `chunk_game_id`, `global_game_index`, `game_seed`가 함께 저장된다.
- `run_chunked_batch.py`는 청크 병합 시 `game_id`를 전역 유일값으로 다시 부여하고, 원래 청크 내부 번호는 `chunk_game_id`로 보존한다.


## v7.61 forensic logging patch notes
- `resource_f_change` now records `reason`, `source`, `requested_delta`, and clamp metadata.
- Global F is clamped to 0 so negative public F values no longer appear in logs.


## v7.61 forensic patch notes
- `resource_f_change` now records `reason`, `source`, `requested_delta`, and `clamped`.
- Public F is clamped at 0 so logs no longer show negative shared F values.

- 특수 처리: pending mark, 강제 이동, burden cleanup, active flip, forensic logging, 교리 연구관/감독관의 턴 시작 짐 1장 제거. team_id가 정의된 모드에서는 같은 팀원도 지원할 수 있고, 기본 모드에서는 자기 짐을 먼저 제거한다.

- 추가: 교리 연구관/감독관은 턴 시작 시 자신 또는 같은 `team_id` 팀원의 짐 카드 1장을 제거한다. 팀 정보가 없는 기본 자유대전에서는 자기 짐만 제거한다.

- 최신 변경: `중매꾼`의 인접 추가 매입도 각 매입마다 조각 1개를 요구하며, 조각이 없으면 추가 매입은 발생하지 않는다.


- 최신 규칙: `중매꾼`은 인접 추가 매입 시에만 조각 1개를 소모한다. `건설업자`는 기본 착지 매입에서 조각 소모 없이 무료 건설을 한다.

- Reliability note: strategy summaries now carry `last_selected_character` and `final_character_choice_counts` so post-game analysis does not depend on mutable `current_character` state.


## v7.61 runtime guard note
- Engine.run now safely rehydrates round order if it is unexpectedly empty before advancing the turn loop.

- 탐관오리 패시브 공납은 이동 대상의 조각이 아니라 탐관오리 자신의 조각(//2)을 기준으로 계산한다.
- 어사/탐관오리는 같은 카드 양면이므로 탐관오리 패시브에는 별도 어사 차단 체크를 두지 않는다.

- 2026-05-03 sync: current handoff documentation confirms `engine.py` remains the gameplay authority behind the modular runtime; draft, turn-start mark, trick, movement, arrival, and round-end flip behavior must be documented through the active runtime contracts instead of duplicated in frontend logic.
- 2026-05-03 nested-sequence sync: `_use_trick_phase()` now records `runtime_last_trick_sequence_result` so `TrickChoiceModule` can hand selected-card resolution to `TrickResolveModule` inside the same child sequence. Follow-up trick prompts are scheduled as additional modules in that child sequence instead of restarting the outer turn, and fortune roll-and-arrive actions must flow through explicit sequence modules before turn completion.
- 2026-05-03 target-judicator sync: module runtime no longer resolves mark-target character abilities directly inside `CharacterStartModule`. Character start now yields to `TargetJudicatorModule`; queued marks materialize for `PendingMarkResolutionModule`, while 자객's immediate reveal/skip effect is inserted as `ImmediateMarkerTransferModule`. This keeps Redis resume boundaries aligned with the active turn module and prevents trick continuation from replaying character-start targeting.
