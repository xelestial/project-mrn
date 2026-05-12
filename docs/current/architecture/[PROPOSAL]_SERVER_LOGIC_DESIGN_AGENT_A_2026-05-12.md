# 서버 권위 게임 로직 설계안

작성일: 2026-05-12
작성 범위: 현재 구현 구조를 전제로 하지 않는 장기 서버 권위(authoritative server) 설계 제안
주 근거: 제공된 게임 핵심 룰 요약

## 1. 설계 목표

이 설계의 핵심 목표는 프론트엔드, AI, 네트워크 클라이언트가 어떤 값을 보내더라도 게임 결과는 서버의 룰 엔진과 영속 이벤트 로그만으로 결정되게 만드는 것이다. 클라이언트는 선택지를 표시하고 의도를 제출할 뿐이며, 상태 변경의 권위는 서버가 가진다.

구체 목표는 다음과 같다.

- 모든 게임 상태 변경을 검증 가능한 커맨드와 도메인 이벤트로 표현한다.
- 라운드, 드래프트, 캐릭터 선택, 턴, 마크 효과, 트릭 카드, 이동, 도착지 처리, 지불, 파산, 점수 코인 배치를 하나의 순서 있는 상태 기계로 관리한다.
- 외부 입력 프롬프트는 서버가 만든 대기 결정(pending decision)에만 응답할 수 있게 한다.
- 재접속, 중복 요청, 서버 재시작, 워커 장애 후에도 이벤트 리플레이로 동일한 게임 상태를 복구한다.
- 웹소켓은 상태의 원천이 아니라 서버 이벤트를 배포하고 입력 의도를 전달하는 전송 계층으로 제한한다.
- 장기적으로 단일 서버 프로세스, 다중 서버, AI 워커, 관전 클라이언트가 같은 권위 모델 위에서 동작하게 한다.

## 2. 비목표

다음은 의도적으로 설계 목표에서 제외한다.

- 프론트엔드 로컬 상태를 신뢰해 서버 상태를 보정하는 방식.
- 웹소켓 메시지 순서에 게임 권위를 위임하는 방식.
- AI 응답이나 자동 플레이어의 결과를 검증 없이 이벤트로 기록하는 방식.
- 현재 구현 파일 구조에 맞춘 임시 어댑터 설계.
- 특정 DB, Redis, 메시지 큐 제품에 종속된 도메인 모델.
- 운영 편의를 위해 룰 검증을 일부 생략하는 빠른 처리 경로.

## 3. 도메인 모델과 상태 소유권

서버는 게임을 하나의 집합체(aggregate)로 다룬다. `Game` 집합체는 현재 국면, 플레이어, 캐릭터, 보드, 카드, 자원, 대기 입력, 예약 효과, 이벤트 버전을 소유한다.

핵심 상태는 다음처럼 나눈다.

- `GameSession`: 게임 ID, 참가자 4명, 설정, 현재 버전, 상태(`created`, `running`, `completed`, `aborted`).
- `RoundState`: 라운드 번호, 공개 날씨, 드래프트 패스 상태, 최종 캐릭터 선택 상태, 턴 순서, 라운드 종료 보충 대상 슬롯.
- `PlayerState`: 플레이어 ID, 선택 캐릭터, 위치, 랩 수, 현금, 조각, 점수 토큰, 보유지, 손패 5장, 숨김 카드 슬롯, 부담 카드, 파산 여부.
- `CharacterState`: 캐릭터 ID, 우선순위, 능력 정의, 공개 여부, 이번 라운드 선택자.
- `BoardState`: 타일 ID, 소유자, 가격, 통행료, 적대 상태, 행운/특수 효과 정의, 점수 코인 배치 상태.
- `CardState`: 덱, 버림 더미, 손패, 주사위 카드, 트릭 카드, 부담 카드, 종료 시간 슬롯.
- `TurnState`: 현재 턴 플레이어, 현재 단계, 턴 내 트릭 사용 여부, 이동 방식, 연쇄 효과 큐, 지불 대기, 선택 대기.
- `PendingDecision`: 서버가 발급한 외부 입력 요청. 종류, 대상 플레이어, 허용 선택지, 만료 정책, 관련 이벤트 버전, 중복 방지 키를 가진다.
- `ScheduledEffect`: 마크 능력처럼 미래 조건에 따라 발동하는 예약 효과. 대상 캐릭터, 발동 조건, 실패 조건, 원인 이벤트를 가진다.

상태 소유권 원칙은 단순해야 한다.

