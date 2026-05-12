# MRN Core Rule, Decision, Prompt, and Simultaneous Flow Reference

Status: current reference
Date: 2026-05-12
Audience: server/runtime implementers, external AI worker implementers, playtest harness maintainers

이 문서는 게임의 핵심 룰과 결정 절차를 한 곳에 고정한다. 목적은 "서버가 무엇을 결정하고, 플레이어/AI가 무엇을 선택하며, 동시 진행은 어디에서 어떻게 닫히는가"를 구현 관점에서 명확히 하는 것이다.

## 1. 근거 파일

이 문서는 아래 파일을 기준으로 정리했다.

- `docs/current/Game-Rules.md`
- `docs/current/runtime/round-action-control-matrix.md`
- `engine/runtime_modules/contracts.py`
- `engine/runtime_modules/prompts.py`
- `engine/runtime_modules/round_modules.py`
- `engine/runtime_modules/turn_modules.py`
- `engine/runtime_modules/sequence_modules.py`
- `engine/runtime_modules/simultaneous.py`
- `engine/decision_port.py`
- `packages/runtime-contracts/external-ai/README.md`
- `apps/server/src/services/decision_gateway.py`
- `apps/server/src/services/external_ai_worker_service.py`

## 2. 핵심 원칙

### 2.1 권위

서버/엔진이 권위자다.

- 룰 진행 순서는 서버 런타임 모듈이 결정한다.
- 플레이어와 외부 AI는 서버가 연 프롬프트에 대해 `choice_id` 하나를 고른다.
- 선택 가능한 항목은 서버가 제공한 `legal_choices`가 전부다.
- 클라이언트, 외부 AI, 테스트 스크립트는 새 선택지를 만들 수 없다.
- 프롬프트가 닫힌 뒤 도착한 응답은 같은 진행을 다시 열면 안 된다.

### 2.2 프롬프트는 진행 중단점이다

프롬프트는 "사용자에게 물어보는 UI"가 아니라 런타임 진행의 중단점이다.

프롬프트는 반드시 다음 정보를 가져야 한다.

- `request_id`: 이 질문의 고유 ID
- `request_type`: 질문 종류
- `player_id`: 응답해야 하는 플레이어
- `frame_id`: 어떤 진행 프레임에서 열린 질문인지
- `module_id`: 어떤 모듈이 연 질문인지
- `module_type`: 모듈 타입
- `module_cursor`: 같은 모듈 안에서의 재개 위치
- `resume_token`: 재개 권한 토큰
- `legal_choices`: 허용된 선택지 목록
- `public_context`: 선택 판단에 필요한 공개 문맥
- `expires_at_ms`: 만료 시간

응답은 `choice_id`를 포함해야 하며, 이 값은 해당 프롬프트의 `legal_choices` 안에 있어야 한다.

### 2.3 진행 단위

런타임 진행은 프레임과 모듈로 나뉜다.

- `round` frame: 라운드 전체 진행
- `turn` frame: 한 플레이어의 턴 진행
- `sequence` frame: 트릭, 이동 후 도착, 구매, 보상처럼 한 턴 내부의 하위 절차
- `simultaneous` frame: 여러 플레이어의 선택을 같은 논리 시점에 모으는 절차

모듈은 프레임 안에서 실행되는 최소 진행 단위다. 모듈이 프롬프트를 열면, 응답은 같은 `frame_id`, `module_id`, `module_cursor`, `resume_token`으로 돌아와야 한다.

## 3. 게임 시작 상태

기본 게임은 4인이다.

초기 자원은 다음과 같다.

- 현금: 20
- 파편: 2
- 점수 토큰: 0
- 트릭 카드: 5장
- 숨김 트릭 슬롯: 1장만 숨김
- 나머지 트릭 카드는 공개

시작 보상은 20PT다.

- 파편 1개: 3PT
- 점수 토큰 1개: 3PT
- 현금 1개: 2PT

시작 보상 선택은 구현상 `start_reward` 프롬프트로 표현될 수 있다. 서버는 선택 가능한 보상 조합을 `legal_choices`로 만들고, 플레이어/AI는 하나를 고른다.

## 4. 라운드 절차

