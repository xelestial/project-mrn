# [REPORT] 실제 플레이 UI/UX 발견 사항

Status: REPORT
Date: 2026-04-07
Method: 로컬 서버 기동 + Chrome 직접 플레이 (1 human + 3 AI, Round 1 Turn 2까지)
Session: sess_0ed27a677f80

---

## 플레이 흐름 요약

1. 로비 → Quick Start (1 human + 3 AI)
2. Round 0: 히든 잔꾀 지정 프롬프트
3. Round 1 Turn 1: 드래프트 캐릭터 픽 → 최종 캐릭터 확정
4. Round 1 Turn 2: P2 (아전) 이동 관전 (Observing 상태)

---

## 발견된 문제

### 기존 제안서 대비 수정된 진단

#### BUG-01 — 타일 비용 (수정)
- 기존 진단: "항상 누락"
- 실제 확인: **드래프트 전(Round 0)에만 "-"로 표시, 드래프트 완료 후 "Buy 5냥 / Rent 5냥" 정상 표시됨**
- 의미: 서버는 이미 타일 비용을 내려줌. 드래프트 이전 snapshot에서만 없는 것
- 우선순위 하향 조정

---

### 실제 플레이에서 새로 확인된 버그

#### BUG-09 — "Select a session" 오표시 (신규, 높음)

**화면**: 모든 플레이어 패널(P1~P3) 상단에 "Select a session" 텍스트 고착
**상황**: 게임 진행 중, 캐릭터 배정 완료, 리소스 정상 표시됨에도 제거되지 않음
**예시**: P1 패널에 "교리 연구관" 아래에 "Select a session" 유지
**파일**: `apps/web/src/features/players/PlayersPanel.tsx`
**수정 방향**: 플레이어가 alive 이거나 character 배정된 경우 해당 텍스트 조건 제거

---

#### BUG-10 — 카드 설명 `[효과]`/`[능력N]`/`[도치]` 태그 raw 노출 (신규, 높음)

**화면**: 잔꾀 카드, 인물 카드 설명에 마커 태그가 파싱되지 않고 텍스트로 출력됨
**예시**:
```
[효과] 이번 턴 모든 통행료를 내지 않습니다
[효과] 아무 효과도 없습니다 [효과] 사용하려면 4냥 지불하세요 [효과] 보급 시 4냥 지불하고 새 비책으로 교환할 수 있습니다
[능력1] 라운드 종료 시 붉은 징표 획득(드래프트 전달: 반시계) / [능력2] 조각 8+이면 칸 1장 제거
[도치] - 사치, 종묘, 궁수 간 보다 1칸 부족한 경우 해당 칸으로 도착 할 수 없음
```
**파일**: `apps/web/src/features/prompt/PromptOverlay.tsx` — 카드 description 렌더 부분
**수정 방향**:
- `parseCardText(text: string): ReactNode` 유틸 함수 작성
- `[효과]` → 초록 배지, `[능력N]` → 파랑 배지, `[도치]` → 보라 배지
- 최소 수정: `[...]` 패턴을 `<strong>` 태그로 감쌈

---

#### BUG-11 — 타임라인(Recent Public Actions)이 보드 하단 분리 배치 (신규, 높음)

**화면**: 게임 이벤트 피드가 보드 아래 별도 섹션에 위치 — 스크롤 없이 볼 수 없음
**상황**: 이동, 착지, 드래프트 등 모든 이벤트가 화면 밖에서 발생
**추가 문제**: AI 드래프트 결과가 "Draft pick / No extra detail" — 어떤 캐릭터를 가져갔는지 없음
**파일**: `apps/web/src/App.tsx` — `TimelinePanel` 배치 위치
**수정 방향**: 사이드 컬럼 내 EventFeed 형태로 이동 (상용 재설계 Zone F 참고)

---

### 실제 플레이에서 확인된 UX 개선 필요 사항

#### UX-A — 관전 상태 표시 혼재

**화면**: P2 턴 중 보드 상단에 "P2 (아전)'s turn / Decision requested" 배너 표시
**문제**: 배너는 보드 위에 있고 사이드 플레이어 패널에서는 P2가 강조되지 않음
**의미**: BUG-07(행동자 강조)이 실제로 미구현임을 플레이 중 체감으로 확인
**파일**: `apps/web/src/features/players/PlayersPanel.tsx` — BUG-07과 동일

---

#### UX-B — 히든 잔꾀 선택 프롬프트에 맥락 설명 없음

**화면**: "Choose which trick will stay hidden this round." — 영어 텍스트
**문제**: 히든 잔꾀가 무엇인지, 왜 지금 선택해야 하는지 설명 없음
**추가 문제**: "Public trick" 배지가 무슨 의미인지 플레이어가 알 수 없음
**수정 방향**: 상용 재설계 문서 Zone D `buildPromptContext(hidden_trick_card)` 케이스 적용

---

#### UX-C — 드래프트 카드 설명이 오른쪽 잘림

**화면**: 박수, 아전 카드 설명이 패널 오른쪽 경계에서 잘려 끝까지 보이지 않음
**파일**: `apps/web/src/features/prompt/PromptOverlay.tsx` — 드래프트 카드 그리드
**수정 방향**: 카드 컨테이너에 `overflow: hidden` + `text-overflow: ellipsis` 또는 `line-clamp`

---

## 정상 동작 확인 사항

아래는 코드 분석에서 우려했으나 실제 플레이에서 정상임을 확인:

| 항목 | 확인 내용 |
|---|---|
| 타일 비용 표시 | 드래프트 후 Buy/Rent 정상 표시됨 |
| 플레이어 말(Pawn) | 보드 타일에 숫자 원형 뱃지로 표시됨 |
| 이동 경로 표시 | 경로 타일에 숫자 배지 + 파란 테두리 정상 표시 |
| 착지 타일 강조 | "Arrive" 배지 + 노란 테두리로 명확히 표시됨 |
| 날씨 표시 | 드래프트 후 "풍년든 가을" 정상 표시됨 |
| 캐릭터 이름 | 드래프트 후 플레이어 패널에 캐릭터명 정상 표시됨 |
| Observing 배지 | 내 턴 아닐 때 "Observing" 우측 상단 표시 |
| Latest move 표시 | "Latest move: P2 1 -> 6" 우측 상단 표시됨 |

---

## 업데이트된 수정 우선순위

| 순위 | 항목 | 작업량 | 이유 |
|---|---|---|---|
| 1 | BUG-08 | 1줄 | 리스크 제로 |
| 2 | BUG-09 | ~30분 | "Select a session" 오표시 — 즉시 수정 가능 |
| 3 | BUG-10 | ~2시간 | `[효과]` 태그 — parseCardText() 유틸 하나 |
| 4 | BUG-07 | ~1시간 | 행동자 강조 — prop 추가 |
| 5 | BUG-02 | ~2시간 | "Preparing your turn" 공백 |
| 6 | BUG-11 | 재설계 때 | 타임라인 위치 — EventFeed로 대체 |
| 7 | BUG-03 | ~1시간 | 잔꾀 레이블 분리 |
