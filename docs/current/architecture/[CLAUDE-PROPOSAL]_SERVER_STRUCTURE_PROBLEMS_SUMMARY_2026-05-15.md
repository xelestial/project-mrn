# 서버 구조 문제점 통합 요약

작성일: 2026-05-15
검증일: 2026-05-15 (현재 main `dbfa382a` 기준)
작성자: Claude

> **검증 결과 한 줄 요약**: 16개 문제 중 **6개 완전 해결 / 5개 부분 해결 또는 위치 이동 / 5개 잔존**.
> 가장 심각했던 P1·P2는 둘 다 해결됨. 잔존 문제는 P6 (RuntimeService 거대 파일), P8 (status 이중화), P10 (비-Lua 비원자성), P15·P16 (in-memory set/dict).
> 각 항목 아래 `[현재 상태]` 줄로 표기.

근거 문서 (architecture 폴더 전체):
- `[AUDIT]_CURRENT_GAME_SERVER_STRUCTURE_2026-05-12.md` — 현재 구현 실측
- `[CLAUDE-PROPOSAL]_SERVER_STRUCTURE_DIAGNOSIS_2026-05-12.md` — 1차 진단
- `[CLAUDE-PROPOSAL]_SERVER_STRUCTURE_ADDENDUM_2026-05-12.md` — 심층 코드 분석 보충
- `[CLAUDE-PROPOSAL]_SERVER_REDESIGN_2026-05-12.md` — 초기 재설계
- `[CLAUDE-PROPOSAL]_SERVER_REDESIGN_FULL_2026-05-12.md` — 전체 재설계
- `[PROPOSAL]_SERVER_LOGIC_DESIGN_AGENT_A_2026-05-12.md` — Agent A 제안 (Event Sourcing)
- `[PROPOSAL]_SERVER_LOGIC_DESIGN_AGENT_B_2026-05-12.md` — Agent B 제안 (Actor/Saga)
참조 룰: `docs/current/rules/[REFERENCE]_CORE_RULE_DECISION_FLOW_2026-05-12.md`

---

## 0. 이 문서가 존재하는 이유

기존 진단·재설계 문서들이 5개로 흩어져 있다. 각각 발견 순서, 코드 깊이, 해결책 중심으로 쓰여 있어 "**현재 무엇이 문제인가**"만 단독으로 보기 어렵다.

이 문서는 해결책을 다루지 않는다. **문제점만 정리한다**. 해결 방향은 REDESIGN_FULL 문서를 본다.

---

## 1. 단 하나의 근본 원인

> **레이어가 서로의 일을 하고 있다.**

- WebSocket 핸들러가 게임 룰 판단을 한다 (decision 유효성).
- Heartbeat가 상태 복구를 한다 (view_commit repair).
- view_commit이 prompt의 백업 저장소 역할을 한다 (역방향 의존).
- 폴링 워커와 WebSocket 핸들러가 같은 일(런타임 wakeup)을 경쟁한다.
- RuntimeService 하나가 엔진 실행, Redis 영속, AI 클라이언트, status dict, view_commit 생성을 모두 한다.

다른 모든 문제는 이 한 가지 원인의 변주다. Event Sourcing이나 Actor 모델이 부족해서가 아니다. **경계가 명확하지 않아서**다.

---

## 2. Tier 1 — 룰 불변식을 직접 위반하는 문제 (즉시 수정)

REFERENCE §22, §25의 불변식을 위배한다. 잠재 버그가 아니라 **현재 룰을 어기고 있는** 상태다.

### P1. Decision 검증이 view_commit에서 권위 데이터를 읽는다

