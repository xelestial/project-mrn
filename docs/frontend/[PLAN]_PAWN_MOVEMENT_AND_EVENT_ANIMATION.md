# [PLAN] 말 이동 및 게임 이벤트 애니메이션 구현 계획

Status: PLAN
Date: 2026-04-07
Scope: BoardPanel.tsx, styles.css, App.tsx

---

## 1. 현재 상태 분석

### 1-1. 현재 구현된 것

| 요소 | 현재 동작 |
|---|---|
| `board-moving-pawn-ghost` | `from → to` 단일 arc 1.05s. 중간 타일 미경유 |
| `boardMovingPawnTravel` keyframe | `left/top` CSS var 전환, `cubic-bezier(0.2, 0.82, 0.24, 1)` |
| `recentPathSteps` Map | `tileIndex → stepNumber` (정적 배지로 사용) |
| `tile-move-trail` 클래스 | 경로 타일에 pulse 적용, `--path-step-order * 90ms` delay |
| `pawn-arrived` 클래스 | 목적지 도착 pawn에 scale 애니메이션 |
| `pawn-active-turn-pulse` | 행동자 pawn에 무한 bounce |

### 1-2. 핵심 부재

1. **중간 타일 경유 없음** — ghost pawn이 from에서 to로 직선 비행
2. **렌트/구매 결과 화면 없음** — 착지 후 무슨 일이 생겼는지 알 수 없음
3. **운수 카드 이동 구분 없음** — 일반 이동과 같은 처리
4. **지목 결과 멘트/연출 없음** — 지목 완료 후 결과가 조용히 적용됨
5. **이벤트 순서 연출 없음** — 이동 → 착지 → 렌트 → 결과가 연속적으로 보이지 않음

### 1-3. 사용 가능한 데이터

```typescript
// LastMoveViewModel
lastMove: {
  playerId: number;
  fromTileIndex: number;
  toTileIndex: number;
  pathTileIndices: number[];  // 중간 경유 타일 포함
}

// boardProjection.ts
projectTilePosition(tileIndex, tileCount, topology)
// → { row: number, col: number }
// 현재 grid.cols, grid.rows 기준 좌표 반환

// playerColor(playerId) → CSS color string
// pawnFallback: Map<tileIndex, playerId[]>
```

---

## 2. 말 이동 애니메이션

### 2-1. 목표

플레이어의 말이 **주사위 칸 수만큼 타일을 하나씩 이동**하는 것을 시각적으로 보여준다.
각 타일에서 짧게 머문 뒤 다음 타일로 넘어가며, 마지막 타일에서는 `pawn-arrived` 연출이 나온다.

### 2-2. 구현 전략: JS 스텝 + CSS transition

| 선택지 | 장단점 |
|---|---|
| CSS keyframe 전체를 JS로 생성 | 타일 수에 비례한 복잡도, 브라우저 재계산 비용 |
| **JS `setInterval` + CSS `transition`** | 구현 단순, 타일 수 무관, 기존 코드 최소 변경 ✓ |
| Web Animations API | 정밀하나 과도한 복잡도 |

### 2-3. `usePawnAnimation` 훅 설계

```typescript
// apps/web/src/features/board/usePawnAnimation.ts

export type PawnAnimState = {
  animPlayerId: number | null;
  animTileIndex: number | null;   // ghost pawn이 현재 위치한 타일
  animPhase: "idle" | "moving" | "arrived";
};

export function usePawnAnimation(lastMove: LastMoveViewModel | null): PawnAnimState {
  const [state, setState] = useState<PawnAnimState>({ ... idle ... });
  const prevMoveRef = useRef<LastMoveViewModel | null>(null);

  useEffect(() => {
    if (!lastMove || lastMove === prevMoveRef.current) return;
    if (!lastMove.pathTileIndices || lastMove.pathTileIndices.length === 0) return;

    prevMoveRef.current = lastMove;
    const steps = lastMove.pathTileIndices;  // [tile1, tile2, ..., toTile]
    let i = 0;

    setState({ animPlayerId: lastMove.playerId, animTileIndex: steps[0], animPhase: "moving" });

    const interval = setInterval(() => {
      i++;
      if (i >= steps.length) {
        clearInterval(interval);
        setState({ animPlayerId: lastMove.playerId, animTileIndex: lastMove.toTileIndex, animPhase: "arrived" });
        // arrived 상태는 1.2초 후 idle로
        setTimeout(() => setState({ animPlayerId: null, animTileIndex: null, animPhase: "idle" }), 1200);
        return;
      }
      setState(prev => ({ ...prev, animTileIndex: steps[i] }));
    }, 260);  // 260ms per step → 주사위 6칸: ~1.5초

    return () => clearInterval(interval);
  }, [lastMove]);

  return state;
}
```

