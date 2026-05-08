# Workflow Test Modularization Plan

## Summary

지금 테스트의 약점은 "단위 테스트가 통과했다"를 "작업 흐름이 안전하다"로 오해하기 쉽다는 점이다. 이 프로젝트의 주요 장애는 대개 단일 함수 내부가 아니라 런타임 상태, Redis 저장소, WebSocket 전송, 프론트 decision builder, prompt lifecycle이 서로 어긋나는 경계에서 발생했다.

앞으로 테스트는 함수 단위 증명만으로 끝내지 않고, 실제 기능 경로를 기준으로 묶는다. 단위 테스트는 유지하되, 최종 판정은 연결된 함수들이 하나의 작업 흐름으로 같이 움직이는지 확인하는 workflow gate가 담당한다.

## Problem 1: Unit Pass Does Not Prove Runtime Flow

### Cause

- 런타임 모듈, prompt store, stream publish, view_commit 생성이 각자 테스트되어도 실제 순서가 어긋나면 실패한다.
- `request_not_pending` stale 사례처럼 서버의 최신 `view_commit`에는 prompt가 있는데 pending prompt store에는 없는 상태가 발생할 수 있다.
- 기존 테스트 결과는 `N passed` 중심이라 어느 작업 흐름이 검증됐는지 바로 알기 어렵다.

### Fix

- 테스트를 workflow module 단위로 재분류한다.
- 각 workflow는 "입력 이벤트 -> 내부 상태 변화 -> Redis 기록 -> WebSocket 메시지 -> 클라이언트 decision -> ack -> 후속 commit"까지 필요한 연결 함수를 같이 호출한다.
- 최종 리포트는 단순 테스트 개수가 아니라 workflow별 성공/실패, session id, seed, request id, commit seq, Redis evidence path를 출력한다.

### Target State

- `PromptLifecycleWorkflow`가 통과했다는 말은 prompt 생성, 전달, decision 수신, ack, resolved/expired cleanup까지 한 흐름이 검증됐다는 뜻이 된다.
- `WebSocketProtocolWorkflow`가 통과했다는 말은 REST create/join/start와 seat/spectator WebSocket, reconnect/resume, hidden payload 차단까지 확인됐다는 뜻이 된다.

### Residual Risk

- workflow 테스트가 커질수록 실패 원인 위치가 흐려질 수 있다.

### Follow-up

- workflow 단계마다 `stage`, `component`, `request_id`, `commit_seq`, `redis_key`를 남긴다.
- 실패 시 해당 workflow의 마지막 정상 단계와 첫 실패 단계를 함께 출력한다.

## Problem 2: Prompt And Decision Boundaries Are Under-Tested

### Cause

- prompt는 runtime, PromptService, StreamService, 클라이언트 decision ledger가 모두 관여한다.
- active prompt는 TTL로 지워지면 안 되고, 완료된 prompt cleanup만 TTL 대상이어야 한다.
- stale decision은 정상 rejection인지, 복구 가능한 pending 누락인지 구분해야 한다.

### Fix

`PromptLifecycleWorkflow`를 만든다.

검증 단계:

1. Runtime module이 prompt request를 생성한다.
2. PromptService가 `created -> delivered` 상태를 기록한다.
3. StreamService가 target player에게만 prompt를 보낸다.
4. Headless client가 동일 decision protocol로 응답한다.
5. 서버가 `decision_received -> accepted/rejected/stale -> resolved/expired`를 기록한다.
6. latest `view_commit` 기준으로 pending prompt 누락은 좁은 조건에서만 repair된다.
7. spectator에는 hidden prompt payload가 노출되지 않는다.

### Target State

- prompt 관련 버그는 `test_stream_api.py`의 단편 테스트가 아니라 prompt lifecycle workflow에서 재현된다.
- stale ack가 나오면 리포트가 `true stale`, `repairable missing pending`, `illegal retry` 중 하나로 분류한다.

### Residual Risk

- repair 로직이 과도해지면 실제 stale decision을 잘못 살릴 수 있다.

### Follow-up

- repair 조건은 최신 player-projected `view_commit`의 `request_id`, `player_id`, `prompt_instance_id`, `resume_token`, `view_commit_seq_seen`이 맞을 때만 허용한다.
- 이 조건을 workflow fixture로 고정한다.

## Problem 3: Redis State Is Observable But Not Yet A Test Contract

### Cause

- Redis에는 current state, checkpoint, prompt lifecycle, viewer outbox, latest commit이 흩어져 있다.
- 사람이 Redis를 보면 추적 가능해졌지만, 테스트가 아직 "Redis만 봐도 상태를 이해할 수 있다"를 계약으로 강제하지 않는다.

### Fix

`RedisStateWorkflow`를 만든다.

검증 단계:

1. session 생성 직후 key map이 생성된다.
2. round start, turn start, prompt, decision, commit마다 inspector snapshot이 상태를 설명할 수 있다.
3. active pending prompt TTL은 3시간 정책을 따른다.
4. 완료 prompt, outbox, diagnostic key는 1시간 보관 정책을 따른다.
5. latest `view_commit`, current state, checkpoint가 같은 active frame/module을 가리키는지 확인한다.

### Target State

