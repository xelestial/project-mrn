# Prompt Timing Sub-phase Instrumentation Proposal

Status: implementation proposal — instrumentation only, no behavior change
Date: 2026-05-15
Author: Claude
근거 문서:
- `CLAUDE_CONSULTING_CONTEXT_LIVE_PROTOCOL_BACKEND_TIMING_2026-05-15.md`
- `CLAUDE_CONSULTING_RESPONSE_LIVE_PROTOCOL_BACKEND_TIMING_2026-05-15.md`
- `CODEX_REVIEW_DISAGREEMENTS_LIVE_PROTOCOL_BACKEND_TIMING_2026-05-15.md`

> **목적**: `PromptService.create_prompt()`의 6,681ms (라이브 측정) 원인을 가르기 위한 sub-phase 계측. 본 문서는 **로그 포인트와 측정 절차만** 정의한다. 어떤 행동도 변경하지 않는다. 측정 결과에 따라 어떤 fix가 옳은지가 결정된다.

---

## 0. 핵심 원칙

1. **현재 5초 SLO를 변경하지 않는다.**
2. **새 helper / 컴포넌트를 추가하지 않는다.** 로그만 추가.
3. **lock 동작을 변경하지 않는다.** acquire/held 측정만.
4. **Redis 명령 자체는 바꾸지 않는다.** 호출 전/후에 timer만 둔다.
5. 모든 로그는 기존 logging 인프라(structured log) 위에 새 `event` 키로 추가. 새 sink 없음.

---

## 1. 가르려는 가설

| 가설 | dominant 시 시사점 |
|------|---------------------|
| (A) `_build_prompt_debug_summary` rebuild × 2이 dominant | debug index 빌드를 lazy/async로 분리 옵션 |
| (B) `_prune_resolved`의 단독 HGETALL이 dominant | resolved hash에 TTL 또는 별도 cleanup worker 옵션 |
| (C) `PromptService._lock` 대기 시간이 dominant | lock 밖으로 이동 가능한 작업(예: identity 정규화) 분리 옵션 |
| (D) Redis 콜드 스타트 또는 connection-level | 연결 풀/콜드 패스 워밍업 정책 검토 옵션 |
| (E) 어느 것도 단독 dominant 아님 | 여러 fix를 조합 또는 더 깊은 trace |

측정 없이 어느 가설도 채택하지 않는다.

---

## 2. 계측 추가 위치 (로그 포인트)

### 2.1 `apps/server/src/services/prompt_service.py` — `create_prompt()`

함수 진입 직후, `self._lock` 획득 전/후에 monotonic timer를 둔다. 각 sub-step 종료마다 elapsed_ms를 누적한다.

추가 로그 (event 이름 제안):

```
prompt_service_create_prompt_phase_timing
  request_id
  session_id
  player_id
  request_type
  lock_acquire_wait_ms
  lock_held_ms
  prune_resolved_ms
  prune_resolved_entries
  get_pending_ms
  has_recently_resolved_request_ms
  supersede_pending_for_player_ms
  set_pending_ms
  record_lifecycle_ms
  waiter_setup_ms
  total_ms
  cold_start_flag             # process 시작 후 첫 create_prompt 호출인지
```

`lock_acquire_wait_ms`: `time.monotonic()` 차이로 측정 (acquire 직전→직후).
`lock_held_ms`: acquire→release 차이.
`cold_start_flag`: module-level boolean `_first_create_prompt_seen`를 False로 두고 첫 호출 시 True 로깅 후 토글.

### 2.2 `apps/server/src/services/realtime_persistence.py` — `RedisPromptStore`

#### 2.2.1 `list_resolved()` (P15·prune 후보)

```
redis_prompt_store_list_resolved_timing
  session_id
  elapsed_ms
  entry_count                  # 반환된 hash entry 수
  hash_bytes_estimate          # 가능하면 ÉCHANGE: HLEN 대신 응답 크기 합산
```

#### 2.2.2 `save_pending()` sub-step

```
redis_prompt_store_save_pending_timing
  request_id
  session_id
  hset_pending_ms
  hset_alias_ms
  upsert_debug_record_ms       # 전체
  total_ms
```

#### 2.2.3 `save_lifecycle()` sub-step

```
redis_prompt_store_save_lifecycle_timing
  request_id
  session_id
  hset_lifecycle_ms
  hset_alias_ms
  upsert_debug_record_ms       # 전체
  total_ms
```

#### 2.2.4 `_upsert_debug_record()` sub-step (핵심)

```
redis_prompt_store_upsert_debug_record_timing
  bucket_kind                  # "pending" | "lifecycle" | ...
  session_id
  hset_bucket_ms
  expire_bucket_ms
  marker_check_ms
  marker_present               # bool
  refresh_index_ms             # 전체 (아래 4-bucket 합산 포함)
  set_index_ms
  total_ms
```

