# 모듈 런타임 플레이테스트 시나리오 매트릭스

## 1. 목적

이 문서는 모듈 런타임 마이그레이션 후 각 라운드/턴/시퀀스/동시응답 흐름이 엔진부터 백엔드, Redis, WebSocket, 프론트까지 같은 진행구간 계약으로 통제되는지 검증하기 위한 플레이테스트 매트릭스다.

핵심 기준은 다음과 같다.

- 엔진은 다음 작업의 단일 소유자를 `FrameState`와 `ModuleRef`로 물질화한다.
- 백엔드와 Redis는 엔진이 발급한 `PromptContinuation` 또는 `SimultaneousPromptBatchContinuation`만 저장/재개한다.
- WebSocket은 prompt/decision payload에 `request_id`, `resume_token`, `frame_id`, `module_id`, `module_type`, `module_cursor`, 필요 시 `batch_id`를 그대로 전달한다.
- 프론트는 백엔드가 준 continuation을 생성하지 않고 보존해 되돌려 보낸다.
- 같은 구조의 재실행이 발생해도 완료된 모듈이 다시 시작되지 않아야 한다.

## 2. 공통 통과 기준

- 턴 중 발생한 잔꾀, 운수, 구매, 도착, 재보급은 부모 턴을 재실행하지 않고 자식 시퀀스 또는 동시응답 프레임으로 진행된다.
- 인물 능력은 카드 이름 비교로 후처리하지 않고 `TargetJudicatorModule`, `ModifierRegistry`, `PurchaseDecisionModule`, `DiceRollModule`, `ArrivalTileModule` 같은 소유 모듈에서 처리된다.
- prompt resume 시 continuation 필드 하나라도 현재 활성 prompt와 다르면 백엔드가 결정을 거부하고 엔진 상태는 움직이지 않는다.
- 프론트 재연결/리플레이/더블클릭이 있어도 같은 `request_id` 결정은 한 스트림 키에서 한 번만 전송된다.
- 라운드 종료 카드 플립은 모든 플레이어 턴과 turn-owned `TurnEndSnapshotModule`이 끝난 후 `RoundEndCardFlipModule`에서만 발생한다.
- 턴 종료는 `SequenceFrame` 어댑터가 아니라 활성 `TurnFrame`의 `TurnEndSnapshotModule`이 소유한다.

## 3. 시나리오 매트릭스

