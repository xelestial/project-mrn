# Log Engine Audit & Generation Map

Status: `ACTIVE`  
Updated: `2026-04-03`  
Scope: `GPT` 엔진의 `action_log` / 시각화 스트림(`VisEventStream`) 생성 순서 및 생성 지점

## 1) 감사 목적과 방법

요청사항:

- 로그 엔진에서 로그가 순서대로 생성되는지 점검
- 오류/정합성 이슈 확인
- 모든 로그의 생성 시점을 소스/로직으로 명시

실행 근거:

- 정적 추출(소스 파싱): `result/log_generation_sites.json`
- 샘플 실험:
  - `result/log_engine_audit_100/audit_summary.json`
  - `result/log_engine_audit_100/audit_refined.json`

검증 기준(요약):

- `action_log`: 라운드 프리루드/드래프트/턴/종료 흐름 정합성
- `VisEventStream`: `validate_vis_stream(strict_payload=True)` 통과 여부

---

## 2) 결론 요약

### 2.1 순서 정합성

- `action_log` 메인 플로우는 전반적으로 정상.
- 라운드 단위(날씨→드래프트→최종 캐릭터→순서 결정), 턴 단위(이동/도착/경제 처리 후 마커/종료 판정) 흐름이 유지됨.

### 2.2 확인된 이슈

1. `VisEventStream` 불일치 (`turn_start` vs `turn_end_snapshot`)  
   - 재현: 100게임 중 3게임 (`seed=20260437, 20260438, 20260486`)  
   - 패턴: 턴 시작 후 트릭/지불 단계에서 사망 시, `turn_end_snapshot`이 emit되지 않고 조기 종료되는 케이스 존재
   - 관련 로직: `GPT/engine.py`의 `_take_turn`에서 `_use_trick_phase` 직후 `if not player.alive: return`

2. `action_log` 스키마 불일치 (`event` 키 누락 가능)  
   - 재현: 100게임 중 6게임  
   - 누락 row 예시: `{"event_kind":"policy_action","type":"SWINDLE_SKIP_POLICY", ...}`  
   - 관련 로직: `GPT/effect_handlers.py` `handle_tile_character_effect` (정책 skip 기록 시 `event` 필드 없이 `_log`)

참고:

- `game_end` 뒤에 `game.end.evaluate` semantic row가 1개 더 찍히는 것은 현재 트레이스 훅 호출 순서(핸들러 실행 후 trace)로 인해 발생하며, 현 구조상 의도된 결과.

---

## 3) 로그 생성 파이프라인 (실행 순서)

## 3.1 `action_log` 파이프라인

1. 엔진/핸들러가 `_log({...})`로 런타임 row 기록  
2. 이벤트 버스 디스패치(`emit_first_non_none`) 완료 후 `_trace_semantic_event`가 semantic row 기록  
3. 정책 훅(`PolicyDecisionLogHook`)이 `ai_decision_before/after` row 기록

핵심 소스:

- `GPT/engine.py` `GameEngine._log`
- `GPT/engine.py` `GameEngine._trace_semantic_event`
- `GPT/policy_hooks.py` `PolicyDecisionLogHook.before_decision/after_decision`

## 3.2 라운드 프리루드 순서

1. `marker.flip.resolve` (semantic trace row)
2. `weather_round` (runtime row)
3. `draft_pick`(phase1/phase2)
4. `final_character_choice`
5. `round_order`

## 3.3 턴 순서 (`action_log` 관점)

- 턴 내부 semantic/runtime 이벤트(트릭/착지/구매/렌트/운수 등)
- `turn` runtime row (해당 턴의 요약 스냅샷)
- `marker.management.apply` semantic row
- `game.end.evaluate` semantic row
- 종료 조건 충족 시: `game_end` runtime row (+ trailing `game.end.evaluate` trace row 가능)

---

## 4) 생성 지점 명세 (소스/로직)

