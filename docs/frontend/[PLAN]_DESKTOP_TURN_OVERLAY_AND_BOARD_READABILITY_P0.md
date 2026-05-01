# Desktop Turn Overlay and Board Readability P0 Plan

작성일: 2026-04-30
상태: 구현 전 계획
범위: `apps/web` 데스크톱 매치 화면 UI
기준 브랜치: `main`

## 결론

P0는 모바일 구현을 하지 않는다. 이번 작업은 1440x900, 1600x1000, 1920x1080 데스크톱 해상도에서 실제 플레이 중 판단이 가능한 매치 화면을 만드는 데 집중한다.

중앙 오버레이는 "내 턴의 결정을 요구하는 순간"에는 보드를 꽤 가려도 허용한다. 다만 화면 전체를 덮거나, 현재 행위자/날씨/플레이어 상태/최근 결과까지 한꺼번에 사라지게 만들면 안 된다. 반대로 내 턴이 아닌 공개 이벤트, 이동, 관전 상황에서는 보드가 주인공이어야 한다.

## 사용자 보정 반영

- 모바일 버전 지원은 계획만 세우고 뒤로 미룬다.
- P0 테스트 원칙은 최소 `1440x900`, `1600x1000`, `1920x1080`이다.
- `1600x1000`은 임시 해상도지만, 현재 UI 안정화 중간 기준으로 유지한다.
- 내 턴 중앙 오버레이는 보드를 일부 가려도 괜찮다. 단, 전부 가리는 느낌은 피한다.
- 이전 감사 문서의 모바일 P0 표현은 이 계획에서 대체한다. 모바일은 P0가 아니라 Future Work다.

## 현재 코드 지형

- `apps/web/src/App.tsx`
  - `BoardPanel`의 `overlayContent` 안에 날씨, 플레이어 스트립, 이벤트 피드, 프롬프트, 손패 트레이를 배치한다.
  - `PromptOverlay`에는 이미 `collapsed`, `compactChoices`, `busy`, `secondsLeft`가 있다.
  - `GameEventOverlay`는 전역 이벤트 애니메이션으로 별도 렌더링된다.
- `apps/web/src/features/board/BoardPanel.tsx`
  - 보드 좌표계와 HUD 앵커를 이미 계산한다.
  - `computeBoardHudFrame`와 `computeBoardHudScale`로 안전 영역과 밀도를 잡는 구조가 있다.
- `apps/web/src/features/prompt/PromptOverlay.tsx`
  - 프롬프트 타입별 표면, 선택지 카드, 접힌 칩, 이동/카드/타겟 선택 UI가 이미 들어 있다.
  - P0는 컴포넌트 재작성보다 프레젠테이션 모드와 CSS 토큰을 얹는 방식이 맞다.
- `apps/web/src/styles.css`
  - `.page.page-match` 전용 보드/HUD 레이아웃이 이미 길게 존재한다.
  - 현재 P0 구현은 새 디자인 시스템보다 이 블록을 정리하고 테스트 가능한 토큰으로 고정하는 편이 안전하다.
- `apps/web/e2e/human_play_runtime.spec.ts`
  - mock runtime 기반 Playwright 흐름이 있다.
  - 데스크톱 viewport 게이트를 여기에 추가하거나 별도 `match_desktop_layout.spec.ts`로 분리한다.

## 구현 목표

1. 내 턴 프롬프트는 decision-focus 모드로 명명한다.
2. 내 턴이 아닌 이벤트/관전 상태는 board-preserve 모드로 명명한다.
3. 1440x900에서도 중앙 프롬프트가 사용 가능하고, 접기 한 번으로 보드 맥락을 회복할 수 있어야 한다.
4. 1600x1000과 1920x1080에서는 보드, 플레이어 패널, 공개 이벤트 피드, 프롬프트가 서로 밀어내지 않아야 한다.
5. 모바일은 구현하지 않되, Future Work에 필요한 분기점과 검증 기준만 기록한다.

