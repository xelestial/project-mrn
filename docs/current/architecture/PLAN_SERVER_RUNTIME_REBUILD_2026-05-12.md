# 서버 런타임 재건 계획

Status: ACTIVE
Date: 2026-05-12
Owner: Server runtime
Basis:

- `docs/current/architecture/AUDIT_CURRENT_GAME_SERVER_STRUCTURE_2026-05-12.md`
- `docs/current/architecture/CLAUDE-PROPOSAL_SERVER_STRUCTURE_DIAGNOSIS_2026-05-12.md`
- `docs/current/architecture/CLAUDE-PROPOSAL_SERVER_STRUCTURE_ADDENDUM_2026-05-12.md`
- `docs/current/architecture/CLAUDE-PROPOSAL_SERVER_REDESIGN_FULL_2026-05-12.md`
- `docs/current/engineering/LESSONS_REDIS_RUNTIME_UI_PLAYTEST.md`

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to execute this plan step by step.

## 1. 판단

현재 서버 문제는 성능 튜닝 문제가 아니다. 구조 문제다.

확인된 결함은 `RuntimeService`, WebSocket route, Redis persistence, prompt lifecycle, command wakeup worker가 서로의 책임을 대신 메우는 방식으로 누적된 것이다. 이 상태에서 `view_commit` 수리, heartbeat 조건 분기, worker 재스캔 제한, 테스트 전용 delay override 같은 국소 패치를 계속 넣으면 증상은 줄 수 있지만 권위 경계는 더 흐려진다.

따라서 이 계획의 목표는 "현 구현을 조금 더 안정화"가 아니다. 목표는 아래 4개 경계를 다시 세우는 것이다.

1. 입력 경계: 모든 human, AI, timeout decision은 동일한 command 경로로 들어간다.
2. 실행 경계: 세션당 동시에 하나의 writer만 엔진을 실행하고 Redis에 commit한다.
3. 저장 경계: accepted command와 state transition은 먼저 Redis에 내구적으로 기록된다.
4. 표시 경계: `view_commit`과 heartbeat는 읽기 모델이며 decision 검증이나 prompt 복구에 쓰지 않는다.

## 2. 버릴 것

Claude 재설계안에서 아래 항목은 채택하지 않는다.

### 2.1 단일 프로세스 direct queue 우선 처리

`session_command_queue`에 먼저 push하고 Redis stream은 다중 프로세스 보조 신호로만 쓰는 구조는 버린다.

이유:

- accepted command가 local queue 안에만 있으면 프로세스 crash 시 입력이 사라진다.
- 단일 프로세스와 다중 프로세스의 의미가 달라져 테스트 통과 조건이 배포 조건을 대표하지 못한다.
- 현재 문제의 핵심은 wakeup 지연이 아니라 권위 기록과 실행 경계가 섞인 것이다.

채택할 대체 원칙:

모든 accepted command는 먼저 Redis durable command inbox에 append된다. local queue, pub/sub, watcher는 모두 "깨우기 신호"일 뿐이며 source of truth가 아니다.

### 2.2 pub/sub만으로 outbound 전달 보장

`Redis commit -> pubsub.publish -> WS outbound sender`만으로 전달을 끝내는 설계는 버린다.

이유:

- pub/sub은 놓친 메시지를 복구하지 않는다.
- WebSocket reconnect, server restart, browser sleep 후에는 latest state 재동기화 경로가 별도로 필요하다.
- 현재 frontend/protocol gate는 reconnect와 view recovery를 이미 중요한 검증 대상으로 둔다.

채택할 대체 원칙:

pub/sub은 새 commit 알림이다. 클라이언트가 놓친 commit은 명시적 resume fetch 또는 viewer outbox로 복구한다.

### 2.3 batch response 수집과 completion 판단 분리

`record_response()` 후 `check_complete()`로 batch 완료를 따로 판단하는 구조는 버린다.

이유:

- 동시 응답이 들어오면 두 handler가 모두 완료를 관측하고 `batch_complete` command를 중복 생성할 수 있다.
- timeout worker와 human response가 교차하면 기본 응답과 실제 응답이 같은 batch를 동시에 닫을 수 있다.

채택할 대체 원칙:

batch response 저장, remaining count 감소, completion command 생성 여부 판단은 Redis Lua 또는 동등한 atomic primitive 하나에서 끝낸다.

### 2.4 단순 deterministic request id

`session_id + player_id + action_type + round + turn` 수준의 prompt id는 버린다.

이유:

- 같은 round/turn 안에서 동일 player에게 같은 request type이 여러 번 뜰 수 있다.
- module frame, nested prompt, simultaneous frame, timeout retry, recovery replay를 구분하지 못한다.
- `_request_seq` 같은 process-local counter만 바꾸면 restart/replay 안정성이 없다.

채택할 대체 원칙:

prompt identity는 engine boundary identity에서 만든다. 최소 구성은 `session_id`, `checkpoint_epoch` 또는 `commit_seq`, `frame_id`, `module_id`, `module_cursor`, `player_id`, `request_type`, `prompt_instance_id`, optional `batch_id`다.

### 2.5 RuntimeService를 계속 확장하는 방식

`RuntimeService`를 유지한 채 새 helper를 계속 붙이는 방식은 버린다.

이유:

- 현재 `RuntimeService`는 엔진 실행, checkpoint, lease, prompt continuation, view projection, command boundary, AI transport fallback까지 끌어안고 있다.
- 모듈 하나를 고칠 때 decision route, worker, heartbeat, projection test가 같이 깨지는 구조가 이미 확인됐다.

채택할 대체 원칙:

`RuntimeService`는 phase 중간의 compatibility facade로만 남기고, 최종적으로 `SessionLoop`, `CommandInbox`, `PromptBoundary`, `ViewProjector`, `SessionLoopManager`로 책임을 분리한다.

## 3. 채택할 것

Claude 재설계안에서 아래 방향은 채택한다.

1. 모든 decision 입력을 단일 command router로 수렴한다.
2. 세션마다 하나의 session loop가 엔진 실행을 소유한다.
3. Redis lease로 single writer를 강제한다.
4. engine 실행은 다음 external boundary까지만 진행한다.
5. AI decision, human decision, timeout default decision을 같은 command type으로 처리한다.
6. heartbeat는 상태 조회와 복구를 대신하지 않는다.
7. `view_commit`은 frontend/read model이며 pending prompt 검증 자료가 아니다.
8. `CommandStreamWakeupWorker`는 현재 형태로 유지하지 않고 더 작은 wakeup/recovery 역할로 축소하거나 제거한다.

