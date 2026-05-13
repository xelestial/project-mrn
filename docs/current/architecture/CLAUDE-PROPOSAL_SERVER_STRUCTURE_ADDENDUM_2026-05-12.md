# 서버 구조 진단 보충: 추가 발견 문제

작성일: 2026-05-12  
작성자: Claude  
전제 문서: `CLAUDE-PROPOSAL_SERVER_STRUCTURE_DIAGNOSIS_2026-05-12.md`

이 문서는 초기 진단 이후 코드를 더 깊이 읽어 발견한 추가 문제들을 기록한다.

---

## A. 비원자적 decision 중복 방지 (비-Lua 경로)

### 위치

`apps/server/src/services/realtime_persistence.py:554-573` — `accept_decision_with_command`의 Lua 미지원 fallback 경로

### 무엇이 문제인가

Lua 스크립트가 사용 가능하면(`client.eval` callable) 전체 작업이 하나의 atomic Redis 연산으로 처리된다. 그러나 Lua를 쓸 수 없는 환경에서는 다음 순서로 실행된다:

```
1. hget(pending_key) → pending 존재 확인
2. hsetnx(seen_key) → 중복 방지 키 설정 시도
3. hset(session_seen_key) → 세션 seen 기록
4. _next_seq() → seq 증가
5. pipeline([hdel, hset, hset, xadd]).execute()
```

2번 `hsetnx`와 5번 `pipeline` 사이에 다른 프로세스가 같은 request_id로 `accept_decision_with_command`를 호출하면:

- 두 번째 호출도 2번에서 `hsetnx`가 실패해 일찍 리턴된다 → 괜찮다.
- **하지만** 1번에서 pending 확인과 2번 사이에 첫 번째 호출이 pipeline을 실행해 pending을 삭제한 직후, 세 번째 프로세스가 다시 1번부터 들어오면 pending이 없어 조기 리턴한다.

더 심각한 경우: `_next_seq()` (seq 카운터 증가)와 `xadd` 사이에 크래시가 발생하면 seq 번호는 소비됐지만 command stream에는 이벤트가 없는 gap이 생긴다. CommandWakeupWorker의 offset 로직이 이 gap에서 혼란스러울 수 있다.

### 실제 영향

운영 환경에서 Redis Lua가 항상 사용 가능하면 이 경로는 실행되지 않는다. 그러나 다음 경우 문제가 된다:

- Redis Cluster 모드(cross-slot Lua 제한)
- Redis Sentinel failover 중 임시 불가 상태
- 테스트 환경에서 Lua 없는 mock Redis 사용 시

비-Lua 경로가 silent fallback인 이상, 이 경로도 실제로 실행될 수 있다는 전제하에 검토해야 한다.

---

## B. `_reprocessed_consumed_commands` set의 무한 증가

### 위치

`apps/server/src/services/command_wakeup_worker.py:35`, `:121-124`

### 무엇이 문제인가

```python
self._reprocessed_consumed_commands: set[tuple[str, int, str]] = set()
```

이 set은 `(session_id, command_seq, request_id)` 튜플을 추가할 뿐 제거하지 않는다. 목적은 "이미 재처리한 consumed command를 다시 재처리하지 않는 것"이다.

그러나:
- 세션이 종료되거나 게임이 완료돼도 해당 세션의 튜플은 set에 남는다.
- 서버가 오랫동안 실행되면서 많은 게임이 완료되면 set이 계속 커진다.
- 이 set은 프로세스 메모리에만 존재한다. 서버 재시작 시 초기화되므로, 재시작 후 consumed commands가 다시 재처리될 수 있다(의도된 복구 동작이긴 하나).

증가 속도: 각 게임 세션당 수십 개의 command가 발생한다고 하면, 1000개 게임이면 수만 개의 튜플이 메모리에 잔류한다. 이 정도가 실제 문제가 될 수준은 아니지만, 명시적 TTL 또는 완료 세션 pruning이 없다는 것은 설계상 누락이다.

