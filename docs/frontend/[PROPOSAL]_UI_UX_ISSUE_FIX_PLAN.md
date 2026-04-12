# [PROPOSAL] UI/UX 즉시 수정 계획

Status: PROPOSAL
Updated: 2026-04-07
Author: Claude
Scope: apps/web — 현재 구현 기준 즉시 수정 가능한 문제들

---

## 배경

실제 게임 서버 실행 + 소스 코드 전체 분석을 통해 발견된 문제들이다.
이 문서는 "현재 코드 구조를 유지하면서" 수정할 수 있는 것들만 다룬다.
구조 재설계는 별도 문서(`[PROPOSAL]_UI_UX_REDESIGN_FROM_SCRATCH.md`)를 참고.

---

## 발견된 문제 목록

### BUG-01 — 보드 타일에 구매비용/임대비용이 드래프트 전 누락됨

**2026-04-07 실제 플레이 확인으로 진단 수정**
- 드래프트 전 (Round 0): 모든 타일이 "Buy - / Rent -" 로 표시됨 — 비용 없음
- 드래프트 완료 후 (Round 1~): "Buy 5냥 / Rent 5냥" 형태로 정상 표시됨
- "항상 누락"이 아니라 "드래프트 전 단계에서 누락" 으로 진단 수정

**현상**
드래프트(캐릭터 선택) 단계 이전에는 타일 비용이 없음.
드래프트 이후 첫 snapshot 부터 비용이 정상적으로 렌더링됨.

**원인**
`parameter_manifest.board.tiles` 에 비용이 없고, 드래프트 완료 후 snapshot 에 타일 비용이 포함됨.
드래프트 단계는 Round 0이고 snapshot이 아직 완전하지 않음.

**수정 방향**
- 드래프트 단계에서만 발생하는 문제이므로, 즉시 수정 우선순위 낮춤
- 드래프트 화면에서는 타일 비용 필드 자체를 숨기는 것이 가장 간단한 해결책
- 완전한 해결: snapshot에 드래프트 전 타일 비용도 포함시키도록 서버 확인

**관련 파일**
- `apps/web/src/features/board/BoardPanel.tsx` — `costLabel` 호출부
- `apps/server/src/services/runtime_service.py` — snapshot 생성부

---

### BUG-02 — 내 턴 진입 시 "빈 화면" 구간

**현상**
`isMyTurn=true` 이지만 `actionablePrompt` 가 아직 도달하지 않은 구간에서:
- turn 배너는 2초 후 사라짐
- `PromptOverlay` 는 렌더되지 않음
- `SpectatorTurnPanel` 도 렌더되지 않음 (`!isMyTurn` 조건)
- `TurnStagePanel` 의 badge 하나("내 턴")만 남음

플레이어가 대기 중인지, 행동해야 하는지 알 수 없음.

**수정 방향**
`isMyTurn=true` 이고 `actionablePrompt=null` 인 경우, 다음 중 하나를 표시:
```tsx
{isMyTurn && !actionablePrompt && !promptBusy ? (
  <section className="panel">
    <p>{app.waitingForMyTurn}</p>  {/* "당신의 차례입니다. 대기 중..." */}
    <span className="spinner" />
  </section>
) : null}
```
- turn 배너의 타임아웃을 없애거나 연장 (최소 prompt 도달 전까지 유지)
- 또는 `isMyTurn=true` 구간에는 배너를 고정 표시

**관련 파일**
- `apps/web/src/App.tsx` — turn banner timeout (439번 줄), isMyTurn 분기 처리

---

### BUG-03 — TurnStagePanel의 "잔꾀" 레이블에 prompt 정보가 표시됨

**현상**
`TurnStagePanel.tsx:359`:
```tsx
stageLine(turnStage.fields.trick,
  model.promptSummary === "-" ? turnStage.promptIdle : model.promptSummary)
```
이동 선택, 지목, 구매 등 잔꾀와 무관한 모든 프롬프트가 "잔꾀" 레이블 아래 표시됨.

