# [PROPOSAL] CLAUDE 시각화 구현 의견
## 작성: Claude Sonnet 4.6 | 날짜: 2026-03-28

이 문서는 시각화 게임 전환에 대한 CLAUDE의 구체적 의견이다.
설계 플랜(GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN, VISUALIZATION_GAME_PLAN)과 별도로,
선택 지점에서 어떤 방향이 맞는지 판단 근거를 밝힌다.

---

## 1. 보드 렌더링: Canvas가 아니라 SVG

**의견: SVG + CSS를 쓴다. Canvas는 이 게임에 맞지 않는다.**

Canvas는 실시간 60fps 게임(탄막, 액션)에 적합하다.
이 게임은 턴제다. 이벤트가 발생할 때만 화면이 바뀐다.

SVG가 유리한 이유:
- 타일 하나가 DOM 노드 하나다. 소유주가 바뀌면 `tile.setAttribute('fill', color)` 한 줄이면 된다.
- CSS transition으로 색상·크기 변화 애니메이션이 자동으로 된다.
- 플레이어 토큰 이동: `transform: translate()` + CSS `transition`으로 충분하다.
- 클릭 이벤트가 각 타일에 직접 붙는다. 히트 영역을 따로 계산할 필요가 없다.
- 브라우저 devtools에서 바로 SVG 요소를 검사하고 고칠 수 있다.

Canvas가 필요해지는 시점은 **Phase 5 (Full Match UI)** 이후 파티클 이펙트, 고급 애니메이션을 추가할 때다.
그때 Canvas를 레이어로 올리면 된다. 처음부터 Canvas로 만들면 나중에 갈아엎어야 한다.

---

## 2. 프론트엔드 빌드 도구 없이 간다

**의견: npm, webpack, React, Vue 없이 Vanilla HTML + JS로 시작한다.**

이유:
- 팀이 작고, 빌드 파이프라인 유지보수 비용이 불필요하다.
- `index.html` 하나를 열면 바로 돌아가야 한다.
- Phaser.js, PixiJS는 실시간 게임 엔진이다. 턴제 보드게임에 사용하면 오버엔지니어링이다.
- 외부 의존은 최소화: FastAPI, uvicorn (서버), 그 외 프론트는 표준 Web API만.

나중에 복잡도가 진짜 필요해지면 그때 도입해도 늦지 않다.
지금 넣으면 생산성이 떨어진다.

---

## 3. 텍스트 프로토타입이 먼저다

**의견: 보드 그리기 전에 텍스트 타임라인부터 만든다.**

Phase 1-S (engine 로그 강화)가 끝나면, 보드를 그리기 전에 먼저:

```html
<ol id="timeline">
  <li>[턴 1-P1] 파발꾼 | 주사위: 4+2=6 | 12 → 18 이동</li>
  <li>[턴 1-P1] 타일 18 구매 | 4냥 지불</li>
  <li>[턴 1-P1] 잔꾀 '마당발' 사용</li>
  ...
</ol>
```

이걸 만들면 두 가지가 검증된다:
1. engine event stream이 실제로 replay를 재구성하기에 충분한지
2. frame_builder의 로직이 맞는지

시각적 보드 없이도 이 단계에서 AI 동작을 분석할 수 있다.
GPT의 "suspicious step" 분석도 이 텍스트 타임라인으로 먼저 작동한다.

---

## 4. Human Play의 핵심 난제는 async bridge다

**의견: 스레드 기반 blocking queue를 쓴다. asyncio 혼용은 복잡도가 높다.**

현재 `GameEngine`은 완전 동기(synchronous) 파이썬이다.
`HumanDecisionAdapter`가 사람의 입력을 기다려야 하는데, WebSocket은 async다.

선택지:

**A. asyncio.to_thread + Queue** (asyncio 방식)
- 엔진을 별도 스레드에서 실행
- 복잡도가 높고 디버깅이 어렵다

**B. threading.Event + Queue** (스레드 방식) ← 권장
```python
class HumanDecisionAdapter:
    def __init__(self):
        self._prompt_queue = queue.Queue()   # engine → UI
        self._response_queue = queue.Queue() # UI → engine

    def choose_movement(self, state, player):
        self._prompt_queue.put({"type": "movement", ...})
        return self._response_queue.get(timeout=30)  # blocking
```

- 엔진은 별도 `Thread`에서 실행
- WebSocket handler는 `_response_queue.put(response)` 호출
- 30초 타임아웃 시 AI fallback

이 구조가 단순하고 디버깅도 쉽다.
엔진 코드를 전혀 건드리지 않아도 된다 (DI 원칙 준수).

---