## 비범위

- 모바일 레이아웃 구현
- 전체 아트 리디자인
- 새 3D/캔버스 보드 엔진
- 게임 룰, 서버, 이벤트 프로토콜 변경
- 모든 이모지/아이콘 교체
- 로비 전체 개편

## P0 구현 순서

### 1. 데스크톱 레이아웃 게이트 추가

새 Playwright 테스트를 추가한다.

권장 파일:

- `apps/web/e2e/match_desktop_layout.spec.ts`

테스트 시나리오:

- mock runtime으로 4인 매치 화면 진입
- 내 턴 actionable prompt가 열린 상태
- prompt를 접은 상태
- 공개 이벤트 피드가 열린 상태
- 최근 이동/경제 이벤트가 표시된 상태

필수 viewport:

- `1440x900`
- `1600x1000`
- `1920x1080`

검증 항목:

- `.board-panel`이 보이고, bounding box가 viewport 안에 있다.
- `.match-table-player-strip` 또는 플레이어 카드 4개가 보인다.
- `[data-testid="board-weather-summary"]`가 보인다.
- actionable prompt 상태에서 `.prompt-overlay`가 보인다.
- prompt collapsed 상태에서 `[data-testid="prompt-dock-collapsed"]`가 보인다.
- `document.documentElement.scrollWidth <= window.innerWidth + 1`
- 주요 카드 텍스트가 세로로 찌그러지지 않는다. 구현상으로는 선택지 카드의 `boundingBox.width >= 150` 정도를 최소 게이트로 둔다.
- prompt가 펼쳐진 상태에서도 board panel 전체가 화면에서 사라지지 않는다.

스냅샷 저장 위치:

- `.gstack/mrn-desktop-layout-1440x900.png`
- `.gstack/mrn-desktop-layout-1600x1000.png`
- `.gstack/mrn-desktop-layout-1920x1080.png`

### 2. 프롬프트 프레젠테이션 모드 도입

`PromptOverlay` 자체가 "왜 지금 중앙에 있는지" 알 수 있게 최소 prop을 추가한다.

권장 타입:

```ts
type PromptPresentationMode = "decision-focus" | "board-preserve";
```

권장 props:

- `presentationMode?: PromptPresentationMode`
- 기본값은 현재 동작과 가까운 `"decision-focus"`

`App.tsx`에서 산출:

- `visibleActionablePrompt`가 로컬 플레이어의 실제 선택 요청이면 `"decision-focus"`
- 패시브/대기/관전성 정보이거나, future 흐름에서 로컬 결정이 아니면 `"board-preserve"`

CSS hook:

- `.prompt-overlay[data-presentation-mode="decision-focus"]`
- `.prompt-overlay[data-presentation-mode="board-preserve"]`

P0에서는 모드명을 추가해 테스트와 CSS를 분리하는 것이 목적이다. 복잡한 상태 머신은 만들지 않는다.

### 3. decision-focus 레이아웃 조정

내 턴 중앙 프롬프트는 허용한다. 대신 다음 맥락을 유지한다.

- 날씨 요약은 계속 보인다.
- 행위자/플레이어 요약은 계속 보인다.
- 프롬프트 접기 버튼은 항상 첫 화면에서 보인다.
- 프롬프트 높이는 1440x900 기준 `min(58vh, 520px)`를 넘지 않는다.
- draft/final character처럼 원래 큰 프롬프트만 예외로 `min(74vh, 760px)`를 허용한다.
- 선택지 카드 최소 폭은 데스크톱에서 `150px` 아래로 내려가지 않는다.

구현 지점:

- `apps/web/src/features/prompt/PromptOverlay.tsx`
  - root section에 `data-presentation-mode` 추가
  - 접기 버튼과 topbar가 항상 grid 첫 행에 남는지 확인