라운드는 아래 순서로 진행된다.

1. 라운드 시작
2. 초기 보상 또는 라운드 시작 보정
3. 날씨 공개
4. 캐릭터 드래프트
5. 턴 순서 산정
6. 각 플레이어 턴 실행
7. 라운드 종료 카드 뒤집기
8. 라운드 정리 및 다음 라운드 준비

현재 런타임의 라운드 모듈 타입은 다음과 같다.

- `RoundStartModule`
- `InitialRewardModule`
- `WeatherModule`
- `DraftModule`
- `TurnSchedulerModule`
- `PlayerTurnModule`
- `RoundEndCardFlipModule`
- `RoundCleanupAndNextRoundModule`

라운드 종료 카드 뒤집기는 모든 플레이어 턴이 끝나고, 활성 하위 프레임이 없을 때만 실행되어야 한다. 활성 `turn`, `sequence`, `simultaneous` frame이 남아 있으면 라운드 종료 뒤집기는 아직 실행하면 안 된다.

## 5. 날씨 룰

날씨는 라운드마다 공개된다.

- 날씨는 공용 정보다.
- 날씨는 각 플레이어가 선택한 캐릭터의 속성에 영향을 준다.
- 날씨는 개인 보상 카드가 아니다.
- 날씨 효과 적용 여부는 서버가 현재 라운드 상태와 캐릭터 상태를 기준으로 판단한다.

날씨 공개 자체는 선택 프롬프트가 아니다. 다만 날씨 효과 때문에 이후 선택지나 계산 결과가 달라질 수 있다.

## 6. 캐릭터 드래프트

캐릭터 드래프트는 라운드 초반에 실행된다.

절차는 다음과 같다.

1. 캐릭터 카드를 섞는다.
2. 4장을 공개한다.
3. 1차 드래프트를 진행한다.
4. 다시 4장을 공개한다.
5. 2차 드래프트를 1차와 반대 순서로 진행한다.
6. 각 플레이어는 자신이 받은 두 카드 중 최종 캐릭터 하나를 선택한다.

1차 드래프트 시작자는 마커 소유자다.

드래프트 방향은 마커 방향을 따른다.

2차 드래프트는 1차의 역순이다.

각 선택은 `draft_card` 프롬프트로 표현될 수 있다.

- 서버가 현재 공개 카드 중 해당 플레이어가 고를 수 있는 카드를 `legal_choices`에 넣는다.
- 플레이어/AI는 하나의 `choice_id`를 응답한다.
- 서버는 선택된 카드를 플레이어의 후보 카드로 이동한다.
- 이미 선택된 카드는 다음 플레이어의 `legal_choices`에 남으면 안 된다.

최종 캐릭터 선택은 `final_character` 프롬프트다.

- 기본적으로 플레이어가 가진 두 카드 중 하나를 고른다.
- 후보가 하나뿐이면 서버가 자동 확정할 수 있다.
- 최종 캐릭터 선택이 끝나야 턴 순서를 산정할 수 있다.

## 7. 캐릭터 우선순위와 턴 순서

캐릭터 카드에는 우선순위가 있다.

- 우선순위는 1부터 8까지다.
- 낮은 숫자가 먼저 행동한다.
- 최종 선택된 캐릭터의 우선순위가 해당 라운드 턴 순서의 기준이다.

턴 순서 산정은 `TurnSchedulerModule`의 책임이다.

프론트엔드나 외부 AI는 턴 순서를 직접 계산해 authoritative 상태로 제출하면 안 된다. UI 표시를 위해 같은 계산을 복제할 수는 있지만, 실제 진행은 서버 상태가 기준이다.

## 8. 플레이어 턴 절차

한 플레이어 턴은 아래 순서로 진행된다.

1. 턴 시작
2. 예약된 시작 액션 처리
3. 대상 표시/마크 효과 처리
4. 캐릭터 시작 능력 처리
5. 즉시 마커 이전 처리
6. 대상 판정 처리
7. 트릭 사용 창
8. 주사위 또는 주사위 카드 결정
9. 이동 처리
10. 도착 타일 처리
11. 바퀴 보상 처리
12. 운세 처리
13. 턴 종료 스냅샷

