# 서버 재설계안 — 전체

작성일: 2026-05-12  
작성자: Claude  
전제 문서: `[CLAUDE-PROPOSAL]_SERVER_REDESIGN_2026-05-12.md`

이 문서는 초안에서 빠진 영역을 포함한 완전한 설계다.

---

## 1. 전체 데이터 흐름

```
Human Player (WebSocket)
  └→ WS Handler → validate → command_router → session_command_queue
                                                        ↓
AI Worker (HTTP callback)                        Session Loop
  └→ AI Decision Handler → validate → command_router    ↓
                                                  run_engine_step
Prompt Timeout Worker                                    ↓
  └→ timeout_decision → command_router           Redis commit
                                                        ↓
                                                 pubsub.publish
                                                        ↓
                                            WS outbound sender
                                                  (per conn)
                                                        ↓
                                            Human Player (WebSocket)
                                            AI Worker (view_commit)
                                            Spectator (WebSocket)
```

모든 decision 입력은 `command_router`를 통해 하나의 경로로 수렴한다.  
모든 state 출력은 Redis → pub/sub → outbound sender를 통해 전달된다.

---

## 2. Session Loop 전체 명세

### 2.1 생명주기

```
game start (POST /sessions/{id}/start)
  → session_loop_manager.start(session_id)
    → asyncio.create_task(session_loop(session_id))
    → session_command_queues[session_id] = asyncio.Queue()

game complete / failed
  → session_loop exits naturally
  → session_loop_manager.cleanup(session_id)
    → del session_command_queues[session_id]

server restart
  → on startup: for each in_progress session:
      recovery_command = redis.load_pending_command(session_id)
      if recovery_command:
          session_command_queues[session_id].put_nowait(recovery_command)
      session_loop_manager.start(session_id)
```

### 2.2 Loop 본체

```python
async def session_loop(session_id: str):
    lease = await redis.acquire_lease(session_id)
    if lease is None:
        # 다른 프로세스가 이 세션 소유
        return

    try:
        while True:
            command = await asyncio.wait_for(
                session_command_queues[session_id].get(),
                timeout=LOOP_IDLE_TIMEOUT_SEC
            )
            if command.type == "shutdown":
                break

            result = await process_one_command(session_id, command, lease)

            if result.status == "completed":
                await redis.mark_session_completed(session_id)
                break
            if result.status == "failed":
                await redis.mark_session_failed(session_id, result.reason)
                break
            # waiting_input: 다음 command 대기

    except asyncio.TimeoutError:
        # 장시간 command 없음 → lease 반환, loop 종료
        # 다음 command 도착 시 재시작
        pass
    finally:
        await redis.release_lease(session_id, lease)
        session_loop_manager.cleanup(session_id)
```

### 2.3 process_one_command

```python
async def process_one_command(session_id, command, lease):
    # 1. checkpoint 로드
    state = await redis.load_checkpoint(session_id)
    if state is None:
        return Result(status="failed", reason="checkpoint_missing")

    # 2. command 중복 확인
    if await redis.is_command_seen(command.command_id):
        return Result(status="duplicate", command_id=command.command_id)

    # 3. engine 실행 (thread pool)
    decision_resume = build_resume_from_command(command)
    try:
        engine_result = await run_in_executor(
            engine.run_to_next_boundary, state, decision_resume
        )
    except Exception as exc:
        return Result(status="failed", reason=repr(exc))

    # 4. lease 확인 (commit 전)
    if not await redis.verify_lease(session_id, lease):
        return Result(status="stale", reason="lease_lost")

    # 5. Redis atomic commit
    view_commits = build_view_commits(engine_result.state)
    await redis.commit_transition(
        session_id,
        current_state=engine_result.state,
        checkpoint=engine_result.checkpoint,
        view_commits=view_commits,
        command_id=command.command_id,
    )

    # 6. view_commit 전달 알림
    await pubsub.publish(session_id, {
        "commit_seq": engine_result.checkpoint.commit_seq
    })

    return Result(status=engine_result.status)
```

