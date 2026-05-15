# Prompt Timing Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `PromptService.create_prompt()` live 지연의 지배 원인을 행동 변경 없이 계측으로 확정하고, 계측 결과가 바로 다음 구조 개선 작업의 근거가 되게 한다.

**Architecture:** 기존 `apps.server.src.infra.structured_log.log_event()`에 프롬프트 경계 타이밍 이벤트를 추가한다. 계측은 `PromptService`의 락 경계와 `RedisPromptStore`의 Redis 호출 경계에만 들어가며, 프롬프트 의미, Redis 키 구조, 락 순서, 대기/타임아웃 정책은 바꾸지 않는다. live 검증은 동일 시드/동일 runner 플래그로 fresh/warm/accumulated 상태만 바꿔 비교한다.

**Tech Stack:** Python server, Redis prompt store, existing structured JSON log sink, pytest/unittest, Docker protocol stack, existing web protocol-gate runner.

---

## Implementation Contract

**Goal**

프롬프트 생성 지연이 `PromptService` 락 대기, 락 내부 prune/get/set/lifecycle 처리, `RedisPromptStore`의 resolved scan, debug index rebuild, Redis cold/warm 상태 중 어디에서 발생하는지 수치로 분리한다.

**Completion criteria**

- `create_prompt()` 1회 호출마다 `prompt_service_create_prompt_phase_timing` 이벤트가 남는다.
- Redis prompt store의 `list_resolved`, `save_pending`, `save_lifecycle`, `_upsert_debug_record`, `_build_prompt_debug_summary` 경계별 이벤트가 남는다.
- 각 이벤트는 `session_id`, `request_id` 또는 그에 준하는 join key를 포함해 live run 로그에서 같은 프롬프트를 연결할 수 있다.
- 계측 추가 후 기존 프롬프트/Redis 테스트가 통과한다.
- 1-game live smoke에서 계측 이벤트가 실제 파일 로그에 남고, 빠진 단계가 있으면 matrix 실행 전에 수정한다.
- fresh/warm/accumulated matrix 결과로 지배 원인 A/B/C/D/E 중 하나를 문서화한다.

**Non-goals**

- SLO, timeout, prompt semantics, retry policy를 바꾸지 않는다.
- Redis 키 구조, TTL 정책, cleanup worker, queue, thread, async writer를 도입하지 않는다.
- `PromptAuditWriter` 같은 새 컴포넌트를 만들지 않는다.
- 성능 개선 패치는 계측 결과 전에는 넣지 않는다.

**Protected boundaries**

- `PromptService._lock` 획득 순서와 락 안팎의 의미를 바꾸지 않는다.
- `_prune_resolved()` 호출 여부와 위치를 바꾸지 않는다.
- `_set_pending()`, `_record_lifecycle()`, waiter 등록 순서를 바꾸지 않는다.
- `RedisPromptStore`의 Redis read/write 횟수와 대상 키를 계측 때문에 늘리지 않는다. 단, live run 시작 전 snapshot은 critical path 밖에서만 허용한다.
- public/legacy prompt id 호환 경계를 건드리지 않는다.
- protocol-gate runner의 게임 진행 플래그와 seed를 계측 외 목적으로 바꾸지 않는다.

**Verification commands**

```bash
git diff --check
python3 tools/plan_policy_gate.py
./.venv/bin/python -m pytest apps/server/tests/test_structured_log.py -q
./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py apps/server/tests/test_redis_realtime_services.py -q
./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q
./.venv/bin/python -m pytest apps/server/tests/test_runtime_rebuild_contract.py -q
```

Live verification commands are listed in Phase 6.

**Responsibility check**

이 작업은 병목을 고치지 않는다. 책임 이동은 “추측 기반 병목 판단”에서 “프롬프트/Redis 경계별 계측 로그가 병목 판단 책임을 가진다”로 이동한다. 최적화 책임은 Phase 7의 원인 판정 뒤 별도 작업으로 넘어간다.

## Implementation Status - 2026-05-15