| ID | 시나리오 | 트리거 | 엔진 소유 구간 | 백엔드/Redis 계약 | 프론트/WebSocket 계약 | 구조 불변식 | 자동화 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MRN-MOD-001 | 첫 턴 실행 | 드래프트와 라운드 setup 완료 후 첫 번째 플레이어 턴 진입 | `RoundFrame -> PlayerTurnModule -> TurnFrame` | `runtime_frame_stack`가 첫 턴 `TurnFrame`을 보존하고 완료 journal을 저장 | 첫 prompt/event는 활성 플레이어와 `active_module_*`를 표시 | 첫 턴은 드래프트 재시작 없이 `CharacterStartModule`부터 한 번만 실행 | `engine/test_runtime_round_modules.py`, `engine/test_runtime_sequence_modules.py`, `npm run e2e:module-runtime` |
| MRN-MOD-002 | 드래프트 최종 결정 | 플레이어가 1차 선택 후 최종 후보를 확정 | `DraftModule` 계열 라운드 setup 경계 | Redis checkpoint에는 백엔드가 발급한 draft request와 choice set만 저장 | 최종 결정 화면은 이전 선택 카드를 잃지 않고 같은 request 계열로 표시 | 박수 같은 1차 선택 카드가 2차 최종 결정에서 사라지지 않음 | `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_first_human_draft_resume_auto_resolves_forced_draft_before_final_character`, `apps/web/src/domain/selectors/promptSelectors.spec.ts` |
| MRN-MOD-003 | 산적 지목 후 잔꾀 | 산적이 지목한 뒤 같은 턴 잔꾀 prompt가 열림 | `CharacterStartModule -> TargetJudicatorModule -> TrickSequenceFrame` | 잔꾀 prompt checkpoint는 부모 턴의 `frame_id`와 자식 `module_id/module_cursor`를 저장 | decision은 `buildDecisionMessage`로 continuation을 그대로 반환 | 잔꾀 재개가 `CharacterStartModule`을 재실행하지 않아 지목 prompt가 다시 열리지 않음 | `engine/test_runtime_sequence_modules.py::test_bandit_mark_then_trick_followup_never_replays_target_or_trick_window`, `apps/server/tests/test_prompt_module_continuation.py`, `apps/web/src/hooks/useGameStream.spec.ts` |
| MRN-MOD-004 | 잔꾀 후속 선택 | 잔꾀 카드가 후속 대상/보상 선택을 요구 | `TrickChoiceModule -> TrickResolveModule -> TrickDeferredFollowupsModule` | Redis는 같은 `TrickSequenceFrame` 안의 다음 `module_cursor`만 갱신 | 프론트는 새 prompt를 같은 prompt surface로 교체하고 이전 request 중복 전송을 막음 | 후속 선택은 턴 루프 재진입이 아니라 잔꾀 시퀀스 내부 반복 | `engine/test_runtime_sequence_modules.py`, `engine/test_runtime_prompt_continuation.py` |
| MRN-MOD-005 | 운수 추가 이동/도착 | 운수 결과가 추가 주사위, 이동, 도착을 생성 | `FortuneResolveModule -> MapMoveModule -> ArrivalTileModule`, 임대료 발생 시 `RentPaymentModule -> LandingPostEffectsModule` | 추가 액션은 `ActionSequenceFrame`으로 저장되며 새 턴 checkpoint를 만들지 않고, action payload는 해당 native module과 일치해야 함 | stream runtime projection은 active module을 fortune/move/arrival/rent/post-effect 순서로 표시 | 운수 추가 행동은 현재 시퀀스의 후속 모듈이며 턴 스케줄러를 다시 호출하지 않음 | `engine/test_runtime_sequence_modules.py`, `engine/test_runtime_sequence_handlers.py`, `engine/test_runtime_effect_inventory.py`, `apps/server/tests/test_runtime_semantic_guard.py`, `npm run e2e:module-runtime` |
| MRN-MOD-006 | 건설업자 무료 구매 | 건설업자 턴의 착지 구매 prompt | `CharacterStartModule -> ModifierRegistry -> PurchaseDecisionModule -> PurchaseCommitModule` | modifier registry가 `builder_free_purchase`를 저장하고 구매 prompt/commit에서만 참조하며 purchase action은 native purchase module에만 저장 | 구매 prompt는 일반 구매 surface를 유지하고 비용 breakdown만 반영 | module runner에서는 카드 이름만으로 무료 구매가 적용되지 않음 | `engine/test_runtime_turn_handlers.py`, `engine/test_runtime_sequence_modules.py`, `engine/test_tile_effects.py`, `engine/test_runtime_effect_inventory.py`, `apps/server/tests/test_runtime_semantic_guard.py`, `npm run e2e:module-runtime` |
| MRN-MOD-007 | 파발꾼 주사위 modifier | 파발꾼이 +1/-1 주사위 모드를 선택 | `CharacterStartModule -> DiceRollModule` | `pabalggun_dice_delta` single-use modifier가 저장되고 소비 시 consumed 처리 | 주사위 prompt/결과 event는 modifier 반영 후 값을 표시 | 주사위 보정은 이동/도착이 아니라 DiceRollModule에서만 결정됨 | `engine/test_runtime_turn_handlers.py`, `engine/test_runtime_effect_inventory.py` |
| MRN-MOD-008 | 어사 무뢰 억제 modifier | 어사가 활성이고 무뢰 인물이 턴을 시작 | `CharacterModifierSeedModule -> CharacterStartModule -> TargetJudicatorModule` | 억제 modifier가 대상 player id에 귀속되어 round scope로 저장 | 프론트는 억제된 인물의 불가능한 prompt를 받지 않음 | 산적/자객 이름을 if문으로 빼는 대신 억제 modifier 때문에 능력 모듈이 비활성화됨 | `engine/test_runtime_effect_inventory.py`, `engine/test_runtime_target_judicator_modules.py` |
| MRN-MOD-009 | 재보급 동시 응답 | 종료 값이 설정 배수와 일치해 모든 대상이 짐 처리/재보급 | `ConcurrentResolutionSchedulerModule -> SimultaneousResolutionFrame -> SimultaneousProcessingModule -> SimultaneousPromptBatchModule -> ResupplyModule -> SimultaneousCommitModule -> CompleteSimultaneousResolutionModule` | `resolve_supply_threshold`는 동시응답 프레임으로 승격되고, `SimultaneousPromptBatchContinuation`이 player별 응답과 batch id를 저장 | 각 프론트는 자기 prompt에 같은 `batch_id`/`missing_player_ids`/`resume_tokens_by_player_id`를 받고 응답 완료 후 대기 상태가 됨 | 순차 턴 모듈이 아니라 모든 대상 응답이 모일 때까지 동시응답 프레임이 소유 | `engine/test_runtime_simultaneous_modules.py::test_resupply_module_commits_only_after_all_batch_responses`, `apps/server/tests/test_runtime_semantic_guard.py::test_checkpoint_allows_matching_simultaneous_resupply_action_module`, `apps/server/tests/test_runtime_service.py`, `apps/web/src/domain/selectors/promptSelectors.spec.ts` |
| MRN-MOD-010 | 라운드 종료 카드 플립 | 모든 턴과 턴 종료 스냅샷이 완료 | `TurnEndSnapshotModule -> RoundEndCardFlipModule` | `TurnEndSnapshotModule`은 turn frame에서만 유효하고, active turn context가 없는 라운드 프레임 checkpoint에서만 marker/card flip event publish | 프론트는 라운드 종료 event로만 카드 플립 애니메이션/상태 갱신 | 턴 중간 marker flip event와 sequence-owned turn-end module는 구조상 emit될 수 없음 | `engine/test_runtime_round_modules.py`, `engine/test_runtime_sequence_modules.py`, `apps/server/tests/test_runtime_semantic_guard.py` |
| MRN-MOD-011 | 프론트 중복 결정 전송 | 더블클릭, replay recovery, 재연결 직후 동일 prompt 응답 | `PromptContinuation`이 가리키는 현재 module | backend idempotency와 request ledger가 같은 request 재처리를 막음 | `createDecisionRequestLedger`가 stream key별 중복 전송을 차단 | 같은 request id decision은 네트워크 레벨에서도 한 번만 나감 | `apps/web/src/hooks/useGameStream.spec.ts`, `apps/server/tests/test_stream_module_idempotency.py` |
| MRN-MOD-012 | prompt continuation mismatch | 오래된 prompt 또는 다른 module의 decision이 도착 | 현재 활성 prompt module | `resume_token/frame_id/module_id/module_type/module_cursor/batch_id` mismatch면 reject | 프론트는 backend-issued continuation 외 값을 만들지 않음 | 백엔드는 추정 재개를 하지 않고 현재 모듈과 일치할 때만 처리 | `apps/server/tests/test_prompt_module_continuation.py`, `apps/web/src/hooks/useGameStream.spec.ts` |
| MRN-MOD-013 | 남의 토지 도착 임대료 | 플레이어가 소유자가 다른 토지에 도착 | `ArrivalTileModule -> RentPaymentModule -> LandingPostEffectsModule` | `resolve_arrival`은 임대료 action만 큐잉하고, `resolve_rent_payment`가 현금/파산 mutation을 소유하며, 후처리는 별도 checkpoint로 이어짐 | 프론트는 도착, 임대료 지불, 같은 칸 보너스/인접 구매 후처리를 순차 module event로 받음 | 임대료 지불은 도착 모듈 재실행이나 후처리 재개 중 중복 차감되지 않음 | `engine/test_engine_resumable_checkpoint.py`, `engine/test_runtime_sequence_modules.py`, `apps/server/tests/test_runtime_semantic_guard.py`, `npm run e2e:module-runtime` |
| MRN-MOD-014 | 재보급 eligible 스냅샷 재개 | 재보급 prompt가 일부 응답 후 Redis checkpoint에서 재개 | `SimultaneousResolutionFrame -> SimultaneousProcessingModule -> SimultaneousPromptBatchModule -> ResupplyModule -> SimultaneousCommitModule -> CompleteSimultaneousResolutionModule` | action payload와 active batch는 `eligible_burden_deck_indices_by_player`와 processed 목록을 저장하고 재개 시 현재 손패로 재계산하지 않음 | 프론트는 `burden_exchange` prompt를 `SimultaneousResolutionFrame`의 완전한 batch wire state에서만 활성으로 취급 | 새로 뽑힌 짐은 이미 시작된 재보급 threshold chain에 끼어들 수 없음 | `engine/test_runtime_simultaneous_modules.py::test_resupply_module_uses_action_eligibility_snapshot_when_resuming`, `apps/server/tests/test_runtime_service.py`, `apps/web/src/domain/selectors/promptSelectors.spec.ts` |
| MRN-MOD-015 | 잔꾀 후속 재시도 idempotency | `TrickResolveModule`이 후속 잔꾀 선택을 삽입한 뒤 worker 재시도/복구로 같은 module을 다시 처리 | `TrickResolveModule -> TrickChoiceModule` in same `TrickSequenceFrame` | `followup_choice_module_id`가 module payload에 저장되고 재시도 시 기존 후속 선택만 재사용 | 프론트는 같은 후속 prompt surface만 유지하고 추가 잔꾀 prompt를 받지 않음 | 같은 resolve module에서 후속 선택이 두 번 삽입되지 않아 잔꾀-지목-잔꾀 루프가 구조적으로 차단됨 | `engine/test_runtime_sequence_modules.py::test_bandit_mark_then_trick_followup_never_replays_target_or_trick_window`, `apps/server/tests/test_prompt_module_continuation.py`, `apps/web/src/hooks/useGameStream.spec.ts` |