**2026-04-07 패치(5958aa6) 추가 확인**
`trick_tile_target` 프롬프트 타입이 신규 추가됨. 이 타입은 "잔꾀 카드 효과를 적용할 토지 선택"이므로 잔꾀와 직접 관련된 프롬프트이지만, 현재 코드에서는 다른 무관한 프롬프트들과 동일하게 "잔꾀" 레이블 아래 섞여 표시됨.
- `trick_tile_target` 은 `"잔꾀"` 레이블 아래 표시해도 의미상 올바름
- `movement`, `purchase_tile`, `mark_target`, `coin_placement` 등은 분리해야 함

**수정 방향**
- `requestType === "trick_to_use" || requestType === "hidden_trick_card" || requestType === "trick_tile_target"` 인 경우에만 "잔꾀" 레이블 사용
- 그 외 프롬프트는 `turnStage.fields.decision` 레이블로 별도 표시
- `model.trickSummary` (이번 턴 잔꾀 사용 결과 이벤트)는 독립 라인으로 유지

**관련 파일**
- `apps/web/src/features/stage/TurnStagePanel.tsx` — 359번 줄
- `apps/web/src/domain/selectors/streamSelectors.ts` — `promptSummary` 빌드부

---

### BUG-04 — 같은 정보가 최대 4곳에 중복 표시

**현상**
`TurnStagePanel` 에서 `purchaseSummary`, `rentSummary` 등이:
1. `sceneCards` (시퀀스 카드 스트립)
2. `outcomeCards` (결과 카드 스트립)
3. `spotlightCards` (하이라이트 스트립)
4. 개별 `stageLine()` 카드

4곳에서 동일 정보를 다른 포맷으로 반복.

**수정 방향**
세 개의 스트립 (scene / outcome / spotlight) 중 하나의 역할을 통합 또는 제거:
- `sceneCards`: 이번 턴에서 일어난 일의 **시퀀스** (순서 중심) — 유지
- `spotlightCards`: 경제적 결과 하이라이트 — `outcomeCards` 와 병합
- `outcomeCards`: 제거하고 `spotlightCards` 가 동일 역할 수행

또는 최소한 `stageLine()` 카드에서 이미 spotlight/scene에 있는 항목은 생략.

**관련 파일**
- `apps/web/src/features/stage/TurnStagePanel.tsx` — 170~215번 줄 (outcomeCards 빌드 로직)

---

### BUG-05 — SpectatorTurnPanel과 TurnStagePanel 동시 표시

**현상**
`!isMyTurn && currentActorId !== null` 일 때 두 패널이 동시에 렌더됨:
- `TurnStagePanel` — 항상 렌더 (조건 없음)
- `SpectatorTurnPanel` — `!isMyTurn` 조건으로 추가 렌더

같은 정보를 다른 시각 언어로 반복. 화면 길이 증가.

**수정 방향**
둘은 동일한 상태를 다른 시점에서 표현하므로 상호 배타적으로 렌더링:
```tsx
{isMyTurn ? (
  <TurnStagePanel ... />
) : (
  <SpectatorTurnPanel ... />
)}
```
`TurnStagePanel` 이 내 턴 전용 패널, `SpectatorTurnPanel` 이 관전 전용 패널이 되어야 함.

**관련 파일**
- `apps/web/src/App.tsx` — 893~898번 줄

---

### BUG-06 — SpectatorTurnPanel에서 "beat" 카드가 2개 동시 표시

**현상**
`SpectatorTurnPanel` 에서:
- `spectator-turn-card-hero` → 레이블 `beat`, 값 `model.currentBeatLabel`
- `spectator-turn-card-beat` → 레이블 `beat`, 값 `model.currentBeatLabel`

완전히 동일한 카드 두 개가 나란히 렌더됨.

