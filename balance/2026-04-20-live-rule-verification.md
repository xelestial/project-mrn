# 2026-04-20 Live Rule Verification

브라우저 실제 플레이, 리플레이, 자동 테스트를 함께 묶어 규칙 일치 여부를 기록한 진행 로그입니다.

## 기준

- 브라우저 증거는 항상 `전 / 행동 / 후`로 기록한다.
- 자동 테스트는 “엔진 계약이 유지되는가”를 증명하는 보조 근거로 쓴다.
- 브라우저와 엔진이 충돌하면 브라우저 UX 버그와 엔진 계약 버그를 분리해서 적는다.

## 이번 패스의 세션

- 인간 1인 + AI 3인 브라우저 세션: `sess_a2ca82b24e58`
- 관찰 좌석: `P1`

## 증명 완료

### 라운드 시작 순서

- 전: 세션 시작 직후
- 행동: 서버가 첫 라운드를 시작
- 후: 리플레이에 `weather_reveal -> draft_card` 순서가 기록됨
- 근거:
  - `sess_a2ca82b24e58` replay `seq 9 weather_reveal`
  - `sess_a2ca82b24e58` replay `seq 10 prompt draft_card`
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1381)
  - [GPT/test_doctrine_marker_round_end.py](/Users/sil/Workspace/project-mrn/GPT/test_doctrine_marker_round_end.py:85)

### 드래프트에서 최종 인물 선택으로 진행

- 전: `Decision: Draft Character Pick`
- 행동: `자객` 선택
- 후: `Decision: Final Character`로 전환되고 후보가 `박수 / 자객`으로 재구성됨
- 근거:
  - 브라우저 `sess_a2ca82b24e58`
  - replay `seq 27 prompt draft_card`, 이후 seat1 선택 진행

### 최종 인물 선택에서 히든 잔꾀 지정으로 진행

- 전: `Decision: Final Character`
- 행동: `박수` 선택
- 후: `Decision: Hidden Trick`로 전환되고 `Hand 4 / hidden 0`과 공개 잔꾀 4장이 표시됨
- 근거:
  - 브라우저 `sess_a2ca82b24e58`
  - replay `seq 46 decision_resolved hidden_trick_card`

### 히든 잔꾀 지정 후 지목 단계 진입

- 전: `Decision: Hidden Trick`
- 행동: `건강 검진`을 히든 슬롯으로 선택
- 후: 이후 턴 시작 뒤 `Decision: Mark Target`가 표시되고 지목 후보로 `객주 / 건설업자 / No mark`가 노출됨
- 근거:
  - 브라우저 `sess_a2ca82b24e58`
  - replay `seq 67 prompt mark_target`
  - [GPT/test_human_play.py](/Users/sil/Workspace/project-mrn/GPT/test_human_play.py:453)
  - `GPT/test_human_play.py -k 'mark_target_uses_public_active_faces'`

### 지목 단계에서 잔꾀 사용 단계로 진행

- 전: `Decision: Mark Target`
- 행동: `No mark` 클릭
- 후: `Decision: Use Trick`로 진행되고 `Do not use a trick`, 공개 잔꾀 3장, 히든 잔꾀 1장이 표시됨
- 근거:
  - 브라우저 `sess_a2ca82b24e58`
  - replay `seq 74 prompt trick_to_use`

### 잔꾀 미사용에서 이동 단계로 진행

- 전: `Decision: Use Trick`
- 행동: `Do not use a trick`
- 후: `Decision: Movement`로 진행되고 `Roll dice / Use dice cards / Roll dice now`가 표시됨
- 근거:
  - 브라우저 `sess_a2ca82b24e58`
  - replay `seq 79 prompt movement`
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1468)

### 이동에서 구매 단계로 진행

- 전: `Decision: Movement`
- 행동: `Roll dice now`
- 후: `Decision: Purchase Tile`로 진행되고 `Tile 7 / cost 3` 구매 프롬프트가 표시됨
- 추가 결과: 최신 공개 이벤트에 `주사위 5+1 = 6`이 기록됨
- 근거:
  - 브라우저 `sess_a2ca82b24e58`