## 4. 자동화 운영

- 이 문서의 필수 시나리오 ID와 자동화 링크는 `tests/test_module_runtime_playtest_matrix_doc.py`가 감시한다.
- 구조 테스트의 중심축은 `engine/test_runtime_effect_inventory.py`, `engine/test_runtime_sequence_modules.py`, `engine/test_runtime_turn_handlers.py`, `engine/test_tile_effects.py`다.
- native sequence handler 검증은 `engine/test_runtime_sequence_handlers.py`가 담당한다.
- 백엔드 continuation/checkpoint 검증은 `apps/server/tests/test_prompt_module_continuation.py`, `apps/server/tests/test_runtime_semantic_guard.py`, stream idempotency 테스트가 담당한다.
- 프론트 decision payload 보존은 `apps/web/src/hooks/useGameStream.spec.ts`의 `buildDecisionMessage` 테스트가 담당한다.
- 프론트 effect context의 자원 변화 표시 검증은 `apps/web/src/features/prompt/promptEffectContextDisplay.spec.ts`가 담당한다. 같은 테스트가 source player/family/name 칩 표시도 감시한다.
- 브라우저 모듈 런타임 회귀 시작점은 `npm run e2e:module-runtime`이다.

## 5. 수동 플레이테스트 기록 규칙