#### 2.2.5 `_build_prompt_debug_summary()` per-bucket (Codex 지적의 핵심)

```
redis_prompt_store_build_prompt_debug_summary_timing
  session_id
  marker_present               # marker 분기 명시
  branch                       # "global_hashes" | "per_session_buckets"
  bucket_a_name                # 실제 읽은 key 이름
  bucket_a_elapsed_ms
  bucket_a_entry_count
  bucket_b_name
  bucket_b_elapsed_ms
  bucket_b_entry_count
  bucket_c_name
  bucket_c_elapsed_ms
  bucket_c_entry_count
  bucket_d_name
  bucket_d_elapsed_ms
  bucket_d_entry_count
  total_ms
```

이 로그가 **`(A) vs marker 분기` 가설을 직접 가른다**: branch 필드가 `global_hashes`로 찍히고 entry_count가 큰 값이면 가설 A가 dominant. branch가 `per_session_buckets`로 찍히고 entry_count가 작으면 debug rebuild는 dominant 아님.

### 2.3 Run-start Redis 스냅샷

같은 protocol gate 실행 시작 시 한 번만 다음을 로그:

```
redis_prompt_keyspace_snapshot_start
  prompts_pending_hlen
  prompts_resolved_hlen
  prompts_decisions_hlen
  prompts_lifecycle_hlen
  debug_marker_exists          # bool
  per_session_debug_bucket_sample_lengths   # 최대 5개 sample
```

`HLEN`은 O(1) Redis 명령이므로 안전하게 critical path 밖에서 한 번 수행.

---

## 3. 측정 절차

### 3.1 실행 매트릭스

같은 seed (`2026051501`)를 다음 4가지 조건에서 각각 한 번씩 실행한다:

| 조건 | Redis 상태 | 서버 프로세스 |
|------|------------|---------------|
| Fresh-Fresh | `FLUSHDB` 직후 | 새로 시작 |
| Fresh-Warm | `FLUSHDB` 직후 | 이미 한 게임을 처리한 프로세스 |
| Accum-Fresh | 직전 runs의 prompt 잔여물 있음 | 새로 시작 |
| Accum-Warm | 잔여물 있음 | 이미 한 게임 처리한 프로세스 |

이 4-매트릭스가 (A)/(D) 가설을 가른다:

- Fresh-Fresh가 빠르고 Accum-Fresh가 느리면 → Redis keyspace 누적이 dominant (가설 A 또는 B).
- Fresh-Fresh가 느리고 Fresh-Warm이 빠르면 → 프로세스 콜드 패스가 dominant (가설 D).
- 둘 다 영향 있으면 합산 효과.

### 3.2 실행 명령 (CONSULTING §Latest Live Failure 형식 그대로)

```bash
cd /Users/sil/Workspace/project-mrn/apps/web

npm run rl:protocol-gate:games -- \
  --games 1 \
  --run-root tmp/rl/full-stack-protocol/instrumentation-${COND} \
  --seed-base 2026051501 \
  -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --timeout-ms 180000 \
  --idle-timeout-ms 60000 \
  --progress-interval-ms 10000 \
  --raw-prompt-fallback-delay-ms off \
  --reconnect after_start,after_first_commit,after_first_decision,round_boundary,turn_boundary \
  --seat-profiles '1=baseline,2=cash,3=shard,4=score' \
  --backend-docker-compose-project project-mrn-protocol \
  --backend-docker-compose-file ../../docker-compose.protocol.yml \
  --backend-docker-compose-service server
```

각 실행 전후 Redis 상태를 기록:

```bash
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml \
  exec redis redis-cli DBSIZE
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml \
  exec redis redis-cli HLEN mrn:protocol:prompts:pending
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml \
  exec redis redis-cli HLEN mrn:protocol:prompts:resolved
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml \
  exec redis redis-cli HLEN mrn:protocol:prompts:decisions
docker compose -p project-mrn-protocol -f docker-compose.protocol.yml \
  exec redis redis-cli HLEN mrn:protocol:prompts:lifecycle
```

### 3.3 결과 비교 — 분석 쿼리

각 실행의 server 로그에서 다음을 추출:

```
1. 첫 DraftModule draft_card prompt의 prompt_service_create_prompt_phase_timing 전체
2. 첫 DraftModule의 redis_prompt_store_build_prompt_debug_summary_timing 두 인스턴스
   (save_pending 경로, save_lifecycle 경로)
3. 첫 DraftModule의 redis_prompt_store_list_resolved_timing
4. 두 번째 DraftModule prompt (정상 29ms 케이스)의 동일 셋
```

비교 표 (실제 작성):