---

## 3. Command Router

모든 decision 입력의 단일 진입점.

```python
class CommandRouter:
    def route(self, session_id: str, command: Command) -> RoutingResult:
        queue = session_command_queues.get(session_id)

        if queue is None:
            # 이 프로세스에 session loop가 없음
            # → Redis command stream에 기록 (다른 프로세스가 처리)
            return self._route_to_redis(session_id, command)

        # 이 프로세스에 session loop 있음 → 직접 queue에 push
        queue.put_nowait(command)
        return RoutingResult(status="queued_local")

    def _route_to_redis(self, session_id, command):
        redis.append_command(session_id, command)
        return RoutingResult(status="queued_remote")
```

**다중 프로세스 처리 원칙:**

```
Process A: session X의 loop 실행 중 (lease 보유)
Process B: session X의 WebSocket에서 decision 수신

Process B:
  1. decision validate (PromptService → Redis)
  2. command_router.route(session_X, command)
     → Process B에 session_X의 queue 없음
     → Redis command stream에 append

Process A:
  → CommandWatcher (단순 Redis stream poller)
     최신 seq 확인 → 새 command → session_X queue에 push
  → session loop가 command 처리
```

단일 프로세스 환경에서는 Redis stream 없이 direct queue push만 사용한다.  
다중 프로세스 환경에서는 Redis stream이 cross-process signal 역할만 한다.

`CommandWatcher`는 현재 `CommandStreamWakeupWorker`보다 훨씬 단순하다:

```python
class CommandWatcher:
    async def run(self):
        while True:
            for session_id in active_sessions_on_this_process():
                last_seq = local_offsets[session_id]
                new_commands = redis.commands_after(session_id, last_seq)
                for cmd in new_commands:
                    if session_id in session_command_queues:
                        session_command_queues[session_id].put_nowait(cmd)
                        local_offsets[session_id] = cmd.seq
            await asyncio.sleep(WATCHER_INTERVAL_SEC)
```

이 워커는 **cross-process 누락 복구**만 담당한다. 같은 프로세스의 경우 CommandRouter가 직접 queue에 push한다.

---

## 4. 동시 배치 프롬프트 처리 (Simultaneous Frame)

### 4.1 흐름

`burden_exchange` 같은 동시 배치 프롬프트는 여러 플레이어 응답을 모아야 한다.

```
Engine hits simultaneous frame
  → PromptRequired(batch=True, participant_ids=[1,2,3,4])
  → Session Loop: status = "waiting_batch"
  → Redis: store batch_prompt (request_ids per player)
  → pubsub: publish prompt_opened signal
  → WS outbound: deliver per-player prompts

Each player responds:
  → WS Handler: validate (per-player prompt)
  → BatchCollector.record_response(batch_id, player_id, choice)
  → BatchCollector.check_complete(batch_id)
    → if all required responses received:
        command = Command(type="batch_complete", batch_id=batch_id)
        command_router.route(session_id, command)
    → else: 응답 수집 대기 계속

Timeout:
  → PromptTimeoutWorker: expire batch prompt
  → default_policy 적용 → batch_complete command 생성
  → command_router.route(session_id, command)
```

### 4.2 BatchCollector

```python
class BatchCollector:
    def record_response(self, batch_id, player_id, choice_id, resume_token):
        # 검증: batch_id, player_id, resume_token, choice_id in legal_choices
        # Redis에 원자적으로 기록
        redis.record_batch_response(batch_id, player_id, choice_id)

    def check_complete(self, batch_id) -> bool:
        batch = redis.load_batch(batch_id)
        if batch.commit_policy == "all_required":
            return len(batch.missing_player_ids) == 0
        # timeout_default는 PromptTimeoutWorker가 처리
        return False
```

BatchCollector는 Session Loop와 독립적으로 동작한다. Session Loop는 `batch_complete` command가 queue에 들어올 때만 재개된다.

### 4.3 단일 배치 응답이 loop를 재개하지 않는 이유

