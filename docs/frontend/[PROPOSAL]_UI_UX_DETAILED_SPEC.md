# [PROPOSAL] UI/UX 세부 상세 계획

Status: PROPOSAL
Updated: 2026-04-07
Author: Claude
Scope: 실제 치수와 컴포넌트 동작이 명시된 구현 가능한 상세 사양

---

## 왜 지금 구조가 "작게 보이는가" — 수치로 증명

현재 `match-layout` CSS:
```css
grid-template-columns: minmax(0, 1.45fr) minmax(320px, 420px);
```

1440px 뷰포트 기준:
- 전체 사용 가능 너비: 1440 - 32(패딩) = 1408px
- 보드 컬럼: ≈ 600px
- 사이드 컬럼: 420px (고정 최대)

보드 ring 타일 계산:
- grid-template-columns: repeat(11, 1fr), gap: 8px
- 타일 1개 너비: (600 - 10×8) ÷ 11 = **47px**
- `tile-live-tag strong`: font-size: 10px — 47px 타일에서 읽을 수 없음
- `tile-head strong` (타일 번호): font-size: 17px — 47px 타일에서 공간 80% 소진

`TurnStagePanel` 카드 계산:
- 사이드 컬럼: 420px, 패딩: 16px×2, gap: 10px×2
- 카드 1개: (420 - 32 - 20) ÷ 3 = **119px**
- `turn-stage-card-top strong`: font-size: 15px — 119px 카드 헤더가 15px 텍스트로 가득 참
- `turn-stage-line strong`: font-size: 13px — 카드당 3-4줄이 들어가면 각 줄은 13px로 판독 불가

플레이어 카드:
- `players-grid`: CSS에서 확인 필요 (아래)
- `player-card` 내부 small 폰트: 11px — 상태 수치가 11px

---

## 목표 치수 (1440px 뷰포트 기준)

### 레이아웃 비율 변경

**현재** → **변경 후**
```css
/* 현재 */
grid-template-columns: minmax(0, 1.45fr) minmax(320px, 420px);

/* 변경 후 */
grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
/* 최대 사이드 너비: max-width: 480px 추가 */
```

결과:
- 보드 컬럼: ≈ 912px (+52%)
- 사이드 컬럼: ≈ 480px (+14%)

보드 타일 재계산:
- (912 - 10×8) ÷ 11 = **75px** (+60%)
- 이 크기에서 타일 번호(17px), 존 색상, 말 토큰이 모두 판독 가능

---

## ZONE A: 헤더 — 전면 재작성

### 현재 헤더

```
[게임 제목 42px]
[부제목 작은 글씨]
[로비|매치|연결접기|컴팩트|KO|EN] ← 버튼 6개 나열
```

**문제**: 타이틀이 공간 많이 차지. 버튼들이 "도구"처럼 보임. 게임 상태 정보 없음.