| 조건 | total_ms | lock_acquire_ms | lock_held_ms | prune_resolved_ms | save_pending.upsert_debug_ms | save_lifecycle.upsert_debug_ms | debug_summary.branch | debug_summary.total_ms |
|------|----------|-----------------|--------------|-------------------|------------------------------|--------------------------------|---------------------|------------------------|
| Fresh-Fresh | ? | ? | ? | ? | ? | ? | ? | ? |
| Fresh-Warm | ? | ? | ? | ? | ? | ? | ? | ? |
| Accum-Fresh | ? | ? | ? | ? | ? | ? | ? | ? |
| Accum-Warm | ? | ? | ? | ? | ? | ? | ? | ? |

---

## 4. 판단 기준

측정 후 다음 규칙으로 dominant 가설을 결정한다. 임계는 권고치이며 측정 결과에 따라 재조정 가능.

### 4.1 가설 A (debug summary rebuild) 채택 조건

다음 모두 충족:
- `save_pending.upsert_debug_ms + save_lifecycle.upsert_debug_ms > 0.6 × total_ms`
- `debug_summary.branch == "global_hashes"` 또는 entry_count 큰 per-session bucket
- `prune_resolved_ms < 0.2 × total_ms`

채택 시 다음 검토:
- debug index를 누가 읽는가 (operator dashboard, /metrics endpoint, support tool, 없음?)
- 필요 freshness (실시간? 분 단위? 호출 시점만?)
- 위 답에 따라 (a) lazy build (조회 시점) (b) periodic worker (c) 완전 제거 중 선택

### 4.2 가설 B (`_prune_resolved`) 채택 조건

다음 모두 충족:
- `prune_resolved_ms > 0.5 × total_ms`
- `list_resolved.entry_count`가 첫 호출에서 큰 값 (수백~수천)
- 두 번째 호출에서 entry_count가 크게 줄거나 0

채택 시:
- resolved 엔트리에 Redis TTL 부여 검토 (예: 10분, 1시간)
- 또는 prompt-timeout-worker 확장으로 정기 cleanup
- `create_prompt` 진입 시점의 inline prune 제거

### 4.3 가설 C (lock contention) 채택 조건

다음 충족:
- `lock_acquire_wait_ms > 0.3 × total_ms`
- 같은 시간대 다른 thread/task가 같은 `PromptService`를 사용 중인 흔적 (다른 로그에서 cross-reference)

채택 시:
- lock 밖으로 이동 가능한 작업 식별 (identity 정규화, request_id 결정 등)
- RLock의 reentrant 사용 패턴 문서화
- background worker가 lock을 길게 잡는 경로 조사

### 4.4 가설 D (Redis/container cold path) 채택 조건

다음 충족:
- Fresh-Fresh가 Accum-Fresh와 비슷하게 느리고, Fresh-Warm/Accum-Warm은 빠름
- 즉 dominance가 keyspace보다 process warmup에 비례

채택 시:
- Redis client connection pool 워밍업
- 첫 prompt 직전에 dummy HGETALL을 실행하는 startup probe 검토 (최종 fix 아님, 진단용)

### 4.5 가설 E (분산) 처리

dominant가 없으면 (어느 가설도 60% threshold 미달):
- 측정을 한 단계 더 깊게: Redis OBJECT ENCODING, Python gc.stats(), thread 별 timer
- 컴포넌트 변경 없이 추가 trace

---

## 5. 안전성

본 instrumentation은 다음을 보장한다:

- 모든 timing은 `time.monotonic()` 기반. 추가 system call 없음.
- Redis 호출 수는 변하지 않음. 단 run-start snapshot은 HLEN 4회 추가 (O(1)).
- 새 lock·thread·queue 없음.
- 기존 log sink 사용. 새 endpoint 없음.

성능 영향: 호출당 ~10μs 추가 예상. 6.7s 신호 대비 noise 수준.

배포 영향: 단일 파일 수정 (prompt_service.py, realtime_persistence.py)만으로 가능. 별도 worker 변경 없음.

---

## 6. 본 문서가 하지 않는 것

- 컴포넌트 추가 제안하지 않음.
- 행동 변경(SLO, lock 정책, 영속화 위치) 제안하지 않음.
- `PromptAuditWriter` 또는 다른 분리 helper를 결론으로 채택하지 않음.
- 측정 결과를 미리 단정하지 않음.

이 모든 결정은 §3 측정 결과를 본 후 별도 문서에서 진행한다.

---

## 7. 다음 산출물 (측정 후 작성될 문서)

- `CLAUDE_FINDINGS_PROMPT_TIMING_INSTRUMENTATION_<DATE>.md` — 측정 결과 표 + dominant 가설 + fix 권고
- (필요 시) `CLAUDE_PROPOSAL_PROMPT_<FIX_TARGET>_<DATE>.md` — fix별 별도 제안서

본 문서는 산출물이 아니라 **측정 정의서**다.