현재 런타임의 턴 모듈 타입은 다음과 같다.

- `TurnStartModule`
- `ScheduledStartActionsModule`
- `PendingMarkResolutionModule`
- `CharacterStartModule`
- `ImmediateMarkerTransferModule`
- `TargetJudicatorModule`
- `TrickWindowModule`
- `DiceRollModule`
- `MovementResolveModule`
- `MapMoveModule`
- `ArrivalTileModule`
- `LapRewardModule`
- `FortuneResolveModule`
- `TurnEndSnapshotModule`

중요한 점은 캐릭터 효과, 트릭, 이동, 도착 처리가 한 덩어리로 섞이면 안 된다는 것이다. 각 단계는 모듈 경계가 있고, 프롬프트 응답은 원래 모듈로 돌아와야 한다.

## 9. 마크/대상 지정 룰

마크 능력은 대상을 즉시 공격하는 구조가 아니다.

핵심 룰은 다음과 같다.

- 마크는 특정 플레이어가 아니라 특정 캐릭터를 대상으로 삼는다.
- 대상은 아직 턴을 시작하지 않은 캐릭터여야 한다.
- 이미 턴을 끝냈거나 진행 중인 캐릭터는 일반적으로 대상이 될 수 없다.
- 마크 효과는 지정 즉시 해결되는 것이 아니라 대상 캐릭터의 턴 시작 시점에 해결된다.
- 대상 캐릭터를 가진 플레이어의 턴이 시작되면 `PendingMarkResolutionModule`이 먼저 실행된다.

`mark_target` 프롬프트는 대상 캐릭터 선택이다.

서버는 현재 합법적인 대상 캐릭터를 `legal_choices`에 넣어야 한다.

예시는 다음과 같다.

- Bandit 계열: 대상에게 마크를 남기고 대상 턴 시작에 효과를 준다.
- Chuno 계열: 대상 턴 시작 시 대상을 Chuno 위치로 끌어오고, 그 위치의 도착 처리를 먼저 실행할 수 있다.
- Baksu/Mansin 계열: 대상 턴 시작 시 캐릭터 시작 처리보다 앞서 효과를 발생시킨다.

마크 처리에서 중요한 불변식은 "대상 지정"과 "효과 발동"을 분리하는 것이다.

## 10. 트릭 카드 룰

플레이어는 트릭 카드를 가진다.

기본 구조는 다음과 같다.

- 시작 트릭 카드 수: 5장
- 숨김 슬롯: 1장
- 나머지 슬롯: 공개
- 일반적으로 한 턴에 트릭은 1장만 사용한다.
- 트릭 사용 타이밍은 캐릭터 능력 이후, 주사위 굴림 이전이다.

트릭 사용 창은 `TrickWindowModule`에서 열린다.

트릭 관련 sequence 모듈은 다음과 같다.

- `TrickChoiceModule`
- `TrickSkipModule`
- `TrickResolveModule`
- `TrickDiscardModule`
- `TrickDeferredFollowupsModule`
- `TrickVisibilitySyncModule`

트릭 선택은 `trick_to_use` 프롬프트다.

- 선택지는 사용 가능한 트릭 카드와 skip이다.
- 서버는 현재 타이밍에 사용할 수 없는 트릭을 `legal_choices`에 넣으면 안 된다.
- 플레이어가 skip을 고르면 트릭 해석 sequence는 skip 경로로 닫힌다.

숨김 트릭 관련 선택은 `hidden_trick_card` 프롬프트다.

- 숨김 트릭을 사용한 뒤 숨김 슬롯이 비면, 공개 카드 중 하나를 숨김 슬롯으로 옮기는 선택이 필요할 수 있다.
- 선택 가능한 공개 카드만 `legal_choices`에 들어가야 한다.

트릭 해결 중 후속 선택이 있으면 `specific_trick_reward` 같은 프롬프트가 열릴 수 있다.

- 이 프롬프트는 새 턴이나 새 트릭 창이 아니다.
- 원래 트릭 sequence 안에서 닫혀야 한다.
- 응답 후 `TrickDeferredFollowupsModule` 또는 관련 후속 모듈이 이어진다.

## 11. 주사위와 이동 룰

