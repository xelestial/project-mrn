# Codex Review Disagreements - Claude Live Protocol Backend Timing Response

Status: review note before adopting Claude's recommendation
Date: 2026-05-15
Target document: `CLAUDE_CONSULTING_RESPONSE_LIVE_PROTOCOL_BACKEND_TIMING_2026-05-15.md`

## Position

Claude's main direction is useful: the latest live failure is very likely in the
prompt creation/persistence/observability path, not in game rules or protocol
identity routing.

However, several claims need correction or stronger evidence before they are used
as an implementation plan. The safe next step remains instrumentation first, not
behavior change.

## Hard To Accept As Written

### 1. "4개 prompt hash를 무조건 HGETALL" is overstated

Claude says `_build_prompt_debug_summary()` unconditionally scans the four global
prompt hashes:

- `prompts:pending`
- `prompts:resolved`
- `prompts:decisions`
- `prompts:lifecycle`

The current code is more conditional than that.

Relevant code:

- `apps/server/src/services/realtime_persistence.py`
  - `_upsert_debug_record()` calls `_touch_debug_index_marker()` before refresh.
  - `_build_prompt_debug_summary()` checks `_prompt_debug_marker_key(...)`.
  - When the marker exists, it reads the per-session debug bucket keys instead of
    the global prompt hashes.

So the accurate statement is:

> One `create_prompt()` can still trigger repeated debug summary rebuilds, and each
> rebuild reads four Redis buckets. But those buckets are normally session debug
> buckets after the marker exists, not necessarily the four global prompt hashes.

The performance concern remains plausible, but the exact mechanism must be measured
instead of asserted as a global hash scan.

### 2. "8회 full-hash HGETALL" is not proven

Claude counts:

- `save_pending()` -> `_upsert_debug_record()` -> summary rebuild
- `save_lifecycle()` -> `_upsert_debug_record()` -> summary rebuild
- each rebuild reads four buckets

The "2 rebuilds x 4 buckets" structure is correct. What is not proven is that all
eight reads are expensive full-hash scans over large global structures.

They may be:

- per-session debug bucket scans,
- small but slow due to Redis/client/container scheduling,
- large because debug buckets accumulated,
- or not the dominant cost at all if `_prune_resolved()` or another call dominates.

This is exactly why sub-phase timing and bucket counts are required before a design
change.

### 3. "두 번째 호출 29ms는 prune 후 가벼워졌기 때문" is a hypothesis, not evidence

The observed fact is:

- first `DraftModule` prompt path: `create_prompt_ms=6681`, transition total 6772ms
- next `DraftModule` prompt path after accepted decision: total 29ms

Claude explains this as keyspace cleanup/prune making the second call cheap. That
may be true, but the current evidence does not prove it.

Other plausible explanations:

- first prompt creation warmed Redis/client/debug paths,
- first draft prompt hit a cold CPU/container scheduling path,
- first prompt had a different lifecycle/debug shape than the second,
- first prompt was delayed by a transient Redis/client stall,
- the second prompt may have skipped or shortened a path that was not yet measured.

The document should mark this as a candidate explanation, not a conclusion.

### 4. Python lock contention is dismissed too quickly

Claude rates Python lock contention as weak because the run is a single game.
That is not sufficient.

Reasons:

- the server process may still have workers/background tasks touching the same
  prompt service or Redis-backed prompt state,
- the RLock held time can be large even without another foreground player,
- lock wait time and lock held time were not measured,
- a single-game test does not prove there was no in-process contention.

Lock contention may still be unlikely, but it should not be dismissed without
explicit lock acquire/held timing.

### 5. "audit/debug/lifecycle index는 critical path에서 빼야 한다" is directionally right but too broad

Debug index rebuild looks like a good candidate for removal from the critical path.
But lifecycle itself may be part of the authoritative audit/recovery contract,
depending on current recovery and operator tooling.

The safer split is:

- keep the minimum authoritative prompt state write in the critical path,
- keep only lifecycle writes that are required for correctness/recovery,
- move derived debug index rebuilds out of the critical path,
- prove whether lifecycle records themselves are correctness data or observability
  data before moving them.

In other words, "debug index async" is probably correct. "audit/lifecycle async" is
not yet proven.

### 6. "PromptAuditWriter" may be premature

Claude proposes a new `PromptAuditWriter` or worker. That may become the right
shape, but creating another service too early risks repeating the existing
patchwork pattern.

Before adding a component, the implementation plan should answer:

- Which data is authoritative?
- Which data is derived?
- Which data must be transactionally consistent with pending prompt creation?
- Which data can be eventually consistent?
- What reads the current debug index, and what freshness does it require?
- Is a periodic rebuild enough, or should debug views be request-time/lazy?

Only after those answers should a new writer/worker be introduced.

### 7. The response underplays `_prune_resolved()`

`PromptService.create_prompt()` calls `_prune_resolved()` immediately after acquiring
the lock. `RedisPromptStore.list_resolved()` uses `HGETALL` over resolved prompts.

This could be the dominant cost, either alone or combined with debug summary
refresh. Claude mentions it, but the TL;DR strongly focuses on debug summary rebuild.

The next measurement must treat `_prune_resolved()` as a first-class suspect, not a
secondary detail.

## Parts I Agree With

These points are strong enough to preserve:

1. The latest failure is not evidence of a game-rule failure.
2. The latest failure is not evidence that the protocol identity route change
   failed.
3. The failure concentrates in prompt creation timing:
   `create_prompt_ms=6681`, `replay_wait_ms=53`, transition total 6772ms.
4. The current code puts non-trivial Redis/debug work under `PromptService._lock`.
5. The 5000ms backend timing gate should not be relaxed.
6. The next step should be instrumentation before behavior change.

## Required Evidence Before Adoption

Add structured timing and count logs for:

1. `PromptService.create_prompt()`
   - lock acquire wait time
   - lock held time
   - `_prune_resolved()`
   - `_get_pending()`
   - `_has_recently_resolved_request()`
   - `_supersede_pending_for_player()`
   - `_set_pending()`
   - `_record_lifecycle()`
2. `RedisPromptStore`
   - `list_resolved()` elapsed and entry count
   - `save_pending()` sub-step elapsed
   - `save_lifecycle()` sub-step elapsed
   - `_upsert_debug_record()` elapsed
   - `_refresh_debug_index()` elapsed
   - `_build_prompt_debug_summary()` per-bucket elapsed and entry count
   - whether summary used session debug buckets or global prompt hashes
3. Redis state at run start
   - relevant hash lengths
   - debug marker existence
   - per-session debug bucket lengths

## Adoption Rule

Do not adopt "PromptAuditWriter" or async audit separation until instrumentation
proves which part dominates.

If the dominant cost is debug summary rebuild, the first behavioral fix should be
limited to derived debug index refresh, not prompt correctness persistence.

If the dominant cost is `_prune_resolved()`, the first behavioral fix should be TTL
or cleanup ownership, not audit writer extraction.

If neither dominates, revisit Redis client behavior, lock behavior, and container
runtime scheduling before changing the architecture.
