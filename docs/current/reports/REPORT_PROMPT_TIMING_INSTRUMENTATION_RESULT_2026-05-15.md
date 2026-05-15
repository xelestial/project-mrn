# Prompt Timing Instrumentation Result - 2026-05-15

## Goal

`PromptService.create_prompt()` live 지연을 추측이 아니라 계측 로그로 분류한다. 이 리포트는 `PLAN_PROMPT_TIMING_INSTRUMENTATION_2026-05-15.md` Phase 6-7의 결과 문서다.

## Scope

- In scope: 1-game live protocol-gate matrix, Redis prompt keyspace snapshot, PromptService/RedisPromptStore timing event 분석, A-E 원인 분류.
- Out of scope: 최적화 구현, SLO 변경, timeout 변경, Redis key 구조 변경, 게임 룰 변경.

## Runs

All runs used the same runner shape:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run rl:protocol-gate:games -- \
  --games 1 \
  --seed-base 2026051501 \
  -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --timeout-ms 180000 \
  --idle-timeout-ms 60000 \
  --progress-interval-ms 10000 \
  --raw-prompt-fallback-delay-ms off \
  --backend-docker-compose-project project-mrn-protocol \
  --backend-docker-compose-file ../../docker-compose.protocol.yml \
  --backend-docker-compose-service server