## 4. 목표 아키텍처

### 4.1 입력 흐름

```text
Human WS decision
External AI callback
Prompt timeout worker
        |
        v
Decision intake validation
        |
        v
CommandInbox.accept(command)  # Redis durable append, idempotency, seq assignment
        |
        v
CommandRouter.wake(session_id)  # local queue/pubsub/watcher signal only
        |
        v
SessionLoop drains CommandInbox from Redis
```

핵심 조건:

- handler가 local queue에 command를 직접 넣기 전에 반드시 Redis append가 성공해야 한다.
- Redis append가 실패하면 decision은 accepted가 아니다.
- local wakeup 실패는 복구 가능해야 한다. 다음 poll, pub/sub, reconnect, loop restart가 Redis inbox를 다시 읽는다.

### 4.2 실행 흐름

```text
SessionLoopManager
        |
        v
SessionLoop.acquire_lease(session_id)
        |
        v
load checkpoint
        |
        v
drain next durable command
        |
        v
engine.run_to_next_boundary()
        |
        v
atomic commit checkpoint + view_commit + prompt state + command terminal state
        |
        v
publish lightweight commit signal
```

핵심 조건:

- 세션 loop만 엔진을 실행한다.
- decision route, prompt timeout worker, external AI worker는 엔진을 실행하지 않는다.
- commit 전 lease를 검증한다.
- command terminal state는 `accepted`, `processing`, `committed`, `rejected`, `superseded`, `expired` 중 하나로 명확히 남긴다.

### 4.3 출력 흐름

```text
Redis commit
        |
        v
commit signal
        |
        +--> active WS sender fetches new view_commit
        +--> reconnect/resume fetches latest view_commit or viewer outbox
        +--> AI worker polls or receives prompt-specific notification
```

핵심 조건:

- heartbeat는 `type=heartbeat`, connection metadata, optional latest known seq 정도만 보낸다.
- heartbeat에서 `view_commit`을 읽어 decision route를 보정하지 않는다.
- `view_commit` 누락은 viewer recovery 문제로 처리한다. pending prompt 누락을 view model에서 재생성하지 않는다.

## 5. 새 책임 경계

### 5.1 `CommandInbox`

새 파일 후보:

- `apps/server/src/services/command_inbox.py`
- `apps/server/tests/test_command_inbox.py`

책임:

- command idempotency key 검증
- accepted command Redis append
- monotonic sequence 부여
- command state transition 기록
- pending command drain API 제공
- batch completion command의 중복 생성 방지 primitive 제공

금지:

- engine 실행
- WebSocket 송신
- view projection 생성

### 5.2 `CommandRouter`

새 파일 후보:

- `apps/server/src/services/command_router.py`
- `apps/server/tests/test_command_router.py`

책임:

- already accepted command에 대한 wake signal 발송
- current process owner가 있으면 local queue wake
- owner가 없거나 다른 process면 Redis signal 또는 poll recovery가 보도록 표시

금지:

- Redis durable append 없이 local queue에 command 삽입
- prompt pending state를 view_commit에서 복구

### 5.3 `SessionLoop`와 `SessionLoopManager`

새 파일 후보:

- `apps/server/src/services/session_loop.py`
- `apps/server/src/services/session_loop_manager.py`
- `apps/server/tests/test_session_loop.py`

책임:

- Redis lease 획득/갱신/반납
- checkpoint load
- durable command drain
- engine boundary execution
- atomic state/prompt/view/command commit
- idle 종료와 restart recovery

금지:

- HTTP/WS token 검증
- AI provider 호출
- frontend payload formatting

### 5.4 `PromptBoundary`

새 파일 후보:

- `apps/server/src/services/prompt_boundary.py`
- `apps/server/tests/test_prompt_boundary.py`

책임:

- engine prompt boundary를 pending prompt record로 변환
- deterministic prompt identity 생성
- prompt pending/resolved/expired state transition
- batch prompt participant state 관리

금지:

- `view_commit` 기반 prompt 수리
- process-local counter를 단독 identity source로 사용

### 5.5 `ViewProjector`

새 파일 후보:

- `apps/server/src/services/view_projector.py`
- `apps/server/tests/test_view_projector.py`

책임:

- authoritative checkpoint를 player/spectator view로 projection
- latest view commit 저장
- optional viewer outbox materialization

금지:

- command accept/reject 판단
- prompt pending 여부 판단

## 6. 단계별 실행 계획

### Phase 0 - 계약 테스트부터 고정

목표: 현재 나쁜 결합이 다시 들어오지 못하게 먼저 실패 조건을 명문화한다.

작업:

- [x] `apps/server/tests/test_runtime_rebuild_contract.py` 추가
- [x] decision validation이 `view_commit` 존재 여부에 의존하지 않는다는 테스트 추가
- [x] missing pending prompt를 `view_commit`에서 repair하지 않는다는 테스트 추가
- [x] accepted command는 local wakeup 전에 Redis durable record가 존재해야 한다는 테스트 추가
- [x] heartbeat가 `view_commit`을 읽거나 prompt repair를 트리거하지 않는다는 테스트 추가

검증:

- [x] `./.venv/bin/python -m pytest apps/server/tests/test_runtime_rebuild_contract.py -q`

완료 조건:

- 기존 구현에서는 최소 하나 이상 실패해야 한다.
- 이후 phase들은 이 테스트를 통과시키는 방향으로만 진행한다.

2026-05-12 구현 상태:

- 완료: `view_commit` 기반 decision reject, pending prompt repair, heartbeat snapshot repair 재진입을 제거했다.
- 완료: `CommandInbox` 계약 테스트로 accepted command reference가 durable append 이후에만 반환된다는 조건을 고정했다.

### Phase 1 - Durable Command Inbox 도입

목표: command acceptance와 wakeup을 분리한다.

작업:

- [x] `CommandInbox.accept()` 구현
- [x] Redis Lua 또는 transaction으로 append, idempotency, seq assignment를 한 경계로 묶는다.
- [x] `RedisCommandStore`의 non-Lua fallback을 production path에서 제거하거나 fail-closed로 바꾼다.
- [x] command state enum과 terminal state를 명시한다.
- [x] 기존 decision route는 아직 `RuntimeService`를 호출하더라도 command accept는 `CommandInbox`를 통과하게 한다.

수정 후보:

- `apps/server/src/services/realtime_persistence.py`
- `apps/server/src/services/command_inbox.py`
- `apps/server/src/routes/stream.py`
- `apps/server/tests/test_redis_realtime_services.py`
- `apps/server/tests/test_command_inbox.py`