- 서버 룰 엔진만 `Game` 상태를 변경한다.
- 클라이언트와 AI는 `Command`만 제출한다.
- 영속 저장소는 이벤트 로그와 스냅샷을 보관하되 룰 판단을 하지 않는다.
- 웹소켓 게이트웨이는 권한 확인, 라우팅, 전송 확인까지만 담당한다.
- 읽기 모델은 표시 최적화용이며 권위 상태가 아니다.

## 4. 커맨드와 결정 수명주기

모든 외부 입력은 서버가 발급한 `PendingDecision`에 대한 응답이어야 한다. 서버가 묻지 않은 선택은 거부한다.

대표 커맨드는 다음과 같다.

- `SubmitDraftCardDecision`
- `SubmitFinalCharacterDecision`
- `SubmitTrickToUseDecision`
- `SubmitMovementDecision`
- `SubmitPurchaseTileDecision`
- `SubmitMarkTargetDecision`
- `SubmitActiveFlipDecision`
- `SubmitBurdenExchangeDecision`
- `SubmitLapRewardDecision`
- `SubmitRunawayStepDecision`
- `SubmitCoinPlacementDecision`
- `SubmitGeoBonusDecision`

커맨드 공통 필드는 다음과 같다.

- `game_id`
- `player_id`
- `decision_id`
- `client_command_id`
- `expected_game_version`
- `payload`
- `submitted_at`

처리 수명주기는 다음 순서로 고정한다.

1. 서버가 룰 진행 중 외부 입력이 필요한 지점에서 `PendingDecisionCreated` 이벤트를 기록한다.
2. 웹소켓 또는 폴링 읽기 모델로 해당 플레이어에게 프롬프트를 노출한다.
3. 클라이언트나 AI가 `decision_id`와 `client_command_id`를 포함해 커맨드를 제출한다.
4. 서버는 게임 ID, 플레이어 권한, decision 존재 여부, decision 상태, expected version, 선택지 유효성, 턴 단계 유효성을 검증한다.
5. 검증 성공 시 `PendingDecisionResolved`와 선택 결과에 따른 도메인 이벤트를 같은 원자적 커밋으로 기록한다.
6. 룰 엔진은 새 이벤트를 적용한 뒤 자동 진행 가능한 단계를 계속 실행한다.
7. 다음 외부 입력이 필요하면 새 `PendingDecision`을 만들고 멈춘다. 게임 종료 조건이면 `GameCompleted`를 기록한다.

중요한 점은 커맨드가 직접 상태를 바꾸지 않는다는 것이다. 커맨드는 의도이고, 상태 변경은 검증을 통과해 생성된 이벤트만 수행한다.

## 5. 이벤트 모델

이벤트는 불변이며 게임별 단조 증가 버전을 가진다. 모든 이벤트에는 `event_id`, `game_id`, `version`, `type`, `payload`, `causation_id`, `correlation_id`, `created_at`을 둔다.

대표 이벤트는 다음과 같다.

- `GameCreated`
- `PlayersSeated`
- `RoundStarted`
- `WeatherRevealed`
- `DraftPassStarted`
- `DraftCardOffered`
- `DraftCardSelected`
- `FinalCharacterPrompted`
- `FinalCharacterSelected`
- `TurnOrderEstablished`
- `TurnStarted`
- `ScheduledMarkEffectTriggered`
- `ScheduledMarkEffectDelayed`
- `ScheduledMarkEffectFailed`
- `CharacterAbilityResolved`
- `TrickCardUsed`
- `MovementDeclared`
- `MovementResolved`
- `TileArrived`
- `TilePurchased`
- `TollCharged`
- `TollPaid`
- `TileTakenOver`
- `FortuneResolved`
- `LapRewardGranted`
- `CoinPlacementResolved`
- `BurdenCardRemoved`
- `PlayerBankrupted`
- `TileMadeHostile`
- `RoundEnded`
- `EmptyTimedSlotsRefilled`
- `GameCompleted`

이벤트 이름은 UI 문구가 아니라 도메인 사실을 표현해야 한다. 예를 들어 "구매 버튼 클릭"이 아니라 `TilePurchased`를 기록한다.

## 6. 턴 처리 상태 기계

플레이어 턴은 명시적 단계로 분리한다.