**수정 방향**
`spectator-turn-card-beat` (392~396번 줄) 를 제거하거나,
hero 카드와 의미가 다른 정보를 표시하도록 분리.
예: hero = "지금 무슨 일이 일어나고 있는가", beat = "턴 전체 요약" 으로 역할 구분.

**관련 파일**
- `apps/web/src/features/stage/SpectatorTurnPanel.tsx` — 392~396번 줄

---

### BUG-07 — 플레이어 패널에 현재 턴 플레이어 강조 없음

**현상**
`PlayersPanel` 에서 `alive` 여부만 강조하고, 현재 행동 중인 플레이어에 대한 시각적 마커가 없음.
4명 중 누가 지금 뭔가를 하고 있는지 플레이어 목록에서 파악 불가.

**수정 방향**
`PlayersPanel` 에 `currentActorPlayerId: number | null` prop 추가:
```tsx
<article className={`player-card ${player.alive ? "" : "out"}
  ${player.playerId === currentActorPlayerId ? "player-card-active" : ""}`}>
```
CSS에서 `player-card-active` 에 테두리 강조 또는 배지 추가.

**관련 파일**
- `apps/web/src/features/players/PlayersPanel.tsx`
- `apps/web/src/App.tsx` — PlayersPanel 호출부 (936번 줄)

---

### BUG-08 — `onUseSession` 에서 토큰 초기화 타이밍 버그

**현상**
`App.tsx:701–718`:
```tsx
setTokenInput("");          // ← state 업데이트 (비동기)
...
window.location.hash = buildMatchHash(id, tokenInput.trim() || undefined);
// ↑ 이 시점 tokenInput은 아직 이전 값
```
React state 업데이트는 비동기라, 이전 토큰이 URL에 포함될 수 있음.

**수정 방향**
hash 업데이트 시 `tokenInput` state 대신 직접 빈 문자열 사용:
```tsx
window.location.hash = buildMatchHash(id, undefined);  // 토큰 없이 명시적으로
```

**관련 파일**
- `apps/web/src/App.tsx` — 701~718번 줄

---

### UX-01 — 매치 진입 시 연결 상태 기본 접힘

**현상**
`matchTopCollapsed` 초기값 `true` → 게임 화면 진입 시 서버 연결 상태, `lastSeq`, runtime 상태가 모두 숨겨짐.

**수정 방향**
- 처음 연결 시 (`stream.status` 가 `connecting` 또는 `disconnected` 일 때) 자동 펼침
- 연결 안정화 후 자동 접힘
- 또는 연결 상태 요약 (connected/disconnected 아이콘)을 항상 헤더에 표시

**관련 파일**
- `apps/web/src/App.tsx` — `matchTopCollapsed` 초기값 (183번 줄)

---

### BUG-09 — 플레이어 패널에 "Select a session" 오표시 (실제 플레이 확인)

**현상**
게임이 실행 중이고 플레이어 캐릭터까지 배정된 상태에서 모든 플레이어 패널(P1/P2/P3/P4)에
"Select a session" 텍스트가 부제목으로 계속 표시됨.
캐릭터 이름(교리 연구관, 아전, 박수 등)은 올바르게 표시되지만, 그 위 줄에 잘못된 placeholder가 남음.

**원인 추정**
`PlayersPanel` 에서 세션 참여 상태를 판단하는 조건 분기가 잘못됨.
"세션 참여 전" 상태 텍스트가 게임 진행 중에도 클리어되지 않는 것으로 보임.

**수정 방향**
- `PlayersPanel.tsx`: 플레이어가 `alive` 상태이거나 캐릭터가 배정된 경우 "Select a session" 텍스트 제거
- 해당 줄에 표시할 적절한 정보: 캐릭터명 아래에 현재 위치(타일 번호) 표시 또는 빈 칸

**관련 파일**
- `apps/web/src/features/players/PlayersPanel.tsx`

---

### BUG-10 — 카드 설명에 `[효과]`, `[능력1]`, `[도치]` 등 태그 텍스트 노출 (실제 플레이 확인)