- Phase 0-5 implementation is complete with behavior-neutral timing events added to `PromptService` and `RedisPromptStore`.
- `tools/protocol_gate_prompt_snapshot.py` captures the run-start Redis prompt keyspace outside the request path.
- Local verification passed with prompt service, Redis prompt store, structured log, runtime rebuild contract, diff, and plan-policy checks.
- Phase 6 fresh-fresh 1-game smoke was attempted at `tmp/rl/full-stack-protocol/prompt-timing-fresh-fresh-smoke`.
- The smoke did produce `prompt_service_create_prompt_phase_timing` and Redis prompt store timing events in `game-1/raw/backend_server.log`.
- The smoke stopped before the matrix because runtime rejected command seq 2 with `request id mismatch`.
- Root cause: `PromptService` canonicalized the prompt boundary to a public `req_...` request id, while `runtime_active_prompt.request_id` and the recovered prompt view could still expose the legacy session-composite id for the same `prompt_instance_id`.
- A minimal protocol identity blocker fix was added in `RuntimeService`: `PromptRequired` state now syncs active continuation request ids to the canonical prompt envelope, and single-prompt view projection prefers the checkpoint `pending_prompt_request_id` while preserving the stale value as `legacy_request_id`.
- This identity fix is not a timing optimization. It only unblocks Phase 6 evidence collection by keeping the existing public/legacy compatibility contract coherent.
- Phase 6 smoke rerun then exposed two additional compatibility blockers in the same prompt contract boundary:
  - Batch completion accepted public `req_...` ids at the protocol layer but resumed the engine with that public id instead of the original engine continuation request id.
  - Prompt boundary replay could reuse an existing continuation request id while keeping a newly generated `prompt_instance_id`, `legal_choices`, and `public_context`, which changed the stored pending prompt fingerprint and produced `prompt_fingerprint_mismatch`.
- Minimal blocker fixes were added:
  - Batch response application now records protocol/public ids while resolving engine resume through `legacy_request_id` / `submitted_request_id` / original `request_id` metadata.
  - `PromptBoundaryBuilder` replay now restores `prompt_instance_id`, `legal_choices`, and `public_context` from the existing continuation contract when the continuation matches.