## 5. "언제나 사용할 수 있는 잔꾀" 처리

**의견: 잔꾀 인터랙션을 별도 `trick_window` 이벤트로 명시한다.**

현재 엔진은 잔꾀 사용 기회를 내부적으로 `phase` 파라미터로 처리한다.
사람이 플레이할 때 이 창이 언제 열리고 닫히는지 UI가 알아야 한다.

제안하는 이벤트:
```json
{"event": "trick_window_open", "player": 2, "phase": "before_dice", "available_tricks": ["마당발", "과속"]}
{"event": "trick_window_closed", "player": 2, "phase": "before_dice", "used": "마당발"}
{"event": "trick_window_closed", "player": 2, "phase": "before_dice", "used": null}
```

UI는 이 이벤트를 받으면 잔꾀 버튼을 활성화/비활성화한다.
replay에서는 이 이벤트로 "이 시점에 잔꾀를 쓸 수 있었다"는 것이 명확히 보인다.

---

## 6. public_view / analysis_view는 처음부터 분리한다

**의견: 나중에 추가하면 구조를 고쳐야 한다. 처음부터 넣는다.**

```python
class TurnEndSnapshotEvent:
    public_payload: dict    # 모든 플레이어에게 공개된 정보
    analysis_payload: dict  # 히든 카드 내용, AI 의사결정 이유 등
```

렌더러는 모드에 따라 어떤 payload를 사용할지 결정한다.
`analysis_view`는 AI 동작 디버깅과 GPT_TURN_ADVANTAGE 분석에 즉시 활용된다.

---

## 7. JSON Schema를 별도로 정의한다

**의견: Unity 이식을 진지하게 고려하면, 이벤트 계약을 언어 독립적으로 정의해야 한다.**

```
VIEWER/schema/
  replay_event.schema.json
  replay_snapshot.schema.json
  runtime_prompt.schema.json
  player_public_state.schema.json
  board_public_state.schema.json
```

Python 타입 정의(`viewer/public_state.py`)와 JSON Schema를 동기화한다.
Unity C# 클라이언트는 JSON Schema만 보고 타입을 생성할 수 있다.

이 작업이 무겁지 않다. Python dataclass → JSON Schema 변환은 `dataclasses-jsonschema` 또는 `pydantic`으로 자동화된다.

---

## 8. 서버는 단일 프로세스, 단순하게

**의견: Redis, 메시지 큐, 마이크로서비스 없이 FastAPI 단일 프로세스로 충분하다.**

- REST: 게임 목록, 프레임 시퀀스 제공
- WebSocket: 라이브 게임 상태 스트림, 인간 플레이어 결정 수신
- Static: HTML/JS/CSS 서빙

게임 세션이 동시에 여러 개 필요할 때 복잡도를 추가하면 된다.
지금은 `dict[session_id, GameSession]`으로 충분하다.

---

## 9. 구현 순서 의견

GPT 플랜과 CLAUDE 플랜이 모두 "올바른 순서"를 말하고 있다.
내 의견은 그보다 더 작은 단계로 쪼개는 것이다.

```
[S-T1~T4]  engine.py 이벤트 추가          ← 이것부터
[V]        full 로그 1게임 생성 + 검증
[텍스트]   HTML 텍스트 타임라인 prototype   ← 보드 그리기 전에 이걸 먼저
[SVG]      SVG 보드 레이아웃 (정적)
[리플레이] 프레임 시퀀스 + 재생 컨트롤
[패널]     플레이어 패널 + 현황판
[live]     WebSocket + 라이브 상태 스트림
[human]    HumanDecisionAdapter + 잔꾀 window
[UI]       결정 모달, 애니메이션 polish
```

각 단계가 독립적으로 검증 가능하다.
"텍스트 타임라인"이 가장 빨리 가치를 낼 수 있는 단계다.

---

## 요약

| 결정 | 권장 | 이유 |
|------|------|------|
| 보드 렌더링 | SVG + CSS | 턴제 게임, DOM 직접 조작이 유리 |
| 프론트엔드 | Vanilla HTML/JS | 빌드 도구 비용 불필요 |
| 첫 번째 결과물 | 텍스트 타임라인 | 데이터 계약 검증이 먼저 |
| Async bridge | Thread + blocking Queue | 단순, 엔진 불변 |
| 잔꾀 window | 명시적 이벤트 | replay에서도 가시화 가능 |
| Visibility | public/analysis 초기 분리 | 나중에 추가하면 구조 고쳐야 함 |
| 이식성 | JSON Schema 별도 정의 | Unity 이식 경로 확보 |
| 서버 구조 | FastAPI 단일 프로세스 | 지금 필요한 만큼만 |