### 재설계 헤더

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  [로고 24px]  라운드 3 · 턴 2 · P2 교리감독관의 차례  ☀ 맑음  ← 징표 →  [나: P1 사기꾼]  [≡] │
└─────────────────────────────────────────────────────────────────────────────┘
```

**CSS 사양**:
```css
.game-header {
  height: 52px;  /* 고정. 화면 공간 낭비 금지 */
  display: grid;
  grid-template-columns: auto 1fr auto auto auto;
  align-items: center;
  gap: 16px;
  padding: 0 16px;
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(6, 19, 41, 0.94);
  border-bottom: 1px solid #233d68;
}
```

**컴포넌트 내용 및 폰트**:

| 요소 | 크기 | 색상 | 조건 |
|---|---|---|---|
| 로고 | font-size: 18px, font-weight: 800 | #ffda77 | 항상 |
| "라운드 3 · 턴 2" | font-size: 16px | #e8efff | 항상 |
| "P2 교리감독관의 차례" | font-size: 16px, font-weight: 700 | #ffda77 | 내 턴 아닐 때. 내 턴이면: "★ 내 차례" #4ade80 |
| 날씨 배지 | font-size: 14px, padding: 4px 10px | border 포함 pill | 항상 |
| 징표 방향 | font-size: 13px | #c4d4f1 | 항상 |
| 내 플레이어 칩 | font-size: 14px, padding: 6px 12px | 배경 #1c3764, border #ffda77 | 항상 |
| ≡ 메뉴 | 32×32px 버튼 | - | 설정/raw/연결상태 |

**제거 대상**:
- 42px 게임 제목 (로고로 대체)
- 부제목 텍스트
- route-tabs 버튼 줄 (로비/매치는 ≡ 메뉴 안으로 이동)
- compactDensity 버튼 (≡ 메뉴 안으로)
- 언어 전환 (≡ 메뉴 안으로)

**절약 공간**: 헤더가 현재 약 110px → 52px. **58px 확보**.

---

## ZONE B: 보드 패널 — 타일 크기와 내용 재정의

### B-1. 타일 콘텐츠 우선순위 재정의

**현재 타일**에 들어있는 것 (47px 안에):
1. `tile-zone-strip` — 8px 색상 띠
2. `tile-corner-badge` (이동 시) — 10px 텍스트 뱃지
3. `tile-stage-focus` — 포커스 오버레이
4. `tile-live-tag` — 10px 라이브 태그
5. `tile-actor-banner` — 10px 배너
6. `tile-head strong` — 17px 타일 번호
7. `tile-head span` — 12px 타일 종류
8. `tile-body small` — 11px 존 이름 + 비용 (2줄)
9. `tile-foot small` — 11px 소유자
10. `pawn-chips` — 32px 말 토큰

47px 안에 10개 요소. 물리적으로 불가능.

**재정의: 75px 타일 기준 필수/선택적 표시 규칙**

| 요소 | 표시 조건 | 크기 |
|---|---|---|
| 존 색상 띠 | 항상 | height: 6px |
| 타일 번호 | 항상 | font-size: 15px (17px→15px, 공간 절약) |
| 타일 종류 (T2/T3/S/F) | 항상 | font-size: 11px |
| **소유자 색상 점** | 소유자 있을 때만 | 10px 원형 dot, 우상단 |
| **말 토큰** | 플레이어가 있을 때만 | 24px (32px→24px), 최대 2개 표시 후 "+N" |
| 비용 텍스트 | **제거** — 타일에서 삭제 | - |
| 존 이름 텍스트 | **제거** — 타일에서 삭제 | - |
| 소유자 이름 텍스트 | **제거** — 점으로 대체 | - |
| `tile-live-tag` | 포커스 타일만, 간소화 | 8px 텍스트 |
| `tile-actor-banner` | 행동 중인 플레이어 타일 | 10px |

**이유**: 75px 타일에서도 비용 두 줄 + 존 이름 + 소유자 + 번호를 모두 읽는 것은 불가능.
대신 비용/소유자 상세 정보는 **타일 클릭 시 툴팁** 또는 **프롬프트에서 명시**.

**타일 CSS 변경**:
```css
.tile-card {
  min-height: 0;  /* aspect-ratio 1/1로 정사각형 유지 */
  aspect-ratio: 1 / 1;
  padding: 4px;  /* 6px → 4px */
  gap: 2px;      /* 4px → 2px */
}

.tile-head strong {
  font-size: 15px;  /* 17px → 15px */
}

.tile-head span {
  font-size: 10px;  /* 12px → 10px */
}

/* 제거 */
.tile-body {
  display: none;  /* 비용/존 텍스트 숨김 */
}

/* 소유자 dot 추가 */
.tile-owner-dot {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.5px solid rgba(255,255,255,0.5);
}

