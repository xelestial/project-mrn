# [PROPOSAL] UI/UX 상용 게임 레퍼런스 기반 재설계

Status: ARCHIVED_REFERENCE_ONLY
Updated: 2026-04-15
Author: Claude
Scope: apps/web — 상용 디지털 보드게임 UX 패턴 적용

Do not use as an execution source.
Use:
- `docs/frontend/[ACTIVE]_UI_UX_FUTURE_WORK_CANONICAL.md`

---

## 레퍼런스 분석

### Monopoly GO (모바일)
- 보드가 화면 전체를 차지, 다른 모든 정보는 보드 위 오버레이
- 플레이어 말은 크고 애니메이션. 착지 순간 화면 중앙에 타일 클로즈업 팝업
- "임대료 요청" 화면: 전체 화면 크기 이벤트 카드, 금액 대형 텍스트, 상대방 얼굴
- 파산: 별도 애니메이션 씬. 게임이 멈추고 모든 플레이어에게 공지

### 디지털 윷놀이 (카카오게임즈 등)
- 상단 고정: 내 자원 (돈/점수) 항상 노출
- 중앙 하단: 현재 행동 플레이어 이름 + "주사위 굴리는 중..." 텍스트 항상 표시
- 턴 전환 시 화면 밀어내기(slide) 애니메이션

### Catan Universe (PC/웹)
- 우측 사이드바: 모든 플레이어의 자원량을 아이콘+숫자로 항상 표시
- 좌측 하단: "행동 로그" 텍스트 피드 (항상 표시, 스크롤 가능)
- 선택 화면: 왜 이 선택이 필요한지 + 선택지별 결과 미리보기 포함
- 다른 플레이어 턴 중: "P2가 도시를 건설하려고 합니다 — 당신의 동의가 필요합니다" 팝업

### Among Us / 모바일 파티게임 공통 패턴
- 이벤트 인터럽트: 게임을 멈추고 중앙 팝업으로 중요 정보 전달
- 플레이어 "상태 뱃지": 아바타 옆에 현재 상태 아이콘 (이동 중, 구매 중, 파산 등)

---

## 현재 레이아웃의 핵심 문제

```
현재 (1440px):
┌─────────────────────────────┬──────────────────┐
│ 보드 (506px)                │ 사이드 (420px)   │
│ + 턴패널 (119px 카드 3열)   │ 상황/플레이어/   │
│ + 관전패널 (중복)           │ 타임라인         │
│                             │                  │
└─────────────────────────────┴──────────────────┘
```

문제:
- 보드 좌측에 세로로 쌓인 패널들 → 스크롤해야 정보 확인
- 다른 플레이어가 무엇을 하는지: 119px 카드 한 줄로 요약 → 읽기 불가능
- 프롬프트 이유: 전혀 없음. "이동 선택" 버튼만 보임
- 중요 이벤트: 텍스트 피드 한 줄로 흘러감

---

## 목표 레이아웃

```
1440px 화면:
┌──────────────────────────────────────────────────────────────────────────────┐
│ GlobalHeader (52px)                                                          │
│ [로고] [세션ID]     [P1●] [P2○] [P3○] [P4○]     [냥:1200] [내차례/대기]    │
└──────────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────┬───────────────────────────────────────┐
│ BOARD ZONE (좌, 65%)                 │ SIDE ZONE (우, 35%)                   │
│ ┌──────────────────────────────────┐ │ ┌─────────────────────────────────┐   │
│ │                                  │ │ │ ACTOR CARD (현재 행동 플레이어) │   │
│ │      BOARD (정사각형 꽉 참)       │ │ │ 키: 180px, 항상 보임            │   │
│ │      11×11 링 + 중앙 패널        │ │ └─────────────────────────────────┘   │
│ │                                  │ │ ┌─────────────────────────────────┐   │
│ └──────────────────────────────────┘ │ │ EVENT FEED (스크롤)             │   │
│ ┌──────────────────────────────────┐ │ │ 이번 게임에서 일어난 모든 일    │   │
│ │ ACTION ZONE                      │ │ │                                 │   │
│ │ - 내 턴: 프롬프트 + 컨텍스트     │ │ └─────────────────────────────────┘   │
│ │ - 관전: 관전 스트립              │ │ ┌─────────────────────────────────┐   │
│ └──────────────────────────────────┘ │ │ PLAYERS BAR (4명 자원 요약)     │   │
│                                      │ │ 항상 보임                       │   │
│                                      │ └─────────────────────────────────┘   │
└──────────────────────────────────────┴───────────────────────────────────────┘

중요 이벤트 발생시:
┌──────────────────────────────────────────────────────────────────────────────┐
│                          EVENT INTERRUPT OVERLAY                             │
│                   [전체화면 반투명] [중앙 이벤트 카드]                       │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Zone A — GlobalHeader

### 현재 문제
- `h1` 42px 로고가 헤더 절반 차지
- 연결 상태 / 세션 정보 기본 접힘
- 내가 지금 어떤 상태인지 (내 턴 / 대기) 헤더에 없음

### 목표 디자인

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ ●●●  BASEGAME  ┊  매치#4b2a  ┊  P1●최현  P2●이씨  P3●박학  P4●김순   ┊  대기중 ▶ │
│ 14px           ┊  14px       ┊  각 24px badge                        ┊  내상태  │
└──────────────────────────────────────────────────────────────────────────────┘
height: 52px; position: fixed; top: 0;
```

### CSS

```css
.global-header {
  height: 52px;
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  padding: 0 20px;
  gap: 24px;
  background: #0f0f0f;
  border-bottom: 1px solid #2a2a2a;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
}

.global-header-logo {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.global-header-players {
  display: flex;
  gap: 8px;
  justify-content: center;
}

.header-player-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 12px;
  background: #1e1e1e;
  border: 1.5px solid transparent;
}

.header-player-badge.is-actor {
  border-color: #f59e0b;  /* 현재 행동 중인 플레이어 강조 */
  background: #292008;
}

.header-player-badge.is-me {
  border-color: #3b82f6;
}

.header-player-badge.is-dead {
  opacity: 0.35;
  text-decoration: line-through;
}

.header-player-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.header-my-status {
  font-size: 13px;
  padding: 6px 16px;
  border-radius: 6px;
  font-weight: 600;
}

.header-my-status.my-turn {
  background: #f59e0b;
  color: #000;
  animation: pulse 1.5s infinite;
}

.header-my-status.waiting {
  background: #1e1e1e;
  color: #666;
}
```

