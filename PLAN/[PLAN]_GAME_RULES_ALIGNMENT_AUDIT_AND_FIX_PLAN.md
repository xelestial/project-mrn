# [PLAN] Game Rules Alignment Audit And Fix Plan

## 0) 메타
- 상태: `ACTIVE`
- 기준일: `2026-04-03`
- 기준 문서:
  - [docs/Game-Rules.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/docs/Game-Rules.md)
  - [PLAN/[PLAN]_HUMAN_PLAY_UX_RECOVERY_V2.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/PLAN/[PLAN]_HUMAN_PLAY_UX_RECOVERY_V2.md)
  - [PLAN/[PLAN]_HUMAN_RUNTIME_AND_BOARD_READABILITY_STABILIZATION.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/PLAN/[PLAN]_HUMAN_RUNTIME_AND_BOARD_READABILITY_STABILIZATION.md)

## 1) 목적
최신 규칙 문서(`docs/Game-Rules.md`)를 단일 기준으로 삼아, 엔진/서버/웹(React/FastAPI)에서 규칙 해석 차이와 표시 차이를 제거한다.

핵심 목표:
- 규칙 해석 정합성: “룰상 가능한/불가능한 선택”이 코드와 UI에 동일하게 반영
- 턴 파이프라인 정합성: 인물/잔꾀/이동/도착/운수/징표 이벤트 순서 고정
- 인간 플레이 정합성: 플레이어가 판단에 필요한 공개정보를 턴 흐름 안에서 놓치지 않음

## 2) 감사 결과 요약

### 규칙 정합성 매트릭스(요약)
| 규칙 영역 | 현재 상태 | 비고 |
|---|---|---|
| 라운드 시작 시퀀스(날씨/드래프트/우선권) | `검증 필요` | 이벤트 순서 회귀 테스트 보강 필요 |
| 지목(인물 지목 + 미공개 대상 제한) | `불일치` | UI/프롬프트가 플레이어 중심으로 보일 수 있음 |
| 탈출 노비 선택형 이동 | `부분 일치` | 선택 프롬프트 경로 존재, 강제/옵션 경계 재검증 필요 |
| 교리 선택 후 active flip | `불일치 가능성 높음` | 타이밍/횟수(멀티 플립) 규칙 고정 필요 |
| 랩 보상 10PT 분배 | `부분 일치` | 계산 경로는 존재, 결과 표시/추적성 보강 필요 |
| 날씨 효과 지속 표기 | `부분 일치` | selector 경로 존재, 화면 고정 표기/검증 강화 필요 |
| 운수/도착/구매/렌트 관전 가시성 | `부분 일치` | 사건 카드 연속성은 있으나 수용성 개선 필요 |

### A. 확정 불일치(즉시 수정 대상)
1. `지목(mark_target)` 표현/모델 불일치  
- 규칙: 지목은 “플레이어”가 아니라 “인물”을 지목(단, UI에는 대상 인물/플레이어를 함께 표시 가능).  
- 현상: 프롬프트/표기가 플레이어 중심으로 보이는 케이스 존재.  
- 조치: 선택지 모델을 `target_character` 중심으로 고정하고 UI는 `대상 인물 / 현재 플레이어` 동시 노출.

2. `active_flip` 트리거/타이밍 불일치 가능성  
- 규칙: 징표 변경이 발생한 라운드의 “다음 라운드 시작 직전(날씨 전)”에 카드 플립.  
- 현상: 사용자 보고상 비정상 턴에서 플립 요청 발생.  
- 조치: 라운드 경계 이벤트 시퀀스를 엔진/서버 테스트로 고정하고, 잘못된 턴 플립 차단.

3. 교리(연구관/감독관) 이후 플립 횟수  
- 규칙: 1~8 카드 중 원하는 만큼 플립 가능, “플립 종료”로 확정.  
- 현상: 단일 선택형으로 축소될 위험 존재.  
- 조치: `active_flip`를 멀티-액션 세션형 요청으로 강제(반복 선택 + 종료).