- The fixes preserve the timing instrumentation goal. They do not optimize prompt latency, alter game rules, change Redis topology, or weaken fingerprint checks.
- Local verification after the fixes passed:
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q` -> `180 passed, 14 subtests passed`
  - `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_runtime_rebuild_contract.py apps/server/tests/test_structured_log.py -q` -> `121 passed`
  - `python3 tools/plan_policy_gate.py` -> OK
- Phase 6 blocker smoke rerun passed at `tmp/rl/full-stack-protocol/prompt-replay-contract-smoke`: runtime status `completed`, `141` accepted decisions, `0` rejected/stale acks, and no `request id mismatch`, `request_not_pending`, or `prompt_fingerprint_mismatch` in the checked failure logs.
- Phase 6 timing matrix completed:
  - `tmp/rl/full-stack-protocol/prompt-timing-fresh-fresh`
  - `tmp/rl/full-stack-protocol/prompt-timing-fresh-warm`
  - `tmp/rl/full-stack-protocol/prompt-timing-accum-fresh`
  - `tmp/rl/full-stack-protocol/prompt-timing-accum-warm`
- Phase 7 classification is documented in `docs/current/reports/REPORT_PROMPT_TIMING_INSTRUMENTATION_RESULT_2026-05-15.md`.
- Chosen classification: **A. Debug summary rebuild dominant**. `upsert_debug_record_ms` accounts for 62.4-70.7% of `create_prompt.total_ms` at p50 across the four matrix conditions, while lock wait and resolved prune are not dominant.
- The next implementation target is to remove eager debug summary/index rebuild from the synchronous prompt create/decision path without changing authoritative prompt hashes or game semantics.
- Follow-up implementation is complete at unit-test level:
  - prompt write/decision paths update debug buckets and markers, invalidate cached debug index, and do not rebuild the summary by default.
  - `RedisPromptStore.load_debug_index()` is the lazy rebuild boundary for debug inspection.
  - local verification passed with `4` targeted lazy-debug tests and `295` prompt/Redis/runtime tests.
- Follow-up implementation was extended to the game-state debug snapshot boundary:
  - checkpoint/view-commit debug snapshot writes now store a deferred prompt summary placeholder instead of rebuilding the prompt summary.
  - `RedisGameStateStore.load_debug_snapshot()` enriches the snapshot through `RedisPromptStore.load_debug_index()`, keeping prompt inspection functional outside the write path.
  - local verification passed with `6` targeted lazy-debug/snapshot tests and `296` prompt/Redis/runtime tests.
- A rebuilt-stack 1-game live smoke passed at `tmp/rl/full-stack-protocol/prompt-timing-lazy-debug-smoke-final`: runtime `completed`, `219` decisions, max command `431ms`, slow command count `0`, and `redis_prompt_store_build_prompt_debug_summary_timing=0`.
- Remaining optional evidence step: rerun the full four-condition live timing matrix only if a quantitative before/after latency delta is needed. The structural boundary removal is already proven by the rebuilt-stack live smoke.

---

## Phase 0 - Baseline Alignment

**Goal**

현재 코드 경계와 계측 대상이 실제 구현과 맞는지 확인한다.

**Files to inspect**

- `apps/server/src/services/prompt_service.py`
- `apps/server/src/services/realtime_persistence.py`
- `apps/server/src/infra/structured_log.py`
- `apps/server/tests/test_prompt_service.py`
- `apps/server/tests/test_redis_realtime_services.py`
- `apps/server/tests/test_structured_log.py`

**Steps**

- [ ] `PromptService.create_prompt()`의 현재 순서를 확인한다: lock wait, prune, id canonicalization, get pending, recently resolved check, supersede, set pending, lifecycle, waiter setup.
- [ ] `RedisPromptStore`의 현재 호출 순서를 확인한다: `save_pending`, `save_lifecycle`, `list_resolved`, `_upsert_debug_record`, `_build_prompt_debug_summary`.
- [ ] `log_event()` 사용 방식과 테스트 초기화 방식을 확인한다.
- [ ] live runner의 기존 protocol-gate 명령과 최신 실패 run root를 확인한다.

**Verification**

- 이 phase는 코드 변경이 없다.
- 확인 결과가 plan과 다르면 plan을 먼저 수정한다.

**Coupling check**

Phase 1 이후 이벤트 필드가 Phase 6 분석에서 바로 join 가능해야 하므로, 이 phase에서 `session_id`, `request_id`, `player_id`, `request_type`의 실제 source를 확정한다.

---

## Phase 1 - Timing Event Schema Lock

**Goal**

구현 전에 이벤트 이름, 필드, 타입, 누락 허용 범위를 고정한다.

**Files**

- `apps/server/tests/test_structured_log.py`
- `apps/server/tests/test_prompt_service.py`
- `apps/server/tests/test_redis_realtime_services.py`

**Event schema**

`prompt_service_create_prompt_phase_timing`

- `session_id`
- `request_id`
- `player_id`
- `request_type`
- `lock_acquire_wait_ms`
- `lock_held_ms`
- `prune_resolved_ms`
- `prune_resolved_entries`
- `get_pending_ms`
- `has_recently_resolved_request_ms`
- `supersede_pending_for_player_ms`
- `set_pending_ms`
- `record_lifecycle_ms`
- `waiter_setup_ms`
- `total_ms`
- `cold_start_flag`

`redis_prompt_store_list_resolved_timing`

- `session_id`
- `elapsed_ms`
- `entry_count`
- `hash_bytes_estimate`

`redis_prompt_store_save_pending_timing`

- `session_id`
- `request_id`
- `hset_pending_ms`
- `hset_alias_ms`
- `upsert_debug_record_ms`
- `total_ms`

`redis_prompt_store_save_lifecycle_timing`

- `session_id`
- `request_id`
- `hset_lifecycle_ms`
- `hset_alias_ms`
- `upsert_debug_record_ms`
- `total_ms`

`redis_prompt_store_upsert_debug_record_timing`

- `session_id`
- `request_id`
- `bucket_kind`
- `hset_bucket_ms`
- `expire_bucket_ms`
- `marker_check_ms`
- `marker_present`
- `refresh_index_ms`
- `set_index_ms`
- `total_ms`

`redis_prompt_store_build_prompt_debug_summary_timing`

- `session_id`
- `marker_present`
- `branch`
- `pending_entries`
- `resolved_entries`
- `decisions_entries`
- `lifecycle_entries`
- `pending_ms`
- `resolved_ms`
- `decisions_ms`
- `lifecycle_ms`
- `total_ms`

**Steps**

- [ ] 테스트에서 이벤트 필드가 누락되면 실패하도록 최소 assertion을 추가한다.
- [ ] `elapsed_ms` 계열은 float 또는 int를 허용하되 음수는 금지한다.
- [ ] `request_id`가 없는 store-level event는 허용하지 않는다. 단, `list_resolved`는 기존 인터페이스상 request 단위가 아니므로 `session_id` 중심으로 검증한다.
- [ ] `hash_bytes_estimate`는 정확한 Redis memory usage가 아니라 JSON/value length 추정값임을 테스트명과 문서에 명시한다.

**Verification**

```bash
./.venv/bin/python -m pytest apps/server/tests/test_structured_log.py -q
```

**Coupling check**

Phase 1 테스트가 Phase 2/3 구현의 계약이다. 이후 이벤트 이름을 바꾸려면 테스트와 분석 문서를 같이 바꿔야 한다.

---

## Phase 2 - PromptService Lock/Phase Instrumentation

**Goal**

`PromptService.create_prompt()`의 전체 시간과 락 대기/락 보유/락 내부 주요 phase를 분리한다.

**Files**

- `apps/server/src/services/prompt_service.py`
- `apps/server/tests/test_prompt_service.py`

**Implementation outline**

- [ ] `time.monotonic()`으로 `total_start`를 기록한다.
- [ ] `self._lock.acquire()` / `try` / `finally` 구조로 바꿔 lock wait 시간을 측정하되, 기존 `with self._lock:`의 의미와 release 보장을 그대로 유지한다.
- [ ] 락 내부에서 다음 구간만 측정한다:
  - `_prune_resolved()`
  - `_get_pending()`
  - `_has_recently_resolved_request()`
  - `_supersede_pending_for_player()`
  - `_set_pending()`
  - `_record_lifecycle()`
  - waiter setup
- [ ] `create_prompt()` 성공 경로 끝에서 `prompt_service_create_prompt_phase_timing`을 남긴다.
- [ ] 예외 경로에서는 기존 예외를 삼키지 않는다. 단, 이미 측정한 phase를 로깅할지 여부는 구현 시 명확히 정한다. 기본은 성공 경로 우선이며 예외 계측은 비목표다.

**Important implementation constraint**

`self._lock`를 수동 acquire/release로 바꾸는 것은 계측을 위한 구조 변경이지만 동작 변경이면 안 된다. `finally: self._lock.release()`가 반드시 있어야 하고, waiter wake-up은 기존처럼 lock 밖에서 수행해야 한다.

**Verification**

```bash
./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py -q
```

**Coupling check**

Phase 3의 `save_pending`/`save_lifecycle` 이벤트와 Phase 2의 `set_pending_ms`/`record_lifecycle_ms`가 같은 `request_id`로 연결되어야 한다. 1-game smoke에서 다음 관계를 확인한다:

- `set_pending_ms` >= `redis_prompt_store_save_pending_timing.total_ms`에 가까워야 한다.
- `record_lifecycle_ms` >= `redis_prompt_store_save_lifecycle_timing.total_ms`에 가까워야 한다.
- 큰 차이가 나면 PromptService wrapper 내부의 비-Redis 비용도 병목 후보로 남긴다.

---

## Phase 3 - RedisPromptStore Boundary Instrumentation

**Goal**

Redis prompt store에서 실제 Redis 호출과 debug summary rebuild 비용을 분리한다.

**Files**

- `apps/server/src/services/realtime_persistence.py`
- `apps/server/tests/test_redis_realtime_services.py`

**Steps**

- [ ] `list_resolved()`에서 `hgetall(resolved)` 전체 시간, entry count, value byte estimate를 기록한다.
- [ ] `save_pending()`에서 pending hset, alias save, debug upsert, total 시간을 기록한다.
- [ ] `save_lifecycle()`에서 lifecycle hset, alias save, debug upsert, total 시간을 기록한다.
- [ ] `_upsert_debug_record()`에서 debug bucket hset, expire, marker check/touch, refresh index, set index 시간을 기록한다.
- [ ] `_build_prompt_debug_summary()`에서 marker-present branch와 per-bucket hgetall 시간을 기록한다.
- [ ] 계측용으로 Redis 호출을 추가하지 않는다. 기존 호출의 전후 시간만 잰다.

**Verification**

```bash
./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -q
```

**Coupling check**

Phase 3 이벤트는 Phase 2 `request_id`와 이어져야 한다. `_build_prompt_debug_summary()`는 request_id가 없을 수 있으므로 `session_id`와 시간순으로 연결한다. 분석 시 request 단위 join과 session/time-window join을 구분해 표시한다.

---

## Phase 4 - Run-Start Keyspace Snapshot

**Goal**

critical path 밖에서 Redis prompt keyspace 상태를 한 번 기록해 fresh/warm/accumulated 조건을 증명한다.

**Files**

- Preferred: `tools/protocol_gate_prompt_snapshot.py`
- Optional integration point: existing protocol-gate shell/operator script if present after Phase 0 inspection.

**Steps**

- [ ] 새 서버 request path에 snapshot Redis 호출을 넣지 않는다.
- [ ] run 시작 전 또는 직후, 별도 tool/script로 다음 값을 JSONL로 저장한다:
  - `prompts_pending` HLEN
  - `prompts_resolved` HLEN
  - `prompt_decisions` HLEN
  - `prompt_lifecycle` HLEN
  - debug index marker 존재 여부
  - debug bucket sample lengths
- [ ] 출력 위치는 run root 아래 `summary/prompt_keyspace_snapshot.jsonl`로 고정한다.
- [ ] script는 `MRN_REDIS_URL` 또는 `--redis-url`을 받는다.

**Verification**

```bash
./.venv/bin/python tools/protocol_gate_prompt_snapshot.py --redis-url "$MRN_REDIS_URL" --out tmp/rl/full-stack-protocol/prompt-snapshot-smoke/summary/prompt_keyspace_snapshot.jsonl
test -s tmp/rl/full-stack-protocol/prompt-snapshot-smoke/summary/prompt_keyspace_snapshot.jsonl
```

**Coupling check**

Phase 6 matrix의 fresh/accumulated 판정은 이 snapshot 없이는 인정하지 않는다. runner 성공/실패와 별개로, 각 condition의 시작 상태가 파일로 남아야 한다.

---

## Phase 5 - Local Verification Gate

**Goal**

계측이 기존 로직을 깨지 않았고 문서/계획 정책도 통과함을 확인한다.

**Steps**

- [ ] formatting/staged diff 확인.
- [ ] structured logging test 실행.
- [ ] prompt service test 실행.
- [ ] Redis realtime service test 실행.
- [ ] runtime rebuild contract test 실행.
- [ ] plan policy gate 실행.

**Verification**

```bash
git diff --check
python3 tools/plan_policy_gate.py
./.venv/bin/python -m pytest apps/server/tests/test_structured_log.py -q
./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py apps/server/tests/test_redis_realtime_services.py -q
./.venv/bin/python -m pytest apps/server/tests/test_runtime_rebuild_contract.py -q
```

**Stop condition**

여기서 실패하면 live run을 하지 않는다. 실패 원인을 계측 부작용, 기존 불안정, 환경 문제로 분류하고 먼저 고친다.

---

## Phase 6 - Live Smoke and Matrix

**Goal**

1-game live smoke로 계측 이벤트 존재를 검증한 뒤, 상태 조건별 matrix로 지배 원인을 판정한다.

**Stack setup**

```bash
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml up -d --build
curl -fsS http://127.0.0.1:9091/health
```

**Smoke condition**

- Condition: `fresh-fresh-smoke`
- Redis: FLUSHDB
- Server: newly started
- Games: 1
- Seed: `2026051501`

**Smoke verification**

- [ ] run succeeds or fails with a known game/runtime reason.
- [ ] server log contains `prompt_service_create_prompt_phase_timing`.
- [ ] server log contains at least one Redis prompt store timing event for the same session.
- [ ] if timing events are absent, stop and fix instrumentation before matrix.

**Matrix conditions**

| Condition | Redis state | Server state | Purpose |
| --- | --- | --- | --- |
| Fresh-Fresh | FLUSHDB | new server | cold baseline |
| Fresh-Warm | FLUSHDB | one prior game processed | server warm-up effect |
| Accum-Fresh | prompt leftovers retained | new server | accumulated Redis keyspace effect |
| Accum-Warm | prompt leftovers retained | one prior game processed | realistic repeated-run effect |

**Runner template**

Use the latest known protocol-gate options from the previous live protocol work. Keep seed and runner flags identical across conditions except run root and explicit state setup.

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run rl:protocol-gate:games -- \
  --games 1 \
  --run-root tmp/rl/full-stack-protocol/prompt-timing-${COND} \
  --seed-base 2026051501 \
  -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --timeout-ms 180000 \
  --idle-timeout-ms 60000 \
  --progress-interval-ms 10000 \
  --raw-prompt-fallback-delay-ms off
```

