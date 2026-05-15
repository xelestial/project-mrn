# Claude Consulting Response — Live Protocol Backend Timing

Status: review response to `CLAUDE_CONSULTING_CONTEXT_LIVE_PROTOCOL_BACKEND_TIMING_2026-05-15.md`
Date: 2026-05-15
Reviewer: Claude (independent)
Scope: 7 review questions + immediate next step

> **한 줄 요약 (TL;DR)**: 6.7초 병목의 가장 강력한 단일 후보는 **`RedisPromptStore._build_prompt_debug_summary()`가 `_upsert_debug_record()` 호출마다 4개 prompt hash(pending/resolved/decisions/lifecycle)를 무조건 HGETALL 스캔**하는 동작이다. 한 번의 `create_prompt()`가 이 스캔을 **8회** 유발하고 (save_pending + save_lifecycle 각각이 debug upsert를 한 번씩), 전체가 `PromptService._lock`(RLock) 안에서 직렬화된다. 진짜 문제는 prompt 영속화가 아니라 **prompt 영속화 경로에 디버그/감사(audit) 인덱스 빌드가 critical path에 박혀 있는 것**이다.

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
         · _refresh_debug_index() → _build_prompt_debug_summary()
             · HGETALL prompts:pending
             · HGETALL prompts:resolved
             · HGETALL prompts:decisions
             · HGETALL prompts:lifecycle
         · SET debug_index_key
5. _record_lifecycle() → RedisPromptStore.save_lifecycle()
     - HSET prompts:lifecycle
     - HSET prompts:lifecycle:aliases
     - _upsert_debug_record("lifecycle")
         · 위 4-HGETALL 스캔 반복
         · SET debug_index_key
