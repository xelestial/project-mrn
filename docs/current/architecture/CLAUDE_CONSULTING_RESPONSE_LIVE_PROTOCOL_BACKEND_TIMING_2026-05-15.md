# Claude Consulting Response — Live Protocol Backend Timing

Status: review response to `CLAUDE_CONSULTING_CONTEXT_LIVE_PROTOCOL_BACKEND_TIMING_2026-05-15.md`
Date: 2026-05-15
Revision: 2026-05-15 (Codex review 반영, `CODEX_REVIEW_DISAGREEMENTS_LIVE_PROTOCOL_BACKEND_TIMING_2026-05-15.md`)
Reviewer: Claude (independent)
Scope: 7 review questions + immediate next step

> **한 줄 요약 (TL;DR) — 정정판**: 6.7초 병목의 **유력한 후보는 두 가지**다. (a) `RedisPromptStore._build_prompt_debug_summary()`가 `_upsert_debug_record()` 호출마다 4개 bucket을 스캔하고 한 `create_prompt()`이 이를 2회 유발 = 8회 bucket read. (b) `PromptService.create_prompt()` 진입 시 호출되는 `_prune_resolved()` → `RedisPromptStore.list_resolved()` HGETALL 단일 스캔. 어느 쪽이 dominant인지, 또는 둘 다인지는 **측정되지 않았다**. 전체가 `PromptService._lock`(RLock) 아래에서 직렬화된다. 행동 변경 전에 sub-phase 계측이 먼저다 — 별도 문서 `CLAUDE_PROPOSAL_PROMPT_TIMING_INSTRUMENTATION_2026-05-15.md` 참조.

---

## Revision Note — 무엇을 정정했는가 (Codex 지적 반영)

Codex 리뷰가 다음을 정확히 지적했고 본 문서에 반영됐다:

1. **"4개 global hash를 무조건 HGETALL"은 과장이었다.** 코드에는 `_touch_debug_index_marker` + marker check 분기가 있다. marker가 있으면 per-session debug bucket을 읽는 경로로 빠진다. 따라서 "8회 = global full-hash 스캔 8회"라는 단정은 입증되지 않았다. 구조(2 rebuild × 4 bucket)는 맞지만 각 read가 글로벌인지 per-session인지는 측정 사안.
2. **"두 번째 호출 29ms = prune 때문"은 가설이지 결론이 아니다.** Redis warmup, CPU 콜드 스타트, 다른 lifecycle shape, transient stall도 모두 가능. 후보로 격하.
3. **Lock contention을 너무 빨리 일축했다.** 백그라운드 워커(`command-wakeup-worker`, `prompt-timeout-worker`)가 같은 prompt 상태를 만지는 경로가 존재. acquire/held 미측정 상태에서 dismiss하면 안 됨. 재열기.
4. **"audit/debug/lifecycle index를 critical path에서 빼야 한다"는 너무 광범위했다.** lifecycle record는 recovery contract의 일부일 가능성이 있다. debug index와 묶어서 처리하면 안 됨. 두 가지를 분리한다.
5. **`PromptAuditWriter` 제시는 시기상조였다.** authoritative vs derived 구분이 측정으로 확정된 뒤에야 컴포넌트 형태를 결정한다.
6. **`_prune_resolved()`를 secondary로 다룬 건 잘못이다.** HGETALL을 단독으로 하는 first-class suspect로 격상.

전체 방향(계측 우선, SLO 완화 금지, 책임 분리 검토)은 유지된다.

---

## Question 1. `PromptService.create_prompt()`이 한 critical path / lock 아래에서 너무 많은 일을 하는가?

**Yes — 그리고 그 부담의 대부분은 prompt 로직이 아니라 audit 인덱스 빌드다.**

`prompt_service.py:72-125`에서 `self._lock`(RLock)을 잡고 다음을 순차로 실행:

```
1. _prune_resolved()           → list_resolved() = HGETALL(prompts:resolved)
2. (식별자 정규화/검증 - 메모리)
3. _supersede_pending_for_player() = in-memory only (저비용)
4. _set_pending() → RedisPromptStore.save_pending()
     - HSET prompts:pending
     - HSET prompts:pending:aliases (mapping)
     - _upsert_debug_record("pending")
         · HSET debug_bucket_key
         · EXPIRE debug_bucket_key
         · _touch_debug_index_marker() / marker check
         · _refresh_debug_index() → _build_prompt_debug_summary()
             · marker 미존재 시: 4개 global prompt hash HGETALL
             · marker 존재 시: per-session debug bucket을 읽음
             · (어느 분기인지는 측정 필요)
         · SET debug_index_key
5. _record_lifecycle() → RedisPromptStore.save_lifecycle()
     - HSET prompts:lifecycle
     - HSET prompts:lifecycle:aliases
     - _upsert_debug_record("lifecycle")
         · 위 4-bucket read 반복 (분기 동일)
         · SET debug_index_key
```