주사위 단계에서는 실제 주사위 또는 주사위 카드가 이동 값을 만든다.

주사위 카드 룰은 다음과 같다.

- 주사위 카드는 1부터 6까지 값이 있다.
- 주사위 카드는 실제 주사위 값을 대체할 수 있다.
- 주사위 개수에 따라 1장 또는 2장을 사용할 수 있다.
- 주사위 카드는 개인 인벤토리다.

관련 프롬프트는 다음과 같다.

- `pabal_dice_mode`: 주사위 모드 선택
- `dice_card_value`: 사용할 주사위 카드 값 선택
- `movement`: 이동 선택
- `runaway_step_choice`: 도망/단계 이동 선택

`movement` 프롬프트는 이동 가능한 후보 중 하나를 고르는 질문이다.

- 서버는 현재 룰로 가능한 이동 후보만 `legal_choices`에 넣는다.
- 이동 응답은 새 턴을 만들면 안 된다.
- 응답은 현재 `TurnFrame` 또는 관련 action sequence로 돌아와야 한다.
- 이동 후에는 `MapMoveModule`과 `ArrivalTileModule`이 이어진다.

## 12. 바퀴 보상 룰

바퀴 보상은 시작점을 지나거나 조건을 만족했을 때 발생한다.

기본 바퀴 보상은 10PT다.

- 파편 1개: 3PT
- 점수 토큰 1개: 3PT
- 현금 1개: 2PT

`lap_reward` 프롬프트는 보상 조합 선택이다.

- 서버는 보상 포인트 안에서 가능한 조합만 `legal_choices`에 넣는다.
- 응답은 `LapRewardModule` 또는 관련 action sequence로 돌아간다.
- 보상 지급 후 같은 도착 처리 흐름이 계속된다.

## 13. 도착 타일 룰

이동이 끝나면 도착 타일을 처리한다.

대표 분기는 다음과 같다.

- 운세 타일
- 무소유 타일
- 자기 소유 타일
- 타인 소유 타일
- 파산 플레이어가 남긴 hostile 타일
- 특수 타일

무소유 타일에서는 구매 여부를 물을 수 있다.

`purchase_tile` 프롬프트는 타일 구매 선택이다.

- 구매 가능하면 buy/skip 또는 구체 구매안이 `legal_choices`에 들어간다.
- 구매 불가능하면 프롬프트를 열지 않거나 skip만 허용해야 한다.
- 구매 불가 자체는 파산이 아니다.

자기 소유 타일에서는 점수 토큰 배치가 가능할 수 있다.

`coin_placement` 프롬프트는 점수 토큰 배치 선택이다.

- 한 타일에는 최대 3개까지 놓을 수 있다.
- 첫 구매 턴에는 최대 1개 제한이 있다.
- 서버는 남은 토큰, 타일 상태, 제한을 계산해 합법 선택지만 제공한다.

타인 소유 타일에서는 기본적으로 임대료를 낸다.

- 트릭, 날씨, 운세, 캐릭터 효과가 임대료를 바꿀 수 있다.
- Swindler 계열 효과는 타일 탈취를 일으킬 수 있다.
- 지급 불능이면 파산 처리로 이어질 수 있다.

파산 플레이어의 소유 타일은 hostile 타일이 된다.

- hostile 타일 임대료는 구매가의 3배다.
- 임대료는 은행에 지급한다.

## 14. 운세 룰

운세 타일에 도착하면 운세 카드를 열고 즉시 해결한다.

운세의 특징은 다음과 같다.

- 운세는 공개된 순간 해당 플레이어에게 적용된다.
- 운세는 날씨와 다르게 개인 효과다.
- 운세가 이동을 발생시킬 수 있다.
- 운세 이동 후 도착한 위치에서도 도착 처리, 임대료, 구매, 캐릭터 효과가 이어질 수 있다.

운세 관련 action type은 `resolve_fortune_*` 형태로 `FortuneResolveModule`에 매핑된다.

운세가 추가 선택을 요구하면 서버는 해당 시점의 프롬프트를 열어야 한다. 외부 AI가 운세 효과를 독자적으로 계산해서 상태를 제출하면 안 된다.

## 15. 마커와 방향 룰