### 2-4. BoardPanel 변경 요점

```typescript
// BoardPanel.tsx 내부 변경
const { animPlayerId, animTileIndex, animPhase } = usePawnAnimation(lastMove);

// ghost pawn: CSS var 기반 from→to arc 대신 현재 스텝 타일에 직접 배치
const ghostPosition = animTileIndex !== null
  ? projectTilePosition(animTileIndex, tiles.length, normalizedTopology)
  : null;

const ghostStyle = ghostPosition && animPlayerId !== null ? {
  "--board-move-ghost-x": `${((ghostPosition.col - 0.5) / grid.cols) * 100}%`,
  "--board-move-ghost-y": `${((ghostPosition.row - 0.5) / grid.rows) * 100}%`,
  "--board-move-player-color": playerColor(animPlayerId),
} as CSSProperties : null;
```

```tsx
{ghostStyle ? (
  <div
    className={`board-moving-pawn-ghost board-pawn-step ${animPhase === "arrived" ? "board-pawn-arrived" : ""}`}
    style={ghostStyle}
    aria-hidden="true"
  >
    {animPlayerId}
  </div>
) : null}
```

### 2-5. CSS 변경 요점

```css
/* 기존 arc keyframe 제거 또는 유지 (fallback용) */

/* step 기반 ghost: transition으로 타일 간 이동 */
.board-moving-pawn-ghost.board-pawn-step {
  left: var(--board-move-ghost-x);
  top: var(--board-move-ghost-y);
  transition: left 200ms ease-out, top 200ms ease-out;
}

/* 도착 연출 */
.board-moving-pawn-ghost.board-pawn-arrived {
  animation: pawnGhostArrive 0.4s ease-out forwards;
}

@keyframes pawnGhostArrive {
  0%   { transform: translate(-50%, -50%) scale(1.0); opacity: 1; }
  40%  { transform: translate(-50%, -50%) scale(1.4); opacity: 0.9; }
  100% { transform: translate(-50%, -50%) scale(0.0); opacity: 0; }
}
```

### 2-6. 단계별 구현 계획

| 단계 | 내용 | 예상 시간 |
|---|---|---|
| Phase 1 | `usePawnAnimation` 훅 작성 + `BoardPanel`에서 호출 | 1시간 |
| Phase 2 | ghost pawn CSS를 arc → step transition으로 교체 | 30분 |
| Phase 3 | arrived 연출, 타일별 pulse delay 정비 | 30분 |
| Phase 4 | 운수 카드·지목 트리거 구분 (아래 섹션) | 1시간 |

### 2-7. 엣지 케이스

| 상황 | 처리 |
|---|---|
| `pathTileIndices` 비어있음 | 기존 arc fallback 유지 |
| 한 바퀴 완주(랩) | `pathTileIndices`가 출발점을 넘어 계속 이어지므로 자동 처리됨 |
| 순간이동(텔레포트) | step 없이 from→to만 있음 → arc 1회 후 `pawn-arrived` |
| 새 이동이 진행 중 도착 | `useEffect` cleanup이 `clearInterval` 처리 |

---

## 3. 운수 카드 이동 애니메이션

### 3-1. 일반 이동과의 차이

운수(S) 타일 착지 후 카드 효과로 **다시 이동**하는 경우:

- 서버에서 두 번째 `lastMove`가 별도 이벤트로 옴
- 또는 단일 `lastMove`에 `moveKind: "fortune"` 같은 필드가 있을 수 있음

→ **현재 서버 데이터 확인 필요**: `streamSelectors.ts`에서 `LastMoveViewModel`에 `moveKind` 또는 `triggerKind` 필드 유무 확인

### 3-2. 구현 방향 (서버 필드 없는 경우)

1. 착지 타일이 운수 타일(`tileKind === "S"`)이고 직후 새 `lastMove`가 오면 → 운수 이동으로 간주
2. `usePawnAnimation` 훅에서 `moveKind` prop 추가하여 연출 분기

### 3-3. 운수 이동 전용 연출

