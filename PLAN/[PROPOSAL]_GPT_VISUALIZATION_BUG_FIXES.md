# [PROPOSAL] GPT Visualization Bug Fixes

**작성일**: 2026-03-29
**상태**: PROPOSAL
**대상 코드베이스**: GPT
**출처**: GPT 시각화 코드 리뷰 (Phase 2–4 완료 후)

---

## 배경

Phase 2(오프라인 리플레이), Phase 3(라이브 스펙테이터), Phase 4(휴먼 플레이) 구현 완료 후
전체 시각화 코드 리뷰를 수행하였다. 이 문서는 GPT 코드에서 발견된 버그 및 개선 항목을 기록한다.

---

## Critical (🔴) — 수정 필수

### BUG-1: play_html.py — HUMAN_SEAT 인덱싱 오류

**파일**: `GPT/viewer/renderers/play_html.py`
**라인**: 287, 483, 526, 607–608, 620–621, 643

**문제**:
```javascript
const HUMAN_SEAT = {human_seat};  // 0-indexed (0,1,2,3)
```
이벤트 스트림의 `acting_player_id`, `owner_player_id`, `pawn_player_ids`는 **1-indexed** (1,2,3,4).
결과적으로 아래 비교가 **항상 false**:
```javascript
currentActorId === HUMAN_SEAT   // 1 === 0 → false
ownerId === HUMAN_SEAT          // 1 === 0 → false
pawns.includes(HUMAN_SEAT)      // [1,2,...].includes(0) → false
```

**영향**: 인간 시트의 금색 테두리, ★ 폰, 턴 헤더 강조가 절대 표시되지 않음.

**수정**:
```python
# render_play_html() 에서 1-indexed로 변환하여 전달
return _TEMPLATE.format(
    ...
    human_seat_js=human_seat + 1,   # 이벤트 ID와 동일한 1-indexed
    human_seat_display=human_seat,  # 사용자에게 표시하는 0-indexed 레이블
    ...
)
```
```javascript
const HUMAN_SEAT = {human_seat_js};  // 1-indexed
```

---

### BUG-2: play_html.py — PLAYER_COLORS 인덱싱이 live_html.py와 불일치

**파일**: `GPT/viewer/renderers/play_html.py:485, 528, 607, 645`
**비교 대상**: `GPT/viewer/renderers/live_html.py`

**문제**:
- `live_html.py`: `PLAYER_COLORS[((pid-1) % 4)]` — P1→파랑, P2→빨강 (1-indexed 보정)
- `play_html.py`: `PLAYER_COLORS[pid % 4]` — P1→빨강, P2→초록 (보정 없음)

같은 게임을 live spectator와 human play에서 볼 때 플레이어 색상이 다름.

**수정**:
```javascript
// play_html.py 내 모든 PLAYER_COLORS 인덱싱을 통일
PLAYER_COLORS[((pid - 1) % PLAYER_COLORS.length)]
// ownerId도 동일하게
const ci = (ownerId - 1) % PLAYER_COLORS.length;
```

---

### BUG-3: human_policy.py — submit_response 락 범위 부족 (오답 주입 가능)

**파일**: `GPT/viewer/human_policy.py:57–70`

**문제**:
```python
def submit_response(self, response: dict) -> bool:
    with self._lock:
        if self._pending is None:
            return False
    # ← 락 해제 후
    self._response_queue.put_nowait(response)  # 락 밖에서 실행
```

경합 시나리오:
1. 타임아웃 발생 → `_pending = None`, fallback 반환
2. 다음 `_ask` 시작 → `_pending = new_prompt`
3. 늦게 도착한 이전 응답이 `put_nowait` 실행 → **새 질문에 이전 응답 주입**

**수정**:
```python
def submit_response(self, response: dict) -> bool:
    with self._lock:
        if self._pending is None:
            return False
        try:
            self._response_queue.put_nowait(response)
            return True
        except queue.Full:
            return False
```

---