마커는 다음 라운드 드래프트의 시작자와 방향을 결정한다.

핵심은 다음과 같다.

- 마커 소유자가 다음 드래프트의 1차 시작자다.
- 마커 방향이 1차 드래프트 방향이다.
- 2차 드래프트는 1차와 반대 방향이다.
- 특정 캐릭터 선택이나 효과가 라운드 종료 시 마커를 가져가거나 방향을 정할 수 있다.

Doctrine 계열 캐릭터는 최종 선택 또는 라운드 종료 시점에 마커/방향과 관련된 선택을 만들 수 있다.

관련 프롬프트는 다음과 같다.

- `active_flip`: 다음 라운드에 사용할 활성 면 선택
- `doctrine_relief`: Doctrine 계열 구제/보정 선택

마커 이전이 즉시 발생하는 경우 `ImmediateMarkerTransferModule`이 담당한다.

라운드 종료 카드 뒤집기와 활성 면 변경은 모든 플레이어 턴과 하위 프레임이 닫힌 뒤에만 실행되어야 한다.

## 16. 카드 뒤집기와 활성 면

캐릭터 카드는 양면이다.

- 한 시점에 하나의 면만 활성이다.
- 일부 캐릭터는 라운드 종료 시 활성 면을 바꿀 수 있다.
- 활성 면 변경은 다음 라운드 효과와 우선순위 산정에 영향을 줄 수 있다.

`active_flip` 프롬프트는 활성 면 선택이다.

- 서버는 뒤집을 수 있는 카드와 면만 선택지로 제공한다.
- 이미 확정된 라운드 진행 중간에 임의로 활성 면을 바꾸면 안 된다.
- 라운드 종료 처리 경계에서 닫혀야 한다.

## 17. 보급과 부담 카드

트릭 카드 보급은 특정 시점에 발생한다.

기본 룰은 다음과 같다.

- 종료 시간이 3의 배수일 때 보급이 발생한다.
- 빈 트릭 슬롯을 채운다.
- 덱이 부족하면 discard를 섞어 다시 덱으로 만들 수 있다.
- 부담 카드는 보급 시점에 비용을 내고 제거할 수 있다.

부담 카드 제거는 여러 플레이어가 같은 논리 시점에 선택해야 할 수 있다.

이 경우 단일 프롬프트가 아니라 `simultaneous` frame을 사용한다.

`burden_exchange` 프롬프트는 각 참가자에게 개별로 열리지만, 커밋은 batch 단위다.

## 18. 동시 진행 룰

동시 진행은 "서버가 여러 게임을 동시에 돌린다"는 뜻이 아니다. 한 게임 안에서 여러 플레이어의 선택을 같은 논리 시점에 수집해야 하는 절차다.

현재 동시 진행 모듈은 다음과 같다.

- `SimultaneousProcessingModule`
- `SimultaneousPromptBatchModule`
- `ResupplyModule`
- `SimultaneousCommitModule`
- `CompleteSimultaneousResolutionModule`

동시 프롬프트 배치는 `SimultaneousPromptBatchContinuation`으로 표현된다.

필수 필드는 다음과 같다.

- `batch_id`: 배치 고유 ID
- `frame_id`: simultaneous frame ID
- `module_id`: 배치를 연 모듈 ID
- `module_type`: 모듈 타입
- `request_type`: 보통 `burden_exchange`
- `participant_player_ids`: 참가자 목록
- `prompts_by_player_id`: 플레이어별 프롬프트
- `responses_by_player_id`: 수집된 응답
- `missing_player_ids`: 아직 응답하지 않은 플레이어
- `eligibility_snapshot`: 참가 자격 스냅샷
- `commit_policy`: `all_required` 또는 `timeout_default`
- `default_policy`: 타임아웃 기본 선택 정책
- `expires_at_ms`: 만료 시간

커밋 조건은 다음과 같다.

- `all_required`: 모든 필수 참가자의 응답이 있어야 커밋한다.
- `timeout_default`: 만료된 참가자에게 기본 선택을 적용한 뒤 커밋할 수 있다.

중요한 불변식은 다음과 같다.

