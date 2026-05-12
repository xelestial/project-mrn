# 서버 구조 진단: 웹소켓·런타임·커맨드 경계의 뒤엉킴

작성일: 2026-05-12  
작성자: Claude  
근거 파일:
- `docs/current/rules/[REFERENCE]_CORE_RULE_DECISION_FLOW_2026-05-12.md`
- `docs/current/architecture/[AUDIT]_CURRENT_GAME_SERVER_STRUCTURE_2026-05-12.md`
- `docs/current/architecture/[PROPOSAL]_SERVER_LOGIC_DESIGN_AGENT_A_2026-05-12.md`
- `docs/current/architecture/[PROPOSAL]_SERVER_LOGIC_DESIGN_AGENT_B_2026-05-12.md`
- `apps/server/src/routes/stream.py`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/prompt_service.py`
- `apps/server/src/services/command_wakeup_worker.py`

---

## 0. 이 문서의 목적

두 에이전트 제안(Agent A, B)은 둘 다 "장기 이상향"을 그렸다. Event Sourcing, Actor 모델, Saga 등 올바른 방향이지만 현재 코드와의 거리가 너무 멀다. 에이전트들이 이런 이상향을 반복해서 쓰는 동안 실제 코드는 패치 위에 패치가 쌓여 현재의 누더기가 됐다.

이 문서의 목적은 다르다. "현재 코드가 어디서 어떻게 어긋났는가"를 구체적으로 짚는다. 문제마다 근거 파일과 라인 범위를 명시한다. 이상론이 아니라 진단이다.

---

## 1. 가장 심각한 구조 문제: Decision 검증이 view_commit에 묶여 있다

### 무엇이 문제인가

`apps/server/src/routes/stream.py:183-214`의 `_decision_view_commit_rejection_reason`는 클라이언트가 제출한 decision의 유효성을 검증하는 함수다. 그런데 이 검증은 `latest_commit`(최신 view_commit)을 읽어서 수행한다.

```
view_commit.payload.view_state.prompt.active.request_id
view_commit.payload.view_state.prompt.active.player_id
view_commit.payload.view_state.prompt.active.prompt_instance_id
view_commit.payload.view_state.prompt.active.resume_token
```

이것이 왜 문제인가:

- Decision 검증의 권위 있는 데이터는 `PromptService`의 pending prompt다.
- view_commit은 UI 전달용 읽기 모델이지, 룰 판단의 근거가 아니다.
- view_commit이 stale하거나 아직 전달되지 않은 상태면, 유효한 decision이 `stale_prompt_request`로 거부될 수 있다.
- 반대로 view_commit이 잘못 구성된 경우 잘못된 decision이 통과할 수 있다.

REFERENCE 문서 §22에서 명시한 원칙은 이렇다:

> "UI에서 버튼이 보인다는 사실은 선택 가능의 근거가 아니다. 선택 가능 여부의 근거는 서버가 발행한 현재 prompt의 legal_choices다."

현재 구현은 이 원칙을 어기고 있다. view_commit이 "UI가 뭘 봤는가"의 증거이고, 그 증거로 선택 가능 여부를 판단하고 있다.

### 2차 증상: view_commit으로 pending prompt를 재생성

`stream.py:242-296`의 `_repair_missing_pending_prompt_from_view_commit`은 더 심각하다.

pending prompt가 `PromptService`에 없을 때, view_commit에서 active prompt를 꺼내 `PromptService.create_prompt`를 다시 호출한다. 즉 view_commit이 prompt의 백업 소스로 동작하고 있다.

이건 단순 결합이 아니라 역전이다:

- 원래 흐름: engine → prompt created → view_commit에 포함
- 현재 흐름: view_commit → prompt re-created (역방향)

이 역전이 발생한 이유는 알 수 있다. 어딘가에서 pending prompt가 사라지는 버그를 발견했고, view_commit이 상대적으로 안정적이어서 거기서 복구하는 패치를 붙인 것이다. 하지만 이 패치는 "view_commit이 곧 진실"이라는 더 큰 오개념을 구조에 박아버렸다.

---

## 2. 두 개의 런타임 wakeup 경로

decision이 수락되면 RuntimeService를 깨워야 한다. 현재 이 wakeup에는 두 독립 경로가 있다.

**경로 1**: `stream.py:338-424`의 `_wake_runtime_after_accepted_decision`  
WebSocket에서 decision이 accepted되면 asyncio task를 만들어 `_process_pending_runtime_command`를 호출한다. `running_elsewhere` 상태이면 최대 재시도 데드라인까지 루프를 돈다.

**경로 2**: `apps/server/src/services/command_wakeup_worker.py`의 `CommandStreamWakeupWorker`  
별도 폴링 워커가 250ms마다 Redis command stream을 확인하고 RuntimeService를 깨운다.

두 경로가 같은 일을 한다. 의도는 이렇다: "WebSocket 경로가 빠른 우선 처리고, 폴링 워커가 누락 복구다." 그러나 실제 코드를 보면:

- 두 경로 모두 `process_command_once`를 호출한다.
- RuntimeService 내부의 `_command_processing_guard`가 중복 실행을 막는다.
- 즉 한 경로가 먼저 실행되면 다른 경로는 `already_processing` 또는 `running_elsewhere`로 튕긴다.
- WebSocket 경로가 재시도 루프를 돌면서 `running_elsewhere`를 계속 반환받으면 CPU/이벤트 루프를 잡고 있다.

결과: 두 경로가 서로의 존재를 모른 채 경쟁하고, 각각 방어 코드를 추가했으며, 그 방어 코드끼리 또 충돌한다.

---

## 3. heartbeat가 상태 복구 수단이 됐다

`stream.py:625-698`의 `_heartbeat`는 연결 유지 ping이어야 한다. 실제로는:

1. `runtime_service.runtime_status(session_id)` 호출 → checkpoint에서 active module 추출
2. subscriber queue가 비어 있으면 `stream_service.latest_view_commit_message_for_viewer` 호출
3. 최신 view_commit을 재전송
4. 그 다음에야 실제 heartbeat 메시지 전송

`_should_send_heartbeat_view_commit`는 "subscriber queue가 비어 있으면" 조건으로 동작한다. 즉 클라이언트가 너무 빠르게 메시지를 다 소비했거나, 경쟁 조건으로 view_commit이 누락됐을 때, heartbeat가 repair 역할을 한다.

이것은 "delivery_lock 아래의 send → queue dequeue → heartbeat repair"가 세 가지 다른 타이밍에서 같은 역할을 나눠서 하고 있다는 뜻이다. 정상 경로가 어느 것인지 불분명하고, 어느 것이 실패하면 어느 것이 보완하는지도 불분명하다.

AUDIT 문서 §12.4에서 이미 지적됐다:

> "heartbeat는 단순 연결 유지가 아니라 최신 view_commit 재전송/repair 역할까지 한다."

지적은 됐지만 고치지 않았다.

---

## 4. RuntimeService가 5649줄인 이유

현재 `runtime_service.py`는 다음 역할을 한 파일에서 수행한다:

| 역할 | 예시 위치 |
|------|-----------|
| 엔진 실행 (thread pool) | `start_runtime`, `process_command_once` |
| Redis lease 관리 | `_command_processing_guard` |
| checkpoint 읽기/쓰기 | `_mark_checkpoint_waiting_input` |
| view_commit 생성 | `_build_authoritative_view_commits` |
| prompt materialize | `_materialize_prompt_from_checkpoint` |
| view_commit emit | `_emit_latest_view_commit_sync` |
| 외부 AI 클라이언트 관리 | `_ExternalAiTransport`, `_ExternalAiWorkerClient` (4000번대) |
| fallback choice 계산 | `execute_prompt_fallback`, `_fallback_choice_id` |
| in-process status dict | `_status` |
| command boundary 프록시 | `_CommandBoundaryGameStateStore` |
| stream task 스케줄링 | `_schedule_runtime_stream_task` |

이 중에서 "외부 AI 클라이언트 관리"만 해도 클래스 4개 이상(`_ExternalAiTransport`, `_LoopbackExternalAiTransport`, `_ExternalAiWorkerClient`, `_ExternalAiWorkerClientFactory`)이 있고 1000줄이 넘는다. 이것이 `runtime_service.py` 안에 있어야 할 이유가 없다.

5649줄 파일은 "점진적 기능 추가"의 결과다. 기능이 필요할 때마다 기존 서비스에 붙였고, 분리할 시점을 놓쳤다.

### `_CommandBoundaryGameStateStore`의 위험성

`runtime_service.py:109-227`의 `_CommandBoundaryGameStateStore`는 `RedisGameStateStore`를 감싸는 내부 프록시다. command boundary 처리 중 내부 transition을 `deferred_commit`으로 임시 보관하고, terminal status에 도달해야만 실제 Redis에 쓴다.

이 패턴의 위험:

- 서버가 내부 transition 도중 죽으면 `deferred_commit`에 쌓인 staged transition은 사라진다.
- Redis에는 이전 checkpoint만 남아 있고, 중간 단계는 흔적이 없다.
- 복구 시 "이전 checkpoint에서 다시 시작"이 맞는지 알 수가 없다.
- 버그 발생 시 "Redis에 커밋됐는가, 아직 deferred 상태인가"를 파악하는 디버깅이 어렵다.

---

## 5. in-process runtime status와 Redis runtime status의 불일치

`RuntimeService._status`는 Python dict로 관리되는 in-process 상태다.  
`RedisRuntimeStateStore`는 Redis에 저장되는 영속 상태다.

AUDIT 문서 §6.1에서 나열된 status 값들(`idle`, `running`, `waiting_input`, `completed`, `failed`, `recovery_required`, `running_elsewhere`, `rejected`, `stale`)은 어느 저장소가 권위인지 불명확하다.

`runtime_status` 메서드(`runtime_service.py:1196`)는 다음을 합친 dict를 반환한다:
- `self._status[session_id]` (in-process)
- `self._game_state_store.load_checkpoint(session_id)` (Redis)
- `self._runtime_state_store` (Redis)

서버 프로세스가 재시작되면 `_status` dict는 초기화된다. `runtime-status` API가 Redis에서 복구하지 않으면, 클라이언트는 `idle` 상태를 보고 불필요한 재시작을 유발할 수 있다.

`SessionService`의 재시작 복구 경로가 이 문제를 일부 처리하지만, in-process status와 Redis status가 두 개 존재한다는 근본 문제는 남아 있다.

---

## 6. 두 에이전트 제안의 공통 맹점

Agent A와 Agent B 모두 "장기 이상향"을 제시했다. 이 이상향이 틀렸다는 게 아니다. 문제는 현재 코드와의 연결 경로를 전혀 다루지 않았다는 것이다.

두 에이전트가 놓친 것:

**현재 prompt 검증 경로의 실제 체인**  
현재 decision 검증은 WebSocket 레이어(`stream.py`) → PromptService → RedisPromptStore → view_commit 교차 검증의 네 곳에 나뉘어 있다. Agent A/B가 제안한 "단일 PendingDecision 검증"을 도입하려면 이 네 곳을 동시에 바꿔야 한다. 점진적으로 바꿀 수 있는 경로를 제시하지 않았다.

**heartbeat repair 의존성**  
현재 일부 클라이언트 상태 복구가 heartbeat 재전송에 의존한다. 이것을 제거하지 않은 채로 새 구조를 추가하면 두 repair 경로가 공존하게 된다.

**`_CommandBoundaryGameStateStore`의 제거 순서**  
이 프록시를 그냥 제거하면 내부 module step마다 Redis에 쓰게 된다. 성능 영향을 먼저 측정하지 않으면 단순 제거는 불가능하다.

---

## 7. source event와 view_commit 이중 구조의 실제 비용

AUDIT 문서 §12.6에서 지적됐지만 실제 비용을 더 명확히 해야 한다.

현재 stream에는 두 종류가 공존한다:
- `source_events`: `session_created`, `seat_joined`, `decision_ack` 등 원천 이벤트
- `view_commit`: 화면 상태 전체를 담은 읽기 모델

문제는 `view_state` 생성 시 source_events에서 scene/turn_history를 꺼내 view_commit에 합친다는 것이다(`_build_authoritative_view_state`). 즉 view_commit을 만들려면 source_events도 필요하다. 두 구조가 독립적이지 않다.

이 의존성 때문에:
- source_events를 없애면 view_commit 생성 로직을 다시 짜야 한다.
- view_commit을 없애면 클라이언트 상태 복구 경로 전체를 다시 짜야 한다.
- 둘 다 유지하면 Redis 용량, 생성 비용, 디버깅 복잡도가 계속 올라간다.

---

## 8. 이 문서가 말하는 "바닥부터 갈아엎지 않고 고칠 수 있는가"

아래 세 가지는 코드 수준 변경으로 처리 가능하다. 이상향 전환 없이도 가능하다.

### 수정 가능 항목 1: Decision 검증을 view_commit에서 분리

`_decision_view_commit_rejection_reason`의 `request_id`, `player_id`, `resume_token` 검증을 view_commit이 아니라 `PromptService.get_pending_prompt`로 교체한다. view_commit 검증은 `view_commit_seq_seen` 범위 확인만 남긴다.

영향 범위: `stream.py:183-214`, `prompt_service.py`의 getter 추가.

### 수정 가능 항목 2: pending prompt repair 제거 또는 명시적 분리

`_repair_missing_pending_prompt_from_view_commit` 호출 경로를 찾아 제거하거나, 별도 debug-only 경로로 분리한다. 이 함수가 정상 decision 경로에서 호출되면 안 된다.

영향 범위: `stream.py:242-296`과 이 함수를 호출하는 WebSocket decision handler 구간.

### 수정 가능 항목 3: heartbeat를 단순 ping으로 되돌리기

`_should_send_heartbeat_view_commit` 조건을 제거하고, view_commit repair 책임을 heartbeat에서 분리한다. 클라이언트가 명시적 `resume` 메시지를 보내면 최신 view_commit을 재전송하는 현재 경로(`resume` outbound handler)가 이 역할을 담당하면 된다.

영향 범위: `stream.py:625-698`.

---

## 9. 수정하면 안 되는 것

아래 항목은 현재 구조를 유지한다. 건드리면 복구 경로가 깨진다.

- `_CommandBoundaryGameStateStore` 제거: 성능 영향 측정 없이 불가.
- source_events 스트림 제거: view_commit 생성 로직이 의존.
- command wakeup worker 제거: WebSocket 경로의 실패 커버리지가 제거됨.
- Redis lease 메커니즘 변경: 다중 프로세스 중복 실행 방어.

---

## 10. 구조적 전환을 원한다면 선행 조건

Agent A/B가 제안한 방향(Event Sourcing, Actor/Saga)으로 전환하려면 다음이 선행돼야 한다.

1. **prompt 검증 단일화 먼저**: view_commit 의존을 PromptService 의존으로 교체. 이것 없이는 새 구조를 추가해도 두 검증 경로가 공존한다.

2. **pending prompt를 단일 진실로 확립**: 현재 `PromptService.pending`, `view_commit.view_state.prompt.active`, `checkpoint.runtime_active_prompt` 세 곳에 같은 데이터가 있다. 하나만 남기고 나머지는 파생으로 만들어야 한다.

3. **`_CommandBoundaryGameStateStore` 성능 측정**: 이 프록시를 제거하면 내부 step마다 Redis write가 발생한다. 성능 허용 범위를 확인해야 한다.

4. **두 wakeup 경로 중 하나를 정식으로**: WebSocket 경로 또는 폴링 워커 중 어느 것이 주 경로인지 결정하고 나머지를 fallback으로 명시해야 한다. 현재는 둘 다 primary처럼 동작한다.

---

## 11. 요약

| 문제 | 심각도 | 파일/위치 | 비고 |
|------|--------|-----------|------|
| Decision 검증이 view_commit에 의존 | 높음 | `stream.py:183-214` | 룰 원칙 위반 |
| view_commit으로 pending prompt 재생성 | 높음 | `stream.py:242-296` | 역방향 의존 |
| 두 개의 wakeup 경로 경쟁 | 중간 | `stream.py:338-424`, `command_wakeup_worker.py` | 중복, 충돌 |
| heartbeat가 repair 경로 포함 | 중간 | `stream.py:625-698` | 책임 불명확 |
| `RuntimeService` 5649줄 단일 파일 | 중간 | `runtime_service.py` | 유지보수 불가 |
| `_CommandBoundaryGameStateStore` 비가시성 | 중간 | `runtime_service.py:109-227` | 디버깅 어려움 |
| in-process status와 Redis status 이중화 | 중간 | `runtime_service.py:1196` | 재시작 시 불일치 |
| source_events와 view_commit 교차 의존 | 낮음 | `_build_authoritative_view_state` | 제거 불가 구조 |

이 중 **Decision 검증이 view_commit에 의존**과 **view_commit으로 pending prompt 재생성**은 REFERENCE 문서 §25의 불변식 1~8을 직접 위반한다. 이 두 가지는 이상향 전환과 무관하게 지금 고쳐야 한다.