### BUG-4: human_policy.py — 프롬프트의 player_id가 0-indexed로 노출

**파일**: `GPT/viewer/human_policy.py` (모든 `_ask` 호출 내 prompt dict)

**문제**:
```python
prompt = {
    "type": "movement",
    "player_id": player.player_id,  # 0-indexed: 0,1,2,3
    ...
}
```
브라우저 결정 패널에서 "P0" 표시 → 사용자는 "P1"로 인식해야 함.

**수정**:
```python
"player_id": player.player_id + 1,  # 1-indexed: 1,2,3,4
```

---

## Medium (🟡) — 권장 수정

### M-1: play_html.py — 타임아웃 카운트다운 UI 없음

**파일**: `GPT/viewer/renderers/play_html.py`

HTML에 `<div class="dp-timeout" id="dp-timeout">제한 시간: 5분</div>` 요소는 있으나
JavaScript 카운트다운 로직 없음. 정적 텍스트만 표시됨.

**수정 방향**:
```javascript
let decisionTimeStart = null;
let timeoutInterval = null;

function showDecision(prompt) {
    decisionTimeStart = Date.now();
    timeoutInterval = setInterval(() => {
        const remaining = Math.ceil(300 - (Date.now() - decisionTimeStart) / 1000);
        document.getElementById("dp-timeout").textContent =
            remaining > 0 ? `남은 시간: ${remaining}초` : "시간 초과 (AI 자동 선택)";
        if (remaining <= 0) clearInterval(timeoutInterval);
    }, 500);
    ...
}

function hideDecision() {
    clearInterval(timeoutInterval);
    ...
}
```

---

### M-2: play_html.py — pendingDecision 플래그 이중 해제

**파일**: `GPT/viewer/renderers/play_html.py`

`pendingDecision = false`가 두 곳에서 설정됨:
- `pollPrompt()` 내 `else if` 분기
- `hideDecision()` 함수 내부

타이밍에 따라 `hideDecision()`이 중복 호출될 수 있음. `pendingDecision` 플래그보다
overlay 가시성을 단일 진실 공급원으로 사용하는 것이 더 안전함.

**수정 방향**:
```javascript
const isDecisionVisible = () =>
    document.getElementById("decision-overlay").classList.contains("visible");

// pollPrompt 내 조건
if (data.type && !isDecisionVisible()) { showDecision(data); }
else if (!data.type && isDecisionVisible()) { hideDecision(); }
```

---

### M-3: replay.py — turn_start 없이 도착하는 이벤트 처리

**파일**: `GPT/viewer/replay.py`

부분 게임 데이터 로드 시 `turn_start` 없이 이벤트가 도착하면
`current_turn`이 None이어서 해당 이벤트가 `prelude_events`로 잘못 분류됨.

**수정 방향**: 경고 로깅 또는 이벤트를 버리지 않는 방어 로직 추가.

**재검토 의견 (2026-03-29)**: 수정 불필요.

코드(`replay.py:306–316`)를 보면 `turn_start` 없이 도착한 이벤트는
`current_round.prelude_events` 또는 `session_prelude_events`로 들어간다.
이벤트가 **유실되지 않으며**, `prelude_events`는 라운드/세션 서두에 속하는
이벤트를 담는 설계된 버킷이다. "잘못 분류"라는 원래 표현은 부정확하다.
실시간 라이브 스트림에서는 이 경로 자체가 발생할 수 없고, 오프라인 리플레이에서도
정상 스트림은 항상 `turn_start`가 선행한다. 실질적인 문제 없음.

---

### M-4: html_renderer.py — `{{`/`}}` escape 후처리 취약점

**파일**: `GPT/viewer/renderers/html_renderer.py`

```python
html = html.replace("{{", "{").replace("}}", "}")
```

JSON 데이터 내 `{{` 또는 `}}`가 포함될 경우 데이터 손상 가능.

**수정 방향**: `string.Template` 또는 별도 치환 마커(`__META_JSON__` 등) 사용.