---

## Zone B — Board Zone

### 현재 문제
- 보드가 화면 좌측 컬럼의 일부 → 실제 렌더 크기 약 506px
- 타일 크기: 46px. 텍스트 11px → 읽기 불가
- 내부 9×9 영역 완전 공백

### 목표: 보드 크기 확대 + 중앙 정보판

**레이아웃 변경**

```css
.match-layout {
  /* 현재: minmax(0, 1.45fr) minmax(320px, 420px) */
  /* 변경: */
  grid-template-columns: 1fr minmax(320px, 380px);
  margin-top: 52px;  /* GlobalHeader 높이 */
}

.board-ring-ring {
  /* 현재: width: min(100%, calc(100vh - 250px), 1180px) */
  /* 변경: */
  width: min(100%, calc(100vh - 52px - 160px), 760px);
}
```

1440px 기준: 좌측 컬럼 ≈ 1060px → 보드 ≈ 760px → 타일 ≈ 69px (현재 47px 대비 47% 증가)

### 타일 디자인 간소화

```css
.tile-card {
  min-height: 69px;
  padding: 5px 4px;
  gap: 2px;
  position: relative;
}

/* 타일 이름만 크게, 나머지 숨김 */
.tile-head strong {
  font-size: 13px;  /* 현재 17px → 더 작게 (타일도 크니까 적정) */
  line-height: 1.2;
}

.tile-body {
  display: none;  /* 타일 안에 비용 텍스트 제거 */
}

.tile-foot {
  display: none;  /* 타일 안에 ID 숫자 제거 */
}

/* 대신: 소유자 컬러 도트 */
.tile-owner-dot {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

/* 플레이어 위치 표시 개선 */
.tile-pawns {
  position: absolute;
  bottom: 3px;
  left: 3px;
  display: flex;
  gap: 2px;
  flex-wrap: wrap;
}

.tile-pawn {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
  border: 1.5px solid rgba(255,255,255,0.6);
}
```

### 보드 중앙 정보판 (Inner Panel)

현재 9×9 내부 영역(81칸)이 완전히 비어있음. 이를 활용:

```
보드 중앙 (약 5×5 칸 = 345px×345px):
┌─────────────────────┐
│  [현재 라운드: 3]   │
│  [날씨: 맑음 ☀]    │
│  ─────────────────  │
│  이번 턴:           │
│  P2 이씨가 이동 중  │
│  타일 12 → 18       │
│  ─────────────────  │
│  [최근 이벤트]      │
│  P1 건물 구매 완료  │
└─────────────────────┘
```

```css
/* board-ring-inner: 9×9 내부 그리드의 중앙 5×5 영역 */
.board-center-panel {
  grid-column: 2 / 10;   /* 11열 그리드에서 안쪽 9열 */
  grid-row: 2 / 10;
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: auto 1fr auto;
  padding: 16px;
  gap: 12px;
  background: #111;
  border: 1px solid #2a2a2a;
  border-radius: 8px;
  overflow: hidden;
}

.board-center-round-info {
  display: flex;
  gap: 12px;
  align-items: center;
  font-size: 13px;
}

.board-center-actor-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 6px;
}

.board-center-actor-name {
  font-size: 20px;
  font-weight: 700;
  color: #f59e0b;
}

.board-center-actor-action {
  font-size: 14px;
  color: #aaa;
}

.board-center-recent {
  font-size: 12px;
  color: #666;
  border-top: 1px solid #222;
  padding-top: 8px;
}
```

---

## Zone C — Action Zone (보드 하단)

### 현재 문제
- `TurnStagePanel`: 3열 119px 카드들 → 읽기 불가
- `SpectatorTurnPanel`: 별도 패널로 동시 렌더
- 정보 4곳 중복

### 목표: 상태에 따라 단일 패널 전환

```
내 턴 + 프롬프트 있음:  → PromptPanel (아래 설명)
내 턴 + 프롬프트 없음:  → WaitingPanel (스피너 + "처리 중")
관전 중:               → SpectatorStrip (다른 플레이어 행동 피드)
턴 없음:              → IdlePanel (게임 상태 요약)
```

```css
.action-zone {
  width: 100%;
  min-height: 160px;
  max-height: 320px;
  background: #0d0d0d;
  border-top: 2px solid #2a2a2a;
  border-radius: 0 0 8px 8px;
}
```

---

## Zone D — PromptPanel (핵심 재설계)

### 현재 문제
- 이동 선택 버튼만 나옴 → 왜 이 선택인지 모름
- 구매 제안: 돈이 얼마 있는지 / 얼마 내는지 / 이득인지 손해인지 없음
- 지목 선택: 왜 지목하는지 / 지목하면 어떻게 되는지 없음

### 목표: Catan Universe식 "컨텍스트 + 선택지 미리보기"

**프롬프트 패널 구조**

```
┌──────────────────────────────────────────────────────────────┐
│ [이유 영역] 왜 이 선택이 필요한가                            │
│ 예: "타일 15 '한양'에 착지했습니다. 이 타일은 구매 가능합니다"│
├──────────────────────────────────────────────────────────────┤
│ [현재 상태] 내 자원: 냥 1200   이 타일: 구매비 450냥        │
├──────────────────────────────────────────────────────────────┤
│ [선택지 미리보기]                                            │
│ [구매] → 냥 750 남음, 타일 소유권 획득                      │
│ [구매 안함] → 냥 1200 유지, 타일은 구매 가능 상태 유지       │
└──────────────────────────────────────────────────────────────┘
```

**CSS**