---

## C. `PYTEST_CURRENT_TEST` 체크가 production 코드에 있다

### 위치

`apps/server/src/services/runtime_service.py:1803`, `:2541`

```python
ai_decision_delay_ms=0 if os.environ.get("PYTEST_CURRENT_TEST") else 1000
```

### 무엇이 문제인가

이것은 테스트 환경 감지 코드가 production 서비스 코드에 직접 박혀 있는 것이다.

- production에서 AI decision delay가 1000ms로 하드코딩돼 있다.
- 이 값은 config(`MRN_RUNTIME_*` 환경변수)로 제어되지 않는다.
- pytest가 실행되면 이 값이 0으로 바뀐다.

결과적으로 테스트와 production의 AI decision 타이밍이 다르게 동작한다. 더 나쁜 점은, 이 값을 통해 "테스트에서 AI가 즉시 응답한다"는 동작이 암묵적으로 보장되고 있다는 것이다. 누군가 이 코드를 모르고 AI delay를 설정 가능하게 바꾸려 할 때 이 하드코딩이 그것을 방해한다.

---

## D. `module_identity_mismatch` 로직이 두 곳에 독립 구현됨

### 위치

- `apps/server/src/services/command_wakeup_worker.py:366-387` — `CommandStreamWakeupWorker._module_identity_mismatch`
- `apps/server/src/services/runtime_service.py:2214` — `RuntimeService._command_module_identity_mismatch`

### 무엇이 문제인가

두 함수 모두 `frame_id`, `module_id`, `module_type`, `module_cursor` 필드를 command payload와 checkpoint에서 꺼내 비교한다. 로직이 사실상 동일하다.

차이점:
- `command_wakeup_worker.py`는 `_command_payload_field` helper를 통해 `payload.decision.frame_id` 또는 `payload.frame_id`를 꺼낸다.
- `runtime_service.py`는 직접 `command.get("payload")`에서 꺼낸다.

이 두 구현이 diverge하면 "같은 command를 wakeup worker는 valid라고 보고 runtime service는 mismatch라고 보는" 상황이 생긴다. 또는 그 반대. 어느 쪽이 틀렸는지 로그만으로 파악하기 어렵다.

---

## E. `DecisionGateway._request_seq`는 프로세스마다 0부터 재시작한다

### 위치

`apps/server/src/services/decision_gateway.py:1895-1901`

```python
self._request_seq = 0

def next_request_id(self) -> str:
    self._request_seq += 1
    return f"{self._session_id}_req_{self._request_seq}_{uuid.uuid4().hex[:6]}"
```

### 무엇이 문제인가

`_ServerDecisionPolicyBridge`(=DecisionGateway wrapper)는 `process_command_once` 또는 `start_runtime`을 호출할 때마다 새로 만들어진다(`runtime_service.py:1790-1820`, `:2545-2558`). 따라서 `_request_seq`는 매 engine 실행마다 1부터 시작한다.

결과적으로 request_id는 `{session_id}_req_1_{uuid}` 형태로 매번 새 UUID를 포함한다. 같은 게임 세션의 같은 prompt position에서 두 번의 engine run이 발생하면, 첫 번째 request_id와 두 번째 request_id가 다르다.

이것이 안전한 이유: checkpoint에 `pending_prompt_request_id`가 저장되어 있고, `_runtime_prompt_sequence_seed`가 prompt_sequence를 체크포인트에서 복원해, engine이 동일한 `prompt_instance_id`를 재현하도록 seed를 설정한다. 그 덕분에 두 번째 실행에서 생성된 request_id도 같은 `prompt_instance_id`를 포함하게 된다.