**재검토 의견 (2026-03-29)**: 이론상 유효하나 현재 실질 위험 없음.

코드(`html_renderer.py:338–344`)를 보면 순서는 다음과 같다:
1. `html.replace("{meta_json}", json.dumps(...))` — JSON 데이터 주입
2. `html.replace("{turns_json}", json.dumps(...))` — JSON 데이터 주입
3. `html.replace("{{", "{").replace("}}", "}")` — 템플릿 CSS/JS의 `{{`를 `{`로 정리

3번이 1~2번에서 주입된 JSON 안의 `{{`도 함께 처리하므로,
JSON 값에 `{{`가 포함되면 데이터가 손상된다는 지적은 구조적으로 정확하다.

그러나 이 게임의 실제 데이터(캐릭터명, 이벤트 값, 수치 등)에
`{{` 또는 `}}`가 포함될 수 없으므로 **현재는 발생하지 않는 문제**다.
향후 문자열 자유도가 높은 데이터(예: 유저 입력 이름)가 추가될 경우 재검토가 필요하다.

---

## Low (🔵) — 개선 권장

### L-1: 보드 크기 하드코딩

| 파일 | 라인 | 값 |
|------|------|----|
| `play_html.py` | 601 | `i < 40` |
| `html_renderer.py` | 283 | `range(40)` |

**수정**: `board.tiles.length` (JS) 또는 `len(board_data.get("tiles", []))` (Python)으로 대체.

**재검토 의견 (2026-03-29)**: 수정 불필요.

이 게임의 보드는 설계상 항상 40칸으로 고정되어 있다(`CLAUDE/config.py`의
보드 레이아웃이 40칸으로 구성). 동적으로 바뀌는 설계 요소가 아니다.
`tiles.length`를 쓰는 것이 방어적 스타일로는 낫지만, 현재 40이라는 값이
잘못된 가정이 아니므로 버그가 아니다. 보드 크기 가변화 요구가 생길 때 수정하면 충분하다.

---

### L-2: 에러 핸들링 무음 처리

**파일**: `play_html.py`, `live_html.py`

```javascript
catch(e) {}  // 모든 폴 오류 무시
```

**수정**: `console.warn("poll failed:", e)` 최소 추가.

---

### L-3: markdown_renderer.py 필드명 불일치

**파일**: `GPT/viewer/renderers/markdown_renderer.py`

```python
tricks = ", ".join(player.get("public_tricks", [])) or "-"
```

CLAUDE Phase 2-S에서 `public_tricks` → `trick_cards_visible` alias 추가됨.
GPT 렌더러가 어느 쪽을 기준 필드로 사용하는지 명시 필요.
두 필드 모두 확인하는 fallback 적용 권장:
```python
tricks = ", ".join(
    player.get("trick_cards_visible") or player.get("public_tricks") or []
) or "-"
```

---

## 수정 우선 순위

| 순위 | ID | 파일 | 난이도 | 영향 |
|------|-----|------|--------|------|
| 1 | BUG-1 | play_html.py | 낮음 | Critical — 인간 플레이어 강조 작동 안 함 |
| 2 | BUG-2 | play_html.py | 낮음 | High — 색상 일관성 |
| 3 | BUG-3 | human_policy.py | 낮음 | Critical — race condition |
| 4 | BUG-4 | human_policy.py | 낮음 | Medium — 표시 오류 |
| 5 | M-1 | play_html.py | 중간 | Medium — UX |
| 6 | M-2 | play_html.py | 낮음 | Low — 방어 코드 |
| 7 | M-4 | html_renderer.py | 중간 | Medium — 데이터 손상 방지 |
| 8 | L-1–L-3 | 여러 파일 | 낮음 | Low — 코드 품질 |

---

## 관련 문서

- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md` — 원본 시각화 플랜
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md` — 공유 계약
- `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_SUBSTRATE_FOLLOWUP.md` — CLAUDE 측 후속 항목
