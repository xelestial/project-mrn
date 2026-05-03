# Quarterview Board And Event Presentation Plan

## Goal

현재 DOM 그리드형 타일 맵을 쿼터뷰 보드 표현으로 전환한다. 게임 규칙과 서버 이벤트의 `tileIndex` 체계는 유지하고, 클라이언트의 화면 투영, 캐릭터 토큰, 중앙 이벤트 오버레이, 스프라이트 효과, 지목 성공 카드 연출을 단계적으로 교체한다.

## Design Principles

- 게임 로직은 그대로 둔다. `tileIndex`, `ownerPlayerId`, `pawnPlayerIds`, `lastMove.pathTileIndices`는 계속 단일 진실 소스로 사용한다.
- 변경 범위는 `apps/web/src/features/board` 중심으로 시작한다.
- 텍스트가 많은 결정 UI는 DOM으로 유지하고, 보드/캐릭터/이펙트는 DOM 레이어 또는 CSS sprite 레이어로 먼저 구현한다.
- 캔버스/WebGL 전환은 첫 단계에서는 보류한다. 현재 앱은 React + CSS만 쓰고 있으므로, 쿼터뷰 MVP는 새 렌더링 엔진 없이 구현하는 편이 리스크가 낮다.
- 중앙 오버레이는 짧게 뜨고 사라져야 하며, 평소에는 보드 중앙과 하단을 최대한 비워둔다.

## Current Structure

- 보드 렌더링: `apps/web/src/features/board/BoardPanel.tsx`
- 보드 좌표계: `apps/web/src/features/board/boardProjection.ts`
- 이동 애니메이션: `apps/web/src/features/board/usePawnAnimation.ts`
- 중앙 이벤트 큐: `apps/web/src/features/board/useEventQueue.ts`
- 중앙 이벤트 오버레이: `apps/web/src/features/board/GameEventOverlay.tsx`
- 이벤트/상태 셀렉터: `apps/web/src/domain/selectors/streamSelectors.ts`
- 보드 스타일: `apps/web/src/styles.css`

## Phase 1: Asset Intake

### Character Standee Assets

- 첨부된 캐릭터 이미지를 보드 위 이동용 standee asset으로 정규화한다.
- 다운로드 원본은 repo 밖에 있으므로, 사용할 최종 asset만 repo 안으로 복사한다.
- 권장 위치:
  - `apps/web/src/assets/characters/standees/`
  - `apps/web/src/assets/characters/cards/`
- 처리 기준:
  - 흰 배경 제거 또는 투명 PNG/WebP 재생성
  - 시선 방향과 발 위치 anchor 통일
  - 보드용 standee: 높이 기준 180-240px 원본, 화면에서는 CSS scale
  - 카드 일러스트용: 카드 프레임 안에 들어갈 crop 별도 생성
- 메타데이터:
  - `characterId`
  - `displayName`
  - `priority`
  - `attribute`
  - `abilityText`
  - `standeeAsset`
  - `cardArtAsset`
  - `anchorX`, `anchorY`

### Effect Sprite Assets

- 구매: 동전/계약서/토지 인장
- 렌트: 동전이 소유자 방향으로 이동
- 운수: 카드 뒤집힘, 별/운세 문양
- 랩 보상: 원형 통과 링, 보상 조각/돈/승점 코인
- 파산: 붉은 도장, 깨지는 금전 효과
- 잔꾀: 비책 카드, 연기/번쩍임/실루엣
- 지목 성공: 카드 플립 + 목표 캐릭터 카드 강조 + 효과 요약

## Phase 2: Quarterview Projection

### Projection Model

기존 `boardProjection.ts`는 grid row/col만 반환한다. 새 좌표계는 논리 좌표와 화면 좌표를 분리한다.

```ts
type BoardProjectionPoint = {
  tileIndex: number;
  logicalRow: number;
  logicalCol: number;
  x: number;
  y: number;
  z: number;
  lane: "top" | "right" | "bottom" | "left" | "line";
};
```

### Implementation Direction

- `projectTilePosition`은 당장 유지한다.
- 새 함수 `projectTileQuarterview`를 추가해 `x/y/z`를 계산한다.
- `BoardPanel`은 `position: absolute` 기반의 `board-quarterview-layer`에 타일을 배치한다.
- `z`는 타일 행, 캐릭터 발 anchor, 이벤트 sprite를 정렬하는 데 사용한다.
- 링 형태는 유지하되, 화면상으로는 마름모 또는 비스듬한 직사각 링처럼 보이게 한다.

### Acceptance Criteria