4. 탈출 노비 1칸 부족 특수 이동  
- 규칙: “할 수 있다(선택)”이며 강제가 아님.  
- 현상: 일부 경로에서 자동적용/표시 누락 가능성.  
- 조치: `runaway_step_choice`가 조건 성립 시 항상 생성되고, 선택 결과가 이동 이벤트에 명시되도록 고정.

### B. 고위험(정합성 검증 + UI 보강)
1. 랩 보상(10PT 분배) 결과 가시성 부족  
- 규칙: 선택 결과(현금/조각/승점 수량)가 명확해야 함.  
- 조치: `lap_reward_chosen` 상세를 사건 카드/턴극장/최근 이벤트에 동일 문구로 노출.

2. 날씨 공개 및 효과 지속 가시성 부족  
- 규칙: 해당 라운드 내 공용 효과로 해석 가능해야 함.  
- 조치: `weather_name + weather_effect`를 턴 패널에 라운드 고정 상태로 유지.

3. 타 플레이어 행동 관전성 부족  
- 규칙 자체 요구는 아니지만 인간 플레이 필수 UX.  
- 조치: “턴 극장”에서 타인 턴의 이동/구매/렌트/운수/턴종료를 최소 카드 단위로 연속 표시.

### 2026-04-03 실행 점검 업데이트 (엔진/AI)
- 실행:
  - `python GPT/test_rule_fixes.py` → `OK`
  - `python GPT/simulate_with_logs.py --games 100 --policy-mode arena --log-level summary --output-dir ../result/rules_flow_100_post_patch_v2`
- 확인 결과:
  - `턴당 잔꾀 1장` 유지 (`regular_tricks_used`만 증가)
  - `아무때나 사용` 직접 소모 경로 제거 유지 (`anytime_tricks_used = 0.0`)
  - 랩 보상 포인트 예산(10PT) 초과 지급 없음 (`requested_points/granted_points` 클램프 적용)
  - 드래프트 2차는 랜덤 1장 배정 경로 유지
- 신규 반영:
  - `호객꾼` 미구현 상태 제거
    - 잔꾀 단계 사용 가능
    - 이번 라운드 동안 해당 플레이어 말을 경유하는 이동에 감속(`obstacle_slowdown`) 적용
    - 공개 상태에 `obstacle` 효과 표기
  - `언제나 사용` 메타 완전 제거
    - `GPT/trick.csv`의 `*언제나 사용할 수 있습니다` 문구 제거
    - `TrickCard.is_anytime`를 규칙 기준으로 항상 `False` 고정
    - human prompt `trick_phase`를 `regular`로 고정
    - 회귀 테스트(`test_removed_anytime_rule_applies_to_all_trick_cards`) 추가
- 주의:
  - `doc_integrity_ok=false`는 현재 룰 불일치가 아니라 문서 최신화 지연(`doc_older_than_source`)로 발생
  - 별도 문서 동기화 작업 필요

## 3) 구현 워크스트림

### WS-1. 엔진 규칙 정합성 (P0)
- [x] `mark_target` 후보 생성을 “미공개 인물 대상” 규칙으로 재검증
- [x] `active_flip` 발생 조건: `marker_changed_in_previous_round == true` + `before weather`
- [x] `active_flip` 멀티 플립 루프 + `finish` 액션 종료
- [x] `runaway_step_choice` 강제 생성 조건(1칸 부족 특수칸) 재검증
- [x] `호객꾼` 효과 구현(장애물 감속) + 턴 로그(`obstacle_slowdown`) 연결

### WS-2. 서버 계약 정합성 (P0)
- [ ] 프롬프트 payload 표준화:
  - `mark_target`: `target_character`, `target_player_id`, `target_name`
  - `active_flip`: `current_name`, `flipped_name`, `can_continue`
  - `lap_reward`: 최종 지급량 필드(`cash`, `shard`, `coin`) 명시
