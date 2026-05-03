# Turn Structure & Order Source Map

Status: `ACTIVE`  
Updated: `2026-04-12`  
Scope: `GPT` 엔진 턴 진행 순서(라운드 시작 포함)와 로그 생성 지점(소스/메서드/함수)

## 목적

이 문서는 “턴이 실제로 어떤 순서로 진행되는지”를 코드 기준으로 고정한다.

- 라운드 시작 순서
- 턴 시작~종료 순서
- 예외 경로(스킵/사망)
- 각 단계의 로그 생성 방식
  - `action_log` runtime row
  - `action_log` semantic trace row
  - `VisEventStream` row

---

## 1) 최상위 실행 흐름

핵심 루프:

- [`GPT/engine.py:run`](C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py)

실행 순서:

1. 상태 초기화 / 덱 셔플 / 시작 손패 배분
2. `session_start` 시각 이벤트 emit
3. `_start_new_round(state, initial=True)`
4. while 루프:
   - 현재 라운드 오더에서 행동자 선택
   - 생존자면 `_take_turn`
   - 종료 조건 확인 (`_check_end`)
   - 턴 인덱스 증가
   - 라운드 경계면 `_start_new_round(state, initial=False)`
5. 루프 종료 시 `game_end` 시각 이벤트 emit

관련 함수:

- `_start_new_round` (`GPT/engine.py:496`)
- `_take_turn` (`GPT/engine.py:716`)
- `_check_end` (`GPT/engine.py:2995`)
- `_emit_vis` (`GPT/engine.py:203`)
- `_trace_semantic_event` (`GPT/engine.py:227`)
- `EventDispatcher.emit_first_non_none` (`GPT/event_system.py:32`)

---

## 2) 라운드 시작 순서 (Round Prelude)

엔트리:

- `_start_new_round` (`GPT/engine.py:496`)

순서:

1. 라운드/턴 플래그 리셋 (플레이어별 임시 효과 초기화)
2. `round_start` 시각 이벤트 emit
3. 날씨 적용
   - `_apply_round_weather`
   - 현재는 직접 구현이 아니라 `weather.round.apply` 이벤트 버스 래퍼
   - runtime row: `weather_round`
4. `weather_reveal` 시각 이벤트 emit
5. 드래프트
   - `_run_draft`
   - runtime rows: `draft_pick`, `final_character_choice` (+ hidden card 로그)
   - 시각 이벤트: `draft_pick`, `final_character_choice`
6. 우선권 계산 및 `round_order` runtime row 기록

관련 소스:

- `_resolve_marker_flip` (`GPT/engine.py:389`)
- `_apply_round_weather` (`GPT/engine.py`)
- `EngineEffectHandlers.apply_round_weather` (`GPT/effect_handlers.py`)
- `_run_draft` (`GPT/engine.py:579`)
- `round_order` 로그 기록 (`GPT/engine.py:551`)

---

## 3) 턴 순서 (정상 경로)

엔트리:

- `_take_turn` (`GPT/engine.py:716`)

## 3.1 Turn Start

1. `start_log` 생성 (`event='turn_start'`, 내부 runtime log용)
2. 스킵 턴 여부 확인
3. 지목(마크) 큐 해소
   - `_resolve_pending_marks`
   - 내부에서 `mark_resolved` 시각 이벤트 emit 가능
4. 캐릭터 시작 능력 적용
   - `_apply_character_start`
5. `turn_start` 시각 이벤트 emit
6. `trick_window_open` 시각 이벤트 emit

## 3.2 Trick Phase

1. `_use_trick_phase`
   - 트릭 선택/스킵 기록
   - runtime rows: `trick_use_skip` / `trick_used`
   - 시각 이벤트: `trick_used`
2. 생존 중이면 `trick_window_closed` 시각 이벤트 emit

## 3.3 Movement Phase

1. 정책 이동 결정 (`choose_movement`)
2. `_resolve_move`로 이동값 산출
3. `dice_roll` 시각 이벤트 emit
4. `_advance_player` 호출
   - 장애물/조우 보정
   - 랩 보상 처리 (`_apply_lap_reward`)
   - 도착 처리 (`_resolve_landing`)
   - `landing_resolved` 시각 이벤트 emit
   - runtime row `turn` 기록
   - `player_move` 시각 이벤트 emit

## 3.4 End-of-Turn

1. 종료 윈도우 보정(`_maybe_award_control_finisher_window`)
2. `turn_end_snapshot` 시각 이벤트 emit
3. 라운드 마지막 턴이면 징표/카드 플립을 같은 턴의 마지막 공개 이벤트로 처리
   - `_apply_round_end_marker_management`
   - doctrine 계열이면 runtime `marker_moved` + 시각 `marker_transferred`
   - `_resolve_marker_flip` -> `marker.flip.resolve`
   - 카드 플립 시각 이벤트는 `public_phase='turn_end'`로 emit
4. 턴 커서 증가, 라운드 경계면 `rounds_completed` 증가 후 `_start_new_round`