- 모든 타일이 서로 겹치지 않는다.
- `tileIndex` 순서가 현재 이동 경로와 일치한다.
- `lastMove.pathTileIndices`가 쿼터뷰 좌표에서 자연스럽게 이어진다.
- 모바일에서는 보드가 축소되지만 캐릭터와 이벤트가 타일을 완전히 가리지 않는다.

## Phase 3: Character Movement On Tiles

### Rendering

- 기존 `pawn-token` 칩은 디버그/접근성 fallback으로 유지한다.
- 보드 위에는 `CharacterStandeeLayer`를 추가한다.
- 각 플레이어는 현재 `player.position` 또는 `usePawnAnimation`의 `animTileIndex`를 기준으로 standee를 배치한다.
- 같은 타일에 여러 캐릭터가 있으면 small offset을 적용한다.

### Motion

- 이동은 타일 간 보간이 아니라 `pathTileIndices`를 따라 step 이동으로 시작한다.
- 각 step은 `translate3d(x, y, 0) scale(...)`로 이동한다.
- 도착 시 살짝 튀는 settle animation을 넣는다.
- `prefers-reduced-motion`에서는 step transition을 줄이고 즉시 이동한다.

### Acceptance Criteria

- 이동 중에도 실제 도착 타일, 최근 이동 summary, 캐릭터 위치가 서로 어긋나지 않는다.
- 캐릭터가 타일 위에 서 있고 발 anchor가 타일 중앙 하단에 맞는다.
- 여러 명이 같은 타일에 있을 때 누구인지 식별된다.

## Phase 4: Central Event Overlay

현재 `GameEventOverlay`는 렌트와 랩 보상 중심이다. 요구 범위에 맞춰 이벤트 종류를 확장한다.

### Event Kinds

- `purchase`
- `rent`
- `fortune`
- `lap_reward`
- `bankruptcy`
- `trick`
- `mark_success`

### Event Mapping

- 구매:
  - source events: `tile_purchased`, `purchase_tile` resolved
  - overlay: `토지 구매`, 비용, 타일 번호
- 렌트:
  - source events: `rent_paid`
  - overlay: `통행료 지불`, payer, owner, amount
- 운수:
  - source events: `fortune_drawn`, `fortune_resolved`
  - overlay: `운수`, 카드명, 효과 요약
- 랩 보상:
  - source events: `lap_reward_chosen`
  - overlay: `랩 보상`, 받은 보상 bundle
- 파산:
  - source events: `bankruptcy`, `game_end` with bankruptcy reason
  - overlay: `파산`, 대상 플레이어, 원인
- 잔꾀:
  - source events: `trick_used`
  - overlay: `잔꾀`, 카드명, 효과 요약
- 지목 성공:
  - source events: `mark_resolved`, successful `mark_queued`
  - overlay: 카드 이미지 + 지목 성공 효과

### Behavior

- 오버레이는 중앙에 1.8-3.5초 표시 후 사라진다.
- 중요도 높은 이벤트는 queue 우선순위를 높인다.
- 오버레이가 떠도 prompt 조작을 막지 않는 기본 상태를 유지하되, 카드 연출만 짧은 pointer-events none 레이어로 둔다.

## Phase 5: Sprite Effects

### Layering

`BoardPanel` 내부에 다음 레이어를 분리한다.

- `QuarterviewTileLayer`
- `TileEffectLayer`
- `CharacterStandeeLayer`
- `FloatingEventLayer`
- `PromptOverlayLayer`

### Event-Specific Effects

- 구매:
  - 타일 위에 금색 인장 stamp
  - 동전 2-3개가 타일로 떨어지는 효과
- 렌트:
  - payer 캐릭터에서 owner 캐릭터 또는 owner 타일 방향으로 동전이 이동
  - payer 쪽은 붉은 손실 pulse
- 운수:
  - S 타일 위에서 카드가 flip
  - `fortune_drawn`은 카드 등장, `fortune_resolved`는 효과 burst
- 랩 보상:
  - 시작/종료 타일 주변 원형 ring
  - 선택 보상에 따라 cash/shard/coin sprite 표시
- 파산:
  - 대상 캐릭터 주변 desaturate + 붉은 seal
  - 이후 캐릭터 opacity를 낮추거나 제거
- 잔꾀:
  - 카드 silhouette가 캐릭터 앞에 떠오르고, 효과별 색상 burst
  - `trick_used` 이후 해당 카드가 손패에서 사라지는 UI와 시각적으로 연결
- 지목 성공:
  - 지목한 캐릭터 카드가 화면 중앙으로 flip-in
  - 목표 캐릭터 카드가 이어서 reveal
  - 성공 효과를 중앙 overlay로 표시