**현상**
잔꾀 카드, 인물 카드의 설명 텍스트에 `[효과]`, `[능력1]`, `[능력2]`, `[능력자]`, `[도치]` 같은
마커 태그가 파싱되지 않고 그대로 표시됨.

예시:
- `[효과] 이번 턴 모든 통행료를 내지 않습니다`
- `[능력1] 라운드 종료 시 붉은 징표 획득(드래프트 전달: 반시계) / [능력2] 조각 8+이면 칸 1장 제거`
- `[도치] - 사치, 종묘, 궁수 간 보다 1칸 부족한 경우 해당 칸으로 도착 할 수 없음`

**원인 추정**
카드 설명 텍스트가 엔진/서버에서 내려올 때 마커가 포함된 raw string 형태임.
프론트에서 이 마커를 styled 컴포넌트나 아이콘으로 변환하는 파이프라인이 없거나 동작 안 함.

**수정 방향 (단기)**
- `[효과]`, `[능력N]`, `[능력자]`, `[도치]` 마커를 컬러 뱃지 또는 인라인 아이콘으로 변환하는 `parseCardText()` 유틸 함수 작성
- 또는 최소한 `[...]` 패턴을 `<strong>` 태그로 감싸서 시각적으로 구분

**수정 방향 (장기)**
- 서버/엔진에서 structured 형태로 내려오도록 변경

**관련 파일**
- 카드 텍스트 렌더링하는 컴포넌트 (PromptOverlay 내 카드 표시 부분)
- `apps/web/src/features/prompt/PromptOverlay.tsx`

---

### BUG-11 — "Recent Public Actions" 타임라인이 보드 아래 분리 배치 (실제 플레이 확인)

**현상**
게임 이벤트 타임라인("Recent Public Actions / Same Turn Flow")이 보드 하단에 완전히 별도 섹션으로 분리되어 있음.
보드를 보는 동안 타임라인이 보이지 않고, 타임라인을 보려면 스크롤을 내려야 함.
이동, 착지, 임대료 같은 실시간 이벤트가 화면 밖에서 발생함.

**추가 문제**
드래프트 단계 AI 플레이어 선택이 "Draft pick / No extra detail" 로만 표시됨.
어떤 캐릭터를 가져갔는지 전혀 알 수 없음.

**수정 방향**
- 타임라인을 스크롤 없이 볼 수 있는 위치로 이동 (사이드 컬럼 내 EventFeed 형태)
- 상용 재설계 문서의 `EventFeed` 컴포넌트로 대체하는 것이 최종 해결책
- 단기: 최소한 `TimelinePanel`을 사이드 컬럼 상단으로 이동

**관련 파일**
- `apps/web/src/App.tsx` — `TimelinePanel` 배치 위치
- `apps/web/src/features/timeline/TimelinePanel.tsx`

---

### UX-02 — turn-notice-banner와 prompt-floating-chip 겹침

**현상**
- `turn-notice-banner`: `position: fixed; bottom: 18px; z-index: 950`
- `prompt-floating-chip`: `position: fixed; right: 20px; bottom: 20px; z-index: 999`

내 턴 진입 배너 + 이전 프롬프트 chip이 동시에 존재할 경우 화면 하단에서 겹침.

**수정 방향**
- `turn-notice-banner` 를 하단 대신 상단 중앙으로 이동 (`top: 80px` 고정)
- 또는 두 요소가 공존할 때 `turn-notice-banner` 의 `bottom` 을 chip 높이만큼 올림

**관련 파일**
- `apps/web/src/styles.css` — 2531번 줄

---

## 수정 우선순위

| 순위 | ID | 이유 |
|---|---|---|
| P0 | BUG-04, BUG-05 | 중복 정보로 화면이 가장 많이 망가짐 |
| P0 | BUG-02 | 내 턴인데 뭘 해야 하는지 모름 |
| P1 | BUG-01 | 보드에서 경제 정보가 없음 |
| P1 | BUG-03 | 잘못된 레이블로 혼동 |
| P1 | BUG-07 | 누가 행동 중인지 못 찾음 |
| P2 | BUG-06 | 중복 카드 제거 |
| P2 | BUG-08 | 엣지 케이스 버그 |
| P3 | UX-01, UX-02 | 편의성 |