```css
/* 운수 이동 ghost: 일반 이동보다 빠르고 궤적에 번쩍임 */
.board-moving-pawn-ghost.board-pawn-fortune {
  --board-pawn-trail-color: #facc15;
  transition: left 150ms ease-in-out, top 150ms ease-in-out;
}

.board-moving-pawn-ghost.board-pawn-fortune::after {
  content: "✦";
  position: absolute;
  top: -14px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 12px;
  color: #facc15;
  animation: fortuneSparkle 0.4s ease-out infinite;
}

@keyframes fortuneSparkle {
  0%   { opacity: 1; transform: translateX(-50%) scale(1); }
  100% { opacity: 0; transform: translateX(-50%) scale(2); }
}
```

### 3-4. 이벤트 순서 멘트

| 단계 | 보여줄 텍스트 (board-focus-summary) |
|---|---|
| 운수 타일 착지 | `currentBeatLabel: "운수"` + `currentBeatDetail: "카드를 뽑습니다..."` |
| 운수 이동 시작 | `currentBeatLabel: "이동"` + `currentBeatDetail: "운수로 N칸 이동"` |
| 운수 이동 완료 | `pawn-arrived` 연출 |

---

## 4. 렌트 지불 이벤트 연출

### 4-1. 상황

- **내가 타인 소유 타일 착지** → 렌트 지불
- **타인이 내 소유 타일 착지** → 렌트 수취
- **타인이 타인 소유 타일 착지** → 관전 중 발생

### 4-2. 현재 서버 이벤트 구조

`decision_requested` 또는 `beat_applied` 이벤트에서 렌트 관련 정보가 온다.
`TurnStageViewModel.currentBeatKind`가 `"rent"` 또는 유사한 값이 될 때 처리.

→ **확인 필요**: `streamSelectors.ts`에서 `currentBeatKind` 가능한 값 목록

### 4-3. 렌트 이벤트 전용 CriticalEventInterrupt 오버레이

```tsx
// CriticalEventInterrupt — 기존 상용 재설계 스펙 Zone G 활용

type RentEventKind = "rent_pay" | "rent_receive" | "rent_observe";

// 렌트 발생 시 3초간 오버레이 표시
{rentEvent && (
  <div className={`critical-interrupt rent-interrupt rent-${rentEventKind}`}>
    <div className="rent-amount">
      {rentEventKind === "rent_pay"   ? "💸 렌트 지불" : null}
      {rentEventKind === "rent_receive" ? "💰 렌트 수취" : null}
      {rentEventKind === "rent_observe" ? "👀 렌트 발생" : null}
    </div>
    <div className="rent-detail">
      {rentAmount}냥 — P{landOwner}의 {tileName}
    </div>
  </div>
)}
```

### 4-4. 렌트 CSS 연출

```css
/* 렌트 지불: 빨강 shake */
.rent-interrupt.rent-rent_pay {
  background: rgba(220, 38, 38, 0.92);
  animation: rentPayShake 0.5s ease-out;
}

@keyframes rentPayShake {
  0%   { transform: translateX(0); }
  20%  { transform: translateX(-8px); }
  40%  { transform: translateX(8px); }
  60%  { transform: translateX(-5px); }
  80%  { transform: translateX(5px); }
  100% { transform: translateX(0); }
}

/* 렌트 수취: 초록 pulse */
.rent-interrupt.rent-rent_receive {
  background: rgba(22, 163, 74, 0.92);
  animation: rentReceivePulse 0.6s ease-out;
}

@keyframes rentReceivePulse {
  0%   { transform: scale(0.8); opacity: 0; }
  50%  { transform: scale(1.05); opacity: 1; }
  100% { transform: scale(1.0); opacity: 1; }
}

/* 관전 중 렌트: 중립 슬라이드인 */
.rent-interrupt.rent-rent_observe {
  background: rgba(51, 65, 85, 0.88);
  animation: rentObserveSlide 0.4s ease-out;
}

@keyframes rentObserveSlide {
  0%   { transform: translateY(-20px); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
}
```

### 4-5. 렌트 인터럽트 수명

```
착지 확인 → 렌트 인터럽트 표시 (0.5s 입장 애니메이션)
→ 2초 유지
→ 0.3s 퇴장
→ 다음 단계 진행
```

총 ~3초. `setTimeout` + `useEffect` cleanup으로 관리.

---