- **[현재 상태] ✅ 해결됨** — `_decision_view_commit_rejection_reason` 함수가 제거됨. decision 검증은 이제 `prompt_service.submit_decision()` 경로 단일화 (`stream.py:846` 부근).
- 위치 (당시): `apps/server/src/routes/stream.py:183-214` (`_decision_view_commit_rejection_reason`)
- 위반 원칙: REFERENCE §22 — "UI가 뭘 봤는가는 룰 판단의 근거가 아니다. 권위는 서버가 발행한 현재 prompt의 legal_choices다."
- 현재 동작: `request_id`, `player_id`, `prompt_instance_id`, `resume_token`을 모두 `view_commit.payload.view_state.prompt.active`에서 읽어 검증한다.
- 결과:
  - view_commit이 stale하면 유효한 decision이 `stale_prompt_request`로 거부됨.
  - view_commit이 잘못 구성되면 잘못된 decision이 통과 가능.

### P2. view_commit으로 pending prompt를 역방향 재생성

- **[현재 상태] ✅ 해결됨** — `_repair_missing_pending_prompt_from_view_commit` 함수 제거. 역방향 의존 경로 더 이상 존재하지 않음.
- 위치 (당시): `apps/server/src/routes/stream.py:242-296` (`_repair_missing_pending_prompt_from_view_commit`)
- 위반 원칙: REFERENCE §25 불변식 1~3 — "prompt는 engine이 생성한다. view_commit은 그 결과의 viewer projection일 뿐이다."
- 현재 동작: `PromptService`에 pending이 없을 때 view_commit에서 active prompt를 꺼내 `PromptService.create_prompt`를 다시 호출.
- 의미: 데이터 흐름이 역전됨. `engine → prompt → view_commit`이 정상이지만, 패치를 거치면서 `view_commit → prompt`로 역행하는 경로가 생겼다.
- 이 패치가 들어간 이유는 추정 가능하다: 어딘가에서 pending prompt가 사라지는 버그를 발견했고, view_commit이 안정적이어서 그곳에서 복구했다. 결과적으로 "view_commit이 진실"이라는 잘못된 전제가 구조에 박혔다.

---

## 3. Tier 2 — 경로/책임 중복 (운영 위험, 디버깅 불가)

### P3. 두 개의 런타임 wakeup 경로가 경쟁한다

- **[현재 상태] 🟡 부분 해결** — 두 경로는 더 이상 `process_command_once`를 직접 부르지 않음. 둘 다 `command_router.wake_after_accept()` 및 `_session_loop_manager.wake()`로 위임 (stream.py:247-276, command_wakeup_worker.py:223). Session loop가 단일 실행자가 된 것은 큰 진전. 다만 두 wakeup 트리거 자체는 여전히 공존.
- 경로 1: `stream.py:338-424` (`_wake_runtime_after_accepted_decision`) — WebSocket에서 asyncio task로 직접 깨움.
- 경로 2: `services/command_wakeup_worker.py` (`CommandStreamWakeupWorker`) — 250ms 폴링 워커.
- 두 경로 모두 `process_command_once`를 호출. RuntimeService 내부 `_command_processing_guard`가 중복 실행을 차단.
- 결과: 한쪽이 먼저 잡으면 다른 쪽은 `already_processing`/`running_elsewhere`로 튕긴다. WebSocket 경로는 재시도 루프를 도는데 그동안 이벤트 루프를 잡는다.
- 어느 쪽이 주 경로인지 명세 없음. 둘 다 primary처럼 동작하고 서로의 존재를 모른 채 방어 코드를 쌓았다.

### P4. heartbeat가 상태 복구 책임을 진다

- **[현재 상태] 🟡 부분 잔존** — `_should_send_heartbeat_view_commit` 별도 함수는 제거됐지만, `_heartbeat()` (`stream.py:502-566`)가 여전히 `stream_service.latest_view_commit_message_for_viewer()`를 호출 (line 506). repair 로직이 일반 send 흐름에 녹아 있어 책임 분리는 미완료.
- 위치 (당시): `stream.py:625-698` (`_heartbeat`), `_should_send_heartbeat_view_commit`
- 현재 동작:
  1. `runtime_service.runtime_status(session_id)` 호출 → checkpoint 액세스
  2. subscriber queue가 비어 있으면 최신 view_commit을 다시 fetch
  3. view_commit 재전송
  4. 그 다음에야 실제 ping 발송