```css
.prompt-panel {
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 0;
  background: #0a0a0a;
  border-top: 2px solid #f59e0b;
  min-height: 200px;
  max-height: 360px;
}

.prompt-context {
  padding: 16px 20px 8px;
  background: #130f00;
  border-bottom: 1px solid #2a2a2a;
}

.prompt-context-reason {
  font-size: 15px;
  font-weight: 500;
  color: #e0c87a;
  line-height: 1.4;
  margin-bottom: 6px;
}

.prompt-context-state {
  font-size: 13px;
  color: #888;
  display: flex;
  gap: 20px;
}

.prompt-context-state strong {
  color: #ddd;
}

.prompt-choices {
  display: flex;
  gap: 12px;
  padding: 16px 20px;
  overflow-x: auto;
}

.prompt-choice-card {
  flex: 1;
  min-width: 160px;
  max-width: 280px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border: 1.5px solid #333;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  background: #111;
}

.prompt-choice-card:hover {
  border-color: #f59e0b;
  background: #1a1500;
}

.prompt-choice-label {
  font-size: 15px;
  font-weight: 600;
  color: #fff;
}

.prompt-choice-preview {
  font-size: 12px;
  color: #888;
  line-height: 1.4;
}

.prompt-choice-preview.positive { color: #4ade80; }
.prompt-choice-preview.negative { color: #f87171; }
.prompt-choice-preview.neutral  { color: #888; }
```

### 프롬프트 타입별 컨텍스트 메시지

```typescript
// apps/web/src/features/prompt/promptContext.ts

export interface PromptContext {
  reason: string;      // 왜 이 선택이 필요한가
  stateLine: string;   // 현재 상태 요약
  choicePreview: (choice: string) => { text: string; sentiment: "positive" | "negative" | "neutral" };
}

function buildPromptContext(prompt: ActivePrompt, snapshot: SessionSnapshot): PromptContext {
  switch (prompt.type) {
    case "move_select":
      return {
        reason: `타일 ${prompt.currentTile}에서 이동합니다. 이동할 타일을 선택하세요.`,
        stateLine: `현재 위치: 타일 ${prompt.currentTile} | 내 자산: ${snapshot.myMoney}냥`,
        choicePreview: (choice) => {
          const tile = snapshot.tiles[parseInt(choice)];
          if (tile.ownerId && tile.ownerId !== snapshot.myPlayerId)
            return { text: `→ 임대료 ${tile.rentCost}냥 지불 예정`, sentiment: "negative" };
          if (!tile.ownerId && tile.purchasable)
            return { text: `→ 구매 가능 (${tile.purchaseCost}냥)`, sentiment: "neutral" };
          return { text: `→ 이동`, sentiment: "neutral" };
        }
      };

    case "purchase_confirm":
      const tile = snapshot.tiles[prompt.tileIndex];
      const afterPurchase = snapshot.myMoney - tile.purchaseCost;
      return {
        reason: `타일 ${prompt.tileIndex} '${tile.name}'에 착지했습니다. 구매할 수 있습니다.`,
        stateLine: `내 잔액: ${snapshot.myMoney}냥 | 구매비: ${tile.purchaseCost}냥`,
        choicePreview: (choice) => {
          if (choice === "yes")
            return { text: `→ 잔액 ${afterPurchase}냥 남음, 타일 소유권 획득`, sentiment: afterPurchase > 0 ? "positive" : "negative" };
          return { text: `→ 잔액 유지, 타일은 구매 가능 상태`, sentiment: "neutral" };
        }
      };

    case "jinmok_select":  // 지목
      return {
        reason: `지목 카드를 사용합니다. 상대 플레이어를 선택하면 해당 플레이어의 타일로 이동시킬 수 있습니다.`,
        stateLine: `지목 효과: 선택한 플레이어를 지정 위치로 강제 이동`,
        choicePreview: (playerId) => {
          const player = snapshot.players.find(p => p.id === parseInt(playerId));
          return { text: `→ ${player?.name ?? playerId}를 지목`, sentiment: "neutral" };
        }
      };

    case "rent_confirm":
      const landlord = snapshot.players.find(p => p.id === prompt.landlordId);
      return {
        reason: `'${prompt.tileName}' (소유: ${landlord?.name ?? "??"})에 착지했습니다. 임대료를 납부해야 합니다.`,
        stateLine: `내 잔액: ${snapshot.myMoney}냥 | 임대료: ${prompt.rentCost}냥 | 납부 후 잔액: ${snapshot.myMoney - prompt.rentCost}냥`,
        choicePreview: (_) => {
          const after = snapshot.myMoney - prompt.rentCost;
          if (after < 0) return { text: `→ 잔액 부족! 파산 위기`, sentiment: "negative" };
          return { text: `→ ${after}냥 남음`, sentiment: after < 200 ? "negative" : "neutral" };
        }
      };

    case "lap_reward":
      // 패치 5958aa6: 이제 혼합 조합 지원 + public_context에 비용/자원 포함
      const budget = prompt.publicContext["budget"] as number ?? 0;
      const pools = prompt.publicContext["pools"] as Record<string, number> ?? {};
      const cashCost   = (prompt.publicContext["cash_point_cost"]   as number) ?? 2;
      const shardCost  = (prompt.publicContext["shards_point_cost"] as number) ?? 3;
      const coinCost   = (prompt.publicContext["coins_point_cost"]  as number) ?? 3;
      return {
        reason: `${budget}포인트 예산 안에서 보상을 선택합니다. 현금·조각·승점을 조합할 수 있습니다.`,
        stateLine: [
          `예산: ${budget}P`,
          pools["cash"] != null   ? `현금 잔여: ${pools["cash"]}개 (1개=${cashCost}P)`  : null,
          pools["shards"] != null ? `조각 잔여: ${pools["shards"]}개 (1개=${shardCost}P)` : null,
          pools["coins"] != null  ? `승점 잔여: ${pools["coins"]}개 (1개=${coinCost}P)`  : null,
          `내 현금: ${prompt.publicContext["player_cash"] ?? "-"}냥`,
          `내 조각: ${prompt.publicContext["player_shards"] ?? "-"}개`,
          `내 총점: ${prompt.publicContext["player_total_score"] ?? "-"}점`,
        ].filter(Boolean).join(" | "),
        choicePreview: (choiceId) => {
          // choiceId 형식: "cash-2_shards-1_coins-0"
          const m = choiceId.match(/cash-(\d+)_shards-(\d+)_coins-(\d+)/);
          if (!m) return { text: "", sentiment: "neutral" };
          const [, c, s, k] = m.map(Number);
          const parts = [];
          if (c > 0) parts.push(`현금 +${c}`);
          if (s > 0) parts.push(`조각 +${s}`);
          if (k > 0) parts.push(`승점 +${k}`);
          const spent = c * cashCost + s * shardCost + k * coinCost;
          return { text: `→ ${parts.join(" / ")}  (${spent}P 소모)`, sentiment: "positive" };
        }
      };

    case "coin_placement":
      // 패치 5958aa6: 승점 배치 — public_context에 placed_coins, total_score, candidate_tiles 포함
      const placedCoins = prompt.publicContext["player_placed_coins"] as number ?? 0;
      const totalScore  = prompt.publicContext["player_total_score"]  as number ?? 0;
      const candidateTiles = (prompt.publicContext["candidate_tiles"] as number[] ?? []);
      return {
        reason: "승점 코인을 놓을 토지를 선택합니다. 선택한 토지의 가중치가 최종 점수에 반영됩니다.",
        stateLine: `현재 배치 승점: ${placedCoins}개 | 현재 총점: ${totalScore}점 | 후보 토지: ${candidateTiles.length}칸`,
        choicePreview: (tileIdx) => {
          const tile = snapshot.tiles[parseInt(tileIdx)];
          return { text: `→ 타일 ${parseInt(tileIdx) + 1} '${tile?.name ?? "?"}' 에 배치`, sentiment: "neutral" };
        }
      };

    case "trick_tile_target":
      // 패치 5958aa6: 잔꾀 효과의 대상 토지 선택 — card_name, candidate_count, target_scope 포함
      const cardName       = (prompt.publicContext["card_name"]       as string) ?? "잔꾀 카드";
      const candidateCount = (prompt.publicContext["candidate_count"] as number) ?? 0;
      const targetScope    = (prompt.publicContext["target_scope"]    as string) ?? "";
      return {
        reason: `'${cardName}' 효과를 적용할 토지를 선택합니다.${targetScope ? ` (범위: ${targetScope})` : ""}`,
        stateLine: `선택 가능한 토지: ${candidateCount}칸`,
        choicePreview: (tileIdx) => {
          const tile = snapshot.tiles[parseInt(tileIdx)];
          return { text: `→ 타일 ${parseInt(tileIdx) + 1} '${tile?.name ?? "?"}' 대상 지정`, sentiment: "neutral" };
        }
      };

    case "draft_card":
      // 패치 5958aa6: public_context에 draft_phase, offered_names, offered_abilities 포함
      const draftPhase   = (prompt.publicContext["draft_phase"]    as number) ?? 1;
      const offeredNames = (prompt.publicContext["offered_names"]  as string[]) ?? [];
      return {
        reason: `${draftPhase}차 드래프트입니다. 이번 라운드에서 사용할 인물 카드를 가져가세요.`,
        stateLine: `후보 ${offeredNames.length}장: ${offeredNames.join(", ") || "-"}`,
        choicePreview: (cardId) => {
          const abilities = prompt.publicContext["offered_abilities"] as string[];
          const idx = offeredNames.findIndex((_, i) => String(i) === cardId);
          const ability = abilities?.[idx] ?? "";
          return { text: ability ? `→ 능력: ${ability}` : `→ 선택`, sentiment: "neutral" };
        }
      };

    default:
      return {
        reason: prompt.description ?? "선택이 필요합니다",
        stateLine: "",
        choicePreview: () => ({ text: "", sentiment: "neutral" })
      };
  }
}
```