검증:

- [x] duplicate decision id가 두 번 처리되지 않는다.
- [x] Redis append 실패 시 handler는 accepted ack를 반환하지 않는다.
- [x] command seq가 session 단위로 monotonic이다.

2026-05-12 구현 상태:

- 완료: `apps/server/src/services/command_inbox.py`를 추가하고 `PromptService.submit_decision()` 및 timeout fallback command append를 `CommandInbox` 경유로 바꿨다.
- 완료: 기존 Redis atomic prompt accept는 유지하되 호출 경계를 `CommandInbox.accept_prompt_decision()`으로 올렸다.
- 완료: `RedisCommandStore`가 command state hash를 기록한다. append/atomic prompt accept 시 `accepted`, runtime lease 확보 후 `processing`, Redis transition commit 후 `committed`, checkpoint 검증 실패로 소비 offset을 넘길 때 `rejected`를 남긴다.
- 완료: `apps/server/src/domain/command_state.py`에 `CommandState`와 terminal state set을 추가했고, Redis state 기록 경로는 알 수 없는 상태 문자열을 거부한다.
- 완료: non-atomic prompt fallback에서도 command append가 실패하면 accepted ack를 반환하지 않고 pending prompt를 유지한다.
- 완료: 기본 Redis client에서 Lua atomic path가 없으면 `redis_lua_required`로 fail-closed한다. 명시적 test double/client factory만 fallback 경로를 사용할 수 있다.
- 완료: stale decision command는 prompt lifecycle을 근거로 `superseded` 또는 `expired` terminal state를 기록한다.
- 완료: duplicate request id는 기존 command를 재처리하지 않고 `None`을 반환하며, 이 실패는 session command seq를 소비하지 않는 테스트로 고정했다.
- 완료: command seq는 session별로 독립적인 monotonic counter라는 테스트를 추가했다.
- 당시 남은 작업(이후 완료): 실제 session loop 분리와 inbox drain API는 Phase 2/3/7 경계에서 이어서 구현해야 했다.

### Phase 2 - Router를 wake signal 전용으로 축소

목표: queue가 source of truth가 되는 경로를 없앤다.

작업:

- [x] `CommandRouter` 추가
- [x] route 입력 타입을 "accepted command reference"로 제한한다.
- [x] local queue push는 wake signal로만 사용한다.
- [x] remote owner 또는 owner unknown이면 Redis poll recovery로 깨운다.
- [x] route 실패가 command loss가 되지 않도록 기존 command stream recovery worker를 유지한다.

수정 후보:

- `apps/server/src/services/command_router.py`
- `apps/server/src/state.py`
- `apps/server/src/routes/stream.py`
- `apps/server/src/services/command_wakeup_worker.py`

검증:

- [x] local wakeup이 누락되어도 SessionLoop가 Redis inbox에서 command를 다시 발견한다.
- [x] cross-process 수신 command가 current process memory queue에 의존하지 않는다.

2026-05-12 구현 상태:

- 완료: `apps/server/src/services/command_router.py`를 추가했다. 이 서비스는 command를 accept하지 않고, 이미 durable append된 `accepted` command reference만 wakeup 대상으로 받는다.
- 완료: WebSocket decision route와 stream reconnect recovery는 직접 `RuntimeService.process_command_once()`를 호출하지 않고 `CommandRouter`를 통해 wake signal만 보낸다.
- 완료: 같은 session/command seq wakeup은 process-local task map으로 dedupe한다. 처리 중인 runtime이 있으면 `running_elsewhere` 결과에 대해 제한 시간 안에서 재시도한다.
- 완료: `CommandStreamWakeupWorker`가 Redis inbox에서 pending command를 발견하면 runtime을 직접 실행하지 않고 `SessionLoopManager`로 handoff할 수 있다.
- 완료: 이 handoff 경로는 current process memory queue 없이 Redis command store와 consumer offset만 본다.
- 선택: 별도 remote owner/pubsub signal은 채택하지 않았다. 다중 프로세스 복구는 polling worker가 source of truth인 Redis inbox를 다시 읽는 방식으로 보장한다.
- 검증: `apps/server/tests/test_command_wakeup_worker.py`의 cross-process/wakeup handoff 테스트와 `apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_command_wakeup_restart_resumes_queued_purchase_prompt_from_redis`가 process-local memory queue 없이 Redis command store와 consumer offset만으로 pending command를 회복하는 계약을 고정한다.

### Phase 3 - SessionLoop single writer 도입

목표: 엔진 실행과 commit을 세션 loop 하나로 수렴한다.

작업:

- [x] `SessionLoop` 구현
- [x] `SessionLoopManager` 구현
- [x] 세션 시작 시 loop start 또는 lazy wake start 정책 결정
- [x] loop가 Redis lease를 획득한 뒤에만 engine을 실행하게 한다.
- [x] loop가 command inbox를 seq 순서로 drain한다.
- [x] engine 결과 commit과 command terminal state update를 같은 경계에서 수행한다.
- [x] bounded drain 완료 시 lease를 반납하고 loop task를 종료한다.
- [x] restart 시 in-progress session의 pending command를 찾아 loop를 재시작한다.

수정 후보:

