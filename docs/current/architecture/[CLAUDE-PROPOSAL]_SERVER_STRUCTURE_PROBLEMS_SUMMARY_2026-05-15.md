# 서버 구조 문제점 통합 요약

작성일: 2026-05-15
작성자: Claude
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

- 위치: `apps/server/src/routes/stream.py:183-214` (`_decision_view_commit_rejection_reason`)
- 위반 원칙: REFERENCE §22 — "UI가 뭘 봤는가는 룰 판단의 근거가 아니다. 권위는 서버가 발행한 현재 prompt의 legal_choices다."
- 현재 동작: `request_id`, `player_id`, `prompt_instance_id`, `resume_token`을 모두 `view_commit.payload.view_state.prompt.active`에서 읽어 검증한다.
- 결과:
  - view_commit이 stale하면 유효한 decision이 `stale_prompt_request`로 거부됨.
  - view_commit이 잘못 구성되면 잘못된 decision이 통과 가능.

### P2. view_commit으로 pending prompt를 역방향 재생성

- 위치: `apps/server/src/routes/stream.py:242-296` (`_repair_missing_pending_prompt_from_view_commit`)
- 위반 원칙: REFERENCE §25 불변식 1~3 — "prompt는 engine이 생성한다. view_commit은 그 결과의 viewer projection일 뿐이다."
- 현재 동작: `PromptService`에 pending이 없을 때 view_commit에서 active prompt를 꺼내 `PromptService.create_prompt`를 다시 호출.
- 의미: 데이터 흐름이 역전됨. `engine → prompt → view_commit`이 정상이지만, 패치를 거치면서 `view_commit → prompt`로 역행하는 경로가 생겼다.
- 이 패치가 들어간 이유는 추정 가능하다: 어딘가에서 pending prompt가 사라지는 버그를 발견했고, view_commit이 안정적이어서 그곳에서 복구했다. 결과적으로 "view_commit이 진실"이라는 잘못된 전제가 구조에 박혔다.

---

## 3. Tier 2 — 경로/책임 중복 (운영 위험, 디버깅 불가)

### P3. 두 개의 런타임 wakeup 경로가 경쟁한다

- 경로 1: `stream.py:338-424` (`_wake_runtime_after_accepted_decision`) — WebSocket에서 asyncio task로 직접 깨움.
- 경로 2: `services/command_wakeup_worker.py` (`CommandStreamWakeupWorker`) — 250ms 폴링 워커.
- 두 경로 모두 `process_command_once`를 호출. RuntimeService 내부 `_command_processing_guard`가 중복 실행을 차단.
- 결과: 한쪽이 먼저 잡으면 다른 쪽은 `already_processing`/`running_elsewhere`로 튕긴다. WebSocket 경로는 재시도 루프를 도는데 그동안 이벤트 루프를 잡는다.
- 어느 쪽이 주 경로인지 명세 없음. 둘 다 primary처럼 동작하고 서로의 존재를 모른 채 방어 코드를 쌓았다.

### P4. heartbeat가 상태 복구 책임을 진다

- 위치: `stream.py:625-698` (`_heartbeat`), `_should_send_heartbeat_view_commit`
- 현재 동작:
  1. `runtime_service.runtime_status(session_id)` 호출 → checkpoint 액세스
  2. subscriber queue가 비어 있으면 최신 view_commit을 다시 fetch
  3. view_commit 재전송
  4. 그 다음에야 실제 ping 발송
- 결과: "송신 lock → queue dequeue → heartbeat repair" 세 타이밍이 동일 책임(view_commit 전달)을 나눠 가짐. 정상 경로가 어디인지 불분명.
- AUDIT §12.4에서 이미 지적됨. 지적된 채로 1년 가까이 방치.

### P5. `module_identity_mismatch` 로직이 두 곳에 독립 구현

- 위치 1: `command_wakeup_worker.py:366-387` (`_module_identity_mismatch`)
- 위치 2: `runtime_service.py:2214` (`_command_module_identity_mismatch`)
- 둘 다 `frame_id`/`module_id`/`module_type`/`module_cursor`를 비교. 로직이 사실상 동일하지만 payload 추출 helper만 다르게 구현됨.
- diverge 시 "wakeup worker는 valid라고 보고 runtime은 mismatch라고 보는" 비대칭이 가능. 로그만으론 추적 불가.

---