직렬 Redis round-trip은 최소 **~12–16회**다. 그중 **2 × 4 = 8회의 bucket read**가 debug summary rebuild에서 발생한다. **그 8회가 global full-hash 스캔인지 per-session bucket 스캔인지는 marker 상태에 따라 다르며, 본 분석으로는 결정할 수 없다.** 모든 호출이 RLock 안에 있어 같은 프로세스의 다른 prompt 생성·결정 처리는 대기한다. **prompt 로직 자체는 빠르다(`prompt_materialize_ms=1`).** 비용은 영속화 자체가 아니라 영속화에 동거한 부수 작업(prune + debug index rebuild + lifecycle write)에 있다는 것까지는 코드 읽기로 단정할 수 있다.

**근거**: `realtime_persistence.py:383-505`(save_pending/save_lifecycle), `:647-705`(_upsert_debug_record), `:2237-2280`(_build_prompt_debug_summary 4× HGETALL).

---

## Question 2. `RuntimeService`/`DecisionGateway`/`PromptService`/`RedisPromptStore` 사이의 prompt 영속화 책임 분리는 올바른가?

**상위 4계층 분리는 이름상 옳지만, audit/lifecycle/debug 트레일이 `RedisPromptStore` 안에 영속화와 동거하고 있는 것이 잘못이다.**

현재 상태:

| 계층 | 책임 (이름) | 실제로 하고 있는 일 |
|------|-------------|--------------------|
| RuntimeService | engine transition timing 책임자 | `_materialize_prompt_boundary_sync`은 얇음. 좋다. |
| DecisionGateway | engine ↔ PromptService 어댑터 | request_id 정책 + `create_prompt` 호출. timing 로그 발행. |
| PromptService | prompt lifecycle 단일 권위 | lock + identity 정규화 + Redis 위임. 여기까지 OK. |
| RedisPromptStore | Redis 영속화 (CRUD) | **+ 디버그 인덱스 빌드 (audit 책임을 흡수)** |

**문제 지점은 `RedisPromptStore`** — CRUD 계층이 audit 인덱스를 합산해서 SET까지 하고 있다. audit 인덱스는 운영 가시성용이지 prompt 정합성과 무관하다. 그런데 critical path 위에 있어 SLO를 갉아먹는다.

**옳은 분리는 다음과 같아야 한다**:

- `RedisPromptStore.save_pending`/`save_lifecycle`은 단일 HSET + alias만 한다 (atomic 가능).
- audit/debug 인덱스 빌드는 별도 **`PromptAuditWriter`** (또는 background flusher)가 받는다. 비동기 fire-and-forget.
- "디버그 인덱스가 항상 최신이어야 한다"는 요구사항은 없다. eventual consistency로 충분하다.

---

## Question 3. 현재 prompt boundary materialization 모델이 구조적으로 sound한가, 누더기 패치인가?

**Materialization 자체는 sound — `prompt_materialize_ms=1`이 증거다. 누더기는 audit 레이어다.**

`_materialize_prompt_boundary_sync` / `_publish_prompt_boundary_sync`는 얇은 어댑터다. `create_prompt`를 호출하고 결과를 view로 변환한다. 이 자체는 옳은 책임 분리.

문제는 **observability 요구가 누적되면서 `RedisPromptStore`에 디버그 인덱스가 추가됐고 그것이 영속화와 분리되지 않은 것**이다. 누군가 "프롬프트 상태 디버깅이 어려워서 통합 인덱스를 만들자"고 했고, 가장 가까운 곳(`save_pending`)에 박았다. 분리할 시점을 놓쳤다. P6(거대 RuntimeService)와 같은 패턴 — observability 코드가 critical path에 응축됨.

REFERENCE 룰 위반은 아니다. SLO 위반이다.

---

## Question 4. 라이브 timing 증거는 어디를 가리키는가?

**입증되지 않음. 두 first-class 후보와 두 가지 보조 가설이 측정 대기 중이다.**