아래는 “로그가 언제/어디서 생성되는지”를 이벤트군 기준으로 정리한 것이다.

## 4.1 `action_log` 런타임 이벤트 (주요)

- `initial_active_faces`  
  - 소스: `GPT/engine.py` `_initialize_active_faces`  
  - 시점: 게임 시작 직후, 카드 앞/뒷면 초기화

- `initial_public_tricks`  
  - 소스: `GPT/engine.py` `run`  
  - 시점: 시작 손패 배분 후, 공개/비공개 잔꾀 상태 기록

- `weather_round`, `weather_reshuffle`  
  - 소스: `GPT/engine.py` `_apply_round_weather`, `_draw_weather_card`  
  - 시점: 라운드 시작 날씨 처리

- `draft_hidden_card`, `draft_hidden_cards`, `draft_pick`, `final_character_choice`  
  - 소스: `GPT/engine.py` `_run_draft`  
  - 시점: 라운드 시작 드래프트/최종 선택

- `round_order`  
  - 소스: `GPT/engine.py` `_start_new_round`  
  - 시점: 드래프트 완료 후 우선권 확정

- `turn_start`(skip 케이스), `turn`  
  - 소스: `GPT/engine.py` `_take_turn`, `_advance_player`  
  - 시점: 턴 시작(스킵), 턴 요약(정규 턴)

- `resource_f_change`  
  - 소스: `GPT/engine.py` `_change_f`  
  - 시점: F 자원 변경 시

- `trick_supply`, `trick_reshuffle`, `trick_use_skip`, `trick_used`  
  - 소스: `GPT/engine.py` `_run_supply`, `_draw_tricks`, `choose_and_apply`(트릭 단계 내부)  
  - 시점: 트릭 공급/사용 단계

- `fortune_reshuffle`, `fortune_cleanup_before`, `fortune_cleanup_after`  
  - 소스: `GPT/engine.py` `_draw_fortune_card`, `_fortune_burden_cleanup`  
  - 시점: 운수 덱/정리 처리

- `marker_moved`, `marker_flip`, `marker_flip_skip`, `marker_flip_invalid_choice`  
  - 소스: `GPT/effect_handlers.py` `handle_marker_management`, `handle_marker_flip`  
  - 시점: 징표 이동/플립 처리

- `mark_*`, `bandit_tax`, `assassin_reveal`, `baksu_transfer*`, `manshin_burden_clear`, `failed_mark_fallback*`  
  - 소스: `GPT/engine.py` `_queue_mark`, `_resolve_pending_marks`, `_resolve_baksu_transfer`, `_resolve_manshin_remove_burdens`, `_apply_failed_mark_fallback`  
  - 시점: 지목 지정/해결/실패 대체 처리

- `doctrine_burden_relief`, `doctrine_burden_relief_skipped`  
  - 소스: `GPT/engine.py` `_resolve_doctrine_burden_relief`, `_apply_character_start`  
  - 시점: 교리 계열 능력 처리

- `character_ability_applied`, `ability_suppressed`, `control_finisher_window`, `weather_hunt_bonus`, `forced_move`  
  - 소스: `GPT/engine.py` 능력/이동 보조 로직들  
  - 시점: 캐릭터/기상/보조효과 처리

- `trick_global_rent_halved`, `trick_global_rent_double`, `trick_global_rent_double_permanent`  
  - 소스: `GPT/effect_handlers.py` `handle_trick_card`  
  - 시점: 특정 잔꾀 글로벌 효과 적용

- `game_end`  
  - 소스: `GPT/effect_handlers.py` `handle_game_end_evaluate`  
  - 시점: 종료 판정 성공 시

- `ai_decision_before`, `ai_decision_after`  
  - 소스: `GPT/policy_hooks.py` `PolicyDecisionLogHook`  
  - 시점: 정책 판단 함수 호출 전/후

## 4.2 `action_log` semantic trace 이벤트 (event bus)