- Redis inspector output 하나만으로 session status, round/turn, active prompt, pending action, latest commit, viewer별 delivered seq를 설명할 수 있다.
- 테스트 실패 시 Redis evidence JSON이 자동으로 남는다.

### Residual Risk

- Redis evidence가 너무 커지면 디버깅은 쉬워져도 로그 관리가 어려워진다.

### Follow-up

- evidence는 compact summary를 기본으로 하고, raw payload는 `--include-raw` 옵션에서만 저장한다.

## Problem 4: Full-Stack And Browser Tests Are Separated Too Late

### Cause

- headless protocol gate는 빠르지만 화면 렌더링, 실제 browser socket lifecycle, UI state 복원은 별도로 깨질 수 있다.
- 브라우저 수동 테스트는 반복 절차가 명확하지 않으면 매번 확인 범위가 달라진다.

### Fix

`WebSocketProtocolWorkflow`와 `BrowserGameplayWorkflow`를 분리하되 같은 session scenario를 공유한다.

`WebSocketProtocolWorkflow`:

- REST create/join/start
- 4 seat headless clients + spectator
- real WebSocket path
- forced reconnect at game start, prompt received, before decision, round boundary, turn boundary
- latest `view_commit` resume verification

`BrowserGameplayWorkflow`:

- browser open
- new session or supplied session attach
- seat join/start
- one game or configured round count
- prompt visibility, turn history, spectator current/history panel, reconnect banner, final state 확인

### Target State

- headless gate가 통과하면 protocol은 신뢰할 수 있다.
- browser workflow는 같은 contract 위에서 UI projection/rendering 문제만 좁혀서 본다.

### Residual Risk

- 브라우저 테스트는 느리고 비결정적일 수 있다.

### Follow-up

- 브라우저 workflow는 smoke와 full 두 등급으로 나눈다.
- smoke는 1라운드와 reconnect 1회, full은 1게임 전체와 프로파일별 플레이어 조합을 검증한다.

## Workflow Modules

### RuntimeTransitionWorkflow

Scope:

- command dispatch
- runtime frame transition
- scheduled action
- checkpoint
- source event
- authoritative `view_commit`

Required cases:

- round start
- turn start/end
- child frame suspend/resume
- `TargetJudicatorModule`
- `resolve_mark`
- round boundary

### PromptLifecycleWorkflow

Scope:

- prompt creation
- delivery
- active prompt restore
- decision submit
- ack
- resolved/expired cleanup

Required cases:

- normal accepted decision
- illegal choice rejection
- stale decision rejection
- missing pending prompt repair from latest commit
- spectator hidden payload exclusion

### WebSocketProtocolWorkflow

Scope:

- REST session lifecycle
- seat/spectator WebSocket
- reconnect/resume
- commit seq monotonicity
- target-only prompt/ack

Required cases:

- 4 human headless seats
- spectator client
- forced reconnect at defined protocol points
- latest `view_commit` recovery

### RedisStateWorkflow

Scope:

- Redis key layout
- TTL contract
- state inspector
- viewer outbox diagnostics
- prompt lifecycle diagnostics

Required cases:

- active prompt retained
- completed prompt cleanup
- outbox evidence retention
- current/checkpoint/view_commit consistency

### RLDataWorkflow

Scope:

- protocol trace
- replay conversion
- training input
- candidate evaluation
- hidden payload exclusion

Required cases:

- baseline trace collection
- replay conversion no missing records
- PyTorch policy bridge legal choice validation
- candidate vs baseline metrics

### BrowserGameplayWorkflow

Scope:

- rendered frontend
- actual browser WebSocket behavior
- user-visible prompt/turn history/current panel
- one-game smoke

Required cases:

- player profile display
- prompt width/height controls
- turn history current/history split
- reconnect/resume visual recovery
- final game state visible

## Runner Structure

Add a single workflow gate entrypoint:

```text
tools/checks/workflow_gate.py
```

Recommended commands:

```text
make test-workflow-runtime
make test-workflow-prompt
make test-workflow-protocol
make test-workflow-redis
make test-workflow-rl
make test-workflow-browser
make test-workflow-all
```

The runner should emit:

- workflow name
- stage name
- session id
- seed
- request id
- prompt instance id
- commit seq
- source event seq
- redis evidence path
- protocol trace path
- browser screenshot path when applicable

## Migration Plan

1. Inventory existing tests and tag each one with one workflow owner.
2. Extract shared fixtures for session creation, prompt creation, WebSocket connection, Redis snapshot, and headless policy.
3. Wrap existing unit tests into workflow modules without deleting the focused assertions.
4. Add workflow-level report output and fail-fast diagnostics.
5. Replace ad-hoc local smoke commands with named workflow commands.
6. Keep pure unit tests for deterministic helpers, but stop treating them as final acceptance.

## Acceptance Criteria

- A change touching runtime/prompt/stream cannot be marked stable unless `RuntimeTransitionWorkflow`, `PromptLifecycleWorkflow`, and `WebSocketProtocolWorkflow` pass.
- A change touching Redis keys or retention cannot be marked stable unless `RedisStateWorkflow` passes.
- A change touching RL or policy code cannot be marked stable unless `RLDataWorkflow` passes.
- A change touching UI flow cannot be marked stable unless `BrowserGameplayWorkflow` smoke passes.
- Final reports must state workflow pass/fail, not only unit test counts.