- `apps/web/src/styles.css`
  - `.page.page-match .match-table-prompt-shell .prompt-overlay` max-height 토큰 정리
  - `.prompt-choices-compact`의 최소 폭/행 높이 재점검
  - `1440x900`에서 prompt shell이 중앙 column을 과도하게 밀어내지 않도록 `--match-side-panel-width`와 prompt column min 값을 조정

### 4. board-preserve 레이아웃 조정

내 턴이 아닌 정보성 이벤트는 보드를 가리는 정도를 더 낮춘다.

규칙:

- 공개 이벤트 피드는 오른쪽 레일에 머문다.
- 전역 `GameEventOverlay`는 짧은 spotlight로만 쓰고, 긴 텍스트 설명은 오른쪽 이벤트 피드에 둔다.
- 보드 중앙 이동/도착 상태는 보드 위에서 읽혀야 한다.
- board-preserve prompt가 필요할 경우 중앙 full overlay가 아니라 하단/측면 dock 형태를 우선한다.

구현 지점:

- `apps/web/src/features/board/GameEventOverlay.tsx`
  - P0에서는 구조 유지. 필요하면 `data-event-kind`만 추가해 테스트 hook을 확보한다.
- `apps/web/src/styles.css`
  - `.game-event-overlay`가 1440x900에서 보드 전체를 장시간 덮지 않도록 max-width/max-height와 animation duration을 확인한다.
- `apps/web/src/features/theater/CoreActionPanel.tsx`
  - 이미 최근 행동 요약이 있으므로 새 설명 패널을 만들기보다 이 패널의 정보 밀도를 유지한다.

### 5. 보드 HUD 스케일 기준 고정

`computeBoardHudScale` 테스트를 데스크톱 기준으로 확장한다.

권장 수정:

- `apps/web/src/features/board/boardHudScale.spec.ts`
  - 1440x900 viewport-like 입력 추가
  - 1600x1000 입력 추가
  - 1920x1080 입력 추가

검증:

- `promptMaxHeight >= 196`
- `promptShellMaxWidth >= 960`
- `choiceMinWidth >= 150`
- `handGridColumns === 5`
- 1440에서도 density가 과하게 compact로 떨어지지 않는지 확인

목표는 숫자 마법을 줄이는 것이다. CSS와 TS 계산이 같은 viewport 원칙을 바라보게 만든다.

### 6. CSS 정리 원칙

이번 P0에서 CSS를 전부 갈아엎지 않는다. 대신 `.page.page-match` 하단의 match-board v3 블록을 기준으로 다음만 정리한다.

- 데스크톱 전용 토큰을 한곳에 모은다.
- `@media (min-width: 1500px) and (min-height: 850px)` 블록은 `1600x1000`, `1920x1080` 기준으로 검증한다.
- `@media (max-width: 980px)` 모바일/좁은 화면 블록은 P0에서 적극 수정하지 않는다.
- 1440x900에서 레이아웃이 깨지는 경우에만 `max-width: 1180px` 이하용 규칙이 잘못 개입하지 않는지 확인한다.

권장 토큰:

```css
.page.page-match {
  --match-desktop-prompt-max-height: min(58vh, 520px);
  --match-desktop-large-prompt-max-height: min(74vh, 760px);
  --match-desktop-choice-min-width: 150px;
  --match-desktop-side-panel-width: clamp(176px, 11.8vw, 226px);
}
```

### 7. 모바일 Future Work 기록만 추가

P0에서는 모바일 CSS를 고치지 않는다. 대신 문서에 다음 Future Work 기준을 남긴다.

- 목표 viewport 후보: `390x844`, `430x932`, `768x1024`
- 중앙 오버레이 금지에 가까운 하단 sheet 구조
- 선택지 카드는 1열, 손패는 horizontal tray
- 플레이어 상태는 full card가 아니라 compact rail
- 보드는 항상 독립 스크롤/줌 가능한 영역
- 모바일 acceptance는 P0 완료 후 별도 계획에서 확정

## 파일별 작업 목록

### `apps/web/src/App.tsx`