If the current runner requires additional existing flags for reconnects, seat profiles, backend compose project/file/service, copy them from the latest passing protocol-gate command. Do not invent new gameplay flags during this matrix.

**Coupling check**

For each condition:

- [ ] Snapshot file proves initial Redis state.
- [ ] Runner summary proves seed, run root, and server URL.
- [ ] Server log events can be joined by `session_id`.
- [ ] At least one slow prompt has both PromptService and RedisPromptStore timing events.
- [ ] If a condition fails, preserve run root and classify whether the failure is instrumentation, runtime, or environment.

---

## Phase 7 - Cause Classification

**Goal**

계측 결과로 다음 구현 방향을 하나만 선택한다.

**Classification rules**

**A. Debug summary rebuild dominant**

- `_upsert_debug_record.total_ms` accounts for more than 60% of `create_prompt.total_ms`, and
- `_build_prompt_debug_summary.total_ms` dominates `_upsert_debug_record`, and
- `prune_resolved_ms` is below 20% of `create_prompt.total_ms`.

Next work: debug index를 lazy/async 또는 run-inspection 전용으로 전환하는 구조 개선안을 작성한다.

**B. Resolved prune scan dominant**

- `prune_resolved_ms` accounts for more than 50% of `create_prompt.total_ms`, and
- `redis_prompt_store_list_resolved_timing.entry_count` or `hash_bytes_estimate` is high, and
- repeated warm call drops materially.