- 결과: "송신 lock → queue dequeue → heartbeat repair" 세 타이밍이 동일 책임(view_commit 전달)을 나눠 가짐. 정상 경로가 어디인지 불분명.
- AUDIT §12.4에서 이미 지적됨. 지적된 채로 1년 가까이 방치.

### P5. `module_identity_mismatch` 로직이 두 곳에 독립 구현

- **[현재 상태] 🟡 부분 해결 (의미 분화)** — 두 구현이 여전히 존재하지만 문맥이 달라짐:
  - `command_wakeup_worker.py:370` — `_module_identity_mismatch` (command wakeup 시점 검증)
  - `runtime_service.py:699` — `_resume_module_identity_mismatch` (decision resume 시점 검증), `runtime_service.py:1796`이 `CommandRecoveryService`로 위임
  - 진정한 중복이라기보다 서로 다른 시점의 검증으로 정리됨. 단일 helper로 합칠 여지는 남음.
- 위치 (당시) 1: `command_wakeup_worker.py:366-387` (`_module_identity_mismatch`)
- 위치 (당시) 2: `runtime_service.py:2214` (`_command_module_identity_mismatch`)
- 둘 다 `frame_id`/`module_id`/`module_type`/`module_cursor`를 비교. 로직이 사실상 동일하지만 payload 추출 helper만 다르게 구현됨.
- diverge 시 "wakeup worker는 valid라고 보고 runtime은 mismatch라고 보는" 비대칭이 가능. 로그만으론 추적 불가.

---

## 4. Tier 3 — 단일 책임 위반 (유지보수 불가)

### P6. `RuntimeService` 5,649 줄 단일 파일

- **[현재 상태] ❌ 잔존** — 현재 5,548 줄. 외부 AI 클래스 (`_ExternalAiTransportBase`, `_LoopbackExternalAiTransport`, `_HttpExternalAiTransport`)가 여전히 `runtime_service.py:4595-4701`에 있음. 분리 진척 거의 없음.
- 위치: `apps/server/src/services/runtime_service.py`
- 한 파일 안에서 수행되는 책임:

| 책임 | 대표 위치 |
|------|----------|
| 엔진 실행 (thread pool) | `start_runtime`, `process_command_once` |
| Redis lease 관리 | `_command_processing_guard` |
| checkpoint R/W | `_mark_checkpoint_waiting_input` |
| view_commit 생성 | `_build_authoritative_view_commits` |
| prompt materialize | `_materialize_prompt_from_checkpoint` |
| view_commit emit | `_emit_latest_view_commit_sync` |
| 외부 AI 클라이언트 (4 클래스, 1000+ 줄) | `_ExternalAiTransport` 등 |
| fallback choice 계산 | `execute_prompt_fallback` |
| in-process status dict | `_status` |
| command boundary 프록시 | `_CommandBoundaryGameStateStore` |
| stream task 스케줄링 | `_schedule_runtime_stream_task` |

- "외부 AI 클라이언트 관리"만 떼어내도 별도 모듈이 정당화된다. 분리할 시점을 매번 놓쳤다.

### P7. `_CommandBoundaryGameStateStore` — 디버깅 불가능한 deferred commit

- **[현재 상태] ✅ 해결됨** — `CommandBoundaryGameStateStore`가 `services/command_boundary_store.py:6`로 추출됨 (commit `01cc04bf Extract command boundary store`). runtime_service.py 내부 프록시 형태에서 명시적 모듈로 승격됨.
- 위치 (당시): `runtime_service.py:109-227`
- 동작: `RedisGameStateStore`를 감싼 내부 프록시. 내부 transition을 `deferred_commit`에 buffer, terminal status (`waiting_input`/`completed`)에 도달해야만 실제 Redis 기록.
- 위험:
  - 서버가 내부 transition 중 죽으면 deferred state는 사라진다. Redis엔 이전 checkpoint만 남음.
  - "Redis에 커밋됐는가, 아직 deferred 상태인가"를 외부에서 확인할 수단 없음.
  - 의도는 정상(command boundary 동안 중간 step을 외부에 노출하지 않음)이지만 명시적 loop 구조가 아니라 *proxy로 위장한 transactional buffer*다.