- 한 참가자의 응답만으로 전체 보급 결과를 부분 커밋하면 안 된다.
- `missing_player_ids`가 남아 있는데 `all_required` 배치를 완료 처리하면 안 된다.
- batch 응답은 같은 `batch_id`, `frame_id`, `module_id`, `resume_token`에 귀속되어야 한다.
- 동시 배치 응답이 같은 게임의 무관한 단일 프롬프트를 닫거나 supersede하면 안 된다.
- 보급 경계인 `resolve_supply_threshold`는 일반 sequence frame이 아니라 simultaneous frame으로 승격되어야 한다.

## 19. 프롬프트 타입 목록

현재 서버/AI 경계에서 중요한 `request_type`은 다음과 같다.

| request_type | 질문 | 선택 주체 | 핵심 선택지 | 닫힌 뒤 진행 |
| --- | --- | --- | --- | --- |
| `start_reward` | 시작 보상 조합 | 해당 플레이어 | 20PT 내 자원 조합 | 초기 보상 확정 |
| `draft_card` | 드래프트 카드 선택 | 해당 플레이어 | 공개된 합법 카드 | 후보 카드 획득 |
| `final_character` | 최종 캐릭터 선택 | 해당 플레이어 | 보유 후보 1~2장 | 턴 순서 산정 가능 |
| `mark_target` | 마크 대상 캐릭터 선택 | 능력 사용자 | 아직 턴 전인 합법 캐릭터 | 대상 턴 시작 예약 |
| `trick_to_use` | 트릭 사용 여부/카드 선택 | 턴 플레이어 | 사용 가능 트릭 또는 skip | 트릭 해결 또는 주사위 단계 |
| `hidden_trick_card` | 숨김 슬롯 보충 | 트릭 사용자 | 숨길 수 있는 공개 카드 | 트릭 가시성 동기화 |
| `specific_trick_reward` | 트릭 후속 보상 선택 | 트릭 사용자 | 트릭별 합법 선택 | 트릭 후속 처리 |
| `pabal_dice_mode` | 주사위 모드 선택 | 턴 플레이어 | 실제 주사위/카드 사용 모드 | 주사위 값 결정 |
| `dice_card_value` | 주사위 카드 값 선택 | 턴 플레이어 | 보유 주사위 카드 | 이동 값 결정 |
| `movement` | 이동 후보 선택 | 턴 플레이어 | 합법 이동 후보 | 이동 및 도착 처리 |
| `runaway_step_choice` | 특수 단계 이동 선택 | 턴 플레이어 | 가능한 단계 선택 | 이동 또는 후속 처리 |
| `lap_reward` | 바퀴 보상 선택 | 보상 대상 | 10PT 내 자원 조합 | 보상 지급 후 도착 처리 계속 |
| `purchase_tile` | 타일 구매 여부 | 도착 플레이어 | buy/skip 또는 구매안 | 소유권/비구매 처리 |
| `coin_placement` | 점수 토큰 배치 | 타일 소유자 | 0~허용 개수 | 점수 토큰 반영 |
| `geo_bonus` | 지리/지역 보너스 선택 | 대상 플레이어 | 보너스별 합법 선택 | 보너스 지급 |
| `doctrine_relief` | Doctrine 구제 선택 | 대상 플레이어 | 구제안 | 구제 처리 |
| `active_flip` | 활성 면 선택 | 카드 소유자 | 가능한 면 | 다음 라운드 상태 반영 |
| `burden_exchange` | 부담 카드 제거/유지 | 참가 플레이어들 | 제거/유지 또는 비용 지불안 | 동시 배치 커밋 후 보급 |

이 표에 없는 새 프롬프트를 추가하려면 먼저 다음을 정의해야 한다.

- 어떤 frame에서 열리는가
- 어떤 module이 여는가
- 응답 뒤 어떤 module cursor로 돌아가는가
- `legal_choices`는 무엇으로 구성되는가
- stale/duplicate/timeout 응답을 어떻게 처리하는가
- 단일 프롬프트인지 simultaneous batch인지

## 20. 응답 검증 절차

단일 프롬프트 응답은 다음 조건을 통과해야 한다.