1. `turn_opening`: 턴 시작, 대상 마크 효과 검사.
2. `mark_resolution`: 현재 캐릭터를 대상으로 예약된 마크 효과 처리. 대상 캐릭터가 없거나 공개되지 않았으면 룰에 따라 지연 또는 실패 이벤트를 기록한다.
3. `character_ability`: 캐릭터 능력 자동 처리 또는 필요한 선택 프롬프트 발급.
4. `trick_window`: 트릭 카드 사용 선택. 손패 5장, 숨김 1장, 턴당 최대 1장 조건을 서버가 검증한다.
5. `movement_choice`: 주사위 또는 주사위 카드 이동 선택.
6. `movement_resolution`: 이동 거리, 경로, 도착지를 확정한다.
7. `arrival_resolution`: 도착 효과, 행운, 연쇄 효과를 큐에 넣고 순서대로 처리한다.
8. `payment_resolution`: 구매, 통행료, 인수, 비용 지불, 지불 불능 검사를 처리한다.
9. `lap_reward`: 랩 보상 10PT 등 선택 또는 지급 처리.
10. `coin_placement`: 점수 코인 배치 선택이 필요한 경우 프롬프트 발급.
11. `turn_closing`: 턴 종료 불변식 검사 후 다음 턴으로 이동한다.

각 단계는 재진입 가능해야 한다. 서버가 장애 후 복구되면 이벤트 리플레이로 `TurnState`를 복원하고, 미완료 `PendingDecision` 또는 자동 진행 가능한 단계에서 다시 시작한다.

## 7. 웹소켓 계약

웹소켓은 세 가지 메시지 범주만 가진다.

- 서버 발행 이벤트 알림: 확정된 도메인 이벤트 또는 읽기 모델 패치.
- 서버 발행 프롬프트: `PendingDecision` 표시용 메시지.
- 클라이언트 제출 커맨드: `PendingDecision` 응답.

서버에서 클라이언트로 보내는 메시지 예시는 다음과 같다.

```json
{
  "type": "game.event",
  "game_id": "game-123",
  "version": 42,
  "event_id": "evt-42",
  "event_type": "TurnStarted",
  "payload": {
    "player_id": "p2",
    "character_id": "char-low-priority"
  }
}
```

```json
{
  "type": "game.prompt",
  "game_id": "game-123",
  "version": 43,
  "decision_id": "dec-777",
  "prompt_type": "movement",
  "player_id": "p2",
  "choices": [
    { "id": "roll_dice" },
    { "id": "use_dice_card", "card_ids": ["c11", "c19"] }
  ],
  "expires_at": null
}
```

클라이언트에서 서버로 보내는 메시지 예시는 다음과 같다.

```json
{
  "type": "game.command",
  "game_id": "game-123",
  "decision_id": "dec-777",
  "client_command_id": "client-p2-00031",
  "expected_game_version": 43,
  "payload": {
    "choice": "roll_dice"
  }
}
```

응답은 성공, 중복 성공, 거부를 구분한다.

- `command.accepted`: 커맨드가 새로 수락되고 이벤트가 기록됨.
- `command.duplicate`: 같은 `client_command_id`가 이미 같은 결과로 처리됨.
- `command.rejected`: 권한, 버전, decision 상태, 선택지, 룰 불변식 위반으로 거부됨.

클라이언트는 웹소켓 재연결 시 마지막으로 본 `version`을 서버에 보내고, 서버는 누락 이벤트 또는 최신 스냅샷을 다시 보낸다.

## 8. 영속화, 복구, 리플레이 전략

저장 단위는 게임별 이벤트 스트림이다. 커밋 조건은 `game_id`와 `expected_version`에 대한 낙관적 동시성 제어다.

필수 저장 자료는 다음과 같다.

- 이벤트 로그: 모든 도메인 이벤트의 원본.
- 커맨드 처리 기록: `game_id`, `client_command_id`, 처리 결과, 생성 이벤트 범위.
- 스냅샷: 일정 이벤트 수 또는 라운드 경계마다 저장한 `GameState`.
- 읽기 모델: UI 표시용 현재 상태, 프롬프트 목록, 관전 뷰.
- 아웃박스: 웹소켓, 알림, AI 호출 등 외부 전송 대기 작업.

복구 절차는 다음과 같다.

1. 최신 스냅샷을 읽는다.
2. 스냅샷 이후 이벤트를 순서대로 적용한다.
3. 미완료 `PendingDecision`을 복원한다.
4. 자동 진행 가능한 단계가 있다면 서버 내부 커맨드로 이어서 처리한다.
5. 아웃박스 미전송 메시지를 재전송한다.