- `PromptOverlay`에 `presentationMode` 전달
- 로컬 actionable prompt와 passive/waiting 상태를 구분하는 이름을 더 명확히 정리
- 공개 이벤트 피드와 프롬프트가 동시에 있을 때 CSS class hook을 추가할지 판단

### `apps/web/src/features/prompt/PromptOverlay.tsx`

- `PromptPresentationMode` 타입 추가
- root element에 `data-presentation-mode` 추가
- collapsed root에도 같은 hook을 둘지 결정
- 선택지 grid가 compact desktop에서 너무 작아지는지 확인

### `apps/web/src/features/board/GameEventOverlay.tsx`

- `data-event-kind={currentEvent.kind}` 추가
- P0에서 레이아웃 구조 변경은 보류
- 필요하면 `aria-live`는 유지하고 animation만 CSS에서 조절

### `apps/web/src/features/board/boardHudScale.ts`

- 현재 계산식 유지 우선
- 데스크톱 세 해상도 테스트를 통과하지 못할 때만 clamp 값을 조정

### `apps/web/src/features/board/boardHudScale.spec.ts`

- `1440x900`, `1600x1000`, `1920x1080` 기준 케이스 추가
- choice/prompt/hand tray 최소값을 회귀 방지로 고정

### `apps/web/e2e/match_desktop_layout.spec.ts`

- 새 파일 권장
- mock runtime helper는 `human_play_runtime.spec.ts`에서 복제하지 말고 추출 가능성을 먼저 확인
- 추출 비용이 크면 P0에서는 작게 중복하고, 후속으로 helper 분리

### `apps/web/src/styles.css`

- `.page.page-match` match-board v3 영역에 desktop token 추가
- `decision-focus`와 `board-preserve` CSS 분기 추가
- 1440x900에서 prompt shell max-height와 side rail 폭 검증

## 수동 QA 체크리스트

각 해상도에서 확인한다.

- 1440x900
- 1600x1000
- 1920x1080

확인 항목:

- 내 턴 prompt가 열렸을 때 선택지 클릭이 즉시 가능하다.
- 내 턴 prompt가 열렸을 때 날씨/행위자/플레이어 요약이 남아 있다.
- prompt를 접으면 보드가 명확하게 드러난다.
- 공개 이벤트 피드를 열어도 prompt와 카드가 겹쳐 읽기 어려워지지 않는다.
- 이동 이벤트 직후 출발/도착 맥락을 보드에서 볼 수 있다.
- 페이지 전체 가로 스크롤이 생기지 않는다.
- 텍스트가 카드 내부에서 세로쓰기처럼 무너지지 않는다.

## 자동 검증 명령

구현 후 최소 실행:

```bash
cd apps/web
npm run test -- boardHudScale
npm run e2e -- match_desktop_layout.spec.ts
npm run build
```

기존 스크립트명이 다르면 `package.json` 기준으로 맞춘다. Playwright는 `apps/web/playwright.config.ts`의 `127.0.0.1:9000` dev server를 그대로 쓴다.

## 리스크와 대응

- 리스크: 중앙 prompt를 허용하면서도 "너무 가린다"의 기준이 모호하다.
  - 대응: 내 턴은 decision-focus로 허용하되, 접기 버튼/날씨/플레이어 요약/보드 panel 존재를 acceptance로 고정한다.
- 리스크: CSS가 이미 길고 중복 media query가 많다.
  - 대응: 새 레이아웃 체계를 만들지 말고 `.page.page-match` desktop token을 추가하는 방식으로 제한한다.
- 리스크: Playwright mock helper 추출이 예상보다 크다.
  - 대응: P0는 작게 중복해도 된다. 다만 중복이 80줄을 넘으면 helper 추출로 전환한다.
- 리스크: 1600x1000 임시 기준 때문에 나중에 숫자 튜닝이 다시 필요할 수 있다.
  - 대응: 이 해상도는 문서와 테스트 이름에 temporary desktop gate로 명시한다.

## Autoplan Review