---

## Zone E — SpectatorStrip (다른 플레이어 행동 표시)

### 현재 문제
- `SpectatorTurnPanel`: 180px 카드 여러 개 → 읽기 불가
- "P2가 이동 중" 수준의 정보도 없음
- 관전 중인지 내 턴 준비 중인지 불분명

### 목표: 내러티브 피드 형식 (Monopoly GO의 행동 텍스트 스트립)

```
관전 모드:
┌──────────────────────────────────────────────────────────────┐
│ 👁 P2 이씨의 턴                                              │
│ ──────────────────────────────────────────────────────────── │
│ ▶ 주사위 결과: 5+3 = 8칸 이동                               │
│ ▶ 타일 22 '전주'에 착지                                      │
│ ▶ 이씨가 소유한 타일 → 임대료 없음                          │
│   [다음 내 턴까지: P3 → P4 → P1 → 나]                       │
└──────────────────────────────────────────────────────────────┘
```

```css
.spectator-strip {
  padding: 16px 20px;
  background: #0d0d0d;
  border-top: 2px solid #3b82f6;
}

.spectator-strip-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #93c5fd;
  margin-bottom: 10px;
}

.spectator-strip-feed {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.spectator-feed-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 14px;
  line-height: 1.5;
  color: #ccc;
}

.spectator-feed-icon {
  width: 16px;
  flex-shrink: 0;
  color: #666;
  margin-top: 2px;
}

.spectator-turn-order {
  margin-top: 12px;
  font-size: 12px;
  color: #555;
  border-top: 1px solid #1e1e1e;
  padding-top: 8px;
}

.spectator-turn-order .my-turn-next {
  color: #f59e0b;
  font-weight: 600;
}
```

---

## Zone F — Side Column: ActorCard + EventFeed + PlayersBar

### ActorCard (현재 행동 플레이어, 상단 고정)

**패치 5958aa6 반영**: `TurnStageViewModel`에 `actorCash`, `actorShards`, `actorHandCoins`, `actorPlacedCoins`, `actorTotalScore`, `actorOwnedTileCount` 필드가 추가됐다. `decision_requested` 이벤트의 `public_context`에서 자동으로 채워지므로, ActorCard는 별도 snapshot 조회 없이 ViewModel만으로 행동 플레이어의 자원을 표시할 수 있다.

```
┌───────────────────────────────────┐
│ [P2 이씨] 행동 중                │ ← 18px 이름, 배지
│ ──────────────────────────────── │
│ 위치: 타일 22 전주               │ ← 14px
│ 현금: 780냥  조각: 1  승점: 3   │ ← actorCash/actorShards/actorTotalScore
│ 소유 토지: 5칸                   │ ← actorOwnedTileCount
│ [이동 중] ●●●●●●●●              │ ← 진행 표시
└───────────────────────────────────┘
height: 160px; flex-shrink: 0;
```

