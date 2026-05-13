# 서버 재설계안

작성일: 2026-05-12  
작성자: Claude  
전제: 현재 코드를 전면 재작성하지 않는다. 엔진은 건드리지 않는다.

---

## 0. 기본 판단

현재 코드의 문제는 패러다임이 잘못된 것이 아니다. **레이어가 서로의 일을 하고 있는 것이다.**

- WebSocket 핸들러가 decision을 검증한다 (prompt 레이어 일)
- RuntimeService가 view_commit을 만들고 전송까지 한다 (delivery 레이어 일)
- heartbeat가 state repair를 한다 (복구 레이어 일)
- 폴링 워커와 WebSocket이 같은 wakeup을 경쟁한다 (단일 실행 경로 위반)

이것을 고치려면 Event Sourcing도 Actor 모델도 필요 없다. **경계를 명확히 하면 된다.**

---

## 1. 세 개의 레이어

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Delivery                                   │
│  WebSocket 송수신, viewer projection, reconnect      │
├─────────────────────────────────────────────────────┤
│  Layer 2: Session Loop                               │
│  게임 진행, prompt 검증, state commit                │
├─────────────────────────────────────────────────────┤
│  Layer 1: Engine (현재 그대로)                       │
│  룰 계산, module runner, frame/cursor 진행           │
└─────────────────────────────────────────────────────┘
         ↕ Redis (state, checkpoint, view_commits)
```

레이어 간 규칙은 단 하나: **아래 레이어는 위 레이어를 모른다.**

Engine은 WebSocket을 모른다.  
Session Loop는 WebSocket 연결을 모른다.  
Delivery는 게임 룰을 모른다.

---

## 2. Layer 1: Engine (변경 없음)

현재 `engine/` 패키지. 건드리지 않는다.

인터페이스: `state + decision_input → new_state + (PromptRequired | completed)`

Engine은 I/O를 하지 않는다. 순수 함수처럼 동작한다.

---

## 3. Layer 2: Session Loop

### 핵심 개념

게임 세션 하나에 **하나의 비동기 루프**가 붙는다. 이 루프가 해당 세션의 유일한 state writer다.

```python
async def session_loop(session_id: str):
    while True:
        command = await session_command_queue[session_id].get()
        await process_one_command(session_id, command)
```

`process_one_command`는 순서대로:
1. Redis에서 checkpoint 로드
2. Engine 실행 (thread pool, 동기 Python)
3. 결과를 Redis에 commit (state + checkpoint + view_commits)
4. view_commit pointer를 pub/sub channel에 publish

끝. RuntimeService가 현재 하는 것과 같지만, **단일 경로**로만 들어온다.

### Command Queue

세션별 in-process asyncio.Queue. Redis command stream이 아니다.

```
session_command_queues: dict[session_id, asyncio.Queue[Command]]
```

decision이 수락되면 → queue에 push.  
서버 재시작 시 → Redis pending command를 queue에 push해서 loop 재개.

### Prompt 검증

`PromptService.get_pending_prompt(request_id)` 하나로 검증.  
view_commit을 읽지 않는다.

```python
def validate_decision(message) -> ValidationResult:
    prompt = prompt_service.get_pending(message.request_id, session_id)
    if prompt is None:
        return STALE
    if prompt.player_id != message.player_id:
        return REJECT
    if message.resume_token != prompt.payload["resume_token"]:
        return REJECT
    if message.choice_id not in [c["choice_id"] for c in prompt.payload["legal_choices"]]:
        return REJECT
    return ACCEPT
```

view_commit은 이 경로에서 완전히 제거된다.

### Redis commit 구조

현재 `_CommandBoundaryGameStateStore` + deferred commit 패턴을 제거한다.

session loop는 engine이 `waiting_input` 또는 `completed`에 도달할 때만 Redis에 쓴다. 내부 module step은 Redis에 쓰지 않는다. 이것이 이미 command boundary 구조의 의도였다. deferred proxy 없이 loop 구조로 직접 표현한다.

```python
async def process_one_command(session_id, command):
    state = redis.load_checkpoint(session_id)
    decision_resume = build_resume(command)
    
    # engine은 동기, thread pool에서 실행
    result = await run_in_executor(engine.run, state, decision_resume)
    
    if result.status in ("waiting_input", "completed"):
        # 여기서만 Redis write
        await redis.commit(session_id, result)
        await pubsub.publish(session_id, "view_commit_ready")
```

---

## 4. Layer 3: Delivery

### WebSocket 핸들러의 역할

WebSocket 핸들러는 두 가지만 한다:

1. **inbound**: 클라이언트 메시지를 받아 session loop에 넘긴다
2. **outbound**: view_commit pub/sub을 구독해 클라이언트에 전송한다

decision 처리 흐름:

```
client → decision message
  → validate (PromptService만 사용)
  → accept: Redis atomic write + session_command_queue.put(command)
  → send decision_ack (즉시)
  
session_loop processes command
  → Redis commit + pubsub publish

pubsub subscriber (per WebSocket connection)
  → load view_commit from Redis
  → project for viewer
  → send to client
```

decision_ack와 view_commit 전송이 분리된다. ack는 즉시, view_commit은 engine이 다음 상태를 커밋한 뒤.

### heartbeat

ping/pong만 한다.

```python
async def heartbeat():
    while connected:
        await ws.send({"type": "heartbeat", "server_time_ms": now_ms()})
        await sleep(heartbeat_interval)