## 4. Tier 3 — 단일 책임 위반 (유지보수 불가)

### P6. `RuntimeService` 5,649 줄 단일 파일

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

- 위치: `runtime_service.py:109-227`
- 동작: `RedisGameStateStore`를 감싼 내부 프록시. 내부 transition을 `deferred_commit`에 buffer, terminal status (`waiting_input`/`completed`)에 도달해야만 실제 Redis 기록.
- 위험:
  - 서버가 내부 transition 중 죽으면 deferred state는 사라진다. Redis엔 이전 checkpoint만 남음.
  - "Redis에 커밋됐는가, 아직 deferred 상태인가"를 외부에서 확인할 수단 없음.
  - 의도는 정상(command boundary 동안 중간 step을 외부에 노출하지 않음)이지만 명시적 loop 구조가 아니라 *proxy로 위장한 transactional buffer*다.

### P8. in-process status와 Redis status 이중화

- 위치: `runtime_service.py:_status` (in-process Python dict) vs `RedisRuntimeStateStore` (Redis)
- AUDIT §6.1에서 정리된 상태값(`idle`/`running`/`waiting_input`/`completed`/`failed`/`recovery_required`/`running_elsewhere`/`rejected`/`stale`)이 어느 저장소가 권위인지 명세 없음.
- `runtime_status()`가 두 저장소를 머지해 반환. 프로세스 재시작 시 `_status`가 초기화되어 클라이언트가 일시적으로 `idle`을 보고 불필요한 재시작을 유도할 수 있음.

### P9. source_events ↔ view_commit 상호 의존

- AUDIT §12.6에서 지적.
- view_commit 생성 (`_build_authoritative_view_state`) 시 source_events에서 scene/turn_history를 꺼내 합침. 두 스트림이 독립적이지 않음.
- 결과: source_events 제거 → view_commit 생성 로직 재작성, view_commit 제거 → 클라이언트 복구 경로 재작성. 둘 다 유지 → Redis 용량/생성 비용/디버깅 복잡도 지속 증가.

---

## 5. Tier 4 — 잠재 버그/원자성 결함

### P10. 비-Lua 경로의 `accept_decision_with_command` 비원자성

- 위치: `realtime_persistence.py:554-573`
- Lua 사용 가능 시: 전체 atomic.
- Lua 미사용 시: `hget → hsetnx → hset → _next_seq → pipeline([hdel, hset, hset, xadd])` 다단계.
- race 가능 지점: `_next_seq` 증가와 `xadd` 사이에 크래시하면 command stream에 gap이 생긴다. `CommandStreamWakeupWorker`의 offset 추적이 이 gap에서 혼란.
- Redis Cluster cross-slot 제한, Sentinel failover 중 임시 불가, 테스트의 mock Redis 환경에서 실제로 비-Lua 경로가 silently 사용될 수 있음.

### P11. `DecisionGateway._request_seq`가 매 engine run마다 0부터 재시작

- 위치: `decision_gateway.py:1895-1901`
- `_ServerDecisionPolicyBridge`가 `process_command_once`/`start_runtime` 호출마다 새로 생성됨. 따라서 `_request_seq`는 매번 1부터.
- request_id 형식 `{session_id}_req_{seq}_{uuid}`에 매번 새 UUID 포함되어 외관상 안전.
- 실제로는 `_runtime_prompt_sequence_seed`, `_request_prompt_instance_id`, `_prior_same_module_resume_prompt_seed` 세 함수가 prompt_sequence를 checkpoint에서 복원해 같은 `prompt_instance_id`를 재현하도록 보장.
- 이 복원 메커니즘이 깨지면 → `stale_prompt_request` 또는 `prompt_fingerprint_mismatch` 로그가 찍힘. 현재 로그에 보이는 이런 거부의 일부가 이 경로일 가능성이 높음.

### P12. `_stable_prompt_request_id` fallback의 조용한 충돌 가능성

- 위치: `decision_gateway.py:2162-2168`
- 공식: `{session_id}:r{round}:t{turn}:p{player_id}:{request_type}:{prompt_instance_id}`
- `envelope.get("request_id")`가 falsy일 때만 사용되는데, engine이 request_id를 항상 설정한다는 명시적 계약이 없음.
- 같은 (round, turn, player, type)에 같은 prompt_instance_id로 두 번 열리면 ID 충돌 가능. 발생 조건이 불명확해 정적 추론으로 안전성 확신 불가.