수동 플레이테스트 로그는 각 시나리오 ID를 붙여 기록한다. 예를 들어 산적 지목 후 잔꾀 루프가 의심되면 `MRN-MOD-003`, 운수 추가 이동이 턴 재시작처럼 보이면 `MRN-MOD-005`, 카드 플립이 턴 중 발생하면 `MRN-MOD-010`, 재보급 중 새 짐 카드가 같은 threshold chain에 섞이면 `MRN-MOD-014`로 표시한다.

## 6. 1-5 회귀 묶음

이번 구조 회귀 묶음은 다음 순서로 확인한다.

기계 판독용 회귀 pack은 `packages/runtime-contracts/ws/examples/round-combination.regression-pack.json`에 둔다. 문서/fixture/브라우저 시작점은 `tests/test_module_runtime_playtest_matrix_doc.py`가 함께 감시하며, 브라우저 회귀 시작점은 `npm run e2e:module-runtime`이다.

1. `MRN-MOD-003`/`MRN-MOD-004`/`MRN-MOD-015`: 산적 지목 후 잔꾀를 사용하고, 후속 잔꾀 선택이 필요한 카드에서 worker 재시도 또는 재연결이 있어도 `CharacterStartModule`과 `TargetJudicatorModule`이 다시 열리지 않는지 확인한다.
2. `MRN-MOD-005`: 모든 `resolve_fortune_*` 결정형 운수 action이 `FortuneResolveModule -> MapMoveModule -> ArrivalTileModule`로 이어지고 새 `TurnFrame`을 만들지 않는지 확인한다.
3. `MRN-MOD-010`: `TurnEndSnapshotModule`은 active `TurnFrame`에서 턴을 닫고, `RoundEndCardFlipModule`은 모든 `PlayerTurnModule`과 child frame이 종료된 뒤에만 실행되는지 확인한다.
4. `MRN-MOD-014`: 재보급은 `SimultaneousResolutionFrame`만 소유하고, 일반 액션 시퀀스 또는 턴 순차 모듈에 들어가지 않는지 확인한다.
5. 공통: 위 시나리오의 prompt/decision stream은 backend-issued continuation을 그대로 왕복하고, 프론트 생성 request id나 stale continuation이 엔진을 진행시키지 않는지 확인한다.
6. 프론트 prompt surface: backend `effect_context.source_player_id`/`source_family`/`source_name`/`resource_delta`가 있으면 prompt overlay에 원인 플레이어, 원인 유형, 카드/날씨 이름, 현금/승점/조각/짐/카드 증감을 표시하고, 0 또는 unknown delta는 표시하지 않는지 확인한다.

Wire 계약은 모든 단일 prompt에 `request_id`/`request_type`/`player_id`와 `frame_id`/`module_id`/`module_type`/`module_cursor`가 포함되어야 한다. 동시 응답 prompt는 추가로 `batch_id`/`missing_player_ids`/`resume_tokens_by_player_id`를 포함해야 하며, module runner 재개는 `round_setup_replay_base`, `pending_prompt_instance_id - 1`, `frontend-created request id`를 재실행 근거로 사용하지 않는다.