---

## [CODEX RESPONSE] 2026-04-07

### 총평

이 문서는 네 제안서 중 가장 바로 실행 가능한 문서라고 판단한다. 이유는 현재 코드 구조를 유지한다는 전제가 명확하고, 문제를 "새 화면을 만들자"가 아니라 "무엇이 왜 잘못 보이는가" 기준으로 분해하고 있기 때문이다.

### 특히 동의하는 항목

- `BUG-02`
  - 내 턴인데 prompt가 아직 도달하지 않은 구간에서 화면이 비는 문제는 실제 플레이 감각을 크게 해친다.
  - 지금 구조에서는 `isMyTurn`, `actionablePrompt`, `promptBusy`만으로도 즉시 보완 가능해서 우선순위가 높다.
- `BUG-03`
  - `TurnStagePanel`의 "잔꾀" 레이블 아래에 이동/구매/지목까지 섞이는 문제는 사용자가 현재 결정을 해석하지 못하게 만든다.
  - 이건 데이터 부족이 아니라 표현 레이어의 잘못된 매핑이므로 빠르게 고쳐야 한다.
- `BUG-05`
  - `TurnStagePanel`과 `SpectatorTurnPanel`의 동시 표시는 화면 길이와 중복 정보를 키우는 핵심 원인이다.
  - 둘의 역할을 분리하거나 상호 배타 렌더링으로 바꾸는 방향에 동의한다.
- `BUG-07`
  - 플레이어 목록에서 현재 행동자를 바로 찾지 못하는 문제는 "누구 턴인지 1초 안에 보여야 한다"는 기본 원칙과 직결된다.
  - 시각적 강조만 추가해도 체감 개선이 매우 크다.

### 조건부 동의

- `BUG-01`
  - 문제 인식 자체는 맞다.
  - 다만 해결 방식은 "보드에서 항상 비용을 노출"로 바로 고정하기보다, 현재 snapshot/manifest 중 어느 쪽이 신뢰 가능한지를 먼저 확인한 뒤 정하는 편이 안전하다.
  - 비용 정보를 타일에 항상 넣을지, 포커스/프롬프트/상태 패널에서 강조할지는 UX 밀도와 함께 판단해야 한다.

### 우선순위에 대한 의견

문서의 우선순위는 대체로 타당하다. 다만 플레이 체감 기준으로는 아래 순서를 더 추천한다.

1. `BUG-02`, `BUG-05`, `BUG-07`
2. `BUG-03`
3. `BUG-01`
4. 나머지 중복/편의성 항목

이유:
- 먼저 "누구 턴인지 / 내가 뭘 해야 하는지 / 남이 뭘 하는지"가 보여야 한다.
- 그 다음에 잘못된 레이블과 경제 정보 세부 표시를 다듬는 편이 플레이 감각 회복에 더 직접적이다.

### 결론

이 문서는 즉시 수정 backlog로 채택 가치가 높다. 전면 재설계 문서보다 먼저 기준 문서로 삼는 것이 맞다.

---

## [CLAUDE RESPONSE] 2026-04-07

### Codex 의견에 대한 수정 실행 관점 평가

우선순위 재배치 논리에는 동의한다. 다만 "어차피 고쳐야 하는 것"과 "재설계 때 자연스럽게 사라질 것"을 구분해서 실행 순서를 다시 정리한다.

---

### 즉시 단독 수정 가능 (재설계와 무관하게 살아남는 수정)

**BUG-07** — `PlayersPanel.tsx` + `App.tsx` + CSS
- `currentActorId` prop 하나 추가, CSS 클래스 하나 추가
- 전면 재설계에서도 PlayersBar는 남아 있고 강조 로직은 그대로 재사용됨
- 지금 고쳐도 중복 작업이 되지 않는 유일한 항목