## Phase 6: Character Card Presentation

### Card Contents

카드에는 다음을 표시한다.

- 우선권 번호
- 캐릭터명
- 일러스트
- 속성
- 특수 능력
- 앞면/뒷면 상태

### Data Source

- 캐릭터 우선권/양면: `apps/web/src/domain/characters/prioritySlots.ts`
- 캐릭터 텍스트: 현재는 서버/프롬프트에서 받는 설명과 catalog를 우선 활용
- 필요한 경우 frontend catalog에 `characterCardCatalog.ts`를 추가한다.

### Mark Success Sequence

- 전: `mark_queued` 또는 `mark_resolved` 수신
- 행동: actor 카드와 target 카드 정보를 구성
- 후:
  - 카드 이미지가 중앙에 등장
  - 목표 캐릭터가 강조됨
  - 효과 요약 overlay 표시
  - 보드 위 대상 캐릭터 또는 관련 타일에 spotlight 연결

## Phase 7: Testing Plan

### Unit Tests

- `boardProjection.spec.ts`
  - 쿼터뷰 좌표가 tile count별로 고유하고 안정적인지
  - z-order가 행/열 기준으로 일관적인지
- `usePawnAnimation` tests
  - path step이 qv 좌표로 변환되는지
- `useEventQueue` tests
  - 구매/렌트/운수/랩/파산/잔꾀/지목 성공 queue가 올바른 duration과 priority를 가지는지
- `streamSelectors` tests
  - 각 source event가 display event kind로 분류되는지

### Browser Tests

- 새 세션에서 이동 후 캐릭터가 도착 타일 위에 있음
- 구매 이벤트 후 중앙 overlay와 타일 stamp 표시
- 렌트 이벤트 후 payer/owner 방향 효과 표시
- 운수 이벤트 후 S 타일과 중앙 overlay 표시
- 랩 보상 이벤트 후 시작/종료 타일 효과 표시
- 잔꾀 사용 후 카드/효과 overlay 표시
- 지목 성공 후 카드 이미지, 효과 overlay, 대상 강조 표시
- 파산 종료 세션에서 파산 overlay와 캐릭터 상태 표시

### Visual Checks

- 데스크톱: 1440x900, 1280x720
- 모바일: 390x844
- 확인할 것:
  - 캐릭터가 타일과 어긋나지 않는지
  - 중앙 overlay가 prompt와 충돌하지 않는지
  - 보드 중앙이 평상시 비어 있는지
  - 긴 한글 텍스트가 카드/overlay 밖으로 넘치지 않는지

## Recommended Implementation Order

1. Asset copy and metadata scaffold
2. `projectTileQuarterview` 추가 및 테스트
3. `BoardPanel`에 feature flag 기반 qv 레이어 추가
4. 타일을 absolute quarterview로 렌더링
5. 캐릭터 standee layer 추가
6. 이동 애니메이션을 qv 좌표로 연결
7. `GameEventOverlay` 이벤트 종류 확장
8. tile-local sprite effects 추가
9. 지목 성공 카드 overlay 추가
10. Playwright visual regression 및 실제 플레이 검증

## Implementation Status

- 2026-04-24
  - 첨부 캐릭터 이미지를 `apps/web/src/assets/characters/standees/player-1..4.png`로 추가했다.
  - 보드 토큰 용도에 맞게 이미지를 최대 640px로 축소했다.
  - `projectTileQuarterview`를 추가해 기존 `tileIndex`를 쿼터뷰 `x/y/z/lane` 좌표로 투영한다.
  - `BoardPanel`의 ring topology는 쿼터뷰 absolute layer로 렌더링한다.
  - 플레이어 캐릭터 standee layer를 추가하고, 현재 위치와 `usePawnAnimation` 이동 위치를 연결했다.
  - `GameEventOverlay`와 `useEventQueue`를 구매, 운수, 잔꾀, 지목 성공, 파산 이벤트까지 확장했다.
  - 지목 성공 이벤트에는 카드가 뒤집혀 뜨는 형태의 중앙 overlay 스타일을 추가했다.
  - 검증:
    - `npm run test -- boardProjection`
    - `npm run build`
  - 브라우저 검증:
    - Codex in-app browser로 `127.0.0.1:5173` 새 세션을 생성하고 1인 인간 + 3 AI로 실플레이를 진행했다.
    - 카드 플립 이후 다음 턴까지 이동, 구매, 운수, 지목 선택, 잔꾀 선택 UI를 이어서 확인했다.

## Verification Log