- `apps/server/src/services/session_loop.py`
- `apps/server/src/services/session_loop_manager.py`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/state.py`
- `apps/server/src/routes/sessions.py`

검증:

- [x] 같은 session에 대해 두 loop가 동시에 commit하지 않는다.
- [x] lease lost 상태에서는 commit하지 않는다.
- [x] process restart 후 pending accepted command가 사라지지 않는다.

2026-05-12 구현 상태:

- 완료: `apps/server/src/services/session_loop.py`를 추가했다. 이 loop는 Redis command inbox를 consumer offset 이후 seq 순서로 읽고, `decision_submitted` command만 runtime 실행 경계로 넘긴다. `decision_resolved`는 관측 command라 consumer offset만 전진한다.
- 완료: `apps/server/src/services/session_loop_manager.py`를 추가했다. manager는 session id별로 하나의 drain task만 예약하고, 같은 session에 대한 중복 wakeup은 dedupe한다.
- 완료: `CommandRouter`가 `SessionLoopManager`를 받을 수 있게 바꿨고, 실제 server state에서는 router와 `CommandStreamWakeupWorker` 모두 manager로 위임한다.
- 완료: manager 위임 후에도 기존 router의 `running_elsewhere` 재시도 의미가 사라지지 않도록 `deferred` drain 결과를 제한 시간 안에서 재시도한다.
- 완료: loop는 `SessionCommandExecutor`를 통해 command lifecycle control flow를 직접 조립한다. runtime boundary는 Redis lease, command `processing` mark, engine boundary 실행, runtime status/result 적용 같은 저수준 동작을 제공하고, `RuntimeService.process_command_once()`는 같은 executor를 호출하는 호환 wrapper로만 남았다.
- 완료: `consumer_name="runtime_wakeup"`을 유지했다. 새 consumer를 만들면 기존 worker offset과 갈라져 같은 command를 두 실행 경로가 다시 보게 되므로, 전환 중에는 같은 offset을 공유하는 것이 맞다.
- 완료: restart/poll recovery는 기존 `CommandStreamWakeupWorker`가 pending command를 발견한 뒤 manager를 깨우는 형태로 수렴시켰다.
- 완료: `CommandStreamWakeupWorker`가 runtime 처리를 비활성화한 경우에는 pending command를 소비한 것처럼 `runtime_wakeup` offset을 전진시키지 않는다. 비활성 worker가 offset만 저장하면 나중에 manager가 같은 accepted command를 보지 못하므로 command loss가 된다.
- 완료: `SessionLoopManager`는 한 drain이 `yielded`로 끝나도 task를 종료하지 않는다. `max_commands_per_wakeup` 예산을 소진한 동안 들어온 중복 wakeup은 dedupe되므로, yielded를 terminal로 보면 뒤에 남은 durable command가 다음 poll까지 처리되지 않거나 조건에 따라 멈춘다. manager는 이제 `yielded`를 같은 task 안에서 즉시 재-drain한다.
- 완료: loop start 정책은 lazy wake start로 결정했다. session start는 long-lived loop를 만들지 않고, durable accepted command가 생긴 뒤 `CommandRouter` 또는 `CommandStreamWakeupWorker`가 `SessionLoopManager`를 깨운다.
- 완료: SessionLoop는 idle daemon이 아니라 bounded drain task다. `SessionCommandExecutor`는 command마다 Redis lease를 얻고 `finally`에서 lease renewer stop, lease release, process-local processing flag release를 수행한다. manager task는 Redis inbox가 idle이면 종료되고 task map에서 제거된다.
- 완료: process restart 후 pending accepted command 보존은 Redis inbox와 wakeup worker polling으로 처리한다. 단위 테스트는 `test_command_wakeup_restart_resumes_queued_purchase_prompt_from_redis`가, 실서버 smoke는 `tmp/rl/full-stack-protocol/server-rebuild-1game-prompt-probe-fix-20260513` 및 restart/duplicate smoke가 검증했다.
- 검증: 5개 서버와 1개 Redis 조건에서 `tmp/rl/full-stack-protocol/server-rebuild-5server-1redis-yieldfix-20260512` protocol gate가 통과했다.
- 병목 증거: 1개 서버에 20개 게임을 동시에 붙인 조건은 `tmp/rl/full-stack-protocol/server-rebuild-1server-20game-yieldfix-20260512`에서 backend timing gate로 실패했다. 실패 원인은 Redis commit이나 ACK 누락이 아니라 `InitialRewardModule` engine transition wall time이다. 해당 run의 `runtime_transition_phase_timing` 125건 중 3건이 5000ms를 넘었고, 모두 `InitialRewardModule`이었다. 최대값은 `total_ms=6386`, `engine_transition_ms=6238`, `redis_commit_ms=53`, `view_commit_build_ms=11`이다.
- 판단: 이 결과는 command loss 결함은 수정됐지만 단일 Python server process에 20개 live session transition을 몰아넣으면 engine 실행 wall time이 gate 기준을 넘는다는 capacity/bottleneck 증거다. 5서버/1Redis는 통과하고 1서버/20게임만 실패했으므로 현 단계의 병목은 Redis 분리보다 서버 실행자 수와 engine transition scheduling에 더 가깝다.
- 당시 남은 작업(이후 완료): Phase 7의 HTTP external AI command-boundary 통합은 아직 남아 있었다. remote owner/pubsub wake signal은 현재 필수 설계가 아니므로 열린 작업에서 제외한다.

### Phase 4 - decision route에서 view_commit 의존 제거

목표: read model을 write validation에 쓰는 결함을 제거한다.

작업:

- [x] `apps/server/src/routes/stream.py`의 `_decision_view_commit_rejection_reason` 제거
- [x] `_repair_missing_pending_prompt_from_view_commit` 제거
- [x] decision validation은 `PromptService` 또는 `PromptBoundary`의 pending prompt record만 사용한다.
- [x] pending prompt가 없으면 reject한다. 복구는 checkpoint/prompt recovery path에서만 수행한다.
- [x] `view_commit` 기반 repair 테스트를 삭제하고 새 계약 테스트로 대체한다.

수정 후보:

- `apps/server/src/routes/stream.py`
- `apps/server/src/services/prompt_service.py`
- `apps/server/src/services/prompt_boundary.py`
- `apps/server/tests/test_view_commit_decision_contract.py`

검증:

- [x] 최신 `view_commit`이 있어도 pending prompt가 없으면 decision은 accept되지 않는다.
- [x] pending prompt가 있으면 `view_commit` stale 여부와 무관하게 command accept가 가능하다.

### Phase 5 - WebSocket outbound와 heartbeat 정리

목표: heartbeat, view recovery, prompt delivery의 책임을 분리한다.

작업:

- [x] heartbeat payload를 connection liveness 용도로 제한한다.
- [x] connect/resume 시 latest view commit fetch 경로를 명시한다.
- [x] missed pub/sub signal 복구를 위해 explicit latest fetch를 선택한다.
- [x] prompt delivery는 pending prompt 기준으로 재전송한다.
- [x] `view_commit` 전송 누락과 prompt pending 누락을 서로 다른 장애로 분류한다.

수정 후보:

- `apps/server/src/routes/stream.py`
- `apps/server/src/services/stream_service.py`
- `apps/server/src/services/realtime_persistence.py`
- `packages/runtime-contracts/ws/README.md`

검증:

- [x] heartbeat는 prompt repair를 호출하지 않는다.
- [x] reconnect한 client가 latest view를 회복한다.
- [x] reconnect한 client가 자신에게 열린 pending prompt를 회복한다.

2026-05-12 구현 상태:

- 완료: WebSocket connect는 subscriber 등록 후 latest `view_commit`을 직접 조회해 보낸다. resume도 `last_commit_seq`와 관계없이 repair 목적으로 latest `view_commit`을 force 전송한다.
- 완료: heartbeat는 latest `view_commit` 조회, prompt repair, timeout worker 실행을 하지 않는다. heartbeat는 liveness/diagnostic payload만 유지한다.
- 완료: `PromptService.list_pending_prompts()`를 추가했고, seat connect/resume 시 해당 player의 pending prompt를 authoritative prompt store에서 조회해 `prompt` 메시지로 재전송한다.
- 완료: spectator/admin viewer에는 pending prompt repair를 보내지 않는다. prompt visibility는 기존 stream projector를 통과한다.
- 완료: direct pending prompt repair로 보낸 request id는 connection-local set에 기록해, 같은 request id의 queued prompt event가 뒤늦게 도착해도 중복 송신하지 않는다.
- 선택: 아직 durable per-viewer outbox는 만들지 않았다. 현재 Phase 5 선택지는 `view_commit`은 explicit latest fetch, active prompt는 authoritative pending prompt repair다. full viewer outbox는 재접속 중 여러 transient event를 모두 복구해야 할 때 별도 phase로 다시 열어야 한다.

### Phase 6 - batch prompt collector 원자화

목표: simultaneous prompt completion의 중복 command 생성을 제거한다.

작업:

- [x] `BatchCollector` 추가
- [x] response record, remaining count update, completion decision을 Redis atomic primitive로 묶는다.
- [x] timeout default와 human response의 race를 처리한다.
- [x] batch completion command idempotency key를 `batch_id` 기준으로 고정한다.

수정 후보:

- `apps/server/src/services/batch_collector.py`
- `apps/server/src/services/prompt_timeout_worker.py`
- `apps/server/src/services/prompt_service.py`
- `apps/server/tests/test_batch_collector.py`

검증:

- [x] 마지막 두 응답이 동시에 들어와도 `batch_complete` command는 하나만 생긴다.
- [x] timeout과 user response가 교차해도 terminal state는 하나다.

2026-05-12 구현 상태:

- 완료: `apps/server/src/services/batch_collector.py`를 추가했다.
- 완료: production path는 Redis Lua 한 번으로 response `HSETNX`, remaining 계산, batch completion idempotency, command stream append, command state `accepted` 기록을 처리한다.
- 완료: 테스트 fake path는 같은 의미를 lock 기반 fallback으로 검증한다. 기본 Redis client에서 Lua가 없으면 fallback하지 않는다.

2026-05-13 구현 상태:

- 완료: `PromptService.submit_decision()`은 simultaneous batch prompt를 감지하면 개별 `decision_submitted` command를 append하지 않고 `BatchCollector.record_response()`로 응답을 넘긴다.
- 완료: `PromptService.record_timeout_fallback_decision()`도 simultaneous batch prompt에서는 같은 collector를 사용한다. 따라서 human response와 timeout fallback이 교차해도 batch completion 판단은 collector의 atomic primitive 한 곳에서 끝난다.
- 완료: incomplete batch response는 decision record만 accepted로 남기고 `command_seq=None`, `batch_status=pending`, `remaining_player_ids`를 반환한다. 이 상태에서는 runtime wakeup을 하지 않는다.
- 완료: 마지막 batch response가 들어온 경우에만 `batch_complete` command reference를 반환하고, `SessionLoop`는 `batch_complete`를 runtime boundary command로 처리한다.
- 완료: `RuntimeService`는 `batch_complete.responses_by_player_id`에서 선택된 primary response로 기존 prompt resume을 만들고, 나머지 collected response를 active batch state에 먼저 반영한 뒤 engine transition을 재개한다.

### Phase 7 - AI와 timeout을 같은 command 경로로 통합

목표: AI, timeout, human decision의 side path를 없앤다.

작업:

- [x] external AI callback handler가 `CommandInbox.accept()`를 사용하게 한다.
- [x] prompt timeout worker가 default decision command를 같은 방식으로 accept하게 한다.
- [x] HTTP external AI provider 호출은 session loop 밖에서 수행한다.
- [x] HTTP external AI transport는 AI를 기다리지 않고 pending prompt boundary에서 멈춘다.
- [x] HTTP external AI 결과는 다른 decision과 동일하게 command로 들어온다.

수정 후보:

- `apps/server/src/services/external_ai_worker_service.py`
- `apps/server/src/services/prompt_timeout_worker.py`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/routes/prompts.py`