이것이 위험한 이유: 이 복원 메커니즘이 `_runtime_prompt_sequence_seed`, `_request_prompt_instance_id`, `_prior_same_module_resume_prompt_seed` 세 함수에 걸쳐 복잡하게 구현돼 있다(`runtime_service.py:251-332`). 이 로직이 올바르게 동작하지 않으면 engine이 잘못된 prompt_sequence seed에서 시작해 request_id mismatch가 발생한다. 이 case가 발생했을 때 로그에 나타나는 `stale_prompt_request` 또는 `prompt_fingerprint_mismatch`가 이 경로에서 비롯됐을 가능성이 있다.

---

## F. `PromptService._decisions`는 항상 in-memory, Redis에서 복구 불가

### 위치

`apps/server/src/services/prompt_service.py:45`, `:773-786`

### 무엇이 문제인가

`PromptService._decisions` dict는 `_prompt_store`(Redis)가 있어도 항상 in-memory다. `_get_decision`이 `_prompt_store.get_decision`을 호출하므로 Redis에서 읽는다. 하지만 `_waiters`는 오직 in-memory다.

현재 non-blocking mode(`blocking_human_prompts=False`)에서는 `wait_for_decision`을 1ms timeout으로만 호출한다(replay check). 따라서 `_waiters`의 Event는 실제로 거의 사용되지 않는다.

하지만 `submit_decision`에서 `_set_decision` 경로를 보면:

```python
def _set_decision(self, request_id, payload, session_id=None):
    if self._prompt_store is not None:
        self._prompt_store.save_decision(request_id, payload, session_id=session_id)
        return  # in-memory _decisions에는 저장 안 함
    self._decisions[...] = payload
```

즉 Redis가 있으면 `_decisions` in-memory dict에는 쓰지 않는다. `_get_decision`도 Redis를 읽는다. 이것은 올바른 설계다.

**실제 문제는 다른 곳**: `submit_decision`에서 `waiter.set()`을 호출해 in-memory waiter를 깨우는 경로(`prompt_service.py:295`)가 있다. 그런데 이 waiter는 Redis가 있는 환경에서도 `create_prompt` 시점에 in-memory에 등록된다(`prompt_service.py:98`). Redis에서 pending을 복구해도 waiter는 복구되지 않는다. 서버 재시작 후 새 connection에서 `create_prompt`를 다시 호출하면 새 waiter가 등록되지만, 이전 waiter(restart 전에 등록된 것)는 사라진다.

non-blocking mode에서는 waiter를 사용하지 않으므로 실제 영향은 없다. 그러나 blocking mode 코드 경로(`blocking_human_prompts=True`)가 일부 내부 test 코드에서 여전히 사용된다면, 재시작 후 waiter가 없어 무한 대기 또는 즉시 timeout이 될 수 있다.

---

## G. `_stable_prompt_request_id`가 fallback이지만 우선 경로처럼 쓰일 수 있다

### 위치

`apps/server/src/services/decision_gateway.py:1997`, `:2162-2168`

```python
request_id = str(envelope.get("request_id") or self._stable_prompt_request_id(envelope, public_context))
```

`_stable_prompt_request_id` 생성 공식:

```
{session_id}:r{round_index}:t{turn_index}:p{player_id}:{request_type}:{prompt_instance_id}
```

### 무엇이 문제인가

이 ID는 round_index, turn_index, player_id, request_type, prompt_instance_id로 만들어진다. 만약 같은 (round, turn, player_id, request_type)에서 같은 prompt_instance_id로 프롬프트가 두 번 열리면 ID가 충돌한다.

현재 `_request_prompt_instance_id` + `prompt_sequence` 메커니즘이 이를 방지하려 하지만, 이 fallback ID가 실제로 사용되는 경우가 언제인지 명확하지 않다. `envelope.get("request_id")`가 None이거나 빈 문자열일 때 사용되는데, engine이 `request_id`를 항상 설정하는지 명시적 계약이 없다.

---

## H. `_RUNTIME_WAKEUP_TASKS` 모듈 전역 dict — 멀티 프로세스 환경 불완전

### 위치

`apps/server/src/routes/stream.py:19`

