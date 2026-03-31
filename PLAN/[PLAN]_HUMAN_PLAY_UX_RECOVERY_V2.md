# [PLAN] Human Play UX Recovery V2

## Status
- State: `ACTIVE`
- Date: `2026-03-31`
- Owner: `GPT`
- Priority: `P0`

## Why This Plan Exists
React/FastAPI 매치 화면이 실제 플레이 UI가 아니라 스트림 디버거처럼 동작하는 문제가 반복되었습니다.

핵심 증상:
- 고정폭/저가독성 레이아웃
- 프롬프트 위치/선택 UX 회귀
- 내 턴 이후 타 플레이어 진행 가시성 부족
- 말 위치/이동 가시성 부족
- 운수/종료 타일 표현 회귀
- 날씨/운수/랩보상/지목 등 이벤트 요약 불명확

## Definition of Done
- 뷰포트 기반 게임 UI(100vw/100vh)로 기본 가독성 확보
- 매치 상단(로비/연결)은 접기 가능하며 기본 compact
- 프롬프트는 모달 우선이며 카드 전체 클릭 가능
- 잔꾀/히든/주사위 선택 흐름이 인간 친화형으로 제공
- 타 플레이어 액션이 턴 극장에서 연속적으로 보임
- 말 위치가 항상 보이며 최근 이동 강조가 보임
- 운수/종료 타일이 별도 레이아웃으로 표현됨
- 날씨는 라운드 내 지속 표시됨
- Raw JSON은 기본 경로에서 숨김

## Workstreams

### W1. Layout and IA (P0)
- [x] 매치 상단 접기/펼치기
- [x] 풀 뷰포트 기반 레이아웃 유지
- [x] Raw 메시지 기본 숨김
- [ ] 로비 패널 세부 접기 UX 추가 폴리시

### W2. Prompt UX Rebuild (P0)
- [x] 모달 프롬프트 레이어 고정
- [x] 카드 전체 클릭 처리
- [x] 제출 후 busy/스피너 상태
- [x] 이동값 결정: `주사위 굴리기` / `주사위 카드 사용` + 카드칩 방식
- [x] 잔꾀 사용: 단일 통합 카드 리스트(히든 상태 표시)
- [ ] 마크/액티브플립/랩보상 세부 카피 고도화

### W3. Theater and Turn Continuity (P0)
- [x] 턴 극장 카드 피드(이동/구매/렌트/날씨/운수/종료 포함)
- [x] 내 턴 아님 상태 패널 + 스피너
- [ ] 중앙 “턴 스테이지” 고정 카드(현재 액션 지속 노출) 추가

### W4. Board and Pawn Visibility (P0)
- [x] 운수/종료 타일 별도 표현
- [x] 타일 번호/색상/소유/통행료 가독성 개선
- [x] 말(♟ Pn) 가시성 확대
- [x] snapshot 누락 시 최근 이동 기반 말 위치 fallback
- [ ] 이동 경로 애니메이션(중간 칸 트랜지션) 강화

### W5. Projection Correctness (P0)
- [x] 날씨 지속 표기 selector 적용
- [x] marker transfer/lap reward/event 요약 문구 개선
- [ ] active flip 시점/지목 후보 규칙 검증 시나리오 추가
- [ ] draft 1차-2차(랜덤)-최종 2후보 시퀀스 E2E 검증

### W6. Runtime Recovery UX (P1)
- [x] watchdog가 인간 입력 대기 중일 때 `waiting_input` 상태로 표시
- [x] stalled warning을 상황 경고 메인 카드에서 제거(연결 상태로 집중)
- [ ] 연결 장애 가이드(재시도 버튼/문구) 고도화

## Test Pipeline
- Web unit:
  - `promptSelectors`
  - `streamSelectors`
  - `boardProjection`
- Web full:
  - `npm run test -- --run`
  - `npm run build`
- Server:
  - `pytest test_prompt_service/test_runtime_service/test_stream_api/test_sessions_api/test_restart_persistence`

## Current Verification (2026-03-31)
- Web tests: `13 files / 51 tests passed`
- Web build: `passed`
- Server tests: `39 passed`

## Regression Guard Link
- `docs/architecture/human-play-regression-guard.md`