### 2026-04-24 Clean Browser Session

- 환경:
  - server: `127.0.0.1:9090`
  - web: `127.0.0.1:5173`
  - session: `sess_f280f7760bf0`
  - seats: P1 human, P2/P3/P4 AI
- 쿼터뷰 보드:
  - 전: 기존 링 보드가 평면 카드/칩 중심으로 보이고 캐릭터가 타일 위에 서지 않았다.
  - 후: 40개 타일이 쿼터뷰 링으로 배치되고, P1/P2/P3/P4 standee가 현재 타일 위에 표시된다.
  - 판정: 기본 표시 정상. 단, 보드 우측 HUD와 standee/prompt가 가까워지는 장면이 있어 추가 safe-area 튜닝 여지는 있다.
- 드래프트 비공개:
  - 전: 드래프트 선택 전에는 플레이어 패널의 `current_character_face`가 `-`로 표시되어야 한다.
  - 후: P1 선택 도중 상대 패널에는 선택 인물이 즉시 공개되지 않았고, `turn_start` 이후 현재 차례 인물만 공개됐다.
  - 판정: 현재 세션 기준 정상.
- 잔꾀 보유패:
  - 전: 최종 캐릭터 선택 후 P1 잔꾀 패가 보이지 않거나 hidden/public 구분이 깨질 위험이 있었다.
  - 후: 최종 선택 후 P1 패에 `마당발`, `건강 검진`, `긴장감 조성`, `가벼운 분리불안`이 표시되고 hidden trick은 hidden badge로 표시됐다.
  - 판정: 현재 세션 기준 정상.
- 구매 + 잔꾀 `무료 증정`:
  - 전: P2 구매 overlay가 `cost: 0`으로 보여 구매 비용 표시 오류처럼 보였다.
  - 후: 이벤트 전후를 대조하니 P2가 먼저 `무료 증정`을 사용했고, purchase prompt public context도 `cost: 0`, `tile_purchase_cost: 4`를 함께 보냈다. 실제 구매 이벤트도 `result.cost: 0`이었다.
  - 판정: 룰 처리 정상. 비용 0은 무료 구매 효과다.
- 구매 일반 케이스:
  - 전: P1 현금 12, 위치 1, 토지 7 미소유.
  - 후: P1이 7번 칸에 도착해 비용 3으로 구매했고, 현금이 9가 되며 7번 칸 Owner P1로 표시됐다.
  - 판정: 정상.
- 카드 플립 이후 턴:
  - 전: 카드 플립 단계에서 `어사 -> 탐관오리` 선택 후 다음 턴이 끊기거나 잘못된 면이 표시될 위험이 있었다.
  - 후: 플립 이벤트 이후 Round 2 드래프트, 최종 인물 선택, 지목 선택, 이동, 구매, 다음 플레이어 턴 전환까지 진행됐다.
  - 판정: 진행 자체는 정상. 오래 방치된 active flip prompt를 클릭했을 때 `timeout_fallback`이 먼저 처리되는 장면이 있었으므로 장시간 대기 UX는 추가 점검 대상이다.
- 지목:
  - 전: P1이 `자객`으로 `추노꾼`을 지목했다.
  - 후: 해당 라운드에 실제 대상이 없어 `mark_target_missing`이 발생하고 턴이 정상 시작됐다.
  - 판정: 실패/대상 없음 경로 정상. 지목 성공 효과와 카드 overlay는 아직 성공 케이스 증명이 필요하다.
- 운수 `끼어들기`:
  - 전: P1이 16번 칸 구매 직후 운수 `끼어들기`를 뽑았다.
  - 후: `fortune_drawn` -> `tile_purchased` -> `landing_resolved` -> `fortune_resolved` 순으로 처리됐고, `resolution`에 `nearest_player_arrival`, `start_pos: 13`, `end_pos: 15`, `no_lap_credit: true`가 기록됐다.
  - 판정: 이벤트 순서와 전후 상태 기록 정상. 시각 overlay는 노출 확인됨.
- 날씨 `길고 긴 겨울`:
  - 전: Round 3 시작 전 End time 15.00.
  - 후: Round 3 `weather_reveal`에 `[종료]를 1칸 앞당기세요`가 표시됐고 marker/order 상태가 유지됐다.
  - 판정: 표시 정상. 실제 종료 시간 변화는 추가 수치 대조가 필요하다.
- 잔꾀 `번뜩임`:
  - 전: P2가 `번뜩임`을 사용했고 대상은 P1, 교환 수는 1이었다.
  - 후: P2는 `건강 검진`을 받고 P1은 `번뜩임`을 받았으며, P1 public tricks가 `긴장감 조성`, `가벼운 분리불안`, `번뜩임`으로 갱신됐다.
  - 판정: 전/후 패 교환 기록 정상.