```

직렬 Redis round-trip 최소 **~12–16회**, 그중 **8회가 full-hash HGETALL**. 모든 호출이 RLock 안에 있어 같은 프로세스 안의 다른 prompt 생성·결정 처리는 대기한다. **prompt 로직 자체는 빠르다(`prompt_materialize_ms=1`).** 비용은 audit/debug 인덱스 빌드에 있다.

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

**가장 강한 단일 후보: `_build_prompt_debug_summary()`의 4× HGETALL × 2 (per `create_prompt`).**

증거 정렬:

| 가설 | 증거 부합도 | 평가 |
|------|-------------|------|
| Redis prompt alias/lifecycle/debug writes | **강함** | `_upsert_debug_record`가 4 HGETALL을 무조건 수행. keyspace 크기에 선형. |
| Python lock contention | 약함 | 단일 게임 단일 player가 첫 prompt 생성 중. 경쟁자 없음. |
| Container cold path / CPU | 중간 | 첫 호출만 느린 점이 부합하지만, "두 번째 호출 29ms"는 keyspace가 비어서 HGETALL이 가벼워졌다는 가설로도 동일하게 설명된다. |
| Redis connection 콜드 스타트 | 약함 | 같은 transition 안에서 redis_commit_ms=12, view_commit 빌드 6ms는 정상. 연결은 이미 워밍업됨. |

**"왜 첫 호출만 느린가"에 대한 자연스러운 설명**: 게임 시작 직후의 Redis 상태에 직전 세션들의 prompt 잔여물이 누적되어 있을 수 있다 (특히 `_prune_resolved`이 호출되지 않고 TTL 없이 남은 resolved/lifecycle 엔트리). 첫 `create_prompt`이 `_prune_resolved()`를 호출하면서 `list_resolved()` HGETALL이 무거운 hash를 전부 받고, 이어지는 `_upsert_debug_record`의 4× HGETALL도 무겁다. 두 번째 호출 때는 prune이 끝나서 가볍다.

이 가설이 맞다면 **`_reprocessed_consumed_commands`(P15) 무한 증가와 동일한 부류의 누수**가 prompt resolved/lifecycle hash에 일어나고 있을 가능성이 높다. 즉 정리 없이 누적된 hash가 매 prune/디버그 빌드의 비용을 키운다.

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

**부분적으로 yes. 구분이 필요하다.**

- **prompt boundary materialization (1ms)**: critical path에 남아야 한다. SLO에 포함. 이건 룰 결정의 일부다.
- **prompt persistence (HSET pending + alias)**: critical path에 남아야 한다. 클라이언트가 reconnect/decision을 보낼 때 즉시 권위가 있어야 한다. SLO 포함.
- **audit/debug/lifecycle index**: critical path에서 **빼야 한다**. async writeback. SLO 미포함.
- **`_prune_resolved` 같은 cleanup**: critical path에서 빼야 한다. 백그라운드 워커 또는 Redis TTL에 위임.

이렇게 갈라야 prompt boundary atomicity는 보존하면서 audit overhead가 5초 gate를 깨지 않는다.

---

## Question 7. 어떤 책임을 merge/move/delete 해야 누더기 재형성을 막는가?

**Delete**:

- `_build_prompt_debug_summary()`의 무조건적 4-HGETALL 스캔을 critical path에서 **삭제**. 디버그 인덱스가 필요하면 별도 워커가 N초 주기로 빌드하거나, 요청 시점에만 빌드 (lazy).
- `_prune_resolved()`을 `create_prompt` 진입 시점에 호출하는 패턴 삭제. Redis TTL 또는 정기 cleanup 워커로 이동.

**Move**:

- `_upsert_debug_record`/`_refresh_debug_index` → 새 `PromptAuditService` 또는 `prompt-audit-worker`로 이동. `RedisPromptStore`는 CRUD만.
- request_id 결정 (identity 정규화, `_stable_prompt_request_id` 호출)을 lock **밖**으로 이동. 입력이 결정되면 그 후 lock 안으로 들어간다.

**Merge**:

- `save_pending` + `save_lifecycle`의 alias 쓰기를 단일 Lua 스크립트로 묶기. 두 번의 round-trip을 한 번으로.
- `PromptService.create_prompt`와 `PromptService.submit_decision`의 RLock 정책을 단일 도큐먼트화. RLock인 이유와 reentrant 호출 그래프를 명시.

**Keep clear**:

- `RedisPromptStore` = 영속화만.
- `PromptService` = lifecycle 권위(in-memory state machine + Redis 위임)만.
- `DecisionGateway` = engine ↔ PromptService 어댑터만.
- `RuntimeService` = transition orchestration만.

이 네 경계가 깔끔해지면 누군가 다음에 또 observability/디버그 도구를 추가할 때 갈 곳이 명확해진다(audit worker). 지금은 어디에 붙여야 할지 모호해서 "가장 가까운 곳"인 RedisPromptStore에 박혔다.

---

## 결론 — 즉시 다음 행동

1. **계측만 한다.** 위 §5의 1~4번 instrumentation을 추가하고 같은 seed를 재실행.
2. 두 가설을 가른다:
   - (a) `_build_prompt_debug_summary` HGETALL 4× 스캔이 dominant — 그러면 audit 분리가 정답.
   - (b) `_prune_resolved`의 list_resolved() 단독 스캔이 dominant — 그러면 TTL/cleanup worker가 정답.
   - (a)와 (b)는 동일한 keyspace 누수 패턴에서 비롯되므로 둘 다일 가능성이 높다.
3. **행동 변경은 그 다음**. CONSULTING §What Not To Do Yet의 7개 금지 항목을 그대로 따른다 — SLO 완화, identity bridge 제거, prompt 영속화 이동, 새 helper 추가 모두 보류.
4. audit 분리가 확인되면 PLAN_SERVER_RUNTIME_REBUILD의 다음 step으로 **PromptAuditWriter 분리**를 추가한다.

이 진단이 맞다면 5초 gate를 완화하지 않고도 통과 가능하다. 6.7초의 ~99%는 룰·결정·영속화가 아니라 audit 인덱스 빌드 비용이다.