- [ ] 이벤트 순서 계약 테스트 추가:
  - `round_start -> active_flip* -> weather_reveal`
  - `turn_start -> trick_used? -> dice_roll -> player_move -> landing_resolved -> ...`

### WS-3. 웹(React) 규칙 UX 정합성 (P0)
- [ ] `mark_target` 카드 문구를 `대상 인물 / 플레이어` 형식으로 고정
- [ ] `active_flip` UI를 다회 선택형(반복 선택 + 종료 버튼)으로 고정
- [ ] 랩 보상 카드에 “선택 결과 수량”을 명시
- [ ] 턴극장 고정 패널에서 라운드 날씨/효과 지속 표시
- [ ] 타 플레이어 턴 사건 카드(이동/구매/렌트/운수) 시인성 강화

### WS-4. 회귀 방지 (P0)
- [ ] 규칙-코드 매핑 체크리스트 추가(문서+테스트)
- [ ] “이전에 고친 UI 회귀” 항목을 테스트 케이스로 고정
- [ ] 최소 수용 기준(E2E):
  - 1인+AI3 혼합 세션 시작/진행/완료
  - `hidden_trick_card`, `trick_to_use`, `movement`, `mark_target`, `active_flip`, `lap_reward` 모두 정상 왕복

## 4) 테스트 계획

### Engine/Policy
- `GPT/test_rule_fixes.py`
  - 지목 대상 생성/제약
  - 탈출노비 선택형 이동
  - 교리 계열 플립 시퀀스

### Server
- `apps/server/tests/test_runtime_service.py`
- `apps/server/tests/test_prompt_service.py`
- `apps/server/tests/test_stream_api.py`
  - 프롬프트 payload 필드 계약
  - 라운드 경계 이벤트 순서

### Web
- `apps/web/src/domain/selectors/*.spec.ts`
- `apps/web/src/features/prompt/*.spec.tsx` (필요 시 추가)
- `apps/web/e2e/parity.spec.ts`
  - 사람 1 + AI 3 실제 진행 시나리오
  - 턴극장/날씨/랩보상/플립/지목 UI 노출 검증

## 5) 완료 기준(DoD)
- 규칙 문서 기준 P0 불일치 0건
- 엔진/서버/웹 계약 테스트 녹색
- 혼합 세션(인간+AI) E2E에서:
  - 잘못된 턴의 `active_flip` 요청 0건
  - `mark_target`의 인물/플레이어 정보 일치
  - 랩 보상 결과 수량 표시 누락 0건
  - 라운드 날씨/효과 표시 누락 0건

## 6) 운영 원칙
- 규칙 변경 시 절차:
1. [docs/Game-Rules.md](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/docs/Game-Rules.md) 업데이트
2. 본 계획 문서(감사 항목) 업데이트
3. 엔진/서버/웹 테스트 동시 보강
4. `PLAN_STATUS_INDEX` 상태 반영

## 7) 코드 대조 근거(2026-04-03 스냅샷)
- 탈출 노비 선택형 이동 프롬프트 경로 존재:
  - [GPT/viewer/human_policy.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/viewer/human_policy.py)
  - `choose_runaway_slave_step`, `request_type="runaway_step_choice"`
  - [GPT/engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py)
  - `runaway_choice`, `runaway_one_short_pos`, `runaway_bonus_target_pos`

- 지목(표적) 경로 존재:
  - [GPT/viewer/human_policy.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/viewer/human_policy.py)
  - `choose_mark_target`, `_legal_mark_target_players`, `request_type="mark_target"`
  - [GPT/engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py)
  - `result={"target_character": target}` 기록 경로

- 카드 플립 경로 존재:
  - [GPT/viewer/human_policy.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/viewer/human_policy.py)
  - `choose_active_flip_card`, `request_type="active_flip"`