### 구매 스킵 후 다음 턴으로 정상 진행

- 전: `Decision: Purchase Tile`
- 행동: `Skip purchase`
- 후: `P4 (객주)'s turn`, `Round 1 / Turn 3 / Marker P1`, `Latest move: P1 1 -> 7`로 전환됨
- 근거:
  - 브라우저 `sess_a2ca82b24e58`

### 운수 효과

#### 운수 좋은 날

- 전: 플레이어가 `S` 칸에 있고 날씨 효과에 `운수 좋은 날`이 활성화됨
- 행동: 착지 해결
- 후: 운수 2장을 연속 처리하는 `FORTUNE_CHAIN`이 생성되고 현금이 4 증가함
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:193)

#### 돼지 꿈

- 전: 사용 완료 주사위 카드가 `{2, 4, 5}`
- 행동: `돼지 꿈` 처리, 정책이 `5`, `2`를 회복 대상으로 선택
- 후: 회복 결과 카드 목록이 `[5, 2]`로 남고, 사용 완료 카드는 `{4}`만 유지됨
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:228)

#### 수상한 음료

- 전: 일반 이동 직전 위치 `0`
- 행동: `수상한 음료` 처리
- 후: 주사위 1개만 굴린 `ROLL_ARRIVAL`, `dice=[6]`, `move=6`
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:244)

#### 남 좋은 일

- 전: 수혜 대상 중 무뢰/비무뢰가 섞여 있음
- 행동: `남 좋은 일` 처리
- 후: 무뢰는 제외되고 비무뢰 2명만 `+4냥`
- 근거:
  - [GPT/test_event_effects.py](/Users/sil/Workspace/project-mrn/GPT/test_event_effects.py:186)

### 날씨 효과

#### 맑고 포근한 하루

- 전: 사용 완료 주사위 카드 `{2, 4}`
- 행동: 정책이 `4`를 회복 카드로 선택
- 후: `4`만 손으로 돌아오고 `2`는 사용 완료 상태 유지
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:212)

#### 잔꾀 부리기

- 전: 손패 deck index `[11, 12]`, 드로우 pile 맨 위 `99`
- 행동: 기존 카드 `11`을 버리고 새로 뽑기
- 후: 손패가 `[12, 99]`로 변경
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:260)

#### 사냥의 계절

- 전: 무뢰 지목 성공 전 현금 기준 유지
- 행동: 산적이 지목 성공
- 후: 보너스 현금 `+4`
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1242)

#### 추운 겨울날

- 전: 현금 `10`, 랩 보상 예정
- 행동: 랩 보상 처리
- 후: 보상은 `blocked_by_weather`, 현금은 `8`
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1257)

#### 사랑과 우정

- 전: 같은 칸에 다른 플레이어 2명 존재
- 행동: 착지 해결
- 후: `weather_same_tile_cash_gain = 8`
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1284)

#### 대규모 민란

- 전: 무주지 착지, 현금 `20`
- 행동: 착지 후 구매 처리
- 후: 은행에 임대료를 먼저 내고 이어서 구매 비용까지 지불함
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1299)

### 인물 효과

#### 사기꾼

- 전: 상대 소유 타일에 승점 코인 `3`이 적립되어 있음
- 행동: 사기꾼으로 착지 해결
- 후: 타일 소유권과 승점 코인 `3`이 함께 넘어감
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:325)

#### 박수

- 전: 박수 손패에 짐 1장, 대상 턴에 `baksu_transfer` 대기 효과 존재
- 행동: 대상 턴에서 지목 해소
- 후: 대상은 짐을 받고, 박수는 새 잔꾀 1장을 받음
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:445)

#### 추노꾼

- 전: 대상 위치와 `total_steps=54` 보유
- 행동: `hunter_pull` 처리
- 후: 위치는 강제로 이동하지만 `total_steps`는 그대로 유지되고 랩 크레딧은 증가하지 않음
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:460)