1. `request_id`가 존재한다.
2. `resume_token`이 일치한다.
3. `frame_id`가 일치한다.
4. `module_id`가 일치한다.
5. `module_cursor`가 일치한다.
6. `player_id`가 일치한다.
7. `choice_id`가 `legal_choices` 안에 있다.
8. 프롬프트가 아직 유효하다.

하나라도 실패하면 해당 응답은 현재 진행을 재개할 수 없다.

동시 프롬프트 응답은 여기에 추가로 batch 조건을 확인해야 한다.

1. `batch_id`가 일치한다.
2. 응답 플레이어가 `participant_player_ids`에 포함된다.
3. 해당 플레이어의 prompt resume 정보가 일치한다.
4. 중복 응답 정책이 명확하다.
5. 응답 후 `missing_player_ids`를 갱신한다.
6. 커밋 조건을 만족할 때만 `SimultaneousCommitModule`로 넘어간다.

## 21. 외부 AI 선택 규약

외부 AI는 게임 상태를 변경하지 않는다.

외부 AI의 역할은 다음뿐이다.

1. 서버가 제공한 프롬프트를 받는다.
2. `public_context`와 허용된 선택지를 읽는다.
3. `legal_choices` 중 하나의 `choice_id`를 고른다.
4. 서버에 응답한다.

외부 AI가 하면 안 되는 일은 다음과 같다.

- 서버가 제공하지 않은 선택지를 생성
- 다음 모듈을 직접 지정
- 보상/임대료/이동 결과를 직접 커밋
- 숨김 정보를 근거로 선택
- 이미 닫힌 프롬프트를 재개
- 다른 플레이어의 프롬프트에 응답

`packages/runtime-contracts/external-ai/README.md`의 핵심도 같다. `legal_choices`가 권위 있는 선택지 목록이고, worker는 하나의 `choice_id`를 반환한다.

## 22. 웹소켓/상태 전파 관점의 절차

웹소켓은 룰의 권위자가 아니다. 상태와 프롬프트를 전달하는 통로다.

일반 절차는 다음과 같다.

1. 서버 런타임이 모듈을 실행한다.
2. 모듈이 자동으로 닫히면 상태 커밋과 view commit이 발생한다.
3. 모듈이 선택을 요구하면 prompt commit이 발생한다.
4. 서버는 웹소켓 또는 API를 통해 클라이언트/AI에게 프롬프트를 노출한다.
5. 클라이언트/AI가 선택을 제출한다.
6. 서버는 resume token과 choice를 검증한다.
7. 같은 frame/module cursor로 런타임을 재개한다.
8. 결과 상태와 다음 프롬프트 또는 다음 view commit을 발행한다.

따라서 UI에서 버튼이 보인다는 사실은 "선택 가능"의 근거가 아니다. 선택 가능 여부의 근거는 서버가 발행한 현재 prompt의 `legal_choices`다.

## 23. 파산 룰

파산은 지불 불능으로 발생한다.

핵심은 다음과 같다.

- 임대료나 비용을 낼 수 없으면 파산할 수 있다.
- 타일을 살 돈이 없는 것은 파산이 아니다.
- 파산 플레이어의 소유 타일은 hostile 타일로 남는다.
- hostile 타일의 임대료는 구매가의 3배다.
- hostile 임대료는 은행에 낸다.

파산 처리도 서버가 authoritative하게 수행한다. 외부 AI는 파산 여부를 직접 선언하지 않는다.

## 24. 재시도, 중복, stale 응답

프롬프트 기반 진행에서는 재시도와 중복 응답이 정상적으로 발생할 수 있다.

처리 원칙은 다음과 같다.

- 같은 `request_id`에 같은 응답이 다시 오면 idempotent하게 처리하거나 이미 처리됨으로 거절한다.
- 다른 `request_id`의 응답으로 현재 프롬프트를 닫으면 안 된다.
- 같은 `player_id`라도 `resume_token`이 다르면 재개하면 안 된다.
- 이전 module cursor의 응답은 현재 module cursor를 재개하면 안 된다.
- timeout으로 기본 선택이 적용된 뒤 늦게 온 응답은 상태를 되돌리면 안 된다.

이 원칙이 없으면 같은 게임에서 중복 이동, 중복 구매, 중복 트릭 보상, 중복 라운드 종료가 발생한다.