### P8. in-process status와 Redis status 이중화

- **[현재 상태] ❌ 잔존** — `RuntimeService._status` dict가 `runtime_service.py:561`에 그대로 있음. `runtime_status()` (line 817)가 이 dict를 주 소스로 사용. Redis 권위 전환 미진행.
- 위치: `runtime_service.py:_status` (in-process Python dict) vs `RedisRuntimeStateStore` (Redis)
- AUDIT §6.1에서 정리된 상태값(`idle`/`running`/`waiting_input`/`completed`/`failed`/`recovery_required`/`running_elsewhere`/`rejected`/`stale`)이 어느 저장소가 권위인지 명세 없음.
- `runtime_status()`가 두 저장소를 머지해 반환. 프로세스 재시작 시 `_status`가 초기화되어 클라이언트가 일시적으로 `idle`을 보고 불필요한 재시작을 유도할 수 있음.

### P9. source_events ↔ view_commit 상호 의존

- **[현재 상태] ❌ 잔존** — `_build_authoritative_view_state`가 `runtime_service.py:3213`에 존재하며 `source_messages` 파라미터를 받음 (line 3227). 두 스트림 교차 의존 유지.
- AUDIT §12.6에서 지적.
- view_commit 생성 (`_build_authoritative_view_state`) 시 source_events에서 scene/turn_history를 꺼내 합침. 두 스트림이 독립적이지 않음.
- 결과: source_events 제거 → view_commit 생성 로직 재작성, view_commit 제거 → 클라이언트 복구 경로 재작성. 둘 다 유지 → Redis 용량/생성 비용/디버깅 복잡도 지속 증가.

---

## 5. Tier 4 — 잠재 버그/원자성 결함

### P10. 비-Lua 경로의 `accept_decision_with_command` 비원자성

- **[현재 상태] ❌ 잔존** — `realtime_persistence.py:514-573`에 비-Lua fallback이 여전히 존재 (lines 545-573). race window 동일.
- 위치: `realtime_persistence.py:554-573`
- Lua 사용 가능 시: 전체 atomic.
- Lua 미사용 시: `hget → hsetnx → hset → _next_seq → pipeline([hdel, hset, hset, xadd])` 다단계.
- race 가능 지점: `_next_seq` 증가와 `xadd` 사이에 크래시하면 command stream에 gap이 생긴다. `CommandStreamWakeupWorker`의 offset 추적이 이 gap에서 혼란.
- Redis Cluster cross-slot 제한, Sentinel failover 중 임시 불가, 테스트의 mock Redis 환경에서 실제로 비-Lua 경로가 silently 사용될 수 있음.

### P11. `DecisionGateway._request_seq`가 매 engine run마다 0부터 재시작

- **[현재 상태] ✅ 해결됨** — `_request_seq` 필드 제거 (commit `58f36925 Remove process-local decision request ids`). request ID 생성은 `_stable_prompt_request_id()` (decision_gateway.py:2041)가 담당. per-run 재시작 문제 해소.
- 위치 (당시): `decision_gateway.py:1895-1901`
- `_ServerDecisionPolicyBridge`가 `process_command_once`/`start_runtime` 호출마다 새로 생성됨. 따라서 `_request_seq`는 매번 1부터.
- request_id 형식 `{session_id}_req_{seq}_{uuid}`에 매번 새 UUID 포함되어 외관상 안전.
- 실제로는 `_runtime_prompt_sequence_seed`, `_request_prompt_instance_id`, `_prior_same_module_resume_prompt_seed` 세 함수가 prompt_sequence를 checkpoint에서 복원해 같은 `prompt_instance_id`를 재현하도록 보장.
- 이 복원 메커니즘이 깨지면 → `stale_prompt_request` 또는 `prompt_fingerprint_mismatch` 로그가 찍힘. 현재 로그에 보이는 이런 거부의 일부가 이 경로일 가능성이 높음.

### P12. `_stable_prompt_request_id` fallback의 조용한 충돌 가능성