/* 말 토큰 크기 축소 */
.pawn-token {
  min-width: 24px;  /* 32px → 24px */
  height: 24px;
  font-size: 10px;
}
```

### B-2. 보드 내부 공간 활용

**현재**: 11×11 grid에서 외부 ring(40칸)만 사용, 내부 9×9 = 81칸 완전 빈 공간.

**변경**: 내부 중앙 영역에 `board-center-panel` 배치.

```css
.board-center-panel {
  grid-column: 2 / 11;   /* 열 2~10 */
  grid-row: 2 / 11;      /* 행 2~10 */
  display: grid;
  place-items: center;
  padding: 16px;
  border-radius: 16px;
  background: rgba(6, 15, 32, 0.72);
  border: 1px solid rgba(50, 80, 130, 0.4);
  pointer-events: none;  /* 타일 상호작용 방해 안 함 */
}
```

내부 패널 내용 (고정, 항상 보임):
```
┌─────────────────────────────────┐
│  라운드 3 / 턴 2                 │  font-size: 22px
│                                 │
│  ☀ 맑음                        │  font-size: 16px + 날씨 효과 14px
│  효과: 이동 +1                  │
│                                 │
│  현재: P2 교리감독관             │  font-size: 15px
│  → 주사위 굴리는 중...           │  font-size: 13px, 애니메이션 점
└─────────────────────────────────┘
```

9×9 내부 영역 = (75×9 + 8×8)px ≈ **675px × 675px** → 이 공간에 큼직하게 표시.

**내 턴일 때 내부 패널**:
```
┌─────────────────────────────────┐
│  ★ 내 차례                      │  font-size: 24px, color: #4ade80
│  P1 · 사기꾼                    │  font-size: 16px
│                                 │
│  지금 할 일:                    │  font-size: 14px
│  이동 방법을 선택하세요          │  font-size: 18px, color: #ffda77
│                                 │
│  ⏱ 28초                        │  font-size: 16px
└─────────────────────────────────┘
```

---

## ZONE C: 사이드 패널 — 5개 패널 → 2개 고정 패널

### 현재 사이드 컬럼에 쌓인 패널들
1. `SituationPanel` — 7개 항목 소형 텍스트
2. `PlayersPanel` — player-card 4개 세로 나열
3. `TimelinePanel` — 이벤트 40개 소형 텍스트

→ 세 패널 합산 높이 ≈ 800px+. 화면 아래로 스크롤해야 보임.

### 재설계: 사이드 컬럼 구조

```css
.match-side-column {
  position: sticky;
  top: 52px;          /* 헤더 높이 */
  height: calc(100vh - 52px);
  display: grid;
  grid-template-rows: auto 1fr;
  gap: 12px;
  overflow: hidden;   /* 내부에서만 스크롤 */
}
```

#### C-1. 상단 고정: 플레이어 바 (PlayersBar)

**현재 PlayersPanel**: 세로 나열, player-card 4개

**변경**: 가로 2×2 그리드, 고정 높이

```css
.players-bar {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.player-bar-card {
  padding: 10px 12px;
  border-radius: 12px;
  background: #081327;
  border: 1px solid #2b4e82;
  display: grid;
  gap: 4px;
}
```

**카드 내용 (각 카드 ~220px 너비)**:

```
┌──────────────────────────┐
│ ► P2  교리감독관         │  ← "►" 현재 턴 표시. font-size: 15px
│ ─────────────────────── │
│ 💰 45냥  🔷 3조각        │  font-size: 14px
│ 🏠 2타일  [숨은 1]       │  font-size: 13px
└──────────────────────────┘
```

| 요소 | 폰트 | 설명 |
|---|---|---|
| "►" + 플레이어 ID | 16px bold | 현재 턴 플레이어에만 표시, 애니메이션 |
| 인물 이름 | 14px | 드래프트 전: "?" |
| 자금 | 14px | 💰 아이콘 포함 |
| 조각 | 14px | 🔷 아이콘 |
| 타일 수 | 13px | 소유 타일 수 |
| 탈락 시 | 전체 dim | opacity: 0.4 |
| 내 카드 | border: #ffda77 | 항상 구분 가능 |

**높이**: 각 카드 약 72px × 2행 + gap = **약 152px** 고정.

#### C-2. 하단 확장: TurnPanel (내 턴 뷰 / 관전 뷰)

나머지 공간 모두 사용: `calc(100vh - 52px - 152px - 12px)` ≈ **684px**.

이 공간에 현재 TurnStagePanel + SpectatorTurnPanel + CoreActionPanel 통합.

내부 스크롤 허용:
```css
.turn-panel {
  overflow-y: auto;
  border-radius: 16px;
  border: 1px solid #3c5f95;
  background: #0e1f3d;
  display: grid;
  align-content: start;
  gap: 0;
}
```

---

## ZONE D: TurnPanel 상세 — 내 턴 뷰

### D-1. 레이아웃

```
┌─────────────────────────────────────────────────┐ ← border-bottom: 1px
│  섹션 헤더  "★ 내 차례 · P1 · 사기꾼"  [▼]     │  height: 48px
├─────────────────────────────────────────────────┤
│  컨텍스트 바                                     │  height: 44px, 1줄
│  ☀ 맑음 · 이동+1    사기꾼: 타일 인수 가능      │
├─────────────────────────────────────────────────┤
│  프롬프트 영역 (inline)                          │  flex-grow: 1
│  [프롬프트 유형별 내용]                          │
│                                                 │
│  ⏱ ████████████░░░░░░  28초                   │  height: 36px
├─────────────────────────────────────────────────┤
│  방금 일어난 일 (최근 3개만)                     │  ~120px
│  • 날씨 공개: 맑음                              │
│  • 드래프트: 사기꾼 선택                        │
│  • P3 이동 완료 (타일 15)                       │
└─────────────────────────────────────────────────┘
```

### D-2. 프롬프트 영역 — 유형별 구체적 설계

모든 프롬프트는 이 영역에서 처리. fixed modal 제거.

#### 이동 선택 (movement)

```
┌─────────────────────────────────────────────────┐
│  이동 방법 선택                                  │  font-size: 16px
│  현재 위치: 타일 8    날씨 보너스: +1            │  font-size: 13px
├─────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐             │
│  │  🎲 주사위   │  │  🃏 카드 3   │             │  카드 height: 80px
│  │   굴리기     │  │    사용      │             │  font-size: 16px
│  │  이동 1~6   │  │  3칸 이동    │             │  font-size: 13px
│  └──────────────┘  └──────────────┘             │
│  (손 패가 있으면 카드 1~6 선택지 추가)           │
└─────────────────────────────────────────────────┘
```

선택지 버튼:
```css
.prompt-choice-movement {
  padding: 14px 16px;
  min-height: 80px;
  font-size: 16px;  /* 현재 emphasis card는 button 내 strong 14px */
  border-radius: 14px;
  display: grid;
  gap: 4px;
}

.prompt-choice-movement strong {
  font-size: 18px;  /* 주요 선택지 레이블 */
}

.prompt-choice-movement small {
  font-size: 13px;  /* 부가 설명 */
  color: #c8d7f4;
}
```

#### 구매 결정 (purchase_tile)

```
┌─────────────────────────────────────────────────┐
│  타일 15 구매하겠습니까?                         │  font-size: 18px
│  하늘색 지역 · T3                               │  font-size: 13px
├─────────────────────────────────────────────────┤
│  구매가: 30냥    임대료: 8냥                     │  font-size: 22px  ← 크게
│  현재 내 자금: 45냥 → 구매 후: 15냥             │  font-size: 14px
├─────────────────────────────────────────────────┤
│  ┌────────────────────┐  ┌──────────────────┐  │
│  │  ✓ 구매 (30냥)     │  │  ✗ 패스          │  │  height: 72px
│  └────────────────────┘  └──────────────────┘  │  font-size: 18px
└─────────────────────────────────────────────────┘
```

```css
.prompt-purchase-cost {
  font-size: 22px;  /* 현재 모든 prompt 정보는 12-14px */
  font-weight: 800;
  color: #ffda77;
}
```

#### 인물 드래프트 (draft_card, final_character)

이 경우만 fullscreen overlay 사용 (카드 2장을 충분히 크게 봐야 하기 때문).

```
┌──────────────────────────────────────────────────────────┐  overlay, 600px 너비
│  인물 선택  라운드 3    P1 당신 선택 중    ⏱ 22초        │
├──────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐  ┌─────────────────────────┐│
│  │   교리감독관            │  │   사기꾼                ││
│  │   우선순위: 3           │  │   우선순위: 5           ││  카드 height: 200px
│  │                        │  │                        ││  font-size: 22px 이름
│  │  능력:                 │  │  능력:                 ││
│  │  징표 소유 + 방향 결정 │  │  다른 플레이어           ││  font-size: 14px 설명
│  │                        │  │  타일 인수 가능          ││
│  └─────────────────────────┘  └─────────────────────────┘│
│                  [이 카드 선택]                           │  각 카드 하단 버튼
│                                                          │
│  다른 플레이어: P2 ✓  P3 선택 중...  P4 대기            │
└──────────────────────────────────────────────────────────┘
```

```css
.draft-overlay {
  width: min(640px, calc(100vw - 32px));
  /* 타이트한 fixed: 1420px가 아니라 640px */
}

.draft-card {
  min-height: 200px;  /* 현재 emphasis card는 약 90px */
  padding: 20px;
}

.draft-card-name {
  font-size: 22px;  /* 현재 카드 레이블: 14px */
  font-weight: 800;
}

.draft-card-priority {
  font-size: 15px;
  color: #b6c5e7;
}

.draft-card-ability {
  font-size: 14px;
  line-height: 1.6;
  margin-top: 12px;
  color: #dfeaff;
}
```

#### 지목 선택 (mark_target)

```
┌─────────────────────────────────────────────────┐
│  지목할 인물을 선택하세요                        │  font-size: 16px
│  (자신보다 나중에 턴인 플레이어만 선택 가능)    │  font-size: 13px, 회색
├─────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐     │
│  │  사기꾼          │  │  객주            │     │  height: 64px
│  │  P2 플레이어     │  │  P3 플레이어     │     │  font-size: 16px
│  └──────────────────┘  └──────────────────┘     │
│  ┌──────────────────┐  ┌──────────────────┐     │
│  │  추노꾼 (공개됨) │  │  패스            │     │  disabled: 흐리게
│  │  P4 - 비활성     │  │  지목 안 함      │     │
│  └──────────────────┘  └──────────────────┘     │
└─────────────────────────────────────────────────┘
```

현재 문제: `markChoiceTitle/Description` 이 `target_character` 기준으로 작성되어 있지만
실제로는 플레이어 ID가 함께 표시되어야 함 → 위 layout에서 두 줄로 명시.

#### 랩 보상 (lap_reward)

```
┌─────────────────────────────────────────────────┐
│  🏃 완주 보상 선택                               │  font-size: 18px
│  현재 조각: 3개   현재 자금: 32냥                │  font-size: 14px
├─────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐│
│  │  💰 현금    │  │  🔷 조각    │  │  🏆 승점 ││  height: 88px
│  │  +15냥     │  │  +4개       │  │  +1점    ││  font-size: 22px ← 수량 크게
│  │            │  │            │  │          ││
│  └─────────────┘  └─────────────┘  └──────────┘│
└─────────────────────────────────────────────────┘
```

```css
.prompt-reward-amount {
  font-size: 22px;  /* 현재 prompt 내 수량은 description 13px에 묻힘 */
  font-weight: 900;
  color: #ffda77;
}
```

### D-3. 타임바 재설계

```css
.prompt-timebar {
  height: 6px;  /* 현재 height 미지정, 얇게 보임 */
  border-radius: 999px;
  background: rgba(50, 80, 130, 0.5);
  overflow: hidden;
  margin: 8px 0 4px;
}

.prompt-timebar span {
  display: block;
  height: 100%;
  background: linear-gradient(90deg, #4ade80, #facc15, #f87171);
  /* 남은 비율에 따라 색상 변화: 녹→황→적 */
  background-size: 300% 100%;
  background-position: calc(100% - var(--time-ratio) * 100%) center;
  transition: width 1s linear, background-position 1s linear;
}
```

10초 이하 숫자 표시:
```css
.prompt-seconds-critical {
  font-size: 24px;  /* 현재 secondsLeft 표시 없음 (텍스트로만) */
  font-weight: 900;
  color: #f87171;
  animation: criticalPulse 0.8s ease-in-out infinite;
  text-align: center;
}
```

---

## ZONE E: TurnPanel — 관전 뷰

### E-1. 레이아웃

현재 `SpectatorTurnPanel` 문제:
- 12개 소형 카드(180px 최소 너비)가 grid로 나열
- `journeyCards` + `spotlightCards` + `payoffBeats` 3중 구조
- 전부 동일한 정보를 다른 형태로 반복

**재설계**: 단일 이벤트 피드 (최신 이벤트 위에서 아래로).

```
┌─────────────────────────────────────────────────┐
│  👁 P2 · 교리감독관의 차례   R3 / T2            │  height: 48px
├─────────────────────────────────────────────────┤
│  방금 일어난 일 (실시간 서술)                    │
│                                                 │
│  ① 주사위 굴림 ————————— 5 나옴                │  font-size: 16px
│                                                 │
│  ② 이동 ——————————————— 7→12 (5칸)             │  font-size: 16px
│      [7] ▶ [8] ▶ [9] ▶ [10] ▶ [11] ▶ [12]     │  타일 칩 13px
│                                                 │
│  ③ 도착 ——————————————— 하늘색 타일 12          │  font-size: 16px
│      P1 소유 타일 · 임대료 12냥 발생            │  font-size: 14px, 경고색
│                                                 │
│  ④ 임대료 지불 ————————— P2 → P1  12냥         │  font-size: 16px
│      P2: 45냥 → 33냥   P1: 32냥 → 44냥         │  font-size: 13px
├─────────────────────────────────────────────────┤
│  P2 현재 상태: 💰 33냥  🔷 3조각               │  font-size: 14px
└─────────────────────────────────────────────────┘
```

### E-2. 이벤트 서술 컴포넌트

각 이벤트는 하나의 `turn-event-row` 로 표시:

```
① [이벤트 아이콘] [이벤트 이름] ——— [핵심 결과값]
   [보조 설명 (선택적)]
```

```css
.turn-event-row {
  display: grid;
  grid-template-columns: 24px auto 1fr auto;
  gap: 8px 12px;
  align-items: baseline;
  padding: 10px 0;
  border-bottom: 1px solid rgba(50, 80, 130, 0.3);
  font-size: 15px;  /* 현재 core-action feed: 12px */
}

.turn-event-index {
  font-size: 12px;
  color: #6b85b0;
  font-weight: 700;
}

.turn-event-name {
  color: #b6c5e7;
  font-size: 14px;
}

.turn-event-divider {
  border-top: 1px solid rgba(80, 110, 160, 0.3);
  margin: auto 0;
}

.turn-event-value {
  font-size: 16px;   /* 현재 core-action strong: 14px */
  font-weight: 700;
  color: #f2f6ff;
  text-align: right;
  white-space: nowrap;
}

.turn-event-sub {
  grid-column: 2 / -1;
  font-size: 13px;
  color: #8fa8d0;
  margin-top: -4px;
}
```

**내 타일에 상대 도착 시 강조**:
```css
.turn-event-row-alert {
  background: rgba(255, 218, 119, 0.08);
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid rgba(255, 218, 119, 0.3);
  margin: 4px 0;
}

.turn-event-row-alert .turn-event-value {
  color: #ffda77;
}
```

### E-3. 이벤트 서술 생성 로직 (streamSelectors 변경)

현재 `selectCoreActionFeed` 가 반환하는 `CoreActionItem.detail` 은 짧은 요약 문자열.

추가 필요:
```typescript
export type TurnEventRow = {
  seq: number;
  index: number;         // ①②③ 순번
  icon: string;          // 이벤트 아이콘 이모지 또는 클래스
  name: string;          // 이벤트 이름
  value: string;         // 핵심 결과값 (크게 표시)
  subText?: string;      // 보조 설명
  tone: "move" | "economy" | "effect" | "decision" | "alert";
  isAlert: boolean;      // 내 타일에 상대 도착 등 내게 영향 있는 이벤트
  tilePath?: number[];   // 이동 경로 타일 인덱스
};

export function selectTurnEventFeed(
  messages: InboundMessage[],
  localPlayerId: number | null,
  text: StreamSelectorTextResources
): TurnEventRow[]
```

이 함수에서 `player_move`, `dice_roll`, `landing_resolved`, `tile_purchased`, `rent_paid`, `fortune_drawn`, `fortune_resolved` 를 각각 위 구조로 변환.

---

## ZONE F: 제거 대상 — 완전 삭제

### 삭제 이유와 대체 방법

| 컴포넌트/요소 | 삭제 이유 | 대체 |
|---|---|---|
| `SituationPanel` | 헤더와 보드 내부에 정보 이미 있음 | GlobalHeader로 통합 |
| `TurnStagePanel` 의 `sceneCards` 스트립 | TurnPanel 이벤트 피드로 대체 | TurnPanel E-1 |
| `TurnStagePanel` 의 `outcomeCards` 스트립 | sceneCards와 중복 | 삭제 |
| `TurnStagePanel` 의 `spotlightCards` 스트립 | sceneCards와 중복 | 삭제 |
| `SpectatorTurnPanel` 의 `journeyCards` | TurnPanel E-1로 대체 | 삭제 |
| `SpectatorTurnPanel` 의 `payoffBeats` | TurnPanel E-1로 대체 | 삭제 |
| `CoreActionPanel` | TurnPanel E-1로 흡수 | 삭제 |
| `IncidentCardStack` (`theaterFeed`) | EventTimeline 하단 패널로 이동 | 접힘 패널 |
| Worker 상태 카드 (일반 뷰) | 일반 플레이어 불필요 정보 | ≡ 메뉴 내 숨김 |
| 보드 위 `board-weather-summary` 텍스트 | 보드 내부 패널로 통합 | BoardCenterPanel |
| 보드 위 `board-focus-summary` 텍스트 | 보드 내부 패널로 통합 | BoardCenterPanel |
| 보드 위 `board-move-summary` 텍스트 | TurnPanel 이벤트 피드로 대체 | 삭제 |
| `tile-body` (비용/존 텍스트) | 타일이 너무 작음, 프롬프트에서 명시 | 타일 hover 툴팁 |
| `turn-notice-banner` (fixed bottom) | 보드 내부 패널로 통합 | BoardCenterPanel |
| `promptSecondsLeft` 텍스트 표현 | 시각적 타임바 + 10초 이하만 숫자 | 타임바 강화 |

---

## ZONE G: 이벤트 타임라인 — 하단 접힘 패널

지금 `TimelinePanel`은 항상 표시됨.

**변경**:
```css
.event-timeline-drawer {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 90;
  max-height: 0;
  overflow: hidden;
  transition: max-height 300ms ease-out;
  background: rgba(6, 15, 32, 0.96);
  border-top: 1px solid #2b4e82;
}

.event-timeline-drawer.open {
  max-height: 40vh;
  overflow-y: auto;
}

.event-timeline-toggle {
  position: fixed;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  z-index: 91;
  padding: 4px 20px;
  border-radius: 12px 12px 0 0;
  font-size: 12px;
  background: #1c3764;
  border: 1px solid #345a93;
  border-bottom: none;
  cursor: pointer;
  color: #b6c5e7;
}
```

**드로어 내 이벤트 항목**: `timeline-item` 을 현재 크기 유지 (11-12px 텍스트 허용 — 히스토리는 작아도 됨).

---

## 구현 단계별 작업 목록

### Phase 1 — 레이아웃 수정 (가장 즉각적 효과)

1. **match-layout 비율 변경**
   - `minmax(0, 1.45fr) minmax(320px, 420px)` → `minmax(0, 2fr) minmax(0, 1fr)`
   - 사이드 컬럼 `max-width: 480px` 추가
   - 예상 파일: `styles.css` 292번 줄

2. **헤더 높이 축소 + 게임 정보 통합**
   - `App.tsx` 헤더 섹션 교체 (756-801번 줄)
   - 새 `GlobalHeader` 컴포넌트 생성
   - 기존 헤더 제목 42px → 로고 18px
   - route-tabs 버튼들 → `≡` 메뉴로 이동
   - 게임 상태 정보 (라운드/턴/날씨/현재 턴 플레이어) 헤더 삽입

3. **사이드 컬럼 sticky + height 고정**
   - `match-side-column` 에 `height: calc(100vh - 52px)`, `overflow: hidden` 추가

4. **`TurnStagePanel` / `SpectatorTurnPanel` 상호 배타 렌더**
   - `App.tsx` 893~898번 줄 수정
   - `isMyTurn ? <MyTurnPanel> : <SpectatorView>`

### Phase 2 — 타일 콘텐츠 단순화

5. **타일에서 텍스트 정보 제거**
   - `BoardPanel.tsx` 262-266번 줄 (`tile-body` 섹션) 제거
   - `tile-foot` 소유자 텍스트 → 소유자 dot으로 교체
   - CSS: `.tile-body { display: none }`

6. **소유자 dot 추가**
   - `BoardPanel.tsx` 타일 렌더에 `tile-owner-dot` div 추가
   - `playerColor(ownerPlayerId)` 색상 적용

7. **보드 내부 패널 (BoardCenterPanel)**
   - `BoardPanel.tsx` 에 `board-center-panel` div 추가 (타일 렌더 루프 외부)
   - grid-column/row 내부 영역 배치
   - 라운드, 날씨, 현재 턴 행동자 표시

### Phase 3 — TurnPanel 이벤트 피드

8. **`selectTurnEventFeed` 함수 추가**
   - `streamSelectors.ts` 에 `TurnEventRow` 타입 및 selector 추가
   - `player_move`, `dice_roll`, `rent_paid`, `tile_purchased`, `fortune_drawn`, `fortune_resolved`, `lap_reward_chosen` 처리

9. **`TurnEventFeed` 컴포넌트 생성**
   - `apps/web/src/features/stage/TurnEventFeed.tsx`
   - `TurnEventRow[]` 를 받아 ①②③ 형태로 렌더
   - `isAlert` 시 강조

10. **관전 뷰 (`SpectatorView`) 교체**
    - `SpectatorTurnPanel.tsx` 를 `SpectatorView.tsx` 로 교체
    - 내부: 행동자 헤더 + `TurnEventFeed` + 행동자 현재 상태 바

### Phase 4 — 프롬프트 inline화

11. **구매/랩보상/지목 프롬프트 inline 전환**
    - `PromptOverlay.tsx` 에서 `purchase_tile`, `lap_reward`, `mark_target` 섹션을 `TurnPanel` 내부로 이동
    - fixed modal → inline 컴포넌트

12. **드래프트 전용 오버레이**
    - `DraftOverlay.tsx` 신규 생성
    - `draft_card`, `final_character` 타입만 fullscreen modal 유지
    - 카드 height: 200px, 이름 font-size: 22px

13. **타임바 시각 강화**
    - `styles.css` prompt-timebar height: 6px, 색상 전환 gradient
    - 10초 이하 카운트다운 숫자 표시

### Phase 5 — 정리

14. **제거 대상 컴포넌트 삭제**
    - `SituationPanel` 렌더 제거 (`App.tsx` 935번 줄)
    - `TurnStagePanel` 내 sceneCards/outcomeCards/spotlightCards 삭제
    - `SpectatorTurnPanel` 내 journeyCards/payoffBeats 삭제 (Phase 3에서 대체됨)
    - `CoreActionPanel` 렌더 제거 (Phase 3에서 대체됨)
    - `board-weather-summary`, `board-focus-summary`, `board-move-summary` 보드 텍스트 제거

15. **`PlayersBar` 가로 전환 + 현재 턴 강조**
    - `PlayersPanel.tsx` grid 변경: 세로 → 2×2 가로
    - `currentActorPlayerId` prop 추가
    - `player-card-active` 스타일 추가

---

## 최종 예상 화면 구성 (1440px 뷰포트)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  헤더 (52px)                                                                │
│  [로고] 라운드 3 · 턴 2 · ► P2 교리감독관  ☀ 맑음·이동+1  ← →  [나:P1]  [≡]│
├───────────────────────────────────────────┬─────────────────────────────────┤
│                                           │  플레이어 바 (152px, 2×2 grid) │
│                                           │  ┌──────┐┌──────┐             │
│  보드 (912px 너비, 1:1 비율, ~860px 높이)  │  │►P2  ││ P1  │             │
│                                           │  │교리  ││사기  │             │
│  ┌──┬──┬──┬──┬──┬──┬──┬──┬──┬──┬──┐    │  │45냥  ││32냥  │             │
│  │1 │2 │3 │4 │5 │6 │7 │8 │9 │10│11│    │  └──────┘└──────┘             │
│  ├──┤  ┌──────────────────────┐  ├──┤    │  ┌──────┐┌──────┐             │
│  │40│  │ 라운드 3 / 턴 2      │  │12│    │  │ P3   ││ P4   │             │
│  ├──┤  │ ☀ 맑음 / 이동+1     │  ├──┤    │  │추노  ││만신  │             │
│  │39│  │ ► P2 교리감독관      │  │13│    │  │28냥  ││51냥  │             │
│  ├──┤  │ 주사위 굴리는 중...  │  ├──┤    │  └──────┘└──────┘             │
│  │38│  └──────────────────────┘  │14│    ├─────────────────────────────────┤
│  ├──┤                            ├──┤    │  TurnPanel (나머지 전체 높이)   │
│  │37│                            │15│    │                                │
│  ├──┤                            ├──┤    │  👁 P2 교리감독관의 차례       │
│  │36│                            │16│    │  ─────────────────────────────│
│  ├──┤                            ├──┤    │  ① 주사위 ────────── 5 나옴   │
│  │35│  ...나머지 보드 타일들...   │17│    │                                │
│  ├──┤                            ├──┤    │  ② 이동 ────── 7→12 (5칸)    │
│  │34│                            │18│    │  [7]▶[8]▶[9]▶[10]▶[11]▶[12] │
│  ├──┤                            ├──┤    │                                │
│  │33│                            │19│    │  ③ 도착 ────── 하늘색 타일12  │
│  ├──┤                            ├──┤    │  ⚠ P1 소유 · 임대료 12냥     │
│  │32│31│30│29│28│27│26│25│24│23│22│    │                                │
│  └──┴──┴──┴──┴──┴──┴──┴──┴──┴──┴──┘    │  ④ 임대료 ──── P2→P1  12냥   │
│   (타일 1개 ≈ 75px)                      │  P2: 45냥→33냥  P1: 32냥→44냥 │
│                                           │                                │
│                                           │  P2 현재: 💰 33냥  🔷 3조각  │
└───────────────────────────────────────────┴─────────────────────────────────┘
   [▲ 이벤트 이력] ← 하단 toggle 버튼 (고정, 평소 숨김)
```

---

## [CODEX RESPONSE] 2026-04-07

### 총평

이 문서는 구현 관점에서 유용하다. 특히 "왜 지금 작게 보이는가"를 수치로 설명한 부분이 좋다. 단순한 취향 문제가 아니라, 현재 grid 비율과 카드 폭이 실제 가독성을 무너뜨린다는 점을 설득력 있게 보여준다.

### 동의하는 부분

- 헤더를 52px 수준의 정보형 헤더로 압축하자는 방향
  - 현재 제목/탭/토글 줄은 게임 정보보다 도구 정보가 앞선다.
  - 라운드/턴/현재 행동자/날씨/내 상태를 헤더 1계층으로 끌어올리는 판단이 맞다.
- 보드 컬럼을 더 넓혀야 한다는 판단
  - 현재 보드는 "항상 보인다"보다 "존재만 한다"에 가깝다.
  - 타일이 읽히지 않으면 보드 중심 UX가 성립하지 않는다.
- 내부 9×9 공간을 활용하자는 제안
  - 현재처럼 비워두기보다 중앙에 현재 턴/날씨/행동 정보를 크게 보여주는 편이 훨씬 낫다.
  - 이건 로그 패널을 늘리는 것보다 체감 개선이 크다.

### 그대로 채택하면 위험한 부분

- 문서의 치수/열 비율은 방향성으로는 좋지만 "고정 사양"으로 바로 받아들이면 위험하다.
  - 최근 코드에서는 보드 상단 배치, 오버레이, 턴 배너 등 이미 일부 변경이 있었기 때문에 실제 사용 가능한 폭은 문서 작성 시점과 조금 다를 수 있다.
  - 따라서 `2fr / 1fr`, `75px 타일`, `52px 헤더`는 출발점이지 최종값으로 못 박기보다는 프로토타입 기준으로 보는 편이 맞다.
- 타일 내부 비용/존 이름/소유자 텍스트를 모두 제거하는 제안
  - 밀도 문제를 해결하려는 의도는 이해하지만, 현재 프로젝트는 규칙 이해 부족도 핵심 문제라서 정보를 너무 많이 걷어내면 설명력이 다시 떨어질 수 있다.
  - "항상 보이는 정보"와 "포커스 시 보이는 정보"를 분리하는 방식으로 조정하는 편이 더 안전하다.

### 왜 이 문서가 중요한가

이 문서는 단순한 미감 제안서가 아니라, 현재 레이아웃이 물리적으로 읽히지 않는다는 근거를 제공한다. 그래서 전면 재설계 문서보다 실제 구현 우선순위를 정하는 데 더 직접적인 가치가 있다.

### 결론

이 문서는 세부 치수의 절대 사양이라기보다, 현행 UI를 더 읽히게 만들기 위한 강한 레이아웃 가이드로 채택하는 것이 적절하다.
Status: ARCHIVED_REFERENCE_ONLY

This proposal is not the current execution source of truth.
Use `docs/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md` and active frontend docs first.