이번 autoplan은 현재 세션에서 단일 검토자로 수행했다. 사용자가 별도 하위 에이전트 실행을 명시하지 않았으므로 외부 subagent/codex dual-voice는 실행하지 않았다.

### CEO Review

Verdict: scope reduction with rigor.

가장 중요한 판단은 모바일을 P0에서 빼는 것이다. 지금 제품 가치는 "플레이 중 무슨 일이 일어나는지 이해된다"에 있고, 모바일까지 동시에 해결하려 하면 데스크톱 품질도 흐려진다. 내 턴 중앙 오버레이 허용은 맞는 보정이다. 보드게임 UI에서 결정을 요구하는 순간에는 선택지가 주연이어야 한다.

단, P0가 단순 CSS 예쁘게 만들기로 흐르면 실패한다. acceptance는 미감이 아니라 플레이 판단 가능성으로 고정해야 한다.

### Design Review

Verdict: pass with constraints.

현재 디자인의 핵심 문제는 중앙 overlay 자체가 아니라 상태별 위계가 섞이는 것이다. 내 턴은 decision-focus, 남의 턴/이벤트는 board-preserve로 나누면 사용자는 "지금 내가 선택해야 하는가"를 즉시 이해한다.

디자인 기준:

- 내 턴: prompt 우선, 보드 맥락 보조
- 남의 턴: 보드 우선, 이벤트 보조
- 결과 순간: 짧은 spotlight 후 이벤트 피드로 회수
- 모바일: 별도 sheet 중심 설계로 후속 처리

### Engineering Review

Verdict: implementable without rewrite.

기존 구조가 이미 필요한 훅을 갖고 있다. `BoardPanel.overlayContent`, `PromptOverlay.collapsed`, `compactChoices`, `computeBoardHudScale`, Playwright mock runtime을 재사용하면 된다. 서버나 룰 계층을 건드릴 이유가 없다.

엔지니어링 원칙:

- 새 상태 머신 금지
- `presentationMode` 같은 얇은 prop으로 CSS와 테스트를 분리
- viewport 테스트를 먼저 추가해 CSS 튜닝을 가둠
- desktop token은 CSS 한 영역에 모음

### DX Review

Verdict: light only.

개발자 대상 기능 변경은 아니므로 별도 DX 리뷰는 생략한다. 다만 e2e 명령과 screenshot 위치를 문서에 고정해 다음 작업자가 같은 기준으로 확인할 수 있게 한다.

## Decision Audit Trail

| 결정 | 이유 | 대안 | 상태 |
| --- | --- | --- | --- |
| 모바일 구현을 P0에서 제외 | 데스크톱 플레이 가독성이 먼저 | 모바일 동시 구현 | 확정 |
| 테스트 해상도를 1440x900, 1600x1000, 1920x1080으로 고정 | 사용자 기준과 현재 UI 안정화 필요 | 반응형 전체 매트릭스 | 확정 |
| 내 턴 중앙 overlay 허용 | 결정 순간에는 선택지가 주연이어야 함 | 항상 보드 보존 | 확정 |
| `presentationMode` prop 추가 | 상태별 CSS와 테스트를 명확히 분리 | 기존 class 추론만 사용 | 권장 |
| Playwright desktop layout spec 추가 | 회귀 방지에 직접적 | 수동 QA만 수행 | 권장 |
| 서버/룰 변경 없음 | 문제는 프레젠테이션 계층 | 이벤트 프로토콜 확장 | 확정 |

## Final Gate

구현 착수 조건:

- 이 문서의 P0 범위에 동의
- 모바일은 Future Work로 유지
- 데스크톱 세 해상도 스크린샷을 완료 증거로 저장

완료 조건:

- `boardHudScale` 관련 단위 테스트 통과
- desktop layout Playwright spec 통과
- `npm run build` 통과
- 세 해상도에서 before/after 또는 final screenshot 확보
- 중앙 prompt가 내 턴에만 강하게 등장하고, 다른 상태에서는 보드가 주인공임을 확인
