# Human Play Regression Guard

## Purpose
React/FastAPI 전환 중, 이미 고쳤던 human-play UX 문제가 다시 살아나는 것을 방지합니다.

이 문서는:
- 고정 이슈 레저(ledger)
- 테스트 매핑 표
- PR 체크리스트 역할을 동시에 수행합니다.

## Non-Negotiable Invariants
- 기본 화면은 디버거가 아니라 “플레이 UI”여야 한다.
- 활성 프롬프트는 항상 보드 위 계층(모달)에서 보인다.
- 타 플레이어 턴 진행이 끊기지 않고 보인다.
- 말 위치는 항상 확인 가능하다.
- 기본 경로에서 Raw JSON을 강제 노출하지 않는다.

## Regression Ledger

### R-001 상단 정보가 게임 본문을 가림
- Guard:
  - 매치 상단은 접기 가능
  - 기본은 compact
- Tests:
  - match route 기본 상태 스냅샷

### R-002 프롬프트가 아래쪽에 떠서 놓침
- Guard:
  - 프롬프트는 모달 레이어 고정
- Tests:
  - `PromptOverlay` 모달 렌더 테스트

### R-003 잔꾀 UI 중복(히든/공개 분리 중복)
- Guard:
  - `trick_to_use`는 단일 카드 리스트
  - 히든 상태는 카드 내부 메타로만 표기
- Tests:
  - prompt selector + prompt component snapshot

### R-004 이동값 UI가 조합 나열로 회귀
- Guard:
  - `주사위 굴리기` / `주사위 카드 사용` 2단 구조
  - 카드칩([1]..[6]) 선택식
- Tests:
  - movement prompt rendering test

### R-005 말 위치 가시성 저하
- Guard:
  - 타일 내 말 마커(큰 대비색) 필수
  - snapshot 누락 시 최근 이동 fallback 표시
- Tests:
  - board projection + board render test

### R-006 타 플레이어 턴이 조용히 스킵됨
- Guard:
  - 턴 극장에서 move/purchase/rent/weather/fortune/end가 모두 노출
- Tests:
  - stream selector multi-player fixture

### R-007 지목 대상 표기 의미 불명확
- Guard:
  - `대상 인물 / 플레이어` 형식 표기
- Tests:
  - mark_target fixture test

### R-008 카드 뒤집기 타이밍 혼선
- Guard:
  - event sequence 검증(라운드 전 처리)
- Tests:
  - runtime integration sequence test (to add)

### R-009 운수/종료 타일이 일반 타일처럼 렌더됨
- Guard:
  - `운수`, `종료-1`, `종료-2` 전용 렌더 분기
- Tests:
  - board tile rendering tests

### R-010 날씨/운수 이벤트 가시성 부족
- Guard:
  - 상황판(weather persistent) + 턴 극장 카드 동시 반영
- Tests:
  - weather persistence selector test

### R-011 Recent 영역이 JSON 중심으로 회귀
- Guard:
  - 기본은 요약 카드
  - Raw는 토글에서만 노출
- Tests:
  - App match default render test

### R-012 랩 보상 값 불명확
- Guard:
  - 선택지에 보상량(현금/조각/승점) 명확 표기
- Tests:
  - lap reward mapping test

### R-013 내 턴이 아닐 때 상태가 불명확
- Guard:
  - `P{n}의 턴` + spinner 노출
- Tests:
  - actor mismatch UI state test

### R-014 watchdog 경고 오탐(입력 대기 중)
- Guard:
  - pending prompt 존재 시 `waiting_input` 상태 사용
  - stalled warning 오탐 억제
- Tests:
  - runtime service watchdog prompt-pending test (to add)

## PR Rule
다음 경로를 수정하는 PR은 이 문서를 함께 갱신해야 합니다:
- `apps/web/src/features/prompt/*`
- `apps/web/src/features/board/*`
- `apps/web/src/domain/selectors/*`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/prompt_service.py`

## Release Gate
아래가 모두 충족되지 않으면 human-play 안정화 완료로 간주하지 않습니다.
- R-001 ~ R-014 핵심 시나리오 통과
- Web test/build green
- Server runtime/session/stream/prompt tests green