- 징표 이전 + AI 카드 플립:
  - 전: Round 3 종료 후 P2가 교리 계열 인물로 징표를 획득했다.
  - 후: `marker_transferred` 이후 AI P2의 `active_flip` 결정과 `marker_flip` 이벤트가 연속 발생했고, 모든 slot이 순차적으로 뒤집혔다.
  - 판정: 진행은 정상. AI가 가능한 카드를 모두 뒤집는 전략이 의도인지 룰/밸런스 확인 필요.
- 잔꾀 `건강 검진`:
  - 전: Round 4 Turn 11 시작 시 P2가 잔꾀 사용 창에 진입했다.
  - 후: P2가 `건강 검진`을 사용했고 `resolution.type`은 `GLOBAL_RENT_HALF_THIS_TURN`으로 기록됐다.
  - 판정: 사용 이벤트와 효과 기록 정상. 실제 렌트 절반 적용은 렌트 발생 시 추가 증명 필요.
- 지목 대상 없음 반복:
  - 전: P1이 Round 3에서 `파발꾼`, Round 4에서 `객주`를 지목했다.
  - 후: 두 케이스 모두 현재 대상이 없어 `mark_target_missing`으로 정리되고 P1 턴이 정상 시작됐다.
  - 판정: 대상 없음 경로 정상. 성공 경로는 아직 미검증.
- 재검증:
  - `cd apps/web && npm run test -- boardProjection`
  - `cd apps/web && npm run build`

### 2026-04-25 Directional Character Sprite Verification

- 환경:
  - web: `127.0.0.1:5173`
  - session: `sess_f280f7760bf0`
  - 브라우저 URL: `/#/match?session=sess_f280f7760bf0`
- 스프라이트 배경:
  - 전: 첨부/원본 캐릭터 이미지에는 흰 배경이 있어 쿼터뷰 보드 위에서 사각 박스로 보일 위험이 있었다.
  - 후: `apps/web/src/assets/characters/sprites/player-{1..4}/{front-right,front-left,back-right,back-left}.png` 16개 PNG를 생성하고, edge-connected white background만 alpha로 제거했다.
  - 브라우저 확인: 실제 보드 위 P1/P2/P4가 흰 사각 배경 없이 cutout 형태로 표시됐다.
  - 판정: 투명 배경 적용 정상.
- 방향 대응:
  - 전: 말은 플레이어별 단일 standee 이미지라 이동 방향과 무관하게 같은 방향으로 보였다.
  - 후: idle 상태는 쿼터뷰 lane 기준 `top -> back-right`, `right -> front-right`, `bottom -> front-left`, `left -> back-left`로 고정하고, 이동 중에는 이전 타일과 현재 타일의 쿼터뷰 좌표 차이로 방향을 계산한다.
  - 브라우저 확인: DOM 이미지 경로가 `/src/assets/characters/sprites/player-1/back-left.png`, `/src/assets/characters/sprites/player-2/back-right.png`, `/src/assets/characters/sprites/player-4/back-right.png`로 잡혔고, 부모 standee의 `data-facing`도 각각 `back-left`, `back-right`, `back-right`로 일치했다.
  - 이전 이동 샘플: P1 이동 중 `front-left -> back-left` 방향 변화가 관측됐다.
  - 판정: 쿼터뷰 방향 선택 로직 정상.
- 재검증:
  - 전: 방향 계산 테스트 없음.
  - 후: `boardProjection` 테스트에 lane idle facing 및 tile-step movement facing 케이스를 추가했다.
  - 결과: `cd apps/web && npm run test -- boardProjection` 통과, `cd apps/web && npm run build` 통과.
- 참고:
  - 현재 back 방향 이미지는 원본 cutout을 기반으로 한 darker/cooler directional variant다. 추가 아트 품질 개선은 신규 에셋 요청이 있을 때 별도 작업으로 다룬다.

### Remaining Proof Targets

- 2026-04-25 현재 이 섹션의 항목은 구현/검증 문서 기준으로 닫았다.
- 지목 성공:
  - 전: `mark_queued`/`mark_resolved`가 current turn reveal stack에 없어 중앙 overlay와 라운드 기록 증명이 약했다.
  - 후: `mark_queued`, `mark_resolved`를 current turn/round reveal stack에 포함했고, 성공 이벤트는 `mark_success` overlay 대상으로 enqueue된다.
  - 증거: `streamSelectors` 테스트 `includes mark success events in turn and round reveal stacks`, seed 12 audit `#0100`, `#0141`.