데이터 소스:
- `model.actorCash` → 현금 (냥)
- `model.actorShards` → 조각
- `model.actorTotalScore` → 총점 (`actorHandCoins + actorPlacedCoins`)
- `model.actorOwnedTileCount` → 소유 토지 수

null인 경우(아직 decision_requested 미도달): "-" 표시로 폴백.

```css
.actor-card {
  padding: 16px;
  background: #0d0d0d;
  border: 1.5px solid #f59e0b;
  border-radius: 8px;
  flex-shrink: 0;
}

.actor-card-name {
  font-size: 18px;
  font-weight: 700;
  color: #f59e0b;
  margin-bottom: 10px;
}

.actor-card-stats {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 4px 12px;
  font-size: 13px;
}

.actor-card-stats dt { color: #666; }
.actor-card-stats dd { color: #ddd; font-weight: 500; }

.actor-progress {
  display: flex;
  gap: 3px;
  margin-top: 10px;
}

.actor-progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f59e0b;
}

.actor-progress-dot.pending {
  background: #333;
}
```

### EventFeed (이번 게임 전체 이벤트 스크롤)

```
┌───────────────────────────────────┐
│ 게임 기록                         │ ← 13px 제목
│ ──────────────────────────────── │
│ T12 P1 타일 8 구매 +50냥        │ ← 12px, 위에서 최신
│ T11 P3 P2에게 임대료 30냥        │
│ T10 P2 운수 카드 뽑음           │
│ T09 P1 타일 3 이동              │
│ ...                              │
└───────────────────────────────────┘
flex: 1; overflow-y: auto;
```

```css
.event-feed {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
  background: #090909;
  border-radius: 8px;
}

.event-feed-header {
  font-size: 12px;
  color: #555;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #1e1e1e;
}

.event-row {
  display: grid;
  grid-template-columns: 30px 24px 1fr;
  gap: 4px;
  padding: 4px 0;
  font-size: 12px;
  line-height: 1.4;
  border-bottom: 1px solid #0f0f0f;
}

.event-row-turn { color: #555; }
.event-row-player { color: #aaa; font-weight: 600; }
.event-row-text { color: #ccc; }

/* 중요도별 강조 */
.event-row.critical { background: #1a0000; }
.event-row.critical .event-row-text { color: #f87171; }
.event-row.gain .event-row-text { color: #4ade80; }
.event-row.loss .event-row-text { color: #fb923c; }
```

### PlayersBar (항상 표시, 하단 고정)

**포함 데이터**: `cash`(냥), `shards`(조각), `ownedTileCount`(소유 타일 수), `hiddenTrickCount`(히든 잔꾀 수) — API에서 모두 내려옴.

```
┌────────────────────────────────────────────────────┐
│ ● P1 최현   1200냥  ◆3조각  🏠3칸  🃏2잔꾀       │ ← 내 정보 (강조)
│ ○ P2 이씨    780냥  ◆1조각  🏠5칸  🃏1잔꾀  ▶행동│ ← 현재 행동 중
│ ○ P3 박학    540냥  ◆0조각  🏠2칸  🃏0잔꾀       │
│ ✕ P4 김순      0냥  파산                           │ ← 파산 (흐림)
└────────────────────────────────────────────────────┘
height: 4 × 52px = 208px; flex-shrink: 0;
```

각 행의 자원 아이콘은 항상 표시. 값이 0인 항목은 흐림 처리해 시각적 노이즈 최소화.

```css
.players-bar {
  flex-shrink: 0;
  background: #0d0d0d;
  border-radius: 8px;
  overflow: hidden;
}

.player-row {
  display: grid;
  grid-template-columns: 24px 80px 1fr;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  height: 52px;
  border-bottom: 1px solid #111;
  transition: background 0.1s;
}

/* 자원 아이콘 묶음 */
.player-row-resources {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: nowrap;
}

.player-resource {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  white-space: nowrap;
}

.player-resource-icon {
  font-size: 11px;
  opacity: 0.7;
}

.player-resource-value {
  font-size: 13px;
  font-weight: 600;
}

/* 냥: 노랑, 조각: 보라, 타일: 초록, 잔꾀: 파랑 */
.player-resource.cash   .player-resource-value { color: #f59e0b; }
.player-resource.shards .player-resource-value { color: #a78bfa; }
.player-resource.tiles  .player-resource-value { color: #4ade80; }
.player-resource.tricks .player-resource-value { color: #60a5fa; }

/* 값 0이면 흐림 */
.player-resource.zero { opacity: 0.3; }

.player-row.is-me {
  background: #0a0f1a;
}

.player-row.is-actor {
  background: #130f00;
  border-left: 3px solid #f59e0b;
}

.player-row.is-dead {
  opacity: 0.4;
}

.player-row-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}

.player-row-name {
  font-size: 13px;
  font-weight: 500;
  color: #ccc;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-row-money {
  font-size: 13px;
  font-weight: 600;
  color: #f59e0b;
  white-space: nowrap;
}

.player-row-tile {
  font-size: 11px;
  color: #555;
  white-space: nowrap;
}
```

---

## Zone G — Critical Event Interrupt Overlay

### 현재 문제
- 파산: 이벤트 피드 한 줄로 흘러감
- 임대료 발생: 관전자에게 보이지 않음
- 특수 카드 효과: 작은 카드에 요약

### 목표: 중요 이벤트는 게임을 멈추고 전면 알림

**이벤트 인터럽트 조건**
1. 내가 임대료를 내야 함 (rent_confirm 프롬프트)
2. 다른 플레이어가 파산함
3. 내가 파산 위기 (자산 < 200냥)
4. 특수 카드: 어사, 자객, 사기꾼 효과

**디자인 (Monopoly GO 스타일)**