검증:

- [x] non-batch human과 timeout decision은 같은 `decision_submitted` command append 경로를 사용한다.
- [x] simultaneous batch human과 timeout decision은 같은 `BatchCollector` completion 경로를 사용하고, 완료 시 하나의 `batch_complete` command로 session loop에 들어온다.
- [x] HTTP external AI decision의 persisted command shape가 human/timeout과 동일하다.
- [x] HTTP external AI endpoint 지연이 session loop lease를 장시간 점유하지 않는다.

2026-05-12 구현 상태:

- 완료: `PromptService.record_timeout_fallback_decision()`은 timeout fallback decision을 `CommandInbox.append_decision_command()`로 기록하고, 성공 시 accepted command reference를 반환한다.
- 완료: `PromptTimeoutWorker`는 timeout fallback command가 accepted된 뒤 `CommandRouter.wake_after_accept()`를 호출한다. 따라서 human decision과 timeout fallback 모두 durable command append 이후 wakeup된다.
- 2026-05-12 당시 의도적 미완료: external AI는 아직 동일 경계로 수렴하지 않았다. 당시 서버에는 AI callback handler가 없고, `apps/server/src/services/runtime_service.py`의 `_LocalAiDecisionClient`, `_LoopbackExternalAiTransport`, `_HttpExternalAiTransport`가 runtime 실행 중 `DecisionGateway.resolve_ai_decision()`으로 동기 resolve/publish했다.
- 2026-05-12 당시 근거: `apps/server/src/external_ai_app.py`의 `/decide`는 게임 서버가 AI 결과를 받는 callback이 아니라 외부 AI worker 프로세스가 요청을 받아 choice를 반환하는 endpoint였다. 게임 서버 쪽 `_HttpExternalAiTransport.resolve()`는 이 worker를 호출한 뒤 같은 runtime call stack 안에서 `DecisionGateway.resolve_ai_decision()`으로 결정 이벤트를 publish했다.
- 2026-05-12 당시 채택하지 않은 수정: `_HttpExternalAiTransport.resolve()`나 worker response 처리 직후 `CommandInbox.accept()`를 끼워 넣지 않았다. 그렇게 하면 당시 동기 결정 publish는 그대로 남고 command stream에도 같은 결정이 추가되어, 하나의 AI 선택에 대해 두 authoritative path가 생겼다.
- 2026-05-12 당시 판단: 이 상태에서 AI 결과만 `CommandInbox`에 append하면 runtime이 prompt boundary에서 멈추는 구조가 없어서 "동기 AI 실행 + command 재입력" 이중 경로가 된다. AI까지 수렴하려면 Phase 3 `SessionLoop`가 먼저 pending AI prompt boundary에서 멈추고, 외부 worker 결과가 나중에 같은 decision command로 재진입해야 했다.