| 후보 | 증거 부합도 | 평가 |
|------|-------------|------|
| `_prune_resolved()` → `list_resolved()` HGETALL 단독 스캔 | **first-class** | RLock 진입 직후 호출. resolved hash가 누적됐다면 단독으로도 수초 가능. 단독 측정 필요. |
| `_build_prompt_debug_summary()` rebuild × 2 (save_pending + save_lifecycle) | **first-class** | 2 × 4 bucket read 구조 확정. marker 분기로 global vs per-session인지는 미확정. 측정 필요. |
| `PromptService._lock` (RLock) 대기 시간 | 재열림 | 같은 prompt 상태를 만지는 백그라운드 워커(`command-wakeup-worker`, `prompt-timeout-worker`)가 contention 유발 가능. 단일 게임이라는 사실만으론 dismiss 못 함. lock acquire/held 측정 필요. |
| Redis 연결 콜드 스타트 / Python container CPU | 약~중 | 같은 transition의 redis_commit_ms=12, view_commit 6ms가 정상이므로 연결 자체는 워밍업됨. 그러나 첫 `create_prompt`이 prune+debug rebuild 경로를 새로 깨우는 cold path를 탔을 가능성은 남음. |

**"왜 첫 호출만 느린가"는 단일 가설로 설명되지 않는다.** 가능한 설명:

- 직전 세션 잔여물이 resolved/lifecycle hash에 누적되어 첫 prune·debug rebuild가 무거웠고, 첫 호출이 그것을 비웠다.
- 첫 호출이 Redis/client/debug 경로를 워밍업했다.
- 첫 draft prompt와 두 번째 prompt의 lifecycle/debug shape가 다르다 (예: marker 미존재 → 존재로 전환됨).
- 첫 호출 도중 transient Redis/client stall.

이 중 어느 것이 dominant인지는 측정 없이 결정할 수 없다. **다음 단계는 추측이 아니라 sub-phase timing**이다 (Q5 참조).

가설이 (a) prune 또는 (b) debug rebuild로 확정되면, 둘 다 동일한 부류의 **prompt keyspace 누수 패턴**(정리 없이 누적되는 resolved/lifecycle hash)에서 비롯됐을 가능성이 높다 — P15(`_reprocessed_consumed_commands` 무한 증가)와 같은 형상.

---

## Question 5. 행동 변경 전에 어떤 instrumentation을 추가해야 하는가?

CONSULTING §Recommended Immediate Investigation에 동의. 그 위에 다음을 추가:

**필수 (이걸 먼저 봐야 답이 나옴)**:

1. `_build_prompt_debug_summary()` 진입 시 4개 HGETALL **각각의 응답 entry 수**와 elapsed_ms 로깅. 한 호출 안에서 따로.
2. `_prune_resolved()`의 `list_resolved()` 응답 entry 수와 elapsed_ms.
3. `RedisPromptStore.save_pending` / `save_lifecycle`의 sub-step별 timing (HSET, alias HSET, _upsert_debug_record total, lifecycle write total).
4. `PromptService._lock` acquire wait time vs held time. RLock이므로 reentrant 횟수도.

**선택 (causation 확정용)**:

5. Redis `OBJECT ENCODING prompts:pending` 등으로 ziplist→hashtable 전환 시점 추적.
6. 같은 seed를 fresh Redis (DBSIZE=0)에서 vs 누적 keyspace에서 실행 비교.

**미리 보지 않아도 되는 것**:

- 첫 호출의 GC pause — 가설에 불필요.
- 시스템 콜 단위 trace — overshoot.

---

## Question 6. Prompt 생성을 engine transition timing에서 빼야 하는가?

**부분적으로 yes. 단, 어느 부분이 'derived'인지 측정으로 확정한 뒤에 결정한다.**

코드 읽기 만으로 다음까지는 말할 수 있다:

- **prompt boundary materialization (1ms)**: critical path 유지. SLO 포함. 룰 결정의 일부.
- **prompt persistence (HSET pending + alias)**: critical path 유지. 클라이언트 decision/reconnect 시 즉시 권위 필요.
- **debug index rebuild (`_build_prompt_debug_summary`)**: 운영 가시성용으로 보임. critical path에서 **빼는 것이 후보**. 그러나 "어디서 이 인덱스를 읽고 어떤 freshness가 필요한지" 확인 후 결정.
- **lifecycle record write**: **추가 검토 필요**. 단순 audit 트레일이면 빼도 되지만, recovery/operator tooling이 이 기록에 의존한다면 authoritative 데이터다. 분리 전에 사용처 조사 필요. (Codex 지적)
- **`_prune_resolved` 같은 cleanup**: critical path 진입 시점에서 호출되는 게 잘못. TTL 또는 별도 cleanup 워커로 이동 후보.

**즉, "debug index를 비동기로"는 거의 확실히 옳고, "lifecycle을 비동기로"는 아직 미확정**이다. 이 둘을 묶어서 다루지 않는다.

---

## Question 7. 어떤 책임을 merge/move/delete 해야 누더기 재형성을 막는가?