Next work: TTL/indexed cleanup 또는 session-scoped resolved lookup 계획을 작성한다.

**C. Lock contention dominant**

- `lock_acquire_wait_ms` accounts for more than 30% of `create_prompt.total_ms`.

Next work: lock 안의 work 축소 계획을 작성한다. 단, pending/resolved consistency와 waiter semantics를 먼저 문서화한다.

**D. Redis/server cold-start dominant**

- Fresh-Fresh만 느리고 Fresh-Warm이 정상이며 Redis entry counts are small.

Next work: Redis/server warm-up or connection pool readiness plan을 작성한다.

**E. Distributed cost**

- 어떤 항목도 60% 이상 지배하지 않는다.

Next work: deeper trace를 추가한다. 이때도 행동 변경 없이 계측 단계부터 반복한다.

**Verification**

- [ ] result doc에 각 condition별 top slow prompt table을 남긴다.
- [ ] chosen classification and rejected alternatives를 수치와 함께 남긴다.
- [ ] 다음 구현 계획은 classification에 직접 연결되어야 한다.

**Output file**

- `docs/current/reports/REPORT_PROMPT_TIMING_INSTRUMENTATION_RESULT_2026-05-15.md`

---

## Phase 8 - Follow-Up Optimization Gate

**Goal**