```python
_RUNTIME_WAKEUP_TASKS: dict[tuple[str, int], asyncio.Task[None]] = {}
```

### 무엇이 문제인가

이것은 모듈 레벨 전역 dict다. asyncio Task를 (session_id, command_seq) 키로 추적해 중복 wakeup을 방지한다.

- 단일 프로세스 내에서는 올바르게 동작한다.
- 여러 서버 프로세스를 띄우면 각 프로세스는 자신의 `_RUNTIME_WAKEUP_TASKS`를 가진다. 프로세스 A의 Task가 진행 중임을 프로세스 B는 알 수 없다.
- 이 경우 두 프로세스가 동시에 같은 (session_id, command_seq)에 대해 `process_command_once`를 호출할 수 있다. RuntimeService의 Redis lease 메커니즘이 이 중복을 방어하지만, 불필요한 충돌이 발생한다.

또한 done callback(`_drop_completed_task`)이 정상 완료 시 항목을 제거한다. 그러나 asyncio Task가 `CancelledError`로 취소되면 done callback은 호출되지만 항목 제거는 된다. 예외로 crash되면 역시 done callback이 호출되므로 제거된다. 즉 Task 완료 시 제거는 올바르다. 하지만 WebSocket이 끊겨 connection이 닫히면 해당 connection에서 만들어진 Task가 강제 취소되는지 여부에 따라 Task가 dict에 남을 수 있다.

---

## 요약 테이블

| 문제 | 심각도 | 위치 | 비고 |
|------|--------|------|------|
| 비-Lua decision 중복 방지 비원자성 | 중간 | `realtime_persistence.py:554-573` | Lua 사용 환경에선 무해, 비-Lua fallback에서 race |
| `_reprocessed_consumed_commands` 무한 증가 | 낮음 | `command_wakeup_worker.py:35` | 장기 서버에서 메모리 누수 |
| `PYTEST_CURRENT_TEST` 프로덕션 코드 내 | 중간 | `runtime_service.py:1803, 2541` | 테스트/프로덕션 행동 diverge |
| `module_identity_mismatch` 중복 구현 | 낮음 | `command_wakeup_worker.py:366`, `runtime_service.py:2214` | diverge 위험 |
| `_request_seq` per-run 재시작 | 중간 | `decision_gateway.py:1895` | 복잡한 prompt_sequence 복원 메커니즘에 의존 |
| `_waiters` in-memory, Redis 복구 불가 | 낮음 | `prompt_service.py:47, 98` | non-blocking mode에선 무해 |
| `_stable_prompt_request_id` 충돌 조건 | 낮음 | `decision_gateway.py:2162-2168` | 사용 조건 불명확 |
| `_RUNTIME_WAKEUP_TASKS` 모듈 전역 | 낮음 | `stream.py:19` | 멀티 프로세스 환경에서 불완전한 중복 방지 |

---

## 진단 문서와 합산한 우선순위

앞 문서와 이 문서를 합친 전체 우선순위는 다음과 같다.

**즉시 수정 대상** (룰 불변식 위반 또는 데이터 손상 가능):
1. Decision 검증이 view_commit에 의존 (`stream.py:183-214`)
2. view_commit으로 pending prompt 역방향 재생성 (`stream.py:242-296`)

**다음 iteration 수정 대상** (잠재 버그, 운영 위험):
3. `PYTEST_CURRENT_TEST` 프로덕션 코드 제거
4. 비-Lua `accept_decision_with_command` 원자성 확보 또는 Lua 필수화
5. `module_identity_mismatch` 중복 구현 통합

**기술 부채로 추적** (장기적 문제):
6. `_reprocessed_consumed_commands` TTL/pruning 추가
7. `_request_seq` per-run 재시작 → prompt_sequence 복원 로직 단순화
8. `_RUNTIME_WAKEUP_TASKS` → 멀티 프로세스 환경에서 충분한지 재확인