리플레이는 디버깅과 검증의 핵심 기능이다. 특정 게임 ID와 이벤트 버전을 입력하면 동일한 상태가 재현되어야 한다. 랜덤성은 이벤트에 결과를 기록한다. 예를 들어 주사위 굴림은 "굴린다"가 아니라 `MovementResolved`에 확정 결과를 저장한다. 그래야 리플레이가 난수 생성기 상태에 의존하지 않는다.

## 9. 동시성, 스케일링, 락과 순서 보장

게임 하나의 이벤트 스트림은 단일 순서를 가져야 한다. 가장 단순하고 견고한 방식은 게임별 actor 또는 single-writer shard를 두는 것이다.

권장 모델은 다음과 같다.

- 같은 `game_id`의 커맨드는 항상 같은 게임 워커로 라우팅한다.
- 게임 워커는 한 번에 하나의 커맨드 또는 내부 진행 작업만 처리한다.
- 이벤트 저장소는 `expected_version` 조건으로 원자 커밋한다.
- 커밋 실패 시 상태를 다시 읽고 커맨드를 재검증한다.
- 다중 서버 환경에서는 라우팅 테이블 또는 분산 락을 사용하되, 락은 이벤트 저장소의 버전 검사를 대체하지 않는다.

락 정책은 좁아야 한다.

- 게임 단위 락은 허용한다.
- 플레이어 단위 락만으로 게임 상태를 갱신하는 것은 금지한다. 한 플레이어 선택이 보드, 다른 플레이어 자원, 예약 효과를 함께 바꿀 수 있기 때문이다.
- 웹소켓 세션 락은 권위 락이 아니다.
- AI 워커 락은 decision 응답 중복을 줄이는 보조 장치일 뿐이다.

스케일링은 게임 단위 수평 분산으로 해결한다. 한 게임 내부를 여러 워커가 동시에 처리하려는 시도는 룰 순서 보장을 깨뜨리므로 피한다.

## 10. 실패 처리와 중복/재전송 처리

실패 처리는 "거부", "재시도 가능", "자동 보정", "게임 중단"을 구분한다.

거부해야 하는 경우:

- 존재하지 않는 `decision_id`.
- 이미 해결된 decision에 다른 payload 제출.
- 해당 플레이어가 아닌 사용자의 decision 응답.
- 현재 단계에서 허용되지 않는 프롬프트 종류.
- 서버가 제시하지 않은 선택지.
- 손패에 없는 트릭 카드 사용.
- 턴당 두 번째 트릭 카드 사용.
- 자원이 부족한데 비용 지불을 성공으로 제출.
- 파산 상태 플레이어의 일반 행동 제출.

재시도 가능한 경우:

- 네트워크 단절.
- 웹소켓 전송 실패.
- 이벤트 커밋 충돌.
- AI 응답 타임아웃 후 같은 decision 재요청.

중복 처리는 `client_command_id`와 `decision_id`를 함께 사용한다.

- 같은 `client_command_id`와 같은 payload가 이미 처리됐으면 기존 결과를 반환한다.
- 같은 `client_command_id`가 다른 payload로 오면 거부한다.
- 같은 decision이 이미 해결됐는데 다른 command ID로 다시 오면 `decision_already_resolved`로 거부한다.

외부 전송은 아웃박스 패턴을 사용한다. 이벤트 커밋과 전송 예약은 같은 트랜잭션에 포함하고, 실제 웹소켓 전송은 별도 워커가 수행한다. 전송 실패는 게임 상태를 되돌리지 않는다.

## 11. 운영 관측성

운영 로그와 지표는 룰 흐름을 추적할 수 있어야 한다. 단순 HTTP 성공률만으로는 부족하다.

필수 로그 필드:

- `game_id`
- `round`
- `turn_player_id`
- `phase`
- `version`
- `event_id`
- `decision_id`
- `command_id`
- `prompt_type`
- `correlation_id`
- `result`
- `reject_reason`

필수 지표:

- decision 생성 수, 해결 수, 만료 수, 거부 수.
- prompt type별 평균 응답 시간.
- 이벤트 커밋 충돌 수.
- 게임별 이벤트 처리 지연.
- 웹소켓 재연결 수와 누락 이벤트 재전송 수.
- 리플레이 검증 실패 수.
- 파산, 지불 실패, 마크 지연/실패 같은 중요 룰 이벤트 카운트.
- AI decision timeout과 fallback 발생 수.

필수 운영 도구:

- 게임 ID 기준 이벤트 타임라인 조회.
- 특정 version까지 리플레이.
- 현재 pending decision 조회.
- 같은 command ID의 처리 이력 조회.
- 읽기 모델과 이벤트 리플레이 결과 비교.

## 12. 단계별 이전 전략

현재 구현을 전제로 하지 않는 장기 설계이므로 이전은 기능 단위로 잘라야 한다.

1. 룰 용어 사전 확정
   라운드, 턴 단계, prompt type, 이벤트 이름, 자원 이름, 카드 슬롯 의미를 문서화한다.

2. 순수 룰 엔진 추출
   입력 `GameState + Command`, 출력 `Events + PendingDecision` 형태의 순수 함수를 만든다. I/O, 웹소켓, DB 접근을 넣지 않는다.

3. 이벤트 로그 도입
   신규 게임부터 이벤트를 권위 기록으로 저장한다. 기존 읽기 모델은 이벤트에서 파생되게 한다.

4. pending decision 모델 도입
   모든 외부 입력을 서버 발급 decision에 묶는다. 프론트엔드 임의 액션은 command rejected로 처리한다.

5. 웹소켓 계약 정리
   UI 전용 메시지와 권위 이벤트를 분리한다. 재연결 시 version 기반 catch-up을 지원한다.

6. 커맨드 중복 방지 적용
   `client_command_id` 처리 이력을 저장해 재전송을 안전하게 만든다.

7. 스냅샷과 리플레이 검증 추가
   라운드 경계 스냅샷을 만들고, 이벤트 리플레이 결과와 읽기 모델을 비교한다.

8. 게임별 single-writer 실행 모델 적용
   한 게임의 커맨드는 한 워커가 순서대로 처리하게 한다. 이후 게임 단위 샤딩으로 확장한다.

9. 운영 도구와 지표 보강
   decision, 이벤트, 재연결, 리플레이 실패를 운영 화면 또는 로그 쿼리로 추적한다.

10. 레거시 상태 변경 경로 제거
    이벤트 로그를 거치지 않는 상태 변경, UI 신뢰 기반 변경, 검증 없는 AI 결과 반영을 제거한다.

## 13. 거부해야 할 나쁜 결합

장기적으로 반드시 거부해야 할 결합은 다음과 같다.

- UI 컴포넌트 이름과 도메인 이벤트 이름을 결합하는 것.
- 웹소켓 메시지 수신 순서를 게임 턴 순서로 간주하는 것.
- 프론트엔드가 계산한 이동 결과, 통행료, 파산 여부를 서버가 그대로 받는 것.
- AI 프롬프트 응답을 룰 검증 없이 상태로 반영하는 것.
- 현재 턴 단계 없이 boolean 플래그 묶음으로 진행 상태를 표현하는 것.
- 카드 손패, 숨김 카드, 부담 카드, 종료 시간 슬롯을 단순 배열 인덱스에 암묵적으로 묶는 것.
- 마크 예약 효과를 플레이어 ID에만 묶는 것. 룰상 대상은 캐릭터이며, 해당 캐릭터를 선택한 플레이어의 턴 시작에 발동해야 한다.
- 랜덤 결과를 리플레이 때 다시 계산하는 것.
- 읽기 모델을 권위 상태로 역사용하는 것.
- 락을 웹소켓 연결 또는 브라우저 세션에 묶는 것.
- 결제/통행료/파산 처리를 UI 확인 이후에 별도 보정하는 것.
- 서버 내부 자동 진행과 외부 decision 응답을 같은 타입의 불투명 메시지로 섞는 것.

## 14. 완료 조건

이 설계가 구현되었다고 말하려면 최소한 다음 조건을 만족해야 한다.

- 모든 외부 입력은 서버가 만든 `PendingDecision`에 대한 응답이다.
- 모든 상태 변경은 이벤트로 기록되고, 이벤트 리플레이로 현재 상태가 재현된다.
- 클라이언트가 잘못된 선택, 중복 선택, 늦은 선택을 보내도 서버 상태가 오염되지 않는다.
- 한 게임의 이벤트 버전은 단조 증가하고 커밋 충돌이 감지된다.
- 웹소켓 재연결 후 누락 이벤트를 version 기준으로 복구할 수 있다.
- 파산, 마크 지연/실패, 트릭 카드 제한, 손패/숨김 카드 제한, 라운드 종료 보충 같은 핵심 룰이 서버에서 검증된다.
- 운영자가 게임 ID 하나로 이벤트, decision, command, rejection, replay 상태를 추적할 수 있다.