- 렌트:
  - 전: payer/owner/amount를 사람이 한 번 더 해석해야 했다.
  - 후: `rent_paid` detail은 `Payer -> Owner / amount / tile` 형식이고, overlay는 로컬 플레이어 관점에 따라 `rent_pay`, `rent_receive`, `rent_observe`로 분기한다.
  - 증거: `streamSelectors` rent reveal 테스트, seed 12 audit `#0257 cash 12->8`.
- 랩 보상:
  - 전: 전/후 자원 변화 증거가 별도 audit에 흩어져 있었다.
  - 후: `lap_reward_chosen`은 current reveal/overlay 대상이며 audit에서 선택과 증가량을 함께 남긴다.
  - 증거: seed 12 audit `#0253`, `#0260`, `#0440`.
- 파산:
  - 전: 실브라우저 대표 장면과 audit 증거가 분리되어 있었다.
  - 후: `bankruptcy`는 current reveal/overlay 대상이며 audit은 shortfall/required/cause를 같이 출력한다.
  - 증거: seed 1 audit `#0271`, seed 12 audit `#0441`.
- 장시간 prompt timeout:
  - 전: stale decision 위험이 잔여 검증이었다.
  - 후: timeout/stale 경로는 서버 prompt tests와 stream selector feedback 경로로 자동 회귀에 묶고, 운영 playtest에서는 새 이슈가 발견될 때만 재오픈한다.

## Historical Risks

- 현재 `BoardPanel`은 HUD anchor를 특정 타일 번호와 DOM rect에 의존한다. 쿼터뷰 절대 배치로 바꾸면 prompt/hand tray safe area 계산을 다시 잡아야 한다.
- 첨부 이미지는 흰 배경이 있어 그대로 쓰면 보드 위에서 어색하다. 투명화/anchor normalization이 선행되어야 한다.
- 이벤트 payload가 모든 카드 연출에 충분하지 않을 수 있다. 특히 지목 성공 카드에는 actor/target의 priority, attribute, ability text가 필요하다.
- 중앙 오버레이와 기존 prompt overlay가 동시에 뜨면 플레이 흐름이 답답해질 수 있다. 중요 이벤트는 짧고 강하게, 선택 프롬프트는 항상 읽기 쉽게 유지해야 한다.

## Historical Open Questions

아래 질문은 초기 계획 수립 당시의 판단 항목이다. 현재 구현/검증 잔여 목록으로 취급하지 않는다.

- 쿼터뷰는 완전 마름모 보드인지, 현재 링 보드의 원형 흐름을 비스듬히 눕힌 형태인지 결정해야 한다.
- 캐릭터 이미지는 4명 플레이어 토큰용인지, 16개 인물 카드별 일러스트인지 구분이 필요하다.
- 지목 성공 카드 이미지는 실제 보드게임 카드 스타일로 신규 생성할지, 현재 텍스트 catalog와 첨부 일러스트를 합성해 만들지 결정해야 한다.
- 스프라이트 효과는 CSS-only MVP로 시작할지, sprite sheet/atlas 기반으로 갈지 결정해야 한다.

## 2026-04-26 Flattened Quarterview Board Expansion Plan

### Decision

가능하다. 단, 현재 탑뷰 정사각 다이아몬드에 단순 `scaleY()`를 거는 방식은 금지한다.

이유:

- 타일 내부 텍스트와 캐릭터 standee까지 같이 눌려 정보 가독성이 떨어진다.
- 타일 중심 간격, 회전각, 타일 변 길이가 서로 다른 기준을 쓰게 되어 종료 타일/코너 접합이 다시 불안정해진다.
- 현재 보드의 핵심 요구인 “타일 정보량 보존”과 “종료 타일 2면 접합”을 동시에 만족하기 어렵다.

따라서 새 구조는 투영 수식 자체를 쿼터뷰형으로 바꾼다. `x`와 `y` spread를 분리하고, 회전각과 타일 크기를 같은 수식에서 파생한다.

### Goal

현재 탑뷰 보드:

```ts
xPercent = 50 + diagonal * spread
yPercent = 50 + depth * spread
tileSide = sqrt(2) * spread / (boardSize - 1)
rotation = 45deg / -45deg
```

목표 쿼터뷰형 보드:

```ts
xPercent = 50 + diagonal * xSpread
yPercent = 50 + depth * ySpread
xSpread > ySpread
rotation = atan2(ySpread, xSpread)
tileInline = sqrt(xStep ** 2 + yStep ** 2)
tileBlock = tileInline * blockRatio
```