## 5. 지목 결과 연출

### 5-1. 지목(mark_target / trick_tile_target)이란

- 특정 플레이어 또는 타일을 지목하는 잔꾀 효과
- 효과 발동 → 결과(자원 이동, 이동 강제, 칸 제거 등) 적용

### 5-2. 현재 상태

- `stageFocus.focusTileIndex` / `focusTileIndices`로 타일 강조는 있음
- 결과 적용 후 별도 연출 없음: 조용히 상태가 바뀜

### 5-3. 지목 타입별 연출 계획

#### 5-3-1. 지목 발동 — 타일 지목 선택 중

```css
/* 지목 가능 타일 후보: 박동하는 빨간 테두리 */
.tile-stage-candidate.tile-stage-candidate-ring-mark {
  animation: markTargetCandidatePulse 0.8s ease-in-out infinite;
}

@keyframes markTargetCandidatePulse {
  0%, 100% { box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.5); }
  50%       { box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.9); }
}

/* 최종 지목 타일: 고정 빨간 하이라이트 */
.tile-stage-focus[data-focus-kind="mark"] {
  background: rgba(239, 68, 68, 0.15);
  border: 2px solid #ef4444;
}
```

#### 5-3-2. 지목 결과 오버레이

지목 효과 종류별 결과 오버레이:

```tsx
// 지목 결과 유형
type MarkResultKind =
  | "mark_cash_drain"    // 냥 빼앗김
  | "mark_shard_drain"   // 조각 빼앗김
  | "mark_forced_move"   // 강제 이동
  | "mark_tile_remove"   // 칸 제거
  | "mark_toll_block";   // 통행 차단

{markResult && (
  <div className={`critical-interrupt mark-result-interrupt mark-${markResult.kind}`}>
    <div className="mark-result-icon">
      {markResult.kind === "mark_cash_drain"   ? "🗡️" : null}
      {markResult.kind === "mark_shard_drain"  ? "💎" : null}
      {markResult.kind === "mark_forced_move"  ? "🔀" : null}
      {markResult.kind === "mark_tile_remove"  ? "❌" : null}
      {markResult.kind === "mark_toll_block"   ? "🚫" : null}
    </div>
    <div className="mark-result-headline">{markResult.label}</div>
    <div className="mark-result-detail">{markResult.detail}</div>
    <div className="mark-result-source">
      P{markResult.sourcePlayerId}의 잔꾀 — {markResult.trickName}
    </div>
  </div>
)}
```

#### 5-3-3. 지목 결과 CSS

```css
.mark-result-interrupt {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1200;
  min-width: 280px;
  max-width: 360px;
  padding: 20px 24px;
  border-radius: 12px;
  text-align: center;
  animation: markResultEntrance 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) forwards;
}

@keyframes markResultEntrance {
  0%   { transform: translate(-50%, -50%) scale(0.6); opacity: 0; }
  100% { transform: translate(-50%, -50%) scale(1.0); opacity: 1; }
}

/* 자원 빼앗김: 어두운 보라 */
.mark-result-interrupt.mark-mark_cash_drain,
.mark-result-interrupt.mark-mark_shard_drain {
  background: rgba(109, 40, 217, 0.93);
  border: 2px solid #7c3aed;
}

/* 강제 이동: 파랑 */
.mark-result-interrupt.mark-mark_forced_move {
  background: rgba(37, 99, 235, 0.93);
  border: 2px solid #3b82f6;
}

/* 칸 제거: 빨강 */
.mark-result-interrupt.mark-mark_tile_remove {
  background: rgba(185, 28, 28, 0.93);
  border: 2px solid #ef4444;
}
```

### 5-4. 지목 결과 이벤트 수명

```
지목 확정 → 타일 강조 0.5초
→ 결과 오버레이 등장 (0.4초 애니메이션)
→ 2.5초 유지
→ 결과 오버레이 퇴장 (0.3초)
→ 보드 상태 업데이트 반영
```

---

## 6. 파산 / 대형 이벤트 연출

### 6-1. 파산 (`bankruptcyShake`)

이미 상용 재설계 스펙 Zone G에서 정의됨:

```css
@keyframes bankruptcyShake {
  0%, 100% { transform: translateX(0) scale(1); }
  10%, 30%, 50%, 70%, 90% { transform: translateX(-10px) scale(1.02); }
  20%, 40%, 60%, 80% { transform: translateX(10px) scale(0.98); }
}
```