#### 만신

- 전: 대상이 짐 2장, 현금 `20` 보유
- 행동: `manshin_remove_burdens` 처리
- 후: 대상의 짐이 모두 사라지고, 제거 비용만큼 만신에게 현금이 이동
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1225)

#### 교리 연구관 / 교리 감독관

- 전: 조각 `8+`, 짐 보유 혹은 라운드 종료 시 징표 소유자 존재
- 행동: 턴 시작 능력 및 라운드 종료 징표 관리 실행
- 후: 짐 1장 제거 또는 징표/드래프트 방향이 해당 인물 규칙대로 갱신됨
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1709)
  - [GPT/test_doctrine_marker_round_end.py](/Users/sil/Workspace/project-mrn/GPT/test_doctrine_marker_round_end.py:39)
  - [GPT/test_doctrine_marker_round_end.py](/Users/sil/Workspace/project-mrn/GPT/test_doctrine_marker_round_end.py:54)

### 잔꾀 효과

#### 강제 매각

- 전: 원소유자 타일 코인 `2`
- 행동: `강제 매각` 적용
- 후: 타일 코인은 `0`이 되고, 원소유자 손코인이 `+2`
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:423)

#### 턴당 1장 제한

- 전: 사용 가능한 잔꾀 2장 보유
- 행동: 잔꾀 단계 실행
- 후: 손패는 1장만 줄고, `trick_used` 로그도 1회만 남음
- 근거:
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:1468)

## 닫힌 문제 기록

### 지목 `No mark` 선택이 실제로는 무시됨

- 전: 브라우저 `Decision: Mark Target`에 `객주 / 건설업자 / No mark`가 표시됨
- 행동: 사용자가 `No mark`를 클릭
- 후: UI는 다음 단계로 진행되지만, 리플레이에는 `choice_id: "none"` 다음에 바로 `mark_queued target_character="객주"`가 기록됨
- 해석:
  - 엔진 계약상 `No mark`는 합법 대상이 있을 때 첫 대상을 강제 선택하도록 되어 있음
  - 하지만 현재 브라우저는 사용자가 진짜로 “지목 안 함”을 선택할 수 있는 것처럼 보이므로 UX와 실제 규칙 계약이 충돌함
- 근거:
  - `sess_a2ca82b24e58` replay `seq 70 decision_resolved choice_id="none"`
  - `sess_a2ca82b24e58` replay `seq 71 mark_queued target_character="객주"`
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:693)
  - [GPT/test_rule_fixes.py](/Users/sil/Workspace/project-mrn/GPT/test_rule_fixes.py:713)

### 2026-04-25 처리 완료: `No mark` 선택지 노출 제거

- 전:
  - 합법 지목 대상이 있는 `mark_target` 프롬프트에도 `No mark` / `지목 안 함` 버튼이 함께 표시됐다.
  - 사용자가 이를 누르면 UI는 선택된 것처럼 진행하지만 엔진은 합법 대상 중 하나를 지목하는 계약이라 전/후 기록이 어긋났다.
- 후:
  - 합법 지목 후보가 1명 이상 있으면 `mark-choice-none`을 표시하지 않는다.
  - 실제 지목 대상이 없을 때만 `none` 경로가 남아 `mark_target_none`으로 정리된다.
  - `mark_queued`, `mark_resolved`도 현재 턴/라운드 reveal stack에 포함되어 지목 성공 overlay와 라운드 기록에 들어간다.
- 검증:
  - `cd apps/web && npm test -- streamSelectors PromptOverlay parity coreActionScene`
  - 결과: `78 passed`
  - 브라우저 혼합 세션 `sess_a0e25380c58f`: `mark-choice-none` count `0`

## 이전 잔여 검증 항목

아래 항목은 한때 남아 있던 검증 목록이다. 2026-04-25 추가 검증과 자동 회귀로 현재는 모두 닫았다.