현재 REFERENCE §18 불변식: "한 참가자의 응답만으로 전체 보급 결과를 부분 커밋하면 안 된다."

BatchCollector가 `missing_player_ids`를 확인한 뒤에만 `batch_complete` command를 생성하므로 이 불변식이 자동으로 지켜진다.

---

## 5. 외부 AI 워커 통합

### 5.1 현재 문제

현재 `_ExternalAiTransport`, `_ExternalAiWorkerClient` 등 1000줄이 `runtime_service.py` 안에 있다. AI 로직이 engine 실행 루프 안에 얽혀 있다.

### 5.2 새 구조

AI는 Session Loop 밖에 있다. AI는 HTTP로 prompt를 받고 HTTP로 decision을 보내는 외부 클라이언트일 뿐이다.

```
Session Loop: engine hits prompt for AI seat
  → PromptService.create_prompt()
  → pubsub publish (prompt_opened)
  → status = waiting_input (AI 응답 대기)

AI Notification Service (Session Loop 밖):
  → pubsub 구독
  → prompt_opened 수신
  → AI seat인지 확인
  → HTTP POST to external AI worker:
      { prompt_payload, legal_choices, public_context }

External AI Worker:
  → HTTP 응답: { choice_id }

AI Decision Handler (WebSocket handler와 동급):
  → validate (PromptService)
  → command = Command(type="decision", ...)
  → command_router.route(session_id, command)
```

`_ExternalAiTransport` 클래스군을 `runtime_service.py`에서 분리해 독립 서비스로 만든다.  
Session Loop는 AI인지 Human인지 모른다. 그냥 command를 기다린다.

### 5.3 AI fallback (loopback)

test 또는 자동 플레이를 위한 loopback AI:

```python
class LoopbackAiHandler:
    async def on_prompt(self, prompt):
        # legal_choices에서 첫 번째 선택 (또는 configured choice)
        choice_id = prompt["legal_choices"][0]["choice_id"]
        command = Command(type="decision", choice_id=choice_id, ...)
        command_router.route(prompt["session_id"], command)
```

이것이 현재 `_LoopbackExternalAiTransport`를 대체한다. 훨씬 단순하다.

---

## 6. Prompt Timeout Worker

현재 구조는 유지하되 wakeup 방식을 변경한다.

```python
class PromptTimeoutWorker:
    async def run(self):
        while True:
            expired = await prompt_service.get_expired_prompts()
            for prompt in expired:
                if prompt.is_batch:
                    # batch default policy 적용
                    batch = redis.load_batch(prompt.batch_id)
                    batch.apply_default_for_missing()
                    command = Command(type="batch_complete", ...)
                else:
                    # 단일 프롬프트 default choice
                    choice_id = prompt.default_choice()
                    command = Command(type="decision", choice_id=choice_id, ...)

                command_router.route(prompt.session_id, command)

            await asyncio.sleep(TIMEOUT_WORKER_INTERVAL_SEC)
```

현재처럼 `execute_prompt_fallback` → `RuntimeService`로 우회하지 않는다.  
Timeout worker가 직접 command를 만들어 command_router에 넘긴다.

---

## 7. Prompt ID 결정성

### 7.1 현재 문제

`DecisionGateway._request_seq`가 매 engine 실행마다 0에서 시작하고, UUID를 포함한 request_id를 생성한다. 재시작 후 같은 prompt position에서 다른 request_id가 생성된다. 이를 보정하는 `_runtime_prompt_sequence_seed` 로직이 복잡하다.

### 7.2 새 방식

request_id를 결정론적으로 생성한다.

```
request_id = f"{session_id}:{round}:{turn}:{player_id}:{request_type}:{instance_seq}"
```

`instance_seq`는 같은 (session, round, turn, player, request_type) 조합에서 몇 번째 프롬프트인지다. checkpoint에 마지막 `instance_seq`를 저장해 재시작 후 이어받는다.

이것이 현재 `_stable_prompt_request_id`의 의도다. 이것을 fallback이 아닌 기본 방식으로 올린다.