- 조건: `currentBeatKind === "bankruptcy"` 또는 관련 이벤트
- 오버레이 배경: `rgba(220, 38, 38, 0.92)`, 텍스트: "P{N} 파산"
- 지속: 3초

### 6-2. 랩 완주 보상

```css
@keyframes lapCompletePulse {
  0%   { transform: scale(1); background: rgba(234, 179, 8, 0.0); }
  30%  { transform: scale(1.03); background: rgba(234, 179, 8, 0.25); }
  100% { transform: scale(1); background: rgba(234, 179, 8, 0.0); }
}
```

- 조건: 말이 랩을 완주하여 출발 타일을 통과할 때
- 전체 보드에 황금 pulse + "한 바퀴 완주! +{N}냥" 배너

---

## 7. 이벤트 오케스트레이션 (실행 순서 보장)

### 7-1. 문제

여러 애니메이션이 동시에 시작되면 화면이 혼란스러워진다.
이동 → 착지 → 렌트 → 결과를 **순서대로** 보여줘야 한다.

### 7-2. 이벤트 큐 훅

```typescript
// apps/web/src/features/board/useEventQueue.ts

type GameEvent =
  | { kind: "pawn_move"; lastMove: LastMoveViewModel }
  | { kind: "rent_pay";  amount: number; fromId: number; toId: number; tileName: string }
  | { kind: "rent_receive"; amount: number; fromId: number; tileName: string }
  | { kind: "mark_result"; markKind: MarkResultKind; label: string; detail: string; sourceId: number; trickName: string }
  | { kind: "lap_complete"; playerId: number; reward: string }
  | { kind: "bankruptcy"; playerId: number };

// 큐에 이벤트 추가 → 현재 이벤트가 끝나면 자동으로 다음 이벤트 시작
export function useEventQueue(): {
  currentEvent: GameEvent | null;
  enqueue: (event: GameEvent) => void;
};
```

### 7-3. 이벤트별 기본 지속 시간

| 이벤트 | 지속 시간 |
|---|---|
| pawn_move (N칸) | N × 260ms + 1200ms (arrived) |
| rent_pay | 3000ms |
| rent_receive | 2500ms |
| mark_result | 3000ms |
| lap_complete | 2000ms |
| bankruptcy | 3500ms |

---

## 8. 데이터 흐름 확인 필요 사항

구현 전 다음 파일을 확인해야 한다:

1. **`apps/web/src/domain/selectors/streamSelectors.ts`**
   - `LastMoveViewModel` — `moveKind`(fortune/normal) 필드 있는지
   - `currentBeatKind` 가능한 값 목록
   - 렌트 발생 시 어떤 이벤트로 오는지

2. **`apps/web/src/features/stage/TurnStagePanel.tsx`**
   - `currentBeatKind` 실제 사용 패턴

3. **`apps/web/src/App.tsx`**
   - 이벤트 큐 훅을 어느 레벨에 위치시킬지

---

## 9. 구현 순서 (권장)

| 순서 | 항목 | 예상 시간 | 이유 |
|---|---|---|---|
| 1 | `usePawnAnimation` 훅 작성 | 1시간 | 가장 가시적 효과 |
| 2 | ghost pawn CSS step transition 교체 | 30분 | Phase 1 완성 |
| 3 | 렌트 CriticalEventInterrupt | 1.5시간 | 가장 자주 발생 |
| 4 | 지목 결과 오버레이 | 2시간 | 복잡한 분기 |
| 5 | `useEventQueue` 오케스트레이션 | 1.5시간 | 순서 보장 |
| 6 | 운수 카드 이동 구분 연출 | 1시간 | 서버 데이터 확인 후 |
| 7 | 파산 / 랩 완주 보상 연출 | 1시간 | 빈도 낮음 |

총 예상: **9~10시간**

---

## 10. 레퍼런스

- `apps/web/src/features/board/BoardPanel.tsx` — 현재 ghost pawn 구현
- `apps/web/src/styles.css` — `boardMovingPawnTravel`, `tileMoveTrailPulse`, `pawnArrived` 정의
- `apps/web/src/features/board/boardProjection.ts` — 타일 픽셀 위치 계산
- `docs/frontend/[PROPOSAL]_UI_UX_COMMERCIAL_REDESIGN.md` — Zone G (CriticalEventInterrupt) 스펙