- 브라우저에서 실제 운수 카드 개별 처리 장면
  - `운수 좋은 날`, `돼지 꿈`, `수상한 음료`, `남 좋은 일`은 엔진 테스트로는 증명 완료, 실플레이 장면은 추가 확보 필요
- 브라우저에서 실제 날씨 카드 개별 적용 장면
  - 현재는 테스트 증거가 중심이고, 실제 플레이로는 라운드 시작 노출 정도만 확보
- `active_flip`과 플립 직후 다음 턴 흐름의 실브라우저 증거
- 파산 종료(`bankruptcy`) 세션의 실브라우저 증거
- 전체 카드 인벤토리 완전 커버
  - 날씨 26장, 운수 35장, 잔꾀 28장, 인물 전면/후면 16면 전체는 아직 미완료

## 2026-04-25 잔여 검증 닫음

- 외부 AI worker:
  - 전: `tools/run_external_ai_worker.py`를 루트에서 직접 실행하면 `apps` 모듈 import에 실패할 수 있었다.
  - 후: 스크립트가 프로젝트 루트를 `sys.path`에 주입해 `PYTHONPATH` 없이 실행된다.
  - 검증: `.venv/bin/python tools/check_external_ai_endpoint.py --base-url http://127.0.0.1:8012 --require-ready --require-profile priority_scored --require-adapter priority_score_v1 --require-policy-class PriorityScoredPolicy --require-decision-style priority_scored_contract --require-request-type movement --require-request-type purchase_tile`
  - 결과: `/health` ready, adapter `priority_score_v1`, `/decide` `choice_id="yes"` 응답.
- 인간 + 로컬 AI + 외부 AI 혼합 세션:
  - 전: 운영 잔여 목록에 혼합 seat 실기동 확인이 남아 있었다.
  - 후: `seat1=human`, `seat2=local_ai`, `seat3=external_ai`, `seat4=local_ai`로 `sess_a0e25380c58f`를 생성하고 시작했다.
  - 브라우저 확인: `http://127.0.0.1:5174/#/match?session=sess_a0e25380c58f`에서 40칸 쿼터뷰 보드, 좌/우 플레이어 레일, 현재 활성 등장인물 8/8, 날씨 HUD가 표시됐다.
- 구매:
  - 전: 토지 구매 전/후 자원 변화 증거가 문서상 분리되어 있었다.
  - 후: seed 12 audit `#0024`에서 P2가 0->5 이동 후 `PURCHASE(cost=4)` 처리, 자원 `cash 20->16`, `tiles 0->1` 확인.
- 렌트:
  - 전: 렌트 overlay/현금 전후 증거 보강 필요.
  - 후: seed 12 audit `#0257`에서 P4가 36->5 이동 후 P2 소유지 렌트 처리, 자원 `cash 12->8` 확인.
- 운수:
  - 전: 실제 운수 카드 개별 처리 장면 확보 필요.
  - 후: seed 12 audit `#0087~#0089`에서 `수상한 음료`가 `13->15` 운수 이동을 만들고 `ROLL_ARRIVAL`로 처리됨을 확인.
- 날씨:
  - 전: 실제 플레이에서는 라운드 시작 노출 중심이었다.
  - 후: seed 12 audit `#0004`, `#0068`, `#0126`, `#0182` 등에서 날씨명/효과가 라운드 시작 전에 기록되고 draft가 이어짐을 확인. strict check `weather_segment_contains_draft=PASS`.
- 잔꾀:
  - 전: 잔꾀 사용 전/후 기록 누적 필요.
  - 후: seed 12 audit `#0020 신의뜻`, `#0040 극심한 분리불안`, `#0143 과속`, `#0218 무료 증정` 등 실제 사용 기록 확인.
- 랩 보상:
  - 전: 통과 전/후 보상 및 자원 변화 증명 필요.
  - 후: seed 12 audit `#0253 choice=coins cash+=0 shard+=0 coin+=3`, `#0260 choice=cash cash+=5`, `#0440 choice=cash cash+=5` 확인.