```
전체 화면:
┌────────────────────────────────────────────────────┐
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│░░░░░  ┌──────────────────────────┐  ░░░░░░░░░░░░░│
│░░░░░  │     💸 임대료 납부!      │  ░░░░░░░░░░░░░│
│░░░░░  │  ──────────────────────  │  ░░░░░░░░░░░░░│
│░░░░░  │  P3 박학의 '전주'에     │  ░░░░░░░░░░░░░│
│░░░░░  │  착지했습니다.           │  ░░░░░░░░░░░░░│
│░░░░░  │                          │  ░░░░░░░░░░░░░│
│░░░░░  │  납부액  ┌──────────┐   │  ░░░░░░░░░░░░░│
│░░░░░  │  120냥   │ 납부하기 │   │  ░░░░░░░░░░░░░│
│░░░░░  │          └──────────┘   │  ░░░░░░░░░░░░░│
│░░░░░  └──────────────────────────┘  ░░░░░░░░░░░░░│
│░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
└────────────────────────────────────────────────────┘
```

```css
.event-interrupt-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;  /* PromptOverlay(999)보다 높게 */
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.80);
  backdrop-filter: blur(4px);
}

.event-interrupt-card {
  width: min(480px, calc(100vw - 32px));
  background: #111;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.8);
}

.event-interrupt-header {
  padding: 20px 24px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.event-interrupt-icon {
  font-size: 36px;
}

.event-interrupt-title {
  font-size: 22px;
  font-weight: 700;
}

/* 타입별 색상 */
.event-interrupt-card.rent    { border-top: 4px solid #f59e0b; }
.event-interrupt-card.rent .event-interrupt-title { color: #f59e0b; }

.event-interrupt-card.bankruptcy { border-top: 4px solid #ef4444; }
.event-interrupt-card.bankruptcy .event-interrupt-title { color: #ef4444; }

.event-interrupt-card.gain    { border-top: 4px solid #22c55e; }
.event-interrupt-card.gain .event-interrupt-title { color: #22c55e; }

.event-interrupt-body {
  padding: 0 24px 16px;
  font-size: 15px;
  color: #aaa;
  line-height: 1.6;
}

.event-interrupt-amount {
  font-size: 36px;
  font-weight: 800;
  text-align: center;
  padding: 12px 0;
  color: #fff;
}

.event-interrupt-footer {
  padding: 12px 24px 20px;
  display: flex;
  justify-content: center;
}

.event-interrupt-btn {
  padding: 12px 40px;
  font-size: 16px;
  font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  border: none;
}

.event-interrupt-btn.primary {
  background: #f59e0b;
  color: #000;
}

/* 파산 전용: 전체 애니메이션 */
@keyframes bankruptcyShake {
  0%, 100% { transform: translateX(0); }
  10%, 30%, 50%, 70%, 90% { transform: translateX(-4px); }
  20%, 40%, 60%, 80% { transform: translateX(4px); }
}

.event-interrupt-card.bankruptcy {
  animation: bankruptcyShake 0.6s ease-in-out;
}

/* 다른 플레이어 파산 시 */
.bankruptcy-player-info {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  border-top: 1px solid #1e1e1e;
  border-bottom: 1px solid #1e1e1e;
  margin: 8px 0;
}
```

### 인터럽트 발생 조건 및 메시지

| 이벤트 | 조건 | 제목 | 자동 닫힘 |
|---|---|---|---|
| 임대료 납부 | `rent_confirm` 프롬프트 (내가 납부) | "임대료 납부" | 납부 버튼 클릭 |
| 임대료 수령 | 다른 플레이어가 내 타일에서 임대료 납부 | "임대료 수령!" | 3초 |
| 타인 파산 | `player_eliminated` 이벤트 | "P2 파산!" | 4초 |
| 내 파산 | 잔액 < 납부액 | "파산..." | 확인 버튼 |
| 어사 카드 | `inspector_visit` 이벤트 | "어사 방문!" | 4초 |
| 자객 카드 | `assassin_visit` 이벤트 (내가 대상) | "자객 출현!" | 확인 버튼 |
| 운수 카드 (큰 금액) | 금액 변화 > 200냥 | "운수 카드" | 3초 |

---

## Zone H — 토지 소유 현황 패널

### 현재 문제
- 보드 타일에 소유자 컬러 도트만 있음 → 내가 어느 타일을 가졌는지 보드 전체를 눈으로 찾아야 함
- 소유 타일 수(`ownedTileCount`)는 숫자만 표시 → 어느 타일인지 모름
- 타인 소유 타일 현황 비교 불가

### 데이터 출처
- `player.ownedTileCount`: 각 플레이어의 소유 타일 수 (스냅샷 항상 내려옴)
- `tile.ownerPlayerId`: 보드 타일 스냅샷에 포함 (BoardPanel에서 이미 사용 중)
- 타일 이름: `manifestTiles`에서 조회 가능

### 목표 디자인 (Catan Universe 자원 현황판 참고)

```
사이드 컬럼 — 접이식 패널 (기본 펼침):

┌─────────────────────────────────────┐
│ 토지 현황                    [접기] │
│ ─────────────────────────────────── │
│ ● P1 최현  🏠🏠🏠  (3칸)           │
│   8번 전주  ·  15번 한양  ·  22번 개성 │
│ ─────────────────────────────────── │
│ ○ P2 이씨  🏠🏠🏠🏠🏠  (5칸)       │
│   3번 부산  ·  7번 광주  ·  11번 대구 │
│   19번 수원  ·  31번 원산           │
│ ─────────────────────────────────── │
│ ○ P3 박학  🏠🏠  (2칸)             │
│   2번 인천  ·  38번 평양            │
│ ─────────────────────────────────── │
│ ✕ P4 김순  —  (파산)               │
└─────────────────────────────────────┘
```

접힌 상태에서는 각 플레이어 한 줄로 요약:
```
│ ● P1 최현  🏠×3  ○ P2 이씨  🏠×5  ○ P3 박학  🏠×2  ✕ P4 김순  —  │
```

### CSS