```

상태 repair, view_commit 재전송, runtime status 폴링 없음.

### reconnect

클라이언트가 재접속 시 `last_commit_seq`를 보낸다.

서버는 `view_commit_seq > last_commit_seq`인 최신 view_commit을 즉시 보낸다. 그 이후는 pub/sub 구독으로 계속 받는다.

repair가 아닌 catch-up이다. 차이: repair는 "혹시 빠진 게 있을까?"고 catch-up은 "이후 것을 줘"다. 후자는 결정적이다.

### view_commit 전송

현재 `stream_service.project_message_for_viewer` + `delivery_lock` + `delivered_stream_seqs` 추적 구조를 단순화한다.

```python
async def outbound_sender():
    async for commit_signal in pubsub.subscribe(session_id):
        commit = redis.load_view_commit(session_id, viewer)
        if commit.seq > last_sent_seq:
            await ws.send(commit)
            last_sent_seq = commit.seq
```

중복 억제는 `commit.seq > last_sent_seq` 하나로 충분하다.

---

## 5. 현재 코드에서 제거할 것

| 현재 존재 | 이유 |
|-----------|------|
| `CommandStreamWakeupWorker` | session loop가 단일 경로 대체 |
| `_RUNTIME_WAKEUP_TASKS` 모듈 전역 | session loop가 중복 방지 내재 |
| `_CommandBoundaryGameStateStore` | loop 구조로 대체 |
| `_repair_missing_pending_prompt_from_view_commit` | prompt_service가 단일 진실 |
| `_decision_view_commit_rejection_reason` | prompt_service 검증으로 대체 |
| heartbeat의 view_commit repair 로직 | heartbeat는 ping만 |
| `_should_send_heartbeat_view_commit` | 위 동일 |

---

## 6. 현재 코드에서 유지할 것

| 현재 존재 | 이유 |
|-----------|------|
| Engine (module runner, frame/cursor) | 이미 올바른 설계 |
| Redis lease per session | 멀티 프로세스 single-writer 보장 |
| `PromptService` 핵심 | pending/resolved/decision 관리 |
| `RedisGameStateStore.commit_transition` | Lua atomic commit |
| viewer-scoped view_commit | 정보 보호 |
| `frame_id`, `module_id`, `resume_token` 검증 | REFERENCE §20 그대로 |
| prompt timeout worker | 만료 처리 필요 |

---

## 7. Redis 구조 변경

추가: `session:{session_id}:pubsub` channel — view_commit ready 신호용  
제거: `commands:{session_id}:stream` — session loop queue로 대체 (Redis stream 불필요)  
유지: 나머지 전부

`commands` stream을 제거하면 `CommandStreamWakeupWorker`가 폴링할 대상도 없어진다. in-process asyncio.Queue로 충분하다. 단일 프로세스 내에서는 이것이 더 빠르고 단순하다.

다중 프로세스가 필요하면 (실제로 필요할 때) asyncio.Queue 대신 Redis pub/sub으로 교체하면 된다. 지금은 필요 없다.

---

## 8. 구현 순서

이 순서는 각 단계가 독립적으로 배포 가능하다.

### Step 1: Prompt 검증 분리 (1~2일)

`_decision_view_commit_rejection_reason` 내 request_id/resume_token/player_id 검증을 `PromptService.get_pending_prompt` 기반으로 교체.  
`_repair_missing_pending_prompt_from_view_commit` 호출 제거.

배포 후: decision 검증이 view_commit에 의존하지 않는다. 즉각 확인 가능.

### Step 2: heartbeat 단순화 (반나절)

`_heartbeat`에서 view_commit lookup, `_should_send_heartbeat_view_commit`, runtime status 폴링 제거.  
heartbeat = ping만.

배포 후: heartbeat가 상태 복구를 방해하지 않는다.

### Step 3: session_command_queue 도입 (3~5일)

`CommandStreamWakeupWorker`를 유지한 채로, decision 수락 시 per-session asyncio.Queue에도 push.  
`process_command_once`를 queue에서 꺼낸 command로 호출하는 단순 loop 추가.

두 경로(queue + 폴링 워커)가 공존. Redis lease가 충돌 방지.  
queue 경로가 안정되면 폴링 워커를 끈다.

### Step 4: CommandStreamWakeupWorker 제거 (1일)

Step 3가 안정화된 뒤. 폴링 워커 제거.

배포 후: 단일 wakeup 경로.

### Step 5: _CommandBoundaryGameStateStore 제거 (2~3일)

loop 구조가 내부 step을 자연스럽게 묶으므로 deferred proxy 불필요.  
성능 측정 후 진행.

---

## 9. 이 설계가 하지 않는 것

- Event Sourcing: 현재 checkpoint가 이미 recovery 역할을 한다. ES를 도입하면 engine을 다시 써야 한다. 하지 않는다.
- Actor 모델: Redis lease가 이미 single-writer를 보장한다. Actor 프레임워크는 새로운 복잡도를 추가할 뿐이다.
- 전면 재작성: engine, prompt contract, Redis schema는 그대로 둔다.
- 주사위 결과 이벤트 로그: 필요하지만 이 설계의 범위 밖이다. checkpoint에 이미 state가 있으므로 재현은 가능하다. 별도 task로 처리.

---

## 10. 완료 기준

이 설계가 구현됐다고 말할 수 있으려면:

- decision 검증 경로에 view_commit 로드가 없다
- heartbeat 코드에 view_commit 로드가 없다
- `CommandStreamWakeupWorker`가 없다
- `_RUNTIME_WAKEUP_TASKS`가 없다
- `_repair_missing_pending_prompt_from_view_commit`가 없다
- decision → engine wakeup 경로가 하나뿐이다
- reconnect 시 `last_commit_seq` 기반 catch-up이 작동한다

이 7개가 모두 충족되면 현재 누더기의 핵심 원인이 제거된 것이다.