- 랩 보상 경로 존재:
  - [GPT/viewer/human_policy.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/viewer/human_policy.py)
  - `choose_lap_reward`, `request_type="lap_reward"`
  - [GPT/engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py)
  - `_apply_lap_reward`

- React 날씨 지속/턴 패널 경로 존재:
  - [apps/web/src/domain/selectors/streamSelectors.ts](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/apps/web/src/domain/selectors/streamSelectors.ts)
  - `findPersistedWeather`, `selectTurnStage`
  - [apps/web/src/features/stage/TurnStagePanel.tsx](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/apps/web/src/features/stage/TurnStagePanel.tsx)
  - [apps/web/src/features/status/SituationPanel.tsx](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/apps/web/src/features/status/SituationPanel.tsx)

## 8) 인물 능력(능력1/능력2) 전수 점검 (2026-04-03)

### 점검 결과 요약
- `일치/부분 일치`: 자객, 산적, 추노꾼, 탈출 노비, 아전, 건설업자
- `불일치(우선 수정 필요)`: 어사-탐관오리 상호작용, 파발꾼 능력2, 교리 능력2 조건, 박수/만신 능력2 조건/수량, 객주 보상 강화, 중매꾼 추가매수 규칙, 사기꾼 인수비용 1/2단계

### P0 불일치 상세
1. 어사 봉쇄 누락(탐관오리 패시브 경로)
- 규칙: 어사 존재 시 무뢰 인물 능력 봉쇄
- 현행: `_resolve_move`에서 탐관오리 패시브(공물+추가주사위)가 어사 봉쇄와 무관하게 적용
- 근거:
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):351
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):1616

2. 파발꾼 능력2(주사위 -1, 조각 8+) 미구현
- 규칙: 능력1(+1주사위) 또는 능력2(-1주사위) 중 택1, 능력2는 조각 8+ 조건
- 현행: 항상 `extra_dice_count_this_turn += 1`만 적용
- 근거:
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):1026

3. 교리 연구관/감독관 능력2 조건(조각 8+) 누락
- 규칙: 짐 제거 능력은 조각 8+일 때만
- 현행: 조각 조건 없이 항상 `_resolve_doctrine_burden_relief` 실행
- 근거:
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):1036
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):1325

4. 박수/만신 지목 실패 능력2 조건/수량 불일치
- 규칙: 실패 시 조건 충족(박수 6+, 만신 8+)일 때 짐 1장 제거 + 제거비용 수령
- 현행: fallback 임계값이 박수 5, 만신 7이며, 최대 여러 장 제거 가능
- 근거:
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):1075

5. 객주 보상 강화 불일치
- 규칙: 랩 보상 선택 항목마다 +1, F칸 보상 강화(문서 기준)
- 현행: 랩 보상 뒤 `choose_geo_bonus`로 1종류만 +1; F 보상 강화도 규칙 문구와 1:1 대응이 아님
- 근거:
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):1794
  - [effect_handlers.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/effect_handlers.py):120

6. 중매꾼 추가 구매 규칙 불일치
- 규칙: 소유 타일 도착 시에도 인접 매수 가능, 추가 매수 비용 2배(능력2 시 1배)
- 현행: `owner is None` 분기에서만 발동, 비용 배수 대신 `shard_cost=1` 사용
- 근거:
  - [effect_handlers.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/effect_handlers.py):182
  - [engine.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/engine.py):2515

7. 사기꾼 인수 비용 1/2단계 불일치
- 규칙: 기본 3배, 조각 8+일 때 2배
- 현행: 항상 `2배`로 처리
- 근거:
  - [effect_handlers.py](/C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/effect_handlers.py):867

### P1 점검 포인트
- 인물 속성 정의(`상민/무뢰/잡인`)가 문서와 어긋나는 항목 존재 가능
- 교리 징표 방향(시계/반시계)은 문서 내 서술 상충 구간이 있어 우선 문서 정본 확정 필요