2026-05-13 구현 상태:

- 완료: HTTP external AI transport는 더 이상 session loop call stack 안에서 worker sender/healthchecker를 호출하지 않는다. 대신 `DecisionGateway.resolve_external_ai_prompt()`로 provider=`ai` pending prompt를 생성하고 `PromptRequired` boundary에서 멈춘다.
- 완료: 외부 AI 결과 수신용 callback route `POST /api/v1/sessions/{session_id}/external-ai/decisions`를 추가했다. 이 route는 `PromptService.submit_decision()`을 호출하고, 내부적으로 `CommandInbox.accept_prompt_decision()`을 통해 human decision과 같은 `decision_submitted` command shape를 append한다.
- 완료: callback accept 이후에는 `CommandRouter.wake_after_accept()`로 session loop를 깨운다. wakeup은 local 실행 신호일 뿐이며 durable authority는 Redis command inbox에 남는다.
- 완료: AI provider metadata는 pending prompt, submitted decision payload, persisted command payload, decision resume, stream decision ack에 provider=`ai`로 보존된다.
- 완료: 기존 runtime-service HTTP transport 테스트 중 "session loop가 worker를 직접 호출하고 실패 시 local AI로 fallback한다"를 계약으로 삼던 테스트는 제거했다. 이 동작은 새 구조에서 금지 대상이다. worker 자체 API와 healthcheck/auth helper 검증은 별도 테스트로 유지한다.
- 범위 제한: `_LocalAiDecisionClient`와 `_LoopbackExternalAiTransport`는 이번 변경 범위가 아니다. 이들은 local/loopback test profile의 동기 AI 경로로 남아 있으며, HTTP external AI 운영 경로만 command-boundary 재진입으로 수렴했다.

### Phase 8 - prompt identity 재정의

목표: restart/replay/simultaneous frame에서 prompt id가 흔들리지 않게 한다.

작업:

- [x] `PromptBoundaryId` 또는 `protocol_ids.py` 추가
- [x] identity 구성 요소를 engine boundary에서 가져온다.
- [x] process-local `_request_seq` fallback을 제거한다.
- [x] deterministic id collision test를 추가한다.
- [x] old id shape와 호환이 필요한 외부 payload는 adapter를 둔다.

수정 후보:

- `apps/server/src/services/decision_gateway.py`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/prompt_boundary.py`
- `engine/runtime_modules/runner.py`
- `packages/runtime-contracts/`

검증:

- [x] 같은 round/turn/player/request_type 안의 복수 prompt가 서로 다른 id를 가진다.
- [x] restart 후 같은 boundary replay가 같은 id를 만든다.
- [x] 다른 module frame의 prompt가 충돌하지 않는다.

2026-05-12 구현 상태:

- 완료: `apps/server/src/domain/protocol_ids.py`에 `stable_prompt_request_id()`와 `legacy_prompt_request_id()`를 추가했다.
- 완료: `DecisionGateway._stable_prompt_request_id()`는 더 이상 round/turn-only 문자열을 직접 만들지 않고 shared protocol id helper를 호출한다.
- 완료: `_LocalHumanDecisionClient._attach_active_module_continuation()`은 module prompt의 `frame_id`, `module_id`, `module_cursor`, `runtime_module`을 request id 생성 전에 envelope에 넣는다.
- 완료: boundary id는 `frame_id`, `module_id`, `module_cursor`, optional `batch_id`, `player_id`, `request_type`, `prompt_instance_id`를 포함한다. 따라서 같은 round/turn/player/request_type이라도 module boundary가 다르면 충돌하지 않는다.
- 완료: boundary 없는 prompt는 기존 `session:rX:tY:pZ:type:N` 형식을 유지한다. 이것이 old id shape adapter다.
- 완료: `DecisionGateway`의 process-local request id retry fallback을 제거했다. blocking human prompt가 같은 deterministic `request_id`의 pending prompt를 다시 만나면 새 id를 만들지 않고 기존 prompt payload를 publish/wait 대상으로 재사용한다.
- 완료: `DecisionGateway.resolve_ai_decision()`은 process-local counter/random id를 쓰지 않고 request type, player id, public context fingerprint로 stable protocol id를 만든다. 이 값은 AI 이벤트 상관관계용 id이다. 당시 외부 AI callback 분리는 Phase 7의 남은 작업이었고, HTTP external AI path는 2026-05-13에 provider=`ai` pending prompt와 callback command boundary로 분리됐다.
- 완료: runtime recovery prompt sequence seed 계산은 `apps/server/src/domain/prompt_sequence.py`로 이동했다.
- 완료: 서버 `_LocalHumanDecisionClient`는 더 이상 engine `HumanHttpPolicy._prompt_seq` private field를 prompt sequence source로 읽거나 쓰지 않는다. 서버 adapter가 checkpoint seed에서 이어받은 `_prompt_seq`를 자체 보유한다.
- 남음: process-local prompt sequence source 자체는 아직 완전히 제거하지 않았다. 이를 제거하려면 session loop 또는 prompt boundary service가 prompt boundary 생성을 완전히 소유해야 한다. engine 독립 실행용 `HumanHttpPolicy._prompt_seq`도 이 단계에서는 유지한다.

### Phase 9 - RuntimeService 축소와 legacy worker 제거

목표: compatibility facade를 실제 소유자로 착각하지 않게 정리한다.

작업:

- [x] `RuntimeService`에서 session loop로 이동한 책임을 제거한다.
- [x] command recovery/read query를 `RuntimeService` route facade에서 분리한다.
- [x] command processing guard/stale terminal 판단을 `RuntimeService` 내부 구현에서 분리한다.
- [x] local active command/session task gate를 `RuntimeService` 내부 state에서 분리한다.
- [x] `_CommandBoundaryGameStateStore` private RuntimeService class 제거
- [x] `CommandBoundaryGameStateStore` adapter를 포함한 atomic state/prompt/view/command boundary 완전 분리
- [x] `_runtime_prompt_sequence_seed` 계열 제거
- [x] `CommandStreamWakeupWorker`를 단순 recovery watcher로 축소한다.
- [x] `state.py` 전역 조립을 새 service boundary 기준으로 정리한다.
- [x] 테스트 전용 runtime branch를 production code에서 제거한다.

상태:

- 완료: `RuntimeService`의 `PYTEST_CURRENT_TEST` 기반 AI delay 기본값 분기를 제거했다.
- 완료: `MRN_RUNTIME_AI_DECISION_DELAY_MS` / `RuntimeSettings.runtime_ai_decision_delay_ms`를 추가하고 server state에서 `RuntimeService`로 주입한다.
- 완료: `state.py`는 `SessionLoop`, `SessionLoopManager`, `CommandRouter`, `CommandStreamWakeupWorker`를 같은 durable command boundary 기준으로 조립한다.
- 완료: `CommandStreamWakeupWorker`는 Redis pending-command recovery watcher 역할로 축소되었다. pending command를 발견하면 `SessionLoopManager.wake()`로만 넘기며, manager가 없으면 `runtime_wakeup` offset을 전진시키지 않는다. 이전 direct `RuntimeService.process_command_once()` / `start_runtime()` fallback은 제거했다.
- 완료: `CommandRouter`의 manager-less direct runtime fallback을 제거했다. accepted command wakeup은 `SessionLoopManager`가 있을 때만 schedule되며, manager가 없으면 command를 실행하지 않고 `missing_session_loop_manager`로 skip한다.
- 완료: WebSocket decision route는 더 이상 `session_service` / `runtime_service`로 fallback `CommandRouter`를 조립하지 않는다. route에 주입된 router가 없으면 wakeup을 skip하고 runtime을 직접 호출하지 않는다.
- 완료: `CommandRecoveryService`를 추가해 durable command store와 recovery checkpoint만으로 pending resume command, unprocessed command, command seq matching을 판단하게 했다. `sessions` runtime-status route와 WebSocket connect recovery는 이제 `RuntimeService`가 아니라 이 read-side service를 호출한다.
- 완료: `RuntimeService`의 기존 command recovery 메서드는 내부 command guard 호환을 위한 위임 wrapper로 축소했다. 따라서 route/recovery read path의 소유권은 분리됐지만, `process_command_once()` 내부 guard는 아직 같은 service를 통해 동작한다.
- 완료: `CommandProcessingGuardService`를 추가해 consumer offset guard, stale command terminal 판단, rejected/superseded/expired command state mark를 `RuntimeService` 밖으로 분리했다. `RuntimeService.process_command_once()`는 여전히 lease를 잡고 engine loop를 호출하지만, command precondition/stale terminal 규칙은 새 service에 위임한다.
- 완료: `CommandExecutionGate`를 추가해 in-process active command session lock과 active runtime task guard를 `RuntimeService` 필드 구현에서 분리했다. `RuntimeService`에는 호환 wrapper만 남아 runtime status와 command execution entrypoint가 같은 gate를 바라본다.
- 완료: `CommandBoundaryFinalizer`를 추가해 command-boundary deferred commit 최종화(`deferred_commit` copy, authoritative Redis commit, latest `view_commit` emit, waiting prompt materialization, timing log)를 `RuntimeService._run_engine_command_boundary_loop_sync()` 본문 밖으로 분리했다. 최종 commit side effect 묶음의 소유자는 별도 service로 이동했다.
- 완료: `CommandBoundaryFinalizer`가 authoritative commit 직전에 `commit_guard`를 호출하게 했다. command-boundary loop가 runtime lease를 잃은 상태이면 Redis authoritative state/view/prompt side effect를 실행하지 않고 `runtime_lease_lost_before_commit` stale result를 반환한다.
- 완료: `CommandBoundaryRunner`를 추가해 command-boundary per-call store 생성, transition 반복, terminal 판단, finalizer 호출, module trace/timing result 조립을 `RuntimeService._run_engine_command_boundary_loop_sync()` 본문 밖으로 분리했다. `RuntimeService`는 engine transition과 persistence callables를 주입하는 boundary adapter로 남는다.
- 완료: `SessionCommandExecutor`를 추가해 command lifecycle control flow를 `SessionLoop` 쪽으로 이동했다. `SessionLoop`는 이제 runtime task guard, local command gate, runtime lease acquire/release, command `processing` mark, engine boundary 실행, runtime status result 적용, conflict/failure 처리를 순서대로 조립한다.
- 완료: `SessionLoop`는 더 이상 runtime boundary가 lifecycle interface를 지원하지 않을 때 `RuntimeService.process_command_once()`로 fallback하지 않는다. command lifecycle은 항상 `SessionCommandExecutor` 경로로 들어간다.
- 완료: `RuntimeService.process_command_once()`는 `SessionCommandExecutor(runtime_boundary=self)`를 호출하는 compatibility wrapper로 축소했다. 프로덕션 `SessionLoop` 경로는 `process_command_once()` adapter가 없어도 runtime boundary lifecycle 메서드만으로 명령을 처리한다.
- 완료: `RuntimeService`는 아직 engine transition, runtime state persistence, commit conflict recovery 같은 저수준 동작을 제공하지만, accepted command execution lifecycle의 owner는 `SessionLoop`/`SessionCommandExecutor`다.
- 완료: `CommandBoundaryGameStateStore`를 `apps/server/src/services/command_boundary_store.py`로 분리하고 `RuntimeService` 안의 `_CommandBoundaryGameStateStore` private class 정의를 제거했다. 이제 staging/deferred commit adapter는 독립 테스트를 가진 명시적 service boundary다.
- 보류: `CommandBoundaryGameStateStore` adapter 자체는 아직 필요하다. SessionLoop가 atomic state/prompt/view/command commit을 직접 소유하기 전에는 제거하면 같은 명령 안의 중간 transition commit 방지가 깨진다.
- 완료: `_runtime_prompt_sequence_seed` 구현은 `runtime_service.py`에서 제거하고 `apps/server/src/domain/prompt_sequence.py`의 `runtime_prompt_sequence_seed()`로 이동했다. 이 규칙은 checkpoint/resume prompt instance id를 맞추는 순수 domain 계산으로 분류한다.
- 보류: `RuntimeService.process_command_once()` wrapper는 아직 제거하지 않는다. `SessionLoop` production path는 wrapper fallback 없이 `SessionCommandExecutor`와 lifecycle boundary 메서드로 동작하지만, 기존 runtime service 테스트와 일부 route/stream 테스트가 wrapper를 진단용 호환 entrypoint로 직접 사용한다. 제거는 별도 compatibility cleanup으로 분리한다.

수정 후보:

- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/command_boundary_store.py`
- `apps/server/src/services/command_execution_gate.py`
- `apps/server/src/services/command_recovery.py`
- `apps/server/src/services/command_processing_guard.py`
- `apps/server/src/services/command_wakeup_worker.py`
- `apps/server/src/worker.py`
- `apps/server/src/state.py`
- `apps/server/src/config/runtime_settings.py`