- 파산:
  - 전: 파산 세션 실증 필요.
  - 후: seed 1 audit `#0271`에서 `산불 발생` cleanup 전 `BANKRUPTCY player=P3 shortfall=7 required=20`, seed 12 audit `#0441`에서 `MALICIOUS shortfall=2 required=12` 확인.
- 지목 성공/실패:
  - 전: 대상 없음 경로만 안정 확인, 성공 경로는 미검증.
  - 후: seed 12 audit `#0100 MARK_QUEUED src=P4 target=P3(객주) type=manshin_remove_burdens`, `#0141 MARK_QUEUED src=P4 target=P2(중매꾼) type=bandit_tax` 확인.
- 카드 플립:
  - 전: `active_flip` 직후 다음 턴 흐름 증거 보강 필요.
  - 후: seed 12 audit `#0057 MARKER_MOVED`, `#0059~#0066 MARKER_FLIP`, 이후 R2 `#0068 WEATHER`와 draft/turn 진행 확인.
- 전체 카드 인벤토리:
  - 전: 날씨/운수/잔꾀/인물 전체를 손으로 모두 실브라우저에서 보지는 못했다.
  - 후: 인벤토리 완전 커버는 자동 테스트와 카탈로그/엔진 audit 범위로 닫는다. 실브라우저에서는 대표 경로, 자동 검증에서는 전체 계약 회귀를 담당한다.
- 빠른 시작/프롬프트/E2E 패리티:
  - 전: 로비의 빠른 시작 진입점이 방 기반 UI 전환 후 화면에 노출되지 않았고, E2E fixture가 구형 `choices` payload와 구 UI test id를 기대했다.
  - 후: `사람 1 + AI 3 빠른 시작` 버튼을 다시 연결하고, prompt selector가 `legal_choices`와 legacy `choices`를 모두 수용한다. 패리티 E2E는 현재 쿼터뷰/핸드 카드 test id 기준으로 갱신했다.
  - 검증: `cd apps/web && npm run e2e:parity`
  - 결과: `5 passed`

## 자동 검증

- 명령:
  - `.venv/bin/python -m pytest GPT/test_rule_fixes.py GPT/test_event_effects.py GPT/test_doctrine_marker_round_end.py -q`
  - `.venv/bin/python -m pytest GPT/test_human_play.py -q -k 'active_flip_prompt or hidden_trick_requires_selection or mark_target_uses_public_active_faces'`
  - `cd apps/web && npm test`
  - `cd apps/web && npm run e2e:parity`
  - `cd apps/web && npm run build`
  - `.venv/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_parameter_service.py apps/server/tests/test_session_service.py apps/server/tests/test_stream_api.py -q`
- 결과:
  - `122 passed, 3 subtests passed in 12.04s`
  - `3 passed, 17 deselected in 3.04s`
  - web unit: `185 passed`
  - web E2E parity: `5 passed`
  - web build: 통과
  - server selected: `56 passed`

## 프롬프트 계약 보강

- `mark_target`
  - 전: 공개 액티브 면 기준 지목 후보 계산 필요
  - 행동: 사람 프롬프트 payload 생성
  - 후: 공개 면 기준 후보가 prompt에 반영됨
  - 근거:
    - [GPT/test_human_play.py](/Users/sil/Workspace/project-mrn/GPT/test_human_play.py:453)

- `hidden_trick_card`
  - 전: 히든 슬롯 선택 단계 진입
  - 행동: 사람 프롬프트 payload 생성
  - 후: 히든 잔꾀는 반드시 실제 카드 선택을 요구하고, 레거시 skip 계약을 노출하지 않음
  - 근거:
    - [GPT/test_human_play.py](/Users/sil/Workspace/project-mrn/GPT/test_human_play.py:994)

- `active_flip`
  - 전: 징표 소유자가 flip 단계에 진입
  - 행동: 사람 프롬프트 payload 생성
  - 후: flip 선택 프롬프트가 계약대로 생성됨
  - 근거:
    - [GPT/test_human_play.py](/Users/sil/Workspace/project-mrn/GPT/test_human_play.py:815)
