# [PLAN] Human Runtime And Board Readability Stabilization

Status: `ACTIVE`  
Owner: `GPT`  
Updated: `2026-03-31`

## 1. Why This Plan Exists

Observed in current React/FastAPI runtime:

1. `human` 좌석으로 세션을 만들어도 게임이 즉시 종료되거나 AI끼리 진행되는 것처럼 보임.
2. 사용자는 정상 참가/시작을 했는데도 `finished` 또는 `recovery_required` 상태만 보며 입력할 기회를 받지 못함.
3. 보드 타일이 지나치게 좁아 텍스트가 세로로 깨지고 가독성이 떨어짐.

## 2. Confirmed Root Cause

런타임 서비스가 엔진 정책을 만들 때 세션 좌석 타입(`human`/`ai`)을 정책 레이어에 연결하지 않고, 항상 AI runtime policy만 사용함.

- Session/JWT/Seat 인증 경로는 존재
- WS decision 수신 경로도 존재
- 하지만 엔진 의사결정 지점이 human prompt 브리지로 연결되지 않아 human 좌석이 실제로는 블로킹되지 않음

즉, “세션 모델의 human 좌석”과 “엔진 decision ownership” 사이의 연결이 끊어져 있었다.

## 3. Stabilization Tracks

## Track A. Runtime Correctness (P0)

Goal:
- human 좌석 턴에서는 반드시 prompt가 생성되고, decision 전까지 엔진이 해당 선택을 대기한다.

Scope:
1. Runtime policy assembly에 seat-aware 브리지 추가.
2. PromptService에 blocking wait 경로 추가 (`wait_for_decision`).
3. timeout 시 fallback 이력과 이벤트를 1회만 남기도록 정합성 보장.
4. `start -> join -> stream connect -> prompt -> decision_ack` 경로 회귀 테스트 추가.

Definition of done:
- `1 human + 3 ai` 세션에서 시작 직후 즉시 완주하지 않고 human prompt 대기 상태로 진입.
- human decision 전송 후 해당 request가 정상 해소되고 다음 단계로 진행.
- timeout 시 stale ack + fallback trace가 중복 없이 기록.

## Track B. Match UI Readability (P0)

Goal:
- 보드 타일이 최소 가독성을 보장하고, 색/번호/핵심 경제정보를 한눈에 인지 가능하게 만든다.

Scope:
1. 보드 영역 최소 크기 및 스크롤 컨테이너 분리.
2. 타일 비율 고정(정사각형 계열), 상단 컬러 스트립 추가.
3. 숫자/타일종류/구역/가격/소유자/말 정보의 시각 계층 재정렬.
4. Match 레이아웃에서 보드 컬럼 우선 폭 확보.

Definition of done:
- 40타일 링에서 문자 줄바꿈이 세로로 무너지는 현상 제거.
- 타일 번호/타일종류/가격/소유자/말이 확대 없이 식별 가능.

## Track C. Startup UX Guard (P1)

Goal:
- 사용자가 “왜 멈췄는지/왜 끝났는지”를 UI에서 즉시 이해할 수 있게 한다.

Scope:
1. Lobby/Match에 현재 세션 단계(`waiting`, `in_progress`, `finished`, `recovery_required`)와 원인 텍스트 명시.
2. human seat 미참가 시 start 불가 이유를 명시.
3. runtime recovery_required일 때 복구 절차 안내 문구와 버튼 제공.

Definition of done:
- invalid token, seat mismatch, human not joined, recovery required를 UI에서 구별 가능.

## 4. Implementation Order

1. Track A 런타임 교정 (정합성 최우선)
2. Track B 보드 가독성 개선
3. Track C 시작/복구 UX 가드
4. 통합 회귀 테스트 + 문서 현행화

## 5. Test Pipeline

Server:
- `apps/server/tests/test_prompt_service.py`
- `apps/server/tests/test_runtime_service.py`
- `apps/server/tests/test_sessions_api.py`
- `apps/server/tests/test_stream_api.py`

Web:
- `apps/web/src/features/board/*`
- `apps/web/src/domain/selectors/*`
- `apps/web/src/infra/ws/*`

Manual:
1. Lobby에서 `Seat1=human, Seat2-4=ai` 생성
2. Seat1 join 후 Start
3. Match에서 prompt 수신 확인
4. decision 제출 후 진행 확인
5. board tile 가독성(번호/종류/가격/소유/말) 확인

## 6. Current Status (This PR Line)

- Track A: `IN PROGRESS` (seat-aware runtime prompt bridge 1차 반영)
- Track B: `IN PROGRESS` (보드 최소 크기/타일 비율/색상 스트립 1차 반영)
- Track C: `PENDING`