모든 semantic row는 공통적으로 아래에서 생성된다:

- 소스: `GPT/engine.py` `_trace_semantic_event`
- 트리거: `GPT/event_system.py` `EventDispatcher.emit/emit_first_non_none` 호출 완료 직후

대표 이벤트:

- `marker.flip.resolve`
- `landing.f.resolve`, `landing.s.resolve`, `landing.malicious.resolve`, `landing.unowned.resolve`, `landing.own_tile.resolve`, `landing.force_sale.resolve`
- `tile.character.effect`, `tile.purchase.attempt`, `rent.payment.resolve`
- `lap.reward.resolve`
- `fortune.draw.resolve`, `fortune.card.apply`, `fortune.movement.resolve`, `fortune.cleanup.resolve`
- `payment.resolve`, `bankruptcy.resolve`
- `marker.management.apply`
- `trick.card.resolve`
- `game.end.evaluate`

## 4.3 `VisEventStream` 이벤트 (시각화 스트림)

공통 emitter:

- `GPT/engine.py` `GameEngine._emit_vis`

주요 생성 지점:

- `session_start`: `run` 시작
- `round_start`, `weather_reveal`: `_start_new_round`
- `draft_pick`, `final_character_choice`: `_run_draft`
- `turn_start`, `trick_window_open`, `trick_window_closed`, `dice_roll`, `player_move`, `turn_end_snapshot`: `_take_turn`, `_advance_player`
- `landing_resolved`: `_advance_player`, `_apply_fortune_arrival_impl`
- `tile_purchased`: `_buy_one_adjacent_same_block`, `_matchmaker_buy_adjacent`, `handle_purchase_attempt`
- `rent_paid`: `handle_rent_payment`
- `trick_used`: 트릭 적용 지점
- `mark_resolved`: `_resolve_pending_marks`
- `marker_transferred`, `marker_flip`: `handle_marker_management`, `handle_marker_flip`
- `lap_reward_chosen`: `handle_lap_reward`
- `f_value_change`: `_change_f`
- `bankruptcy`: `_bankrupt`
- `fortune_drawn`, `fortune_resolved`: `_resolve_fortune_tile`, `resolve_fortune_draw`
- `game_end`: `run` 종료 직전

---

## 5) 감사 결과 상세 (100게임)

기준:

- 정책: `HeuristicPolicy('heuristic_v3_gpt','heuristic_v3_gpt')`
- seed: `20260403 ~ 20260502`

결과:

- `action_log` 순서 규칙(라운드/드래프트/턴/종료)은 통과
- `VisEventStream` 검증 실패: 3/100
  - 실패 사유: `turn_start_turn_end_snapshot_mismatch`
  - 문제 seed: `20260437`, `20260438`, `20260486`
- 스키마 이슈(`event` 필드 누락 row): 6/100
  - 유형: `event_kind='policy_action'`, `type='SWINDLE_SKIP_POLICY'`

---

## 6) 유지보수 주의점

1. 함수 중복 정의(파일 내 동일 메서드명 재정의)가 존재함.  
   Python 특성상 “나중 정의만 유효”하므로, 로그 생성 지점을 추적할 때 앞선 정의를 활성 코드로 오해하면 안 됨.

   - `GPT/engine.py`: `_apply_character_start`, `_apply_failed_mark_fallback`, `_matchmaker_buy_adjacent`
   - `GPT/effect_handlers.py`: `handle_unowned_landing`, `handle_own_tile_landing`, `handle_rent_payment`, `handle_tile_character_effect`

2. `game_end` 뒤에 `game.end.evaluate` trace row가 trailing으로 붙는 현재 구조는 이벤트 버스 trace 타이밍(핸들러 실행 후)에서 비롯된 동작임.

3. 시각화 스트림 소비자는 “턴 시작 후 무조건 턴 종료 스냅샷이 온다”를 절대 가정하면 안 됨(현재는 3% 미만의 예외 케이스 존재).