---

## 4) 턴 순서 (예외 경로)

## 4.1 스킵 턴

조건: `player.skipped_turn == True`

순서:

1. runtime row `turn_start` (`skipped=True`) 기록
2. 시각 `turn_start(skipped=True)` emit
3. `_apply_marker_management`
4. 시각 `turn_end_snapshot` emit
5. return

소스:

- `_take_turn` skip branch (`GPT/engine.py:717 이후 첫 분기`)

## 4.2 트릭 단계/중간 처리에서 사망

조건: `_use_trick_phase` 또는 연계 지불/효과 처리 중 `player.alive=False`

순서:

1. `turn_start`는 이미 emit됨
2. `_use_trick_phase` 이후 `if not player.alive: return`
3. `turn_end_snapshot` emit 없이 종료되는 케이스 존재

영향:

- `validate_vis_stream` 기준 `turn_start_turn_end_snapshot_mismatch` 발생 가능
- 100게임 감사에서 3회 재현

소스:

- `_take_turn` (`GPT/engine.py`, `_use_trick_phase` 직후 생존 체크)

## 4.3 오프턴 사망(지급/마크 해소)

특징:

- 턴 주체가 아닌 플레이어가 `payment.resolve`/`bankruptcy.resolve`에서 사망 가능
- forensic 정보는 `_pay_or_bankrupt`에서 수집 후 `handle_bankruptcy`에서 저장

소스:

- `_pay_or_bankrupt` (`GPT/engine.py:2961 부근`)
- `handle_payment` (`GPT/effect_handlers.py:750`)
- `handle_bankruptcy` (`GPT/effect_handlers.py:762`)

---

## 5) 턴 단계별 로그 타입 매핑

## 5.1 action_log runtime row (주요)

- `turn_start`(스킵 branch)
- `trick_use_skip`, `trick_used`
- `turn` (턴 요약)
- `marker_moved`, `marker_flip*`
- `resource_f_change`
- `game_end`

주요 생성 함수:

- `_take_turn`, `_advance_player`, `_change_f`
- `handle_marker_management`, `handle_marker_flip`
- `handle_game_end_evaluate`

## 5.2 action_log semantic trace row

생성 메커니즘:

- 모든 `emit_first_non_none` 호출 결과를 `_trace_semantic_event`가 자동 기록

턴 중 자주 발생:

- `tile.character.effect`
- `tile.purchase.attempt`
- `rent.payment.resolve`
- `landing.*.resolve`
- `trick.card.resolve`
- `marker.management.apply`
- `payment.resolve`
- `bankruptcy.resolve`

## 5.3 시각 이벤트(VisEventStream)

턴 연관 핵심:

- `turn_start`
- `trick_window_open` / `trick_window_closed`
- `trick_used`
- `dice_roll`
- `landing_resolved`
- `player_move`
- `turn_end_snapshot`
- 경제/부가: `tile_purchased`, `rent_paid`, `lap_reward_chosen`, `f_value_change`, `mark_resolved`, `marker_transferred`

공통 emit 함수:

- `_emit_vis` (`GPT/engine.py:203`)

---

## 6) 코드 레벨 주의사항

1. 동일 메서드 중복 정의가 존재한다. Python에서는 “뒤에 선언된 정의”가 실제 적용된다.

- `GPT/engine.py`
  - `_apply_character_start` (2회)
  - `_apply_failed_mark_fallback` (2회)
  - `_matchmaker_buy_adjacent` (2회)
- `GPT/effect_handlers.py`
  - `handle_unowned_landing` (2회)
  - `handle_own_tile_landing` (2회)
  - `handle_rent_payment` (2회)
  - `handle_tile_character_effect` (2회)

2. `game_end` 뒤에 `game.end.evaluate` semantic trace row가 trailing으로 남는 경우가 있다.
   - 이는 event bus trace 시점(핸들러 반환 후) 특성으로 발생한다.

3. `policy_action` 로그(`SWINDLE_SKIP_POLICY`)는 일부 케이스에서 `event` 키 없이 기록된다.
   - 스키마 일관성 점검 시 예외 처리하거나, 코드에서 `event` 필드 보강 필요.

---

## 7) 추천 점검 체크리스트 (턴 변경 작업 시)

1. `turn_start`가 나가면 `turn_end_snapshot`까지 도달하는지 확인
2. `turn` runtime row와 `player_move` 시각 이벤트가 1:1로 맞는지 확인
3. `landing_resolved`와 실제 `landing.*.resolve` semantic 디스패치의 정합성 확인
4. 스킵/사망/오프턴 지불 케이스에서 로그 누락 없는지 확인
5. `game_end` 근처 trailing semantic row를 분석 로직이 허용하는지 확인

---

## 8) 참고 문서

- [runtime-logging-policy.md](/Users/sil/Workspace/project-mrn/docs/current/backend/runtime-logging-policy.md)
- [online-game-interface-spec.md](/Users/sil/Workspace/project-mrn/docs/current/backend/online-game-interface-spec.md)