```css
.land-status-panel {
  background: #0d0d0d;
  border-radius: 8px;
  overflow: hidden;
  flex-shrink: 0;
}

.land-status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  cursor: pointer;
  border-bottom: 1px solid #1e1e1e;
}

.land-status-title {
  font-size: 12px;
  font-weight: 600;
  color: #555;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.land-status-body {
  padding: 0;
}

.land-player-section {
  padding: 10px 14px;
  border-bottom: 1px solid #111;
}

.land-player-section.is-me {
  background: #0a0f1a;
}

.land-player-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.land-player-name {
  font-size: 13px;
  font-weight: 600;
  color: #ccc;
}

.land-player-count {
  font-size: 11px;
  color: #555;
  margin-left: auto;
}

.land-tile-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.land-tile-chip {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  background: #1a1a1a;
  color: #aaa;
  border: 1px solid #2a2a2a;
  white-space: nowrap;
}

/* 내 타일 칩은 색상 강조 */
.land-player-section.is-me .land-tile-chip {
  border-color: #3b82f6;
  color: #93c5fd;
  background: #0a1628;
}
```

### 배치
사이드 컬럼 레이아웃 변경:
```
┌──────────────────────────────────┐
│ ActorCard (140px, flex-shrink:0) │
├──────────────────────────────────┤
│ LandStatusPanel (접이식, ~200px) │
├──────────────────────────────────┤
│ EventFeed (flex:1, 스크롤)       │
├──────────────────────────────────┤
│ PlayersBar (208px, flex-shrink:0)│
└──────────────────────────────────┘
```

---

## Zone I — 잔꾀 현황 패널 (내 패)

### 현재 문제
- 내가 어떤 잔꾀 카드를 손에 들고 있는지 프롬프트(`trick_to_use`, `hidden_trick_card`)가 열릴 때만 확인 가능
- 관전 중엔 내 패를 전혀 볼 수 없음
- "히든 잔꾀 지정" 프롬프트가 왜 뜨는지 — 내 패를 모르면 판단 불가

### 데이터 출처
- `player.hiddenTrickCount`: 내 히든 잔꾀 수 (스냅샷 항상 내려옴)
- `prompt.publicContext` 내 `trick_cards`: 프롬프트 시 패 목록 제공됨
- 단, **프롬프트 밖에서의 패 목록**은 현재 API에서 미제공 → 서버 확인 필요

### 설계 방향 (두 단계)

**1단계 (서버 확인 전): 숫자 기반 표시**
```
┌────────────────────────────────────┐
│ 내 잔꾀 패                         │
│ ─────────────────────────────────  │
│ 🃏 잔꾀 카드 3장 보유               │
│    (히든 1장 포함)                  │
│ ─────────────────────────────────  │
│ 카드 목록은 내 턴에 확인 가능       │
└────────────────────────────────────┘
```

**2단계 (서버에서 항상 패 목록 제공 시): 카드 목록 표시**
```
┌────────────────────────────────────┐
│ 내 잔꾀 패  (3장)                  │
│ ─────────────────────────────────  │
│ [사기꾼]  이동 후 효과 발동         │ ← 일반 잔꾀
│ [추노꾼]  타일 착지 시 발동         │ ← 일반 잔꾀
│ [박수  ]  ██████████  (히든)        │ ← 히든: 이름 숨김
└────────────────────────────────────┘
```

히든 잔꾀 카드는 카드 이름을 숨기고 "히든" 표시만. 상대방에게도 히든이므로 게임 정보 보호.

### CSS

```css
.my-tricks-panel {
  background: #0d0d0d;
  border-radius: 8px;
  padding: 12px 14px;
  flex-shrink: 0;
}

.my-tricks-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.my-tricks-title {
  font-size: 12px;
  font-weight: 600;
  color: #555;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.my-tricks-count {
  font-size: 12px;
  color: #60a5fa;
  font-weight: 600;
}

/* 카드 목록 (2단계) */
.trick-card-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.trick-card-row {
  display: grid;
  grid-template-columns: 80px 1fr;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: #111;
  border: 1px solid #222;
}

.trick-card-name {
  font-size: 13px;
  font-weight: 600;
  color: #ddd;
}

.trick-card-desc {
  font-size: 11px;
  color: #666;
}

/* 히든 카드 */
.trick-card-row.hidden {
  border-color: #1d4ed8;
  background: #0a1628;
}

.trick-card-row.hidden .trick-card-name {
  background: #1e3a5f;
  border-radius: 3px;
  color: transparent;
  user-select: none;
  /* 텍스트 가림 — 자신만 볼 수 있는 화면에서는 hover로 보기 가능 */
}

.trick-card-row.hidden:hover .trick-card-name {
  color: #93c5fd;
  background: transparent;
}

.trick-card-hidden-badge {
  font-size: 10px;
  color: #3b82f6;
  font-weight: 600;
  letter-spacing: 0.05em;
}

/* 숫자만 표시 (1단계) */
.tricks-count-only {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #aaa;
}

.tricks-count-number {
  font-size: 22px;
  font-weight: 700;
  color: #60a5fa;
}
```

### 서버 작업 필요 여부

| 기능 | 필요 서버 변경 | 우선순위 |
|---|---|---|
| 히든 잔꾀 수 표시 | 없음 (이미 `hiddenTrickCount` 내려옴) | 즉시 가능 |
| 전체 잔꾀 수 표시 | 없음 (`hiddenTrickCount` + 일반 카드 수 합산) | 즉시 가능 |
| 카드 이름 목록 표시 | 스냅샷에 `my_trick_cards` 배열 추가 필요 | 서버 확인 후 |

---

## Phase 구현 순서

### Phase 1 — 레이아웃 수정 (1~2일)
1. `App.tsx`: `match-layout` 비율 변경, `GlobalHeader` 분리
2. `styles.css`: 헤더 52px 고정, 보드 크기 수식 변경
3. `PlayersPanel.tsx` → `PlayersBar.tsx` 재작성 (44px 행 기반)
4. `App.tsx`: `currentActorId` → `PlayersBar` + `GlobalHeader` 전달

### Phase 2 — ActorCard + EventFeed (1일)
5. `ActorCard.tsx` 신규 컴포넌트 작성
6. `EventFeed.tsx` 신규 컴포넌트 작성
7. `streamSelectors.ts`: `TurnEventRow` 타입 + `selectEventFeed` 셀렉터