```python
def next_request_id(state, request_type, player_id):
    instance_seq = state.increment_prompt_instance(request_type, player_id)
    return f"{session_id}:{state.round}:{state.turn}:{player_id}:{request_type}:{instance_seq}"
```

UUID를 제거하면 `_runtime_prompt_sequence_seed`, `_request_prompt_instance_id`, `_prior_same_module_resume_prompt_seed` 세 함수가 불필요해진다.

---

## 8. DecisionGateway 처리

현재 2282줄. 역할을 분리한다.

| 현재 DecisionGateway 기능 | 이동 위치 |
|---|---|
| `resolve_human_prompt` — blocking wait | 제거 (non-blocking만 유지) |
| `resolve_human_prompt` — non-blocking PromptRequired | `PromptBoundary` 단순 클래스로 |
| `resolve_ai_decision` | `AiNotificationService`로 이동 |
| request_id 생성 (`next_request_id`) | `PromptBoundary`로 |
| legal_choices 빌더들 (`_build_*_context`) | `PromptContextBuilder`로 분리 |
| prompt publish (`self.publish`) | Session Loop 내부로 |
| `PromptRequired`, `PromptFingerprintMismatch` | 유지 (engine-loop 인터페이스) |

결과적으로 DecisionGateway는 engine이 prompt를 요청할 때 engine↔PromptService 인터페이스 역할만 하는 얇은 클래스가 된다.

---

## 9. WebSocket Handler 전체 명세

```python
@router.websocket("/{session_id}/stream")
async def stream_ws(websocket, session_id):
    viewer = authenticate(websocket, session_id)
    queue = asyncio.Queue()
    pubsub.subscribe(session_id, queue)

    # 접속 즉시 최신 view_commit 전송
    latest = redis.load_view_commit(session_id, viewer)
    if latest:
        await ws.send(latest)

    stop = asyncio.Event()
    asyncio.create_task(outbound_sender(websocket, session_id, viewer, queue, stop))
    asyncio.create_task(heartbeat(websocket, stop))

    try:
        async for message in websocket.iter_json():
            await handle_inbound(websocket, session_id, viewer, message)
    except WebSocketDisconnect:
        pass
    finally:
        stop.set()
        pubsub.unsubscribe(session_id, queue)


async def handle_inbound(ws, session_id, viewer, message):
    msg_type = message.get("type")

    if msg_type == "decision":
        await handle_decision(ws, session_id, viewer, message)

    elif msg_type == "resume":
        # 클라이언트가 last_commit_seq 이후 view_commit 재요청
        last_seq = message.get("last_commit_seq", 0)
        commit = redis.load_view_commit(session_id, viewer)
        if commit and commit["commit_seq"] > last_seq:
            await ws.send(commit)


async def handle_decision(ws, session_id, viewer, message):
    # 1. PromptService로 검증
    result = validate_decision(session_id, message)

    # 2. accepted이면 Redis atomic write + command routing
    if result.status == "accepted":
        command = build_command(message)
        await redis.accept_decision(session_id, message)
        command_router.route(session_id, command)

    # 3. 즉시 ack 전송
    await ws.send(build_decision_ack(result))


async def outbound_sender(ws, session_id, viewer, queue, stop):
    last_sent_seq = 0
    while not stop.is_set():
        try:
            signal = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        commit = redis.load_view_commit(session_id, viewer)
        if commit and commit["commit_seq"] > last_sent_seq:
            await ws.send(commit)
            last_sent_seq = commit["commit_seq"]


async def heartbeat(ws, stop):
    while not stop.is_set():
        await ws.send({"type": "heartbeat", "server_time_ms": now_ms()})
        await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL_SEC)
```

총 ~80줄. 현재 1095줄에서 93% 감소.

---

## 10. 전체 구성 요소 목록