검증:

- [x] `RuntimeService`가 engine 실행과 command accept를 동시에 소유하지 않는다.
- [x] route-level recovery query가 `RuntimeService` command inbox helper를 직접 호출하지 않는다.
- [x] command precondition/stale terminal 판단이 `RuntimeService` 구현 본문이 아니라 별도 service에서 실행된다.
- [x] active command session lock과 active runtime task guard가 별도 execution gate에서 실행된다.
- [x] command-boundary deferred commit finalization이 `RuntimeService` 본문이 아니라 별도 service에서 실행된다.
- [x] command-boundary transition loop와 finalization orchestration이 `RuntimeService` 본문이 아니라 `CommandBoundaryRunner`에서 실행된다.
- [x] command-boundary final authoritative commit 직전에 runtime lease owner를 재검증하고, lease를 잃은 실행자는 Redis commit/view emit/prompt materialization을 하지 않는다.
- [x] command wakeup worker가 consumed command를 무한 재스캔하지 않는다.
- [x] 테스트 전용 env branch 없이 live/headless 설정이 동일한 resolver 경로를 탄다.

### Phase 10 - 통합 게이트

목표: 구조 변경이 실제 게임 진행과 배포 토폴로지에서 통과하는지 확인한다.

필수 검증:

- [x] `./.venv/bin/python -m pytest apps/server/tests -q`
- [x] `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- [x] `python3 tools/plan_policy_gate.py`
- [x] `npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts`
- [x] 1-game live protocol gate
- [x] 5-game, 5-server, 1-Redis protocol gate
- [x] 20-game, 1-server bottleneck protocol gate executed and classified:
  one-server contention still fails the 5s backend command timing gate under
  20 concurrent games, while Redis commit and view commit counts remain at 1.
- [x] restart/reconnect smoke with pending prompt
- [x] duplicate decision rejection smoke

2026-05-13 확인:

- Prompt replay probe 병목을 제거했다. Nonblocking human prompt creation path가
  resolved replay를 확인할 때 `timeout_ms=0` immediate probe를 사용하고,
  `PromptService.wait_for_decision(timeout_ms=0)`는 pending waiter를 만들거나
  resolved hash 전체 TTL prune을 수행하지 않는다.
- 1-game live gate:
  `tmp/rl/full-stack-protocol/server-rebuild-1game-prompt-probe-fix-20260513`.
  `completed`, max command 377ms, max transition 206ms, max Redis commit 1,
  max view commit 1, missing ACK 0.
- 5-game, 5-server, 1-Redis gate:
  `tmp/rl/full-stack-protocol/server-rebuild-5server-1redis-prompt-probe-fix-20260513`.
  All 5 games completed. Max command 1224ms, max transition 538ms, max Redis
  commit 1, max view commit 1, missing ACK 0.
- 20-game, 1-server bottleneck gate:
  `tmp/rl/full-stack-protocol/server-rebuild-20game-1server-prompt-probe-fix-20260513`.
  Fail-fast classified the expected single-server capacity bottleneck:
  command seq 1 took 5357ms under 20 concurrent sessions. The previous
  `replay_wait_ms` prompt bottleneck is gone (`promptTimingCount=0` in the
  failure summary); Redis commit/view commit counts stayed at 1.
- Pending prompt reconnect smoke:
  `tmp/rl/full-stack-protocol/server-rebuild-reconnect-pending-prompt-20260513`.
  Full game completed. All four seats and spectator had one forced reconnect,
  one recovery, and zero pending reconnect recoveries.
- Restart plus duplicate decision smoke:
  `tools/scripts/redis_restart_smoke.py --decision-smoke` against
  `project-mrn-protocol` passed. Status stayed `waiting_input -> waiting_input`,
  worker health checks were 4, first decision ACK was `accepted`, duplicate ACK
  was `stale/already_resolved`, and replay events advanced 25 -> 31.

완료 조건:

- Required correctness gates pass. The intentionally harsh 20-game/1-server
  bottleneck run is not a pass criterion for one-server capacity; its failure is
  classified as one-server command/engine scheduling contention after prompt
  replay and Redis/view commit were ruled out.
- `view_commit`으로 pending prompt를 repair하는 code path가 없다.
- accepted command가 Redis durable inbox를 거치지 않는 code path가 없다.

## 7. 단계별 커밋 기준

이 작업은 한 커밋으로 끝내면 안 된다. 최소 커밋 단위는 아래와 같다.

1. contract tests
2. command inbox
3. command router and wakeup
4. session loop
5. decision route cleanup
6. websocket recovery cleanup
7. batch collector
8. AI/timeout unification
9. prompt identity
10. RuntimeService shrink and worker removal

각 커밋은 적어도 해당 phase의 focused tests를 통과해야 한다. Phase 3 이후부터는 protocol gate smoke를 같이 붙인다.

## 8. 중단 조건

아래 상황이 나오면 더 이상 patch를 얹지 않고 계획을 갱신한다.

- command가 Redis durable inbox 없이 accepted되는 경로가 발견된다.
- session loop 외부에서 engine commit을 수행해야만 테스트가 통과한다.
- pending prompt를 authoritative store가 아니라 `view_commit`에서 복구해야만 진행된다.
- pub/sub 누락을 heartbeat payload 증식으로 막아야 한다.
- prompt identity에 process-local state가 다시 필요해진다.

이 경우 구현을 멈추고 해당 phase의 책임 경계가 틀렸는지 먼저 재검토한다.

## 9. 최종 판정 기준

재건이 끝났다고 말하려면 다음 문장이 모두 참이어야 한다.

1. decision handler는 command를 accept할 뿐 엔진을 직접 진행하지 않는다.
2. accepted command는 Redis에 먼저 남고, queue는 깨우기 신호로만 쓰인다.
3. 세션당 writer는 하나이며 Redis lease로 검증된다.
4. prompt pending state는 authoritative prompt store에 있고, `view_commit`은 읽기 모델이다.
5. heartbeat는 liveness 메시지이며 상태 복구와 decision 검증을 대신하지 않는다.
6. batch prompt completion은 atomic하고 idempotent하다.
7. AI, timeout, human decision은 같은 command lifecycle을 탄다.
8. RuntimeService는 더 이상 서버 런타임의 모든 책임을 끌어안지 않는다.