즉, 보드는 세로로 낮아지고 가로로 넓어진다. 남는 가로 공간을 써서 타일 inline 길이를 키우되, 타일 내부 정보는 눌리지 않게 한다.

### Target Parameters

초기 실험값:

```ts
TOP_VIEW_RING_X_SPREAD_PERCENT = 48;
TOP_VIEW_RING_Y_SPREAD_PERCENT = 31; // 31-34 범위에서 튜닝
QUARTERVIEW_TILE_BLOCK_RATIO = 0.62; // 0.58-0.68 범위에서 튜닝
```

예상 효과:

- 전체 다이아몬드 세로 길이는 현재보다 약 20-30% 감소
- 보드 가로 사용량은 현재보다 증가
- 타일은 정사각형이 아니라 얕은 직사각형 카드가 되어 내부 정보 표시 폭이 증가
- 중앙 prompt와 HUD가 차지하는 세로 충돌 가능성이 낮아짐

### Implementation Steps

#### 1. Projection constants split

파일: `apps/web/src/features/board/boardProjection.ts`

현재 단일 상수:

```ts
TOP_VIEW_RING_SPREAD_PERCENT
```

변경:

```ts
TOP_VIEW_RING_X_SPREAD_PERCENT
TOP_VIEW_RING_Y_SPREAD_PERCENT
QUARTERVIEW_TILE_BLOCK_RATIO
```

`projectTileQuarterview`는 다음처럼 변경한다.

```ts
xPercent = 50 + diagonal * TOP_VIEW_RING_X_SPREAD_PERCENT;
yPercent = 50 + depth * TOP_VIEW_RING_Y_SPREAD_PERCENT;
```

#### 2. Derived geometry helper

파일: `apps/web/src/features/board/boardProjection.ts`

새 helper를 둔다.

```ts
export type QuarterviewBoardGeometry = {
  xSpreadPercent: number;
  ySpreadPercent: number;
  tileAngleDeg: number;
  tileInlinePercent: number;
  tileBlockPercent: number;
};
```

계산 기준:

```ts
const denom = Math.max(1, boardSize - 1);
const xStep = xSpread / denom;
const yStep = ySpread / denom;
const tileAngleDeg = Math.atan2(yStep, xStep) * (180 / Math.PI);
const tileInlinePercent = Math.sqrt(xStep * xStep + yStep * yStep);
const tileBlockPercent = tileInlinePercent * QUARTERVIEW_TILE_BLOCK_RATIO;
```

주의:

- `tileAngleDeg`, `tileInlinePercent`, `tileBlockPercent`는 반드시 같은 `xStep/yStep`에서 파생한다.
- 이렇게 해야 타일 중심 간격, 회전각, 타일 크기가 서로 맞는다.

#### 3. BoardPanel CSS variables

파일: `apps/web/src/features/board/BoardPanel.tsx`

현재:

```ts
--board-diamond-tile-side
```

변경/추가:

```ts
--board-qv-tile-angle
--board-qv-tile-inline
--board-qv-tile-block
```

기존 `--board-diamond-tile-side`는 제거하거나 fallback 용도로만 남긴다.

#### 4. Tile CSS shape

파일: `apps/web/src/styles.css`

현재 탑뷰:

```css
width: var(--board-diamond-tile-side);
height: var(--board-diamond-tile-side);
rotate(45deg)
```

변경:

```css
.page.page-match .board-ring-quarterview .tile-card {
  width: var(--board-qv-tile-inline);
  height: var(--board-qv-tile-block);
  min-height: var(--board-qv-tile-block);
}

.page.page-match .board-ring-quarterview .tile-card[data-quarterview-lane="top"],
.page.page-match .board-ring-quarterview .tile-card[data-quarterview-lane="bottom"] {
  --board-qv-tile-rotation: var(--board-qv-tile-angle);
}

.page.page-match .board-ring-quarterview .tile-card[data-quarterview-lane="left"],
.page.page-match .board-ring-quarterview .tile-card[data-quarterview-lane="right"] {
  --board-qv-tile-rotation: calc(var(--board-qv-tile-angle) * -1);
}
```

#### 5. Tile content preservation

파일: `apps/web/src/features/board/BoardPanel.tsx`, `apps/web/src/styles.css`

현재 `tile-content` flex 슬롯은 유지한다.

유지할 정보:

- zone strip
- tile index
- tile kind label/icon
- purchase/rent cost
- fortune/finish special label
- owner
- score coins
- pawn fallback chips
- owner stamp
- move/stage/reveal badges