## 25. 반드시 지켜야 하는 불변식

아래는 구현 변경 시 깨지면 안 되는 조건이다.

1. `legal_choices` 밖의 선택은 절대 수락하지 않는다.
2. 응답은 원래 `frame_id`와 `module_id`로만 돌아간다.
3. prompt resume은 module cursor를 검증한다.
4. 마크 대상 지정과 마크 효과 발동은 분리한다.
5. 트릭 후속 선택은 새 턴을 만들지 않는다.
6. 이동 선택은 새 `TurnFrame`을 만들지 않는다.
7. `resolve_supply_threshold`는 simultaneous frame에서 처리한다.
8. simultaneous batch는 커밋 조건을 만족할 때만 커밋한다.
9. 라운드 종료 카드 뒤집기는 모든 플레이어 턴과 하위 프레임이 끝난 뒤에만 실행한다.
10. 외부 AI는 상태를 변경하지 않고 `choice_id`만 반환한다.
11. UI 상태는 서버 prompt/view commit을 반영할 뿐 룰 권위자가 아니다.
12. 구매 불능과 지불 불능을 구분한다.
13. 숨김 트릭 정보는 권한 없는 플레이어의 prompt context에 들어가면 안 된다.
14. 라운드 순서, 턴 순서, 마커 방향은 서버 상태에서 계산한다.
15. 자동 확정 가능한 선택은 프롬프트를 열지 않고 서버가 닫을 수 있다.

## 26. 서버 설계에서 이 문서가 의미하는 것

서버 로직 설계는 다음 구조를 만족해야 한다.

- 룰 계산은 런타임/엔진 쪽에 둔다.
- 네트워크 계층은 prompt 전달과 응답 접수만 담당한다.
- Redis나 DB는 prompt, state, view commit의 저장소일 뿐 룰 권위자가 아니다.
- 외부 AI worker는 선택자일 뿐 executor가 아니다.
- headless 테스트 스크립트는 플레이어 입력을 흉내낼 뿐 룰을 우회하면 안 된다.

특히 병렬 테스트에서 중요한 점은 두 종류의 동시성을 구분하는 것이다.

- 게임 인스턴스 동시성: 여러 게임 세션을 동시에 실행하는 서버/테스트 부하 문제
- 게임 내부 동시성: 한 게임 안에서 여러 플레이어 선택을 같은 논리 시점에 모으는 룰 문제

이 둘은 서로 다른 문제다. 게임 인스턴스가 20개 동시에 돈다고 해서 `SimultaneousPromptBatchContinuation`이 20개 게임을 묶는 것은 아니다. simultaneous frame은 한 게임 내부의 룰 경계다.

## 27. 구현 검토 체크리스트

관련 코드를 고칠 때는 최소한 아래를 확인한다.

- 새 prompt가 `request_type` 목록에 정의되어 있는가
- prompt builder가 `legal_choices`를 서버 상태에서 만드는가
- 외부 AI worker가 해당 `request_type`을 처리하는가
- 선택 결과가 원래 frame/module cursor로 돌아가는가
- timeout/default 정책이 필요한가
- 단일 prompt인지 batch prompt인지 명확한가
- prompt가 닫힌 뒤 view commit이 발생하는가
- 중복 응답을 처리해도 상태가 두 번 변하지 않는가
- 프론트엔드가 prompt의 `legal_choices`를 기준으로 버튼을 보여주는가
- headless 테스트가 서버가 제공한 choice만 선택하는가

## 28. 결론

이 게임의 핵심 구조는 "서버 권위 룰 진행 + 프롬프트 중단점 + 합법 선택지 응답 + frame/module resume"이다.

드래프트, 최종 캐릭터, 마크, 트릭, 이동, 구매, 보상, 부담 카드 제거는 모두 같은 원칙으로 처리된다. 서버가 현재 상태에서 가능한 선택지를 만들고, 플레이어/AI가 그중 하나를 고르며, 서버가 원래 진행 지점으로 돌아가 결과를 커밋한다.

동시 진행도 예외가 아니다. 여러 플레이어 응답을 batch로 모을 뿐, 커밋 권한은 서버의 simultaneous frame에 있다.