---

## 7) 관련 파일

- 엔진 본체: `GPT/engine.py`
- 기본 효과 핸들러: `GPT/effect_handlers.py`
- 이벤트 버스: `GPT/event_system.py`
- 정책 로그 훅: `GPT/policy_hooks.py`
- 시각 이벤트 검증기: `GPT/validate_vis_stream.py`
- 감사 산출물:
  - `result/log_generation_sites.json`
  - `result/log_engine_audit_100/audit_summary.json`
  - `result/log_engine_audit_100/audit_refined.json`

---

## 8) 이벤트-소스 라인 매핑 (정적 추출)

아래 목록은 `result/log_generation_sites.json`에서 추출한 “이벤트명 -> 파일:라인(함수)” 매핑이다.

## 8.1 action_log (정적 문자열 이벤트)

- `ability_suppressed` -> GPT/engine.py:1005 (`_apply_character_start`); GPT/engine.py:1087 (`_apply_character_start`)
- `ai_decision_after` -> GPT/policy_hooks.py:69 (`after_decision`)
- `ai_decision_before` -> GPT/policy_hooks.py:59 (`before_decision`)
- `assassin_reveal` -> GPT/engine.py:1018 (`_apply_character_start`); GPT/engine.py:1122 (`_apply_character_start`)
- `baksu_transfer` -> GPT/engine.py:1595 (`_resolve_baksu_transfer`)
- `baksu_transfer_none` -> GPT/engine.py:1562 (`_resolve_baksu_transfer`)
- `bandit_tax` -> GPT/engine.py:922 (`_resolve_pending_marks`)
- `character_ability_applied` -> GPT/engine.py:1199 (`_apply_character_start`)
- `control_finisher_window` -> GPT/engine.py:901 (`_maybe_award_control_finisher_window`)
- `doctrine_burden_relief` -> GPT/engine.py:1627 (`_resolve_doctrine_burden_relief`); GPT/engine.py:1651 (`_resolve_doctrine_burden_relief`); GPT/engine.py:1664 (`_resolve_doctrine_burden_relief`)
- `doctrine_burden_relief_skipped` -> GPT/engine.py:1255 (`_apply_character_start`)
- `draft_hidden_card` -> GPT/engine.py:590 (`_run_draft`)
- `draft_hidden_cards` -> GPT/engine.py:649 (`_run_draft`)
- `draft_pick` -> GPT/engine.py:605 (`_run_draft`); GPT/engine.py:622 (`_run_draft`); GPT/engine.py:638 (`_run_draft`); GPT/engine.py:664 (`_run_draft`); GPT/engine.py:680 (`_run_draft`)
- `failed_mark_fallback` -> GPT/engine.py:1358 (`_apply_failed_mark_fallback`); GPT/engine.py:1425 (`_apply_failed_mark_fallback`)
- `failed_mark_fallback_none` -> GPT/engine.py:1317 (`_apply_failed_mark_fallback`); GPT/engine.py:1328 (`_apply_failed_mark_fallback`); GPT/engine.py:1347 (`_apply_failed_mark_fallback`); GPT/engine.py:1380 (`_apply_failed_mark_fallback`); GPT/engine.py:1397 (`_apply_failed_mark_fallback`); GPT/engine.py:1411 (`_apply_failed_mark_fallback`)
- `final_character_choice` -> GPT/engine.py:706 (`_run_draft`)
- `fortune_cleanup_after` -> GPT/engine.py:2679 (`_fortune_burden_cleanup`)
- `fortune_cleanup_before` -> GPT/engine.py:2675 (`_fortune_burden_cleanup`)
- `fortune_reshuffle` -> GPT/engine.py:2217 (`_draw_fortune_card`)
- `game_end` -> GPT/effect_handlers.py:967 (`handle_game_end_evaluate`)
- `initial_active_faces` -> GPT/engine.py:345 (`_initialize_active_faces`)
- `initial_public_tricks` -> GPT/engine.py:116 (`run`)
- `manshin_burden_clear` -> GPT/engine.py:1604 (`_resolve_manshin_remove_burdens`)
- `mark_blocked` -> GPT/engine.py:1289 (`_queue_mark`)
- `mark_queued` -> GPT/engine.py:1303 (`_queue_mark`)
- `mark_target_coerced` -> GPT/engine.py:994 (`_resolve_mark_target`); GPT/engine.py:1075 (`_resolve_mark_target`)
- `mark_target_missing` -> GPT/engine.py:1284 (`_queue_mark`)
- `mark_target_none` -> GPT/engine.py:1277 (`_queue_mark`)
- `marker_flip_invalid_choice` -> GPT/effect_handlers.py:570 (`handle_marker_flip`)
- `round_order` -> GPT/engine.py:551 (`_start_new_round`)
- `trick_global_rent_double` -> GPT/effect_handlers.py:864 (`handle_trick_card`)
- `trick_global_rent_double_permanent` -> GPT/effect_handlers.py:868 (`handle_trick_card`)
- `trick_global_rent_halved` -> GPT/effect_handlers.py:816 (`handle_trick_card`)
- `trick_reshuffle` -> GPT/engine.py:1522 (`_draw_tricks`)
- `trick_use_skip` -> GPT/engine.py:1836 (`choose_and_apply`)
- `trick_used` -> GPT/engine.py:1843 (`choose_and_apply`)
- `weather_hunt_bonus` -> GPT/engine.py:1448 (`_record_mark_attempt`)
- `weather_reshuffle` -> GPT/engine.py:396 (`_draw_weather_card`)