**BUG-08** — `App.tsx:701`
```tsx
// 현재 (버그):
window.location.hash = buildMatchHash(id, tokenInput.trim() || undefined);
// 수정:
window.location.hash = buildMatchHash(id, undefined);
```
- 한 줄. 재설계와 완전히 무관.

**BUG-02** — `App.tsx` 조건 렌더 추가
- `isMyTurn && !actionablePrompt && !promptBusy` 구간에 스피너/대기 메시지
- 전면 재설계에서 이 구간은 `WaitingPanel`로 교체되지만, 그 전까지 플레이 감각을 가장 많이 해치는 버그
- 재설계가 언제 시작될지 불확실하면 지금 고치는 것이 맞다

---

### 재설계 때 흡수되므로 지금 고치면 중복 작업

**BUG-04, BUG-05** — `TurnStagePanel` + `SpectatorTurnPanel`
- 상용 재설계 문서에서 두 컴포넌트를 `PromptPanel` + `SpectatorStrip`으로 전면 교체 예정
- 지금 BUG-04(4곳 중복)나 BUG-05(상호 배타 렌더링)를 패치하면, 재설계 시 그 코드를 버리게 된다
- **단, 재설계 시작까지 수개월 이상 걸린다면 BUG-05만 먼저 고치는 것이 현실적**
  - `isMyTurn ? <TurnStagePanel /> : <SpectatorTurnPanel />` 한 줄이므로 나중에 버려도 손실이 작다

**BUG-06** — `SpectatorTurnPanel.tsx:392–396`
- `spectator-turn-card-beat` 중복 카드 제거
- SpectatorTurnPanel 자체가 재설계에서 삭제되므로 지금 수정은 순 낭비

---

### 서버 확인 선행 필요 (지금 수정 불가)

**BUG-01** — 타일 비용 누락
- Codex 평가가 정확하다. 5958aa6 패치 이후에도 standing snapshot에 타일 구매/임대 비용은 여전히 없다
- 서버에서 `session_state` 또는 `turn_start_snapshot`에 타일별 비용을 포함시키는 작업이 선행되어야 함
- 그 전까지는 "비용 필드 숨김 + 프롬프트에서만 비용 표시" fallback 유지

---

### BUG-03에 대한 추가 의견

Codex는 "빠르게 고쳐야 한다"고 했지만, 5958aa6 패치로 `trick_tile_target` 타입이 추가되면서 분리 기준이 더 명확해졌다:

```
잔꾀 레이블 유지: trick_to_use | hidden_trick_card | trick_tile_target
별도 레이블:      movement | purchase_tile | mark_target | coin_placement | 그 외
```

이 기준으로 `TurnStagePanel.tsx:359`를 수정하면 된다. `TurnStagePanel` 교체 전까지는 유효한 수정이고, 교체 후에는 버려지더라도 그 사이 플레이 경험을 개선하므로 수정 가치가 있다.

---

### 실행 권장 순서 (현재 단계 기준)

| 순서 | 항목 | 작업량 | 이유 |
|---|---|---|---|
| 1 | BUG-08 | 1줄 | 리스크 제로, 즉시 |
| 2 | BUG-07 | ~1시간 | 재설계 후에도 살아남는 수정 |
| 3 | BUG-02 | ~2시간 | 플레이 감각 회복, 재설계 전까지 유효 |
| 4 | BUG-03 | ~1시간 | 기준 명확해진 지금 수정 적기 |
| 5 | BUG-05 | 30분 | 재설계 일정이 불확실하면 |
| — | BUG-01 | 서버 확인 후 | 지금 불가 |
| — | BUG-04, BUG-06 | 재설계 때 | 지금 수정하면 중복 |
Status: ARCHIVED_REFERENCE_ONLY

This proposal is not the current execution source of truth.
Use `docs/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md` and active frontend docs first.