---

## 6. Tier 5 — 코드 위생/장기 부채

### P13. `PYTEST_CURRENT_TEST` 환경변수 체크가 프로덕션 코드에 박혀 있음

- 위치: `runtime_service.py:1803`, `:2541`
  ```python
  ai_decision_delay_ms=0 if os.environ.get("PYTEST_CURRENT_TEST") else 1000
  ```
- 결과: AI decision delay가 production에선 1000ms로 하드코딩, pytest 실행 중엔 0ms. 설정(`MRN_RUNTIME_*`)으로 제어 불가.
- "테스트에서는 AI가 즉시 응답한다"는 동작이 암묵적으로 보장되어, 누군가 이 값을 설정 가능하게 만들려고 할 때 이 코드가 방해.

### P14. `_RUNTIME_WAKEUP_TASKS` 모듈 전역 dict — 멀티 프로세스 불완전

- 위치: `stream.py:19`
- 단일 프로세스 내 중복 방지는 OK. 여러 서버 프로세스 환경에서 각 프로세스가 자신만의 dict 보유.
- Redis lease가 결과적 안전성을 보장하지만 불필요한 충돌이 wakeup 경로에서 발생.

### P15. `_reprocessed_consumed_commands` set 무한 증가

- 위치: `command_wakeup_worker.py:35`
- `(session_id, command_seq, request_id)` 튜플을 추가만 하고 제거 안 함.
- 1000개 게임이면 수만 개의 튜플이 잔류. 즉각적 문제는 아니지만 명시적 TTL/완료 세션 pruning 부재는 설계 누락.

### P16. `PromptService._waiters`는 in-memory, Redis 복구 불가

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

## 8. 우선순위 요약

| 우선순위 | 항목 | 위치 | 처리 방향 |
|----------|------|------|-----------|
| **즉시** | P1 — view_commit 기반 decision 검증 | `stream.py:183-214` | `PromptService.get_pending`로 교체 |
| **즉시** | P2 — view_commit에서 pending prompt 복구 | `stream.py:242-296` | 호출 경로 제거 |
| **다음 iter** | P3 — 두 wakeup 경로 경쟁 | `stream.py:338`, `command_wakeup_worker.py` | session loop로 단일화 |
| **다음 iter** | P4 — heartbeat가 repair 수행 | `stream.py:625-698` | ping-only로 환원 |
| **다음 iter** | P10 — 비-Lua 비원자성 | `realtime_persistence.py:554-573` | Lua 필수화 또는 원자성 확보 |
| **다음 iter** | P13 — `PYTEST_CURRENT_TEST` 박힘 | `runtime_service.py:1803,2541` | config 항목 분리 |
| **장기** | P5 — `module_identity_mismatch` 중복 | 두 파일 | 단일 helper로 통합 |
| **장기** | P6 — RuntimeService 5,649줄 | `runtime_service.py` | 책임별 분리 |
| **장기** | P7 — deferred commit 프록시 | `runtime_service.py:109-227` | 명시적 loop 구조로 대체 |
| **장기** | P8 — status 이중화 | `_status` vs Redis | 권위 결정 |
| **장기** | P9 — source_events ↔ view_commit 결합 | `_build_authoritative_view_state` | 한쪽 일원화 |
| **장기** | P11 — `_request_seq` per-run 재시작 | `decision_gateway.py:1895` | 결정론적 prompt ID |
| **장기** | P12 — `_stable_prompt_request_id` 충돌 가능성 | `decision_gateway.py:2162` | 주 경로로 승격 |
| **부채** | P14 — `_RUNTIME_WAKEUP_TASKS` 모듈 전역 | `stream.py:19` | 다중 프로세스 대비 |
| **부채** | P15 — `_reprocessed_consumed_commands` 누수 | `command_wakeup_worker.py:35` | TTL/pruning |
| **부채** | P16 — `_waiters` in-memory | `prompt_service.py:47,98` | blocking mode 제거 |

---

## 9. 한 줄로

> **현재 누더기의 90%는 P1, P2 두 가지가 만들었다. 이 둘을 고치지 않으면 어떤 재설계도 같은 자리에 다시 누더기를 쌓는다.**

해결 방향은 `[CLAUDE-PROPOSAL]_SERVER_REDESIGN_FULL_2026-05-12.md` Step 1, Step 2를 본다.