동적(딕셔너리 변수) 이벤트는 정적 추출에서 `event=None`으로 표시되며, 실제 런타임 이벤트명은 아래와 같다.

- `weather_round` (`_apply_round_weather` / `apply_round_weather`)
- `turn` (`_advance_player`)
- `turn_start` skip-row (`_take_turn` 내부 `start_log`)
- `resource_f_change` (`_change_f`)
- `trick_supply` (`_run_supply`)
- `forced_move` (`_apply_forced_landing`)
- `marker_moved`, `marker_flip`, `marker_flip_skip` (`handle_marker_management`, `handle_marker_flip`)
- `policy_action` row (`event` 키 없음; `type=SWINDLE_SKIP_POLICY`) (`handle_tile_character_effect`)

## 8.2 vis_event

- `bankruptcy` -> GPT/engine.py:2983 (`_bankrupt`)
- `dice_roll` -> GPT/engine.py:791 (`_take_turn`)
- `draft_pick` -> GPT/engine.py:606 (`_run_draft`); GPT/engine.py:623 (`_run_draft`); GPT/engine.py:639 (`_run_draft`); GPT/engine.py:665 (`_run_draft`); GPT/engine.py:681 (`_run_draft`)
- `f_value_change` -> GPT/engine.py:1741 (`_change_f`)
- `final_character_choice` -> GPT/engine.py:707 (`_run_draft`)
- `fortune_drawn` -> GPT/engine.py:2438 (`_resolve_fortune_tile`); GPT/effect_handlers.py:926 (`resolve_fortune_draw`)
- `fortune_resolved` -> GPT/engine.py:2447 (`_resolve_fortune_tile`); GPT/effect_handlers.py:935 (`resolve_fortune_draw`)
- `game_end` -> GPT/engine.py:152 (`run`)
- `landing_resolved` -> GPT/engine.py:2108 (`_advance_player`); GPT/engine.py:2269 (`_apply_fortune_arrival_impl`)
- `lap_reward_chosen` -> GPT/effect_handlers.py:739 (`handle_lap_reward`)
- `mark_resolved` -> GPT/engine.py:923 (`_resolve_pending_marks`); GPT/engine.py:936 (`_resolve_pending_marks`); GPT/engine.py:949 (`_resolve_pending_marks`); GPT/engine.py:962 (`_resolve_pending_marks`)
- `marker_flip` -> GPT/effect_handlers.py:607 (`handle_marker_flip`)
- `marker_transferred` -> GPT/effect_handlers.py:506 (`handle_marker_management`)
- `player_move` -> GPT/engine.py:2170 (`_advance_player`)
- `rent_paid` -> GPT/effect_handlers.py:394 (`handle_rent_payment`); GPT/effect_handlers.py:1075 (`handle_rent_payment`)
- `round_start` -> GPT/engine.py:528 (`_start_new_round`)
- `session_start` -> GPT/engine.py:123 (`run`)
- `tile_purchased` -> GPT/engine.py:1779 (`_buy_one_adjacent_same_block`); GPT/engine.py:2860 (`_matchmaker_buy_adjacent`); GPT/engine.py:2901 (`_matchmaker_buy_adjacent`); GPT/effect_handlers.py:1020 (`handle_purchase_attempt`)
- `trick_used` -> GPT/engine.py:1844 (`choose_and_apply`)
- `trick_window_closed` -> GPT/engine.py:768 (`_take_turn`)
- `trick_window_open` -> GPT/engine.py:756 (`_take_turn`)
- `turn_end_snapshot` -> GPT/engine.py:732 (`_take_turn`); GPT/engine.py:846 (`_take_turn`)
- `turn_start` -> GPT/engine.py:723 (`_take_turn`); GPT/engine.py:748 (`_take_turn`)
- `weather_reveal` -> GPT/engine.py:538 (`_start_new_round`)