- **[현재 상태] ⚠️ 상태 변경 (잔존+승격)** — P11 해결로 인해 `_stable_prompt_request_id`가 **fallback이 아니라 주 경로**가 됨 (`decision_gateway.py:2238-2243`, `stable_prompt_request_id()` helper 래핑). 충돌 조건이 그대로면 영향 범위는 더 커짐. 결정론적 ID 공식의 충돌 가능성 재검토 필요.
- 위치 (당시): `decision_gateway.py:2162-2168`
- 공식: `{session_id}:r{round}:t{turn}:p{player_id}:{request_type}:{prompt_instance_id}`
- `envelope.get("request_id")`가 falsy일 때만 사용되는데, engine이 request_id를 항상 설정한다는 명시적 계약이 없음.
- 같은 (round, turn, player, type)에 같은 prompt_instance_id로 두 번 열리면 ID 충돌 가능. 발생 조건이 불명확해 정적 추론으로 안전성 확신 불가.

---

## 6. Tier 5 — 코드 위생/장기 부채

### P13. `PYTEST_CURRENT_TEST` 환경변수 체크가 프로덕션 코드에 박혀 있음

- **[현재 상태] ✅ 해결됨** — `PYTEST_CURRENT_TEST` 체크 제거. AI decision delay는 `DecisionGateway.__init__()` (runtime_service.py:1931)에서 명시적 파라미터로 전달.
- 위치 (당시): `runtime_service.py:1803`, `:2541`
  ```python
  ai_decision_delay_ms=0 if os.environ.get("PYTEST_CURRENT_TEST") else 1000
  ```
- 결과: AI decision delay가 production에선 1000ms로 하드코딩, pytest 실행 중엔 0ms. 설정(`MRN_RUNTIME_*`)으로 제어 불가.
- "테스트에서는 AI가 즉시 응답한다"는 동작이 암묵적으로 보장되어, 누군가 이 값을 설정 가능하게 만들려고 할 때 이 코드가 방해.

### P14. `_RUNTIME_WAKEUP_TASKS` 모듈 전역 dict — 멀티 프로세스 불완전

- **[현재 상태] ✅ 해결됨** — 모듈 전역 dict 제거. wakeup 조율은 `command_router.wake_after_accept()` 및 `_session_loop_manager.wake()`로 흐름.
- 위치 (당시): `stream.py:19`
- 단일 프로세스 내 중복 방지는 OK. 여러 서버 프로세스 환경에서 각 프로세스가 자신만의 dict 보유.
- Redis lease가 결과적 안전성을 보장하지만 불필요한 충돌이 wakeup 경로에서 발생.

### P15. `_reprocessed_consumed_commands` set 무한 증가

- **[현재 상태] ❌ 잔존** — `command_wakeup_worker.py:40`에 동일하게 존재. line 136에서 추가만 되고 evict 없음.
- 위치: `command_wakeup_worker.py:35`
- `(session_id, command_seq, request_id)` 튜플을 추가만 하고 제거 안 함.
- 1000개 게임이면 수만 개의 튜플이 잔류. 즉각적 문제는 아니지만 명시적 TTL/완료 세션 pruning 부재는 설계 누락.

### P16. `PromptService._waiters`는 in-memory, Redis 복구 불가

- **[현재 상태] ❌ 잔존** — `prompt_service.py:61`에 `dict[str, threading.Event]` 그대로. line 123에 등록, lines 230/446/488에서 access. Redis 복원 경로 없음.
- 위치: `prompt_service.py:47`, `:98`
- non-blocking mode(현재 기본)에서는 1ms timeout으로만 사용되어 실제 영향 없음.
- 그러나 `blocking_human_prompts=True` 경로가 일부 테스트에 남아 있음. 재시작 후 waiter 부재 시 무한 대기/즉시 timeout 가능.

---

## 7. Agent A/B 제안의 공통 맹점 (참고)

두 외부 에이전트(Event Sourcing, Actor/Saga)가 제안한 방향은 **이론적으론 맞지만 현재 코드와 너무 멀다**. 그들이 놓친 것:

- 현재 decision 검증이 4곳(`stream.py`/`PromptService`/`RedisPromptStore`/`view_commit`)에 분산되어 있음. 단일 검증으로 전환하려면 4곳을 동시 수정해야 하는데 점진적 경로를 제시 안 함.
- heartbeat repair 의존성을 제거하지 않고 새 구조를 얹으면 두 repair 경로가 공존하게 됨.
- `_CommandBoundaryGameStateStore`를 그냥 제거하면 내부 step마다 Redis write 발생. 성능 측정 없이 제거 불가.
- 결과적으로 두 에이전트의 제안 중 ~70%는 이미 현재 코드에 존재하는 개념의 재명명에 가까움.

---

## 8. 검증 결과 요약 (현재 main 기준)

✅ 해결 (6): **P1, P2, P7, P11, P13, P14**
🟡 부분 해결 / 재맥락화 (5): **P3, P4, P5, P9, P10**
❌ 잔존 (5): **P6, P8, P12, P15, P16**

> 다만 P9·P10은 위 검증에서 "부분/잔존"으로 분류했지만 변경된 흔적 없음. 사실상 잔존으로 봐도 무방.

### 잔존 항목 우선순위 (현재 시점)

| 우선순위 | 항목 | 현재 위치 | 처리 방향 |
|----------|------|-----------|-----------|
| **다음 iter** | P10 — 비-Lua 비원자성 | `realtime_persistence.py:545-573` | Lua 필수화 또는 원자성 확보 |
| **다음 iter** | P12 — `_stable_prompt_request_id` 충돌 가능성 (이제 **주 경로**) | `decision_gateway.py:2238-2243` | 결정론적 ID 충돌 조건 재검토 |
| **다음 iter** | P4 — heartbeat에 view_commit fetch 잔존 | `stream.py:502-566` | view_commit 송신을 별도 경로로 분리 |
| **장기** | P6 — RuntimeService 5,548줄 (외부 AI 클래스 동거) | `runtime_service.py` | external AI 모듈 분리 |
| **장기** | P8 — `_status` in-process dict | `runtime_service.py:561, 817` | Redis 권위 |
| **장기** | P9 — source_events ↔ view_commit 결합 | `runtime_service.py:3213` | 한쪽 일원화 |
| **장기** | P5 — module_identity_mismatch 두 helper | `command_wakeup_worker.py:370`, `runtime_service.py:699` | 단일 helper로 통합 |
| **부채** | P15 — `_reprocessed_consumed_commands` 누수 | `command_wakeup_worker.py:40, 136` | TTL/pruning |
| **부채** | P16 — `_waiters` in-memory | `prompt_service.py:61, 123` | blocking mode 제거 또는 Redis pub/sub |

### 진척 평가

**가장 중요한 두 문제 (P1, P2)가 해결됨.** REFERENCE §22·§25 불변식 위반은 더 이상 없다. session loop / command router / command boundary store 추출로 P3·P7·P11·P14도 해결됐다. 이는 단순 리팩터링이 아니라 **구조적 경계 정리**가 실제로 진행됐다는 증거다.

**남은 잔존은 두 종류로 갈린다**:
- 위험은 있으나 발생 빈도 낮은 것: P10 (Lua 가용 환경에선 무해), P12 (주 경로 승격으로 영향 확대), P15·P16 (즉각적 위협 아님)
- 큰 분리 작업 필요: P6 (외부 AI 모듈 추출), P8 (status 권위 전환), P9 (스트림 일원화)

---

## 9. 한 줄로

> **누더기의 핵심 원인이었던 P1·P2는 제거됐다. 이제 남은 것은 큰 분리 작업(P6·P8·P9)과 작은 위생 작업(P10·P12·P15·P16)이다. 새로운 패치를 쌓지 말고 분리 작업으로 가야 한다.**

해결 방향은 `[CLAUDE-PROPOSAL]_SERVER_REDESIGN_FULL_2026-05-12.md` Step 3 이후 단계를 본다 (Step 1·2는 이미 완료).