> **주의 (Codex 지적 반영)**: 아래 권고는 **측정 후 결정해야 하는 옵션 집합**이다. 새 컴포넌트(예: `PromptAuditWriter`)를 만들기 전에 먼저 "무엇이 authoritative이고 무엇이 derived인가, 어떤 데이터가 transactional consistency를 요구하는가, debug index를 누가 읽으며 어떤 freshness가 필요한가"를 확정한다. 측정·조사 없이 컴포넌트만 추가하면 같은 누더기 패턴이 재형성된다.

### 측정 전에도 합의 가능한 방향

**Keep clear** (이미 합의된 책임 경계):

- `RedisPromptStore` = 영속화 CRUD만.
- `PromptService` = lifecycle 권위(in-memory state machine + Redis 위임)만.
- `DecisionGateway` = engine ↔ PromptService 어댑터만.
- `RuntimeService` = transition orchestration만.

지금은 `RedisPromptStore`가 audit/debug 인덱스 빌드까지 흡수하고 있다. 이 동거가 누더기 패턴의 시작점이라는 점은 측정 없이도 말할 수 있다.

### 측정으로 확정될 때 선택할 옵션들

**가설 A — debug summary rebuild가 dominant인 경우**:
- Delete: `_build_prompt_debug_summary()`을 매 upsert마다 호출하는 패턴.
- Move: debug index 빌드를 (a) lazy (조회 시점에만) 또는 (b) 별도 워커 주기적 빌드 중 하나로 이동. 어느 것이 적절한지는 "debug index를 누가 어떤 freshness로 읽는가" 조사 후 결정.

**가설 B — `_prune_resolved`이 dominant인 경우**:
- Delete: `create_prompt` 진입 시점의 prune 호출.
- Move: resolved 엔트리 cleanup을 (a) Redis TTL 또는 (b) prompt-timeout-worker 확장 중 하나로 이동.

**가설 C — lock contention이 dominant인 경우**:
- Move: lock 밖으로 옮길 수 있는 작업(예: identity 정규화, request_id 결정) 분리. 영속화·debug 빌드는 lock 안 또는 lock 밖이 적절한지 별도 판단.

**가설 D — Redis 콜드 스타트 또는 connection-level**:
- 진단 우선. 컴포넌트 추가 아님. 연결 풀/콜드 패스 워밍업 정책 검토.

### 모든 가설에 공통으로 적용 가능한 정리 작업 (저위험)

- `save_pending` + 그 직후의 alias HSET을 단일 Lua atomic으로 묶기 (round-trip 감소).
- `PromptService.create_prompt`와 `submit_decision`의 RLock 정책을 단일 문서화. RLock인 이유와 reentrant 호출 그래프를 명시.
- request_id 결정(identity 정규화, `_stable_prompt_request_id` 호출)을 lock 밖으로 이동 — 입력 결정 후에만 lock 진입.

이 셋은 측정과 무관하게 좋은 청소다.

---

## 결론 — 즉시 다음 행동

1. **계측만 한다.** 별도 문서 `CLAUDE_PROPOSAL_PROMPT_TIMING_INSTRUMENTATION_2026-05-15.md`에 정의된 로그 포인트를 추가하고 같은 seed (`2026051501`)를 재실행. fresh Redis vs 누적 keyspace 비교 포함.
2. 다음 가설을 측정으로 가른다 (어느 것도 사전 결론 아님):
   - (A) `_build_prompt_debug_summary` rebuild × 2이 dominant — 결과에 따라 debug index 분리 옵션.
   - (B) `_prune_resolved`의 단독 HGETALL이 dominant — 결과에 따라 TTL/cleanup worker 옵션.
   - (C) lock 대기가 dominant — 결과에 따라 lock 밖 이동 옵션.
   - (D) Redis/container 콜드 패스 — 결과에 따라 워밍업 정책 검토.
   - 여러 개가 합산되어 dominant 없이 분산된 경우도 측정 결과에 따라 다르게 대응.
3. **행동 변경은 그 다음**. CONSULTING §What Not To Do Yet의 7개 금지 항목을 그대로 따른다 — SLO 완화, identity bridge 제거, prompt 영속화 이동, 새 helper 추가 모두 보류. **특히 `PromptAuditWriter` 같은 신규 컴포넌트 추가는 측정 결과가 명확히 가설 A를 가리킬 때만**.
4. dominant 가설이 결정되면 PLAN_SERVER_RUNTIME_REBUILD의 다음 step으로 그것에 한정된 fix를 추가한다.

**측정 없이 코드 읽기로 단정할 수 있는 것은 단 하나**: prompt 영속화 critical path에 prune·debug index·lifecycle 같은 비-prompt 작업이 동거하고 있다는 사실. 어느 작업이 5초 gate를 얼마나 갉아먹는지는 측정 사안.