## 8.3 semantic_dispatch (event bus 호출 지점)

- `bankruptcy.resolve` -> GPT/engine.py:2990 (`_bankrupt`); GPT/effect_handlers.py:755 (`handle_payment`)
- `fortune.card.apply` -> GPT/engine.py:2295 (`_apply_fortune_card`)
- `fortune.cleanup.resolve` -> GPT/engine.py:2676 (`_fortune_burden_cleanup`)
- `fortune.draw.resolve` -> GPT/engine.py:2434 (`_resolve_fortune_tile`)
- `fortune.movement.resolve` -> GPT/engine.py:2287 (`_apply_fortune_arrival`); GPT/engine.py:2291 (`_apply_fortune_move_only`)
- `game.end.evaluate` -> GPT/engine.py:2996 (`_check_end`)
- `landing.f.resolve` -> GPT/engine.py:2790 (`_resolve_landing`)
- `landing.force_sale.resolve` -> GPT/engine.py:2805 (`_resolve_landing`)
- `landing.malicious.resolve` -> GPT/engine.py:2798 (`_resolve_landing`)
- `landing.own_tile.resolve` -> GPT/engine.py:2820 (`_resolve_landing`)
- `landing.s.resolve` -> GPT/engine.py:2794 (`_resolve_landing`)
- `landing.unowned.resolve` -> GPT/engine.py:2814 (`_resolve_landing`)
- `lap.reward.resolve` -> GPT/engine.py:2209 (`_apply_lap_reward`)
- `marker.flip.resolve` -> GPT/engine.py:389 (`_resolve_marker_flip`)
- `marker.management.apply` -> GPT/engine.py:2993 (`_apply_marker_management`)
- `payment.resolve` -> GPT/engine.py:2975 (`_pay_or_bankrupt`)
- `rent.payment.resolve` -> GPT/engine.py:2825 (`_resolve_landing`)
- `tile.character.effect` -> GPT/engine.py:2809 (`_resolve_landing`)
- `tile.purchase.attempt` -> GPT/engine.py:2916 (`_try_purchase_tile`)
- `trick.card.resolve` -> GPT/engine.py:1862 (`_apply_trick_card`)