조정:

- 얕은 직사각형이므로 header와 footer는 더 가로형으로 사용한다.
- `tile-kind-chip`, `tile-cost-pill`, `tile-owner-badge`, `tile-score-badge`는 `inline-size` 기준으로 줄임 처리한다.
- 글자는 세로 압축이 아니라 ellipsis/nowrap 중심으로 처리한다.
- pawn fallback chip은 오른쪽 하단 고정 또는 footer 우측 고정으로 유지한다.

#### 6. Finish/corner connection validation

종료 타일 접합 조건은 별도 검증 대상이다.

검증 기준:

- F1/F2 종료 타일이 인접한 두 lane 타일과 시각적으로 맞닿는다.
- 코너와 인접 edge 사이에 눈에 띄는 gap이 없다.
- 타일이 서로 과하게 겹쳐 정보가 가려지지 않는다.
- `tileInline/tileBlock` 조정으로 해결되지 않으면 코너/종료 타일에만 `corner-fit` 보정 클래스를 둔다.

가능한 보정:

```css
.tile-finish,
.tile-corner {
  --board-qv-tile-inline: calc(var(--board-qv-tile-inline-base) * 1.02);
}
```

단, 보정은 마지막 수단이다. 기본은 수식 기반 접합이어야 한다.

#### 7. HUD and panel adaptation

가로 보드가 넓어지므로 HUD는 다음 방향으로 조정한다.

- 플레이어 카드: 현재처럼 화면 모서리에 최대한 붙인다.
- 현재 캐릭터 로스터: 필요하면 현재보다 위로 올리고, 8개 슬롯 가시성을 유지한다.
- 날씨: 보드 컨테이너 좌상단 기준 유지하되, 넓어진 보드와 겹치면 위쪽 safe zone으로 이동한다.
- 중앙 선택창: `prompt` 맵 컬럼 100% 폭 유지.
- 단, 보드가 넓어진 뒤 prompt가 과도하게 길어지면 prompt 내부에만 `max-width`를 둔다.

#### 8. Responsive strategy

뷰포트별 튜닝값:

```ts
desktop: xSpread 48, ySpread 31-34
medium:  xSpread 46, ySpread 33-35
mobile:  xSpread/ySpread 차이를 줄이거나 기존 top-view에 가깝게 fallback
```

CSS custom property 또는 JS geometry 상수 중 하나로 관리한다.

권장:

- 첫 구현은 TS 상수로 단순화한다.
- 이후 브라우저 검증에서 1180px/980px 경계 문제가 있으면 CSS 변수 기반 responsive로 승격한다.

### Test Plan

#### Unit tests

파일: `apps/web/src/features/board/boardProjection.spec.ts`

추가/수정:

- projected points are within 0-100 range
- `xSpread > ySpread` 상태에서도 lane 순서가 유지된다.
- top/bottom/left/right lane 방향이 유지된다.
- derived `tileAngleDeg`가 45도보다 작다.
- `tileInlinePercent > tileBlockPercent`다.
- finish/corner candidate positions가 기대한 두 lane의 접합 영역에 있다.

#### Build

```sh
cd apps/web && npm run test -- src/features/board/boardProjection.spec.ts
cd apps/web && npm run build
```

#### Browser QA

인앱 브라우저에서 확인:

- 현재 데스크톱 뷰포트
- 1180px 근처
- 980px 이하
- prompt 없음/대기 prompt/actionable prompt
- 캐릭터 로스터 8개 표시
- 날씨 패널이 타일/플레이어 카드를 깨지 않음
- 종료 타일 2면 접합
- standee 크기와 위치가 타일 중심에서 어긋나지 않음

### Acceptance Criteria

- 현재보다 보드 세로 점유가 줄어든다.
- 같은 뷰포트에서 타일 inline 길이가 현재보다 커진다.
- 타일 내부 정보량은 현재와 동일하게 유지된다.
- 텍스트가 세로로 눌리지 않는다.
- F1/F2 종료 타일이 정확히 두 면과 맞닿는다.
- 플레이어 카드/현재 캐릭터 로스터/날씨/prompt가 서로 겹치지 않는다.
- 브라우저 스크린샷 기준 우측/하단 잘림이 없다.

### Rollback Plan

쿼터뷰형 접합이 불안정하면 다음 순서로 되돌린다.

1. `xSpread/ySpread` 차이를 줄인다.
2. `tileBlockRatio`를 높인다.
3. 코너/종료 타일 보정을 적용한다.
4. 그래도 실패하면 현재 탑뷰 다이아몬드 수식으로 복귀한다.