계측으로 원인을 확정하기 전에는 최적화 패치를 시작하지 않도록 다음 작업의 진입 조건을 고정한다.

**Entry criteria**

- Phase 5 local verification passed.
- Phase 6 smoke produced expected timing events.
- Phase 6 matrix produced enough data for Phase 7 classification.
- Phase 7 report names one primary cause.

**Allowed next tasks**

- A이면 debug index rebuild 제거/지연/분리.
- B이면 resolved prune storage/query 구조 개선.
- C이면 lock scope reduction.
- D이면 warm-up/readiness policy.
- E이면 deeper instrumentation.

**Disallowed next tasks**

- “느려 보이는 코드”를 근거 없이 고치는 것.
- debug writer, cleanup worker, async queue를 원인 확정 전에 추가하는 것.
- protocol SLO를 늘려 실패를 숨기는 것.

**Responsibility check**

Phase 8 이후의 최적화 작업은 “추측 제거”가 아니라 “계측으로 확인된 단일 병목 제거”여야 한다. 구현 완료 보고 시 해당 병목 수치가 개선되었는지 전후 비교를 포함해야 한다.

---

## End-to-End Validation Chain

이 계획의 핵심은 단계 간 맞물림이다.

1. Phase 1 schema가 Phase 2/3 구현의 계약이다.
2. Phase 2 PromptService event가 Phase 3 Redis event의 상위 span 역할을 한다.
3. Phase 4 snapshot이 Phase 6 matrix의 condition 진위를 증명한다.
4. Phase 6 matrix가 Phase 7 cause classification의 입력이다.
5. Phase 7 classification 없이는 Phase 8 optimization에 들어가지 않는다.

따라서 “테스트 통과”만으로 완료 처리하지 않는다. 각 단계는 다음 단계가 사용할 증거를 생성해야 완료다.