```

| Condition | Run root | Runtime | Decisions | Duration ms |
| --- | --- | --- | ---: | ---: |
| Fresh-Fresh | `tmp/rl/full-stack-protocol/prompt-timing-fresh-fresh` | completed | 134 | 31787 |
| Fresh-Warm | `tmp/rl/full-stack-protocol/prompt-timing-fresh-warm` | completed | 134 | 33334 |
| Accum-Fresh | `tmp/rl/full-stack-protocol/prompt-timing-accum-fresh` | completed | 134 | 34008 |
| Accum-Warm | `tmp/rl/full-stack-protocol/prompt-timing-accum-warm` | completed | 134 | 36650 |

Each run has a pre-run snapshot at `summary/prompt_keyspace_snapshot.jsonl`.

| Condition | Pending | Resolved | Decisions | Lifecycle | Debug marker sample |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fresh-Fresh | 0 | 0 | 0 | 0 | 0 |
| Fresh-Warm | 0 | 0 | 0 | 0 | 0 |
| Accum-Fresh | 0 | 134 | 134 | 134 | 1 |
| Accum-Warm | 0 | 268 | 268 | 268 | 2 |

## PromptService Timing

The analysis filters each `backend_server.log` by the run's `summary.session_id`. This matters because warm-server logs contain previous run events.

| Condition | Prompt count | `create_prompt.total_ms` p50 | p95 | max | `prune_resolved_ms` p50 | `lock_acquire_wait_ms` p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Fresh-Fresh | 134 | 6.711 | 12.722 | 48.567 | 0.327 | 0.002 |
| Fresh-Warm | 134 | 6.865 | 10.868 | 63.957 | 0.332 | 0.001 |
| Accum-Fresh | 134 | 7.096 | 10.853 | 33.472 | 0.688 | 0.002 |
| Accum-Warm | 134 | 7.283 | 11.032 | 17.063 | 1.056 | 0.003 |

## Create-Path Redis Cost

For each prompt, the create-path Redis cost was matched by `request_id` to the `save_pending` and `save_lifecycle` events emitted before the `prompt_service_create_prompt_phase_timing` event.

| Condition | `save_pending + save_lifecycle` p50 | Share of prompt p50 | `upsert_debug_record_ms` p50 | Upsert share of prompt p50 | Direct hset/alias p50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fresh-Fresh | 5.273 | 0.778 | 4.847 | 0.705 | 0.410 |
| Fresh-Warm | 5.437 | 0.772 | 4.936 | 0.707 | 0.408 |
| Accum-Fresh | 5.203 | 0.725 | 4.731 | 0.660 | 0.420 |
| Accum-Warm | 5.073 | 0.686 | 4.694 | 0.624 | 0.422 |

Across all four conditions, direct Redis hset/alias work is small. The create-path store cost is dominated by debug upsert work.

## Top Slow Prompts

| Condition | Request type | Total ms | Dominant measured phases |
| --- | --- | ---: | --- |
| Fresh-Fresh | hidden_trick_card | 48.567 | set pending 37.7%, lifecycle 37.0%, get pending 18.3% |
| Fresh-Warm | trick_to_use | 63.957 | lifecycle 49.5%, prune 15.6%, set pending 8.4% |
| Accum-Fresh | trick_to_use | 33.472 | lifecycle 48.0%, set pending 15.1% |
| Accum-Warm | burden_exchange | 17.063 | get pending 39.1%, lifecycle 18.4%, prune 15.1% |

The single slowest prompts vary, but the steady create-path shape is stable: store lifecycle/pending operations dominate, and those operations are mostly debug upsert work.

## Classification

Chosen classification: **A. Debug summary rebuild dominant**.

Evidence:

- `upsert_debug_record_ms` accounts for more than 60% of `create_prompt.total_ms` at p50 in every condition:
  - Fresh-Fresh: 70.5%
  - Fresh-Warm: 70.7%
  - Accum-Fresh: 66.0%
  - Accum-Warm: 62.4%
- `save_pending + save_lifecycle` accounts for 68.6-77.8% of `create_prompt.total_ms` at p50.
- `direct hset/alias` p50 stays near 0.4ms, so the cost is not the Redis write itself.
- `redis_prompt_store_build_prompt_debug_summary_timing` is the dominant portion of debug upsert work. For example, Fresh-Fresh sums show `build_summary.total_ms=1840.364` versus `upsert_debug.total_ms=2052.290`.

Rejected alternatives:

- **B. Resolved prune scan dominant:** rejected. `prune_resolved_ms` p50 ranges from 0.327ms to 1.056ms. Even in Accum-Warm, where resolved entries reach 401, prune is not more than 50% of create time.
- **C. Lock contention dominant:** rejected. `lock_acquire_wait_ms` p95 is 0.001-0.003ms.
- **D. Redis/server cold-start dominant:** rejected. Fresh-Fresh and Fresh-Warm have similar `create_prompt.total_ms` p50 values, and accumulated conditions do not show a cold-start-only spike.
- **E. Distributed cost:** rejected. A single subpath, debug upsert/debug summary rebuild, consistently explains the majority of create-path time.

## Classified Next Work

The classification selected this implementation target: debug prompt inspection maintenance, not prompt semantics.

1. Remove `RedisPromptStore._build_prompt_debug_summary()` from the synchronous prompt create/decision path.
2. Keep authoritative prompt hashes unchanged.
3. Replace eager debug index rebuild with a lazy inspection endpoint or an explicit offline/snapshot command.
4. Preserve existing debug observability by making the slow path opt-in and outside the game decision critical path.
5. Verify with the same four-condition matrix and compare `create_prompt.total_ms`, `upsert_debug_record_ms`, and `build_prompt_debug_summary_timing`.

Status: the synchronous write-path removal is implemented and validated structurally below. The full four-condition matrix remains as a quantitative before/after comparison, not as the proof that the boundary moved.

## Optimization Follow-up

Implemented after this classification:

- `RedisPromptStore.save_pending()`, `save_lifecycle()`, `save_decision()`, `save_resolved()`, and decision acceptance no longer rebuild the prompt debug summary/index by default.
- Prompt writes still maintain the per-session debug buckets and marker, then invalidate the cached debug index.
- `RedisPromptStore.load_debug_index()` is now the lazy rebuild boundary. Debug inspection still receives a fresh one-hour-TTL index, but game prompt creation and decision submission do not pay the summary scan cost.
- `RedisGameStateStore.save_checkpoint()` and `commit_transition()` no longer rebuild the prompt debug summary while writing the debug snapshot. Stored snapshots carry a deferred prompt summary placeholder, and `load_debug_snapshot()` enriches it through the same lazy debug-index read boundary.
- Unit coverage locks this contract:
  - prompt writes must not emit `redis_prompt_store_build_prompt_debug_summary_timing`
  - debug index reads must emit `redis_prompt_store_build_prompt_debug_summary_timing`
  - lazy rebuilds must use per-session debug buckets, not global prompt hashes
  - game-state debug snapshot writes must not rebuild the prompt summary, while debug snapshot reads must still return prompt counts and active prompt details

Verified locally:

```bash
./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -q -k 'debug_snapshot_defers_prompt_summary_rebuild_until_read or game_debug_snapshot_includes_prompt_and_command_reconstruction_summaries or prompt_debug_index_rebuilds_lazily or prompt_store_logs_write_timing_without_eager_debug_summary_rebuild or prompt_store_debug_summary_rebuilds_on_debug_index_read or prompt_debug_index_lazy_rebuild_uses_session_buckets'
./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_prompt_service.py apps/server/tests/test_runtime_service.py -q
```

Result:

- targeted lazy-debug/snapshot tests: `6 passed, 65 deselected`
- prompt/Redis/runtime suite: `296 passed, 14 subtests passed`

Live smoke after rebuilding the Docker protocol stack:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run rl:protocol-gate:games -- \
  --games 1 \
  --seed-base 2026051503 \
  --run-root /Users/sil/Workspace/project-mrn/tmp/rl/full-stack-protocol/prompt-timing-lazy-debug-smoke-final \
  -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --timeout-ms 180000 \
  --idle-timeout-ms 60000 \
  --progress-interval-ms 10000 \
  --raw-prompt-fallback-delay-ms off \
  --backend-docker-compose-project project-mrn-protocol \
  --backend-docker-compose-file ../../docker-compose.protocol.yml \
  --backend-docker-compose-service server
```

Result:

- run root: `tmp/rl/full-stack-protocol/prompt-timing-lazy-debug-smoke-final`
- runtime status: `completed`
- session id: `sess_DQofh8br2MUKzPUt2u9rQLf5`
- decisions: `219`
- duration: `72955ms`
- max command: `431ms`
- slow command count: `0`
- `redis_prompt_store_build_prompt_debug_summary_timing`: `0`
- `redis_prompt_store_upsert_debug_record_timing`: `1752`; all sampled records had `refresh_requested=false`

The structural boundary move is therefore proven in a production-like 1-game live smoke: prompt debug summary rebuild no longer appears in the game write path. A full four-condition matrix remains useful only for a quantitative latency delta against the earlier baseline.

## Responsibility Check

The completed instrumentation moved bottleneck attribution responsibility from subjective code reading to structured timing evidence. The follow-up optimization moved prompt debug summary/index maintenance out of the synchronous game prompt write path and into the explicit debug inspection boundary, including debug snapshot reads. It did not move or weaken runtime authority. Redis pending/resolved/decision hashes remain authoritative.