### Phase 3 — PromptPanel 컨텍스트 (2일)
8. `promptContext.ts` 작성 (타입별 reason/stateLine/choicePreview)
9. `PromptPanel.tsx` 재작성: 컨텍스트 영역 + 선택지 카드
10. `App.tsx`: `PromptOverlay` → `PromptPanel` (fixed modal 아닌 inline)

### Phase 4 — SpectatorStrip (1일)
11. `SpectatorStrip.tsx` 신규: 내러티브 피드 형식
12. `App.tsx`: `isMyTurn` 분기로 `PromptPanel` / `SpectatorStrip` 전환
13. `TurnStagePanel.tsx` + `SpectatorTurnPanel.tsx` 제거

### Phase 5 — Critical Event Interrupt (2일)
14. `EventInterruptOverlay.tsx` 신규 컴포넌트
15. `streamSelectors.ts`: `selectInterruptEvents` — 인터럽트 조건 판별
16. `App.tsx`: 인터럽트 큐 관리, 표시/닫힘 로직

### Phase 6 — 보드 중앙 패널 (1일)
17. `BoardPanel.tsx`: `board-center-panel` 추가
18. 타일 표시 간소화 (body/foot 숨김, owner dot 추가)

### Phase 7 — 자원/소유/잔꾀 모니터링 (1~2일)
19. `PlayersBar.tsx`: `shards`, `ownedTileCount`, `hiddenTrickCount` 자원 칩 추가
20. `LandStatusPanel.tsx` 신규: 타일별 소유자 목록, 접이식
21. `MyTricksPanel.tsx` 신규: 내 잔꾀 패 표시 (1단계: 숫자, 2단계: 카드명)
22. `streamSelectors.ts`: 타일 소유 목록 셀렉터 (`selectLandOwnership`) 추가
23. 서버 확인: `my_trick_cards` 스냅샷 제공 여부 → 가능하면 2단계 구현

---

## 제거 대상

| 컴포넌트/CSS | 이유 |
|---|---|
| `TurnStagePanel.tsx` | `PromptPanel` + `SpectatorStrip`으로 대체 |
| `SpectatorTurnPanel.tsx` | `SpectatorStrip`으로 대체 |
| `turn-notice-banner` (배너) | `GlobalHeader`의 내 상태 배지로 대체 |
| `prompt-floating-chip` | `PromptPanel` inline으로 대체 |
| `SituationPanel.tsx` | `ActorCard` + `EventFeed`로 대체 |
| `h1` 42px 로고 | `GlobalHeader`의 16px 로고로 대체 |
| `matchTopCollapsed` state | 항상 표시로 단순화 |

---

## 우선순위

| 순위 | 작업 | 이유 |
|---|---|---|
| P0 | Phase 3 (PromptPanel 컨텍스트) | 플레이어가 왜 행동해야 하는지 모름 |
| P0 | Phase 4 (SpectatorStrip) | 다른 플레이어 행동 파악 불가 |
| P0 | Phase 5 (EventInterrupt) | 임대료/파산 등 중요 이벤트 전달 안됨 |
| P1 | Phase 1 (레이아웃) | 보드/패널 크기 문제 |
| P1 | Phase 2 (ActorCard/EventFeed) | 현재 행동 플레이어 + 기록 |
| P2 | Phase 6 (보드 중앙 패널) | 보드 내부 공간 활용 |
| P1 | Phase 7-a (PlayersBar 자원) | 조각/소유수/잔꾀수 항상 보임 — 서버 변경 없음 |
| P1 | Phase 7-b (LandStatusPanel) | 어느 타일을 누가 가졌는지 한눈에 |
| P2 | Phase 7-c (MyTricksPanel) | 내 잔꾀 패 상시 확인 — 서버 확인 필요 |

---

## [CODEX RESPONSE] 2026-04-07

### 총평

이 문서는 상용 게임 UX 패턴을 현재 프로젝트에 연결하려는 시도가 좋다. 특히 "보드가 화면을 지배하고, 중요한 사건은 오버레이나 인터럽트로 크게 보여야 한다"는 방향은 현 상태를 개선하는 데 매우 유효하다.

### 강점

- 참조 대상이 명확하다
  - Monopoly GO, 디지털 윷놀이, Catan류 패턴에서 무엇을 가져오고 싶은지 비교 기준이 분명하다.
- 상용 UX의 핵심을 잘 뽑았다
  - 내 자원 상시 노출
  - 현재 행동 플레이어 상시 노출
  - 이벤트 인터럽트
  - 플레이어 상태 뱃지
- 지금 프로젝트의 문제를 "상태 정보 부족"이 아니라 "계층 설계 실패"로 본 점이 맞다.

### 주의할 점

- 상용 게임의 연출을 그대로 베끼면 안 된다.
  - 이 프로젝트는 웹 기반 React/FastAPI 구조이고, 실시간 이벤트가 스트림으로 들어오는 구조다.
  - 모바일 풀스크린 중심 UX를 그대로 가져오면 오히려 데스크톱 웹에서 과도하게 무거워질 수 있다.
- 이벤트 인터럽트는 남용하면 흐름을 끊는다.
  - 파산, 랩 보상, 지목 확정처럼 정말 중요한 이벤트에는 좋지만
  - 이동, 소규모 운수 처리까지 계속 인터럽트하면 플레이가 오히려 답답해질 수 있다.

### 왜 가치가 있는가

이 문서는 "무엇을 더 크게 보여줄 것인가"를 정하는 데 유용하다. 지금까지는 화면이 많은 정보를 같은 크기로 나열해서, 중요한 것과 덜 중요한 것이 구분되지 않았다. 이 제안서는 그 위계 문제를 바로잡는 데 도움이 된다.

### 결론

이 문서는 즉시 구현 문서라기보다, 연출과 정보 위계를 정할 때 참고할 상용 UX 레퍼런스 문서로 채택하는 것이 적절하다. 특히 보드 우선, 현재 행동자 강조, 중요 이벤트 인터럽트라는 세 축은 후속 개선의 핵심 기준으로 삼을 가치가 있다.
Status: ARCHIVED_REFERENCE_ONLY

This proposal is not the current execution source of truth.
Use `docs/1_READ_FIRST_GAME_STABILIZATION_AND_RUNTIME_GUIDE.md` and active frontend docs first.
