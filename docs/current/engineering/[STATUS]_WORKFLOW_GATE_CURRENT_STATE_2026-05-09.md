# Workflow Gate Current State - 2026-05-09

기록 시각: 2026-05-09 13:45 KST
브랜치: `codex/view-commit-authoritative`

## 현재 목적

사용자가 요청한 `1,2,3` 작업의 범위는 다음으로 해석했다.

1. `test-workflow-runtime` 실패 수정
2. `make test-workflow-all` 실행 및 실패 원인 수정
3. live/browser workflow gate 실행

현재 위 범위는 완료됐다.

## 수정한 내용

### 1. runtime prompt sequence seed 분기 정리

파일:

```text
apps/server/src/services/runtime_service.py
```

`_runtime_prompt_sequence_seed(...)`에서 pending prompt와 checkpoint의 prior same-module resume 중 무엇을 authoritative seed로 사용할지 분기 조건을 좁혔다.

정책은 다음과 같다.

- 현재 decision resume request id와 pending prompt request id가 정확히 같은 경우에는 pending prompt 기준 seed를 우선한다.
- 단, checkpoint의 prior same-module resume과 현재 resume 사이에 prompt instance gap이 있으면 prior resume seed를 사용한다.
- 그 외에는 prior same-module resume seed, checkpoint prompt sequence 순서로 fallback한다.

이 분기는 다음 두 요구를 동시에 만족시키기 위한 것이다.

- 현재 pending prompt가 현재 decision resume과 일치하면 seed는 pending prompt instance 직전이어야 한다.
- 이전 same-module resume이 있고 현재 prompt instance와 gap이 있으면 이전 resume을 authoritative 기준으로 삼아야 한다.

### 2. waiting input recovery 판정 완화 유지

파일:

```text
apps/server/src/services/runtime_service.py
```

`runtime_status(...)`에서 `game_state_store_unavailable` 상태를 stale waiting input recovery 대상으로 잘못 분류하지 않도록 조건을 유지했다.

이 조건은 Redis-backed authoritative state가 없는 테스트 더블/legacy runtime을 불필요하게 `recovery_required`로 바꾸지 않기 위한 것이다.

### 3. live protocol workflow runner 수정

파일:

```text
tools/checks/workflow_gate.py
tools/checks/test_workflow_gate.py
```

`make test-workflow-protocol-live`가 처음에는 `runFullStackProtocolGate.ts`에 지원되지 않는 `--profile smoke`를 넘겨 실패했다. 해당 runner가 받는 profile은 `contract|live`이므로 workflow profile을 protocol profile로 매핑했다.

매핑:

```text
smoke -> contract
local -> live
```

또한 protocol runner는 `--output-dir`를 받지 않고 `--out`, `--replay-out`를 받으므로 trace/replay 경로를 명시하도록 수정했다.

smoke profile에서는 contract protocol이 120초 내에 정상 종료되지 않는 문제가 있었다. smoke gate 목적에 맞게 bounded end rule config를 `--config-json`으로 전달하도록 했다.

## 통과한 검증

### Runtime/Redis 충돌 테스트

명령:

```bash
PYTHONPATH=engine .venv/bin/python -m pytest \
  apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_runtime_prompt_sequence_seed_prefers_current_pending_prompt_over_prior_resume_debug \
  apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_seeds_prompt_sequence_from_previous_same_module_decision \
  apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_continues_after_command_transition_until_prompt
```

결과:

```text
3 passed
```

### Redis workflow gate

명령:

```bash
make test-workflow-redis
```

결과: 통과.

### Workflow gate unit tests

명령:

```bash
PYTHONPATH=engine .venv/bin/python -m pytest tools/checks/test_workflow_gate.py
```

결과:

```text
8 passed
```

### 전체 workflow gate

명령:

```bash
make test-workflow-all
```

결과:

```json
{
  "ok": true,
  "workflows": [
    { "name": "runtime", "ok": true },
    { "name": "prompt", "ok": true },
    { "name": "redis", "ok": true },
    { "name": "protocol", "ok": true },
    { "name": "rl", "ok": true }
  ]
}
```

### Live protocol workflow gate

명령:

```bash
make test-workflow-protocol-live
```

결과:

```json
{
  "ok": true,
  "workflows": [
    { "name": "protocol", "ok": true }
  ]
}
```

### Browser workflow gate

명령:

```bash
make test-workflow-browser
```

결과:

```json
{
  "ok": true,
  "workflows": [
    { "name": "browser", "ok": true }
  ]
}
```

## 현재 git 상태

수정됨:

```text
apps/server/src/services/runtime_service.py
tools/checks/test_workflow_gate.py
tools/checks/workflow_gate.py
```

미추적:

```text
docs/current/engineering/[STATUS]_WORKFLOW_GATE_CURRENT_STATE_2026-05-09.md
.playwright-mcp/
```

`.playwright-mcp/`는 이번 작업과 무관하므로 건드리지 않는다.

## 현재 판단

초기 실패는 Redis 자체 문제가 아니라 runtime prompt sequence seed 정책 충돌이었다. 이후 live protocol gate에서는 workflow runner와 protocol runner의 CLI 계약 불일치, smoke profile의 종료 조건 부재가 추가로 드러났다.

현재 구현 목표였던 runtime fix, full workflow gate, live/browser workflow gate는 모두 검증까지 끝났다.