Prompt/decision 계약 매트릭스는 회귀 pack의 `prompt_decision_contract_matrix`에 기계 판독 가능한 형태로 고정한다.

잔꾀/지목 루프 차단 불변식은 다음 문장으로 고정한다. TrickWindowModule may suspend only into a child TrickSequenceFrame. completed pre-trick modules must not replay after TrickSequenceFrame completion. `SimultaneousPromptBatchContinuation`은 순차 턴 재개가 아니라 동시응답 batch 재개 계약이다.

| request_type | 프레임 계약 | 소유 모듈 | 재개 계약 | 재실행 금지 |
| --- | --- | --- | --- | --- |
| `mark_target` | `TurnFrame` | `CharacterStartModule`, `TargetJudicatorModule` | `PromptContinuation` | must not reopen CharacterStartModule |
| `trick_to_use` | `TrickSequenceFrame` | `TrickWindowModule`, `TrickChoiceModule` | `PromptContinuation` | must not reopen TrickWindowModule |
| `hidden_trick_card` | `TrickSequenceFrame` | `TrickChoiceModule`, `TrickResolveModule` | `PromptContinuation` | must not insert duplicate followup TrickChoiceModule |
| `specific_trick_reward` | `TrickSequenceFrame` | `TrickResolveModule`, `TrickDeferredFollowupsModule` | `PromptContinuation` | must not leave current TrickSequenceFrame |
| `movement` | `TurnFrame` | `DiceRollModule`, `MapMoveModule`, `ArrivalTileModule` | `PromptContinuation` | must not create a new TurnFrame |
| `lap_reward` | `ActionSequenceFrame` | `LapRewardModule` | `PromptContinuation` | must not rerun MovementResolveModule |
| `purchase_tile` | `ActionSequenceFrame` | `PurchaseDecisionModule`, `PurchaseCommitModule` | `PromptContinuation` | must not rerun ArrivalTileModule |
| `coin_placement` | `ActionSequenceFrame` | `ScoreTokenPlacementPromptModule`, `ScoreTokenPlacementCommitModule` | `PromptContinuation` | must not rerun PurchaseCommitModule |
| `burden_exchange` | `SimultaneousResolutionFrame` | `SimultaneousPromptBatchModule`, `ResupplyModule`, `SimultaneousCommitModule` | `SimultaneousPromptBatchContinuation` | must not recalculate eligible burden cards |

Redis 재개 증거는 회귀 pack의 `redis_resume_evidence`와 아래 테스트 이름이 함께 고정한다.

- `MRN-MOD-003`: `PromptContinuation + TrickSequenceFrame` 계약으로 `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_preserves_checkpoint_frame_stack_without_replay`와 `apps/server/tests/test_command_wakeup_worker.py::CommandStreamWakeupWorkerTests::test_wakeup_worker_prefers_command_processing_hook_before_offset`를 통과해야 한다.
- `MRN-MOD-004`: `PromptContinuation + TrickSequenceFrame` 계약으로 `engine/test_runtime_sequence_modules.py::test_trick_followup_runs_inside_child_sequence_before_turn_dice`와 `engine/test_runtime_prompt_continuation.py::test_resume_rejects_same_module_with_stale_cursor`를 통과해야 한다.
- `MRN-MOD-005`: `PromptContinuation + ActionSequenceFrame` 계약으로 `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_prompt_boundary_matrix_preserves_checkpoint_without_replay`와 `apps/server/tests/test_command_wakeup_worker.py::CommandStreamWakeupWorkerTests::test_wakeup_worker_prefers_command_processing_hook_before_offset`를 통과해야 한다.
- `MRN-MOD-014`: `SimultaneousPromptBatchContinuation + SimultaneousResolutionFrame` 계약으로 `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_simultaneous_batch_continuation_survives_service_reconstruction`와 `apps/server/tests/test_command_wakeup_worker.py::CommandStreamWakeupWorkerTests::test_wakeup_worker_prefers_command_processing_hook_before_offset`를 통과해야 한다.
- `MRN-MOD-015`: `PromptContinuation + TrickSequenceFrame` 계약으로 `engine/test_runtime_sequence_modules.py::test_trick_resolve_followup_insertion_is_idempotent_on_module_retry`와 `engine/test_runtime_sequence_modules.py::test_bandit_mark_then_trick_followup_never_replays_target_or_trick_window`를 통과해야 한다.