| 구성 요소 | 역할 | 현재 대응 |
|---|---|---|
| `SessionLoopManager` | 세션별 loop 생성/종료 | `RuntimeService.start_runtime` 일부 |
| `SessionLoop` | 단일 command 처리, engine 실행, Redis commit | `RuntimeService._run_engine_command_boundary_loop_sync` |
| `CommandRouter` | decision → local queue 또는 Redis stream | 없음 (분산) |
| `CommandWatcher` | Redis stream → local queue (cross-process only) | `CommandStreamWakeupWorker` (단순화) |
| `BatchCollector` | 동시 배치 응답 수집, 완료 감지 | `SimultaneousCommitModule` 일부 |
| `PromptBoundary` | engine↔PromptService 인터페이스, request_id 생성 | `DecisionGateway` (단순화) |
| `PromptContextBuilder` | legal_choices, public_context 빌드 | `DecisionGateway._build_*` 함수군 |
| `AiNotificationService` | prompt → external AI HTTP 알림 | `_ExternalAiWorkerClient` (분리) |
| `PromptTimeoutWorker` | 만료 → timeout command 생성 | `PromptTimeoutWorker` (wakeup 방식 변경) |
| `WsHandler` | inbound 검증/routing, outbound 전송, heartbeat | `stream.py` (대폭 단순화) |
| `PromptService` | pending/resolved 관리 | 유지 |
| `RedisGameStateStore` | state/checkpoint/view_commit | 유지 |
| `Engine` | 게임 룰 실행 | 유지 (변경 없음) |

---

## 11. 제거 목록 (전체)

| 제거 대상 | 이유 |
|---|---|
| `CommandStreamWakeupWorker` | `CommandWatcher`로 대체 (훨씬 단순) |
| `_RUNTIME_WAKEUP_TASKS` 모듈 전역 | SessionLoop가 내재적으로 중복 방지 |
| `_CommandBoundaryGameStateStore` | SessionLoop 구조로 대체 |
| `_repair_missing_pending_prompt_from_view_commit` | PromptService가 단일 진실 |
| `_decision_view_commit_rejection_reason` | validate_decision으로 대체 |
| heartbeat view_commit repair | heartbeat = ping만 |
| `blocking_human_prompts=True` 경로 | non-blocking만 유지 |
| `_ExternalAiTransport` 클래스군 (runtime_service 내) | AiNotificationService로 분리 |
| `_request_seq` + UUID request_id | 결정론적 ID로 교체 |
| `_runtime_prompt_sequence_seed` | 결정론적 ID로 불필요 |
| `_request_prompt_instance_id` | 위 동일 |
| `_prior_same_module_resume_prompt_seed` | 위 동일 |
| `_reprocessed_consumed_commands` set | CommandWatcher offset으로 처리 |
| `PYTEST_CURRENT_TEST` 환경변수 체크 | config로 대체 |
| `module_identity_mismatch` 중복 구현 | 하나로 통합 |

---

## 12. 완료 기준 (전체)

**레이어 경계:**
- engine이 WebSocket, Redis, PromptService를 import하지 않는다
- WsHandler가 engine 타입을 import하지 않는다
- SessionLoop가 WebSocket 타입을 import하지 않는다

**단일 경로:**
- decision → engine 경로가 하나다 (`command_router → session_queue → session_loop`)
- heartbeat 코드에 view_commit 로드가 없다

**검증 단순화:**
- decision 검증이 `PromptService.get_pending_prompt` 하나로 끝난다
- view_commit은 검증에 사용되지 않는다

**동시성 안전:**
- 같은 session_id의 engine 실행이 동시에 둘 이상 일어나지 않는다 (Redis lease)
- batch prompt는 모든 required 응답 없이 커밋되지 않는다

**결정론적 복구:**
- 같은 checkpoint에서 engine을 재실행하면 같은 request_id가 생성된다
- 서버 재시작 후 pending command가 있으면 session loop가 자동 재개된다

**코드 크기 (목표):**
- `stream.py`: ~100줄
- `runtime_service.py`: ~800줄 (현재 5649줄)
- `command_wakeup_worker.py`: 제거
- `decision_gateway.py`: ~400줄 (현재 2282줄)
