# Redis Authoritative Game State Plan

## Goal

Move MRN from process-owned game state to Redis-owned game state.

After this migration, the FastAPI backend and the engine may hold temporary local variables while handling one command, prompt, or engine tick, but they must not be the source of truth for live rooms, live sessions, current game state, stream history, prompts, runtime status, or active analysis data. Redis is the authoritative store for active and recently-finished game sessions. The frontend never connects to Redis directly; it only talks to the backend API and websocket/SSE endpoints.

Long-term retention is a separate concern. In the first rollout, finished game logs, summaries, and replay exports should be written to backend-local JSON files after the Redis reconnect/support window ends. A colder external persistent store can replace that local JSON archive later if operations require it.

## Benchmarked Patterns

The design follows the public architecture patterns used by commercial realtime games and managed Redis providers:

- Authoritative server model: clients submit intents; trusted server/runtime validates and applies them.
- Event log plus materialized state: every accepted state transition is appended to a durable ordered log, then a compact current-state snapshot is updated.
- Hot realtime indexes: lobby lists, active sessions, player presence, prompt deadlines, and reconnect windows are maintained in Redis data structures optimized for low-latency reads.
- Atomic mutation boundary: command application uses Redis transactions or Lua scripts so one decision cannot partially mutate room/session/game state.
- Recoverable workers: if an engine/backend process restarts, another process can resume from Redis ownership, leases, prompts, and stream offsets.

Reference basis:

- Redis Hashes: object records and counters: https://redis.io/docs/latest/develop/data-types/hashes/
- Redis Streams: append-only event streams and consumer groups: https://redis.io/docs/latest/develop/data-types/streams/
- Redis persistence: RDB/AOF durability tradeoffs: https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
- Redis distributed locks: lock/lease pattern: https://redis.io/docs/latest/develop/clients/patterns/distributed-locks/
- Google Memorystore game use cases: low latency profiles, leaderboards, stream processing: https://docs.cloud.google.com/memorystore/docs/redis/memorystore-for-redis-overview
- AWS ElastiCache gaming leaderboard pattern: realtime ranking moved from relational storage to Redis: https://aws.amazon.com/blogs/database/building-a-real-time-gaming-leaderboard-with-amazon-elasticache-for-redis/

## Operational Topology

Target runtime shape:

```text
client -> backend api/ws -> redis <- engine worker
                                   <- timeout worker
                                   <- json export worker
```

Responsibilities:

- Backend is the trusted gateway. It authenticates users, validates commands, reads and writes Redis, and streams state to clients.
- Redis is the live game system of record for active rooms and sessions.
- Engine workers are transition executors. They do not own state between transitions.
- Archive or analytics workers move finished-session data out of Redis after the hot window.

This means the backend still "handles" game traffic, but it should stop "owning" game state in process memory.

## Current State Ownership To Remove

Current server ownership points:

- `SessionService` owns `_sessions` in memory and optionally persists to JSON.
- `RoomService` owns `_rooms`, `_session_to_room`, `_next_room_no` in memory and optionally persists to JSON.
- `StreamService` owns `_seq`, `_buffers`, `_subscribers`, `_drop_counts` in memory and optionally persists stream state to JSON.
- `RuntimeService` owns `_runtime_tasks`, `_watchdogs`, `_status`, `_last_activity_ms`, `_fallback_history` in memory.
- `GameEngine.run()` creates and mutates `GameState` inside one runtime process, then emits events.

Target ownership:

- Redis owns live rooms, live sessions, runtime metadata, prompt state, game snapshots, engine checkpoints, event streams, reconnect cursors, and hot analysis events.
- Backend keeps only connection-local websocket queues and stateless request handling.
- Runtime workers keep only a short-lived working copy while applying a single deterministic transition, then commit the result back to Redis before acknowledging the command.
- Long-term history belongs outside Redis after session finalization and export. In the first rollout, that means backend-local JSON archives.

## Redis Deployment Assumptions

Local development:

- Container name: `project-mrn`
- Endpoint: `redis://127.0.0.1:6379/0`
- Current verified version: Redis 7.4.8

Production target:

- Managed Redis or Redis-compatible cluster with private networking, AUTH/TLS, persistence enabled.
- Use AOF `appendfsync everysec` plus RDB snapshots for a good first commercial-grade durability posture.
- Enable key namespace prefix per environment, for example `mrn:dev:*`, `mrn:prod:*`.
- Avoid frontend Redis credentials entirely.
- Add a backend-local JSON archive path for finished game exports, for example `data/game_logs/{session_id}.json`. A separate persistent archive store can be introduced later without changing the Redis ownership model.

## Key Namespace

Use one clear prefix and avoid cross-slot multi-key operations where future Redis Cluster is likely.

Base prefix:

```text
mrn:{env}:
```

Primary keys:

```text
mrn:{env}:ids:room_no                       string counter via INCR
mrn:{env}:rooms:open                        zset room_no by created_at_ms
mrn:{env}:rooms:by_title                    hash normalized_title -> room_no
mrn:{env}:room:{room_no}                    hash room metadata
mrn:{env}:room:{room_no}:seats              hash seat_no -> JSON RoomSeat
mrn:{env}:room:{room_no}:members            hash member_token_hash -> seat_no
mrn:{env}:room_session:{session_id}         string room_no

mrn:{env}:sessions:by_status:{status}       zset session_id by updated_at_ms
mrn:{env}:session:{session_id}              hash session metadata
mrn:{env}:session:{session_id}:seats        hash seat_no -> JSON SeatConfig
mrn:{env}:session:{session_id}:tokens       hash token_hash -> JSON auth principal
mrn:{env}:session:{session_id}:manifest     string JSON public manifest

mrn:{env}:game:{session_id}:state           string JSON canonical GameState snapshot
mrn:{env}:game:{session_id}:checkpoint      hash seq, turn, round, rng_state, schema_version
mrn:{env}:game:{session_id}:events          stream authoritative event log
mrn:{env}:game:{session_id}:commands        stream accepted command/intention log
mrn:{env}:game:{session_id}:analysis        stream analytics/debug events
mrn:{env}:game:{session_id}:view_state      string JSON latest projected backend view_state

mrn:{env}:prompt:{session_id}:active        hash active prompt envelope
mrn:{env}:prompt:{session_id}:by_request    hash request_id -> JSON prompt
mrn:{env}:prompt_deadlines                  zset request_id by deadline_ms
mrn:{env}:prompt_request:{request_id}       hash session_id, player_id, status, choice, deadline

mrn:{env}:runtime:{session_id}              hash status, lease_owner, lease_until_ms, last_activity_ms
mrn:{env}:runtime:leases                    zset session_id by lease_until_ms

mrn:{env}:stream:{session_id}:drop_counts   hash connection/group -> dropped count
mrn:{env}:connections:{session_id}          hash connection_id -> JSON presence

mrn:{env}:archive:export_queue              stream finished session JSON export jobs
mrn:{env}:archive:pending                   zset session_id by finished_at_ms
```

Token values must not be stored in plaintext. Store a keyed hash of room member tokens, host tokens, join tokens, and session tokens. API responses may return the raw token once at creation time.

## Data Model

### Hot State Vs Archive State

Redis is the hot-state store, not the forever-store.

Keep in Redis:

- open room listings
- join and ready state
- active sessions
- current game snapshot
- command and event streams needed for reconnect or spectator sync
- prompt state and deadlines
- runtime leases
- recent debug or analysis events useful for live investigation

Move out of Redis after the hot window:

- final game summaries
- full replay exports
- AI trace bundles
- analytics aggregates
- compliance or audit retention artifacts

Initial archive target outside Redis:

- backend-local JSON files for finished game logs and summaries
- optional local JSON replay bundles derived from command and event streams

Redis should keep enough data to resume, reconnect, inspect, and complete active games. It should not become the only long-term warehouse for every finished game forever.

### Rooms

Redis is the lobby authority.

- `rooms:open` supports low-latency lobby listing.
- `rooms:by_title` prevents duplicate room titles.
- `room:{room_no}` stores title, status, host seat, timestamps, session id, config JSON.
- `room:{room_no}:seats` stores each seat as a JSON payload so seat updates do not rewrite the full room.
- Starting a room is one atomic script:
  - validate room waiting state
  - validate host token
  - validate human seats joined and ready
  - create session metadata
  - move room from open to in-progress
  - write `room_session:{session_id}`
  - append `session_start` / `session_started` events

### Sessions

Redis is the session lifecycle authority.

- `session:{session_id}` stores status, config, resolved parameters, created/started/finished timestamps.
- `session:{session_id}:seats` stores normalized seat configs.
- `session:{session_id}:tokens` maps token hashes to role, seat, player id, expiry metadata.
- Status indexes (`sessions:by_status:*`) replace in-memory filtering.
- Finished sessions stay queryable in Redis only for a bounded reconnect/support window before export and TTL cleanup.

### Game State

Redis is the game state authority.

Canonical state is stored in:

```text
game:{session_id}:state
```

This value is a versioned JSON snapshot of the full deterministic engine state:

- players: position, cash, shards, owned counts, hand coins, revealed/drafted/active character state, per-turn flags, marks, burden/trick state, and private hand state
- board/tile runtime state: tile kind, block/zone metadata, purchase/rent values, owner, score coins, temporary tile rent modifiers, purchase blocks, pawn positions derived from players
- card state: fortune, trick, and weather draw-pile order; discard/graveyard order; current weather; per-player trick hands and hidden trick identity
- active characters and active card faces
- turn/round/marker/f-value and shared resource pools
- pending marks/effects, queued actions, scheduled actions, pending turn-completion envelopes, and in-progress action logs
- current prompt/interrupt state
- schema_version

Do not treat board status or card piles as backend memory caches. The backend may project them into `view_state`, but the authoritative owner/tile/card order must be recoverable from `game:{session_id}:state`.

The engine can keep a local object only while applying one transition. After every accepted transition it must:

1. append command or decision to `game:{session_id}:commands`
2. mutate local state deterministically
3. write full canonical state to `game:{session_id}:state`
4. append emitted events to `game:{session_id}:events`
5. update `game:{session_id}:checkpoint`
6. write latest projected `game:{session_id}:view_state`
7. refresh `runtime:{session_id}.last_activity_ms`

If a transition cannot write all required Redis mutations, it is not considered committed.

### Events And Logs

Use Redis Streams for ordered logs:

- `game:{session_id}:events`: frontend-visible authoritative event stream, replacing `StreamService._buffers`.
- `game:{session_id}:commands`: player/AI submitted command log.
- `game:{session_id}:analysis`: debug, AI scoring, rule traces, runtime timing, benchmark metrics.

The backend websocket endpoint reads Redis Streams by session id and converts entries to the existing frontend message contract. This keeps the frontend contract stable while moving storage.

Retention:

- Keep full event/command streams for active and recently finished sessions.
- Trim long sessions with `XTRIM MINID` or approximate `MAXLEN` only after compact snapshots and export jobs have run.
- Analysis stream can have a shorter retention policy in dev, longer in production/QA.
- Final JSON archival copies should be produced before Redis TTL cleanup.

### View State

The backend projection result belongs in Redis, not process memory.

- `game:{session_id}:view_state` stores latest full projection.
- Each event stream entry may also include a compact `view_state_delta` or full `view_state` when needed by the current frontend contract.
- On reconnect, backend reads:
  - stream range since client last id
  - latest `view_state`
  - session/room metadata

### Runtime Leases

Only one engine worker may own a session at a time.

Use a lease:

```text
runtime:{session_id}
runtime:leases
```

Lease fields:

- `status`: idle, running, waiting_prompt, recovery_required, finished, failed
- `lease_owner`: worker id
- `lease_until_ms`
- `last_activity_ms`
- `engine_seq`
- `error`

Acquire/extend/release must be atomic. For a single Redis instance in dev this can be `SET key value NX PX`; for production, use a safer lock/lease implementation or managed Redis failover policy. The runtime worker must heartbeat and renew the lease while running.

If a worker dies:

1. backend/runtime monitor detects expired lease from `runtime:leases`
2. marks `runtime:{session_id}.status = recovery_required`
3. a new worker reloads `game:{session_id}:state`
4. resumes from pending prompt or next command offset

### Prompts And Human Decisions

Prompts move out of in-memory `PromptService`.

Prompt lifecycle:

1. engine writes `prompt:{session_id}:active`
2. engine appends `prompt_opened` to `game:{session_id}:events`
3. backend exposes prompt over existing HTTP/websocket API
4. player decision endpoint validates session token against Redis
5. accepted decision is written atomically to `prompt_request:{request_id}` and `game:{session_id}:commands`
6. runtime worker consumes the command and clears active prompt

Timeouts:

- `prompt_deadlines` zset stores request_id by deadline_ms.
- A timeout worker scans due prompts, writes deterministic fallback commands, and appends timeout events.

### AI Decisions

AI workers do not own state. They receive a Redis-derived decision context from the backend/runtime worker and return an intent.

For external AI:

- request payload is built from canonical Redis state + public visibility filter
- response is appended to `analysis`
- accepted choice is appended to `commands`

For local AI:

- local policy can run inside the runtime worker, but it must read state from the transition working copy derived from Redis and commit through the same command path.

### Session Lifecycle

Recommended room and session lifecycle:

1. Room created:
   room metadata and seat metadata are written to Redis under a unique `room_no`.
2. Players join, leave, reconnect, or toggle ready:
   backend updates room keys atomically in Redis.
3. Room starts:
   backend allocates `session_id`, initializes live game keys, and moves room state from lobby to in-progress.
4. Game runs:
   engine worker claims the session lease and commits each transition back to Redis.
5. Game finishes:
   session status is marked finished, final snapshot is frozen, JSON export job is enqueued.
6. Hot retention window:
   Redis still serves reconnect, result, replay, and operator inspection for a bounded time.
7. Archive and cleanup:
   archive worker writes final summary and optional replay bundle to a backend-local JSON file, then Redis keys receive TTL or are deleted by policy.

This is the model that scales when many rooms are constantly being created and destroyed: Redis keyspace grows with active demand, not unbounded historical accumulation.

### Local JSON Archive Format

First-rollout archive target:

```text
data/game_logs/{session_id}.json
```

Write policy:

- export only after session status becomes `finished` or `aborted`
- write to a temporary file first, for example `data/game_logs/{session_id}.json.tmp`
- fsync or complete the write
- rename atomically to `data/game_logs/{session_id}.json`
- only after successful write may Redis hot-state cleanup TTL be scheduled

One finished session produces one JSON file.

Top-level shape:

```json
{
  "schema_version": 1,
  "exported_at": "2026-04-29T12:00:00+00:00",
  "exporter": {
    "kind": "backend_local_json",
    "service_version": "git-or-build-id",
    "redis_prefix": "mrn:dev:"
  },
  "session": {
    "session_id": "sess_123456789abc",
    "room_no": 17,
    "room_title": "QA Room",
    "status": "finished",
    "created_at": "2026-04-29T11:00:00+00:00",
    "started_at": "2026-04-29T11:01:00+00:00",
    "finished_at": "2026-04-29T11:24:00+00:00",
    "seed": 42,
    "policy_mode": "heuristic_v3_gpt"
  },
  "manifest": {},
  "summary": {
    "round_index": 6,
    "turn_index": 23,
    "winner_player_id": 2,
    "abort_reason": null,
    "final_f_value": 13.0,
    "final_marker_owner_player_id": 2
  },
  "final_checkpoint": {
    "engine_seq": 418,
    "schema_version": 1,
    "turn": 23,
    "round": 6
  },
  "final_state": {},
  "final_view_state": {},
  "streams": {
    "commands": [],
    "events": [],
    "analysis": []
  },
  "counts": {
    "command_count": 118,
    "event_count": 418,
    "analysis_count": 67
  }
}
```

Required top-level fields:

- `schema_version`: archive schema version, not Redis state schema version
- `exported_at`: UTC ISO timestamp when the JSON file was finalized
- `exporter`: metadata about the exporter implementation
- `session`: stable identifiers and lifecycle timestamps
- `manifest`: public parameter manifest used for the session
- `summary`: quick lookup fields for operators and replay tooling
- `final_checkpoint`: the Redis engine checkpoint used for export consistency
- `final_state`: canonical deterministic game state snapshot from Redis
- `final_view_state`: final backend-projected frontend view state
- `streams`: command, event, and analysis arrays
- `counts`: precomputed counts for quick inspection without scanning arrays

Stream entry format:

```json
{
  "stream_id": "1745928000000-0",
  "seq": 418,
  "type": "event",
  "server_time_ms": 1745928000000,
  "payload": {}
}
```

Rules:

- `commands`, `events`, and `analysis` entries all share the same envelope shape
- `payload` should preserve the backend-visible message payload exactly
- do not strip fields needed for replay or audit
- never store raw auth tokens in any stream payload
- if privacy filtering is later required, produce a second redacted export format instead of mutating the canonical archive

Recommended `summary` fields:

- `winner_player_id`
- `winner_display_name`
- `abort_reason`
- `round_index`
- `turn_index`
- `final_f_value`
- `final_marker_owner_player_id`
- `player_results`

Recommended `player_results` shape inside `summary`:

```json
[
  {
    "player_id": 1,
    "display_name": "Player 1",
    "seat": 1,
    "character": "자객",
    "alive": true,
    "cash": 18,
    "shards": 7,
    "owned_tile_count": 4,
    "total_score": 31,
    "rank": 2
  }
]
```

Optional future fields:

- `replay`: prebuilt replay-friendly condensed timeline
- `analytics`: postprocessed aggregates derived from `analysis`
- `attachments`: paths to supplemental files such as AI traces

Versioning rule:

- changing required top-level fields increments `schema_version`
- adding optional fields does not require breaking existing readers
- readers must ignore unknown fields

## Atomic Transition Boundary

Every state-changing command must have one Redis atomic commit step.

For small mutations:

- Use `WATCH/MULTI/EXEC` on `game:{session_id}:checkpoint` version fields.

For complex multi-key session transitions:

- Use Lua scripts with explicit key lists:
  - room creation
  - room join/ready/leave
  - room start/session creation
  - decision acceptance
  - prompt timeout resolution
  - engine transition commit

All scripts must check:

- schema version
- expected status
- expected engine sequence
- request id uniqueness
- token hash authorization

## Backend Responsibilities After Migration

The backend becomes a Redis-backed API facade:

- validate tokens by Redis lookup
- expose room/session APIs by Redis reads/writes
- stream Redis Stream entries to browser clients
- project or fetch Redis-stored view_state
- coordinate runtime leases
- never trust frontend state
- never keep authoritative room/session/game state in process memory
- enqueue local JSON archive/export work when sessions finish

Allowed in-process state:

- websocket connection queues
- short-lived request-local objects
- runtime asyncio task handles, only as execution handles, not state truth
- small client caches with TTL only if Redis remains authoritative

## Engine Responsibilities After Migration

The engine becomes a deterministic transition executor:

- load canonical state from Redis before work
- apply one prompt/AI/turn transition
- emit events
- commit state/events/checkpoint atomically
- yield if waiting for human input

The current long-running `engine.run()` loop should be split into resumable transition steps:

- `initialize_session`
- `advance_until_prompt_or_turn_end`
- `apply_decision`
- `apply_timeout`
- `resume_after_recovery`

This is the hardest part. Keeping a long-running process with an in-memory `GameState` would violate the target architecture unless every mutation is immediately persisted and recoverable.

## Migration Phases

### Phase 0: Redis Adapter Foundation

- Add `redis>=5` or `redis[hiredis]>=5` to `apps/server/requirements.txt`.
- Add runtime settings:
  - `MRN_REDIS_URL`
  - `MRN_REDIS_PREFIX`
  - `MRN_REDIS_SOCKET_TIMEOUT_MS`
  - `MRN_REDIS_HEALTHCHECK_INTERVAL_MS`
  - `MRN_STATE_STORE=redis`
- Add `RedisClientFactory`.
- Add health check that verifies `PING`, Redis version, and write/read/delete in the configured namespace.

### Phase 1: Redis Stores Behind Existing Interfaces

Keep service APIs stable while replacing storage:

- `RedisSessionStore`
- `RedisRoomStore`
- `RedisStreamStore`
- `RedisPromptStore`
- `RedisRuntimeStore`

At the end of Phase 1:

- JSON file stores are dev fallback only.
- Room/session/stream data survives backend restart through Redis.
- Existing tests pass with fake/in-memory Redis equivalent or a test Redis.

### Phase 2: Redis Streams For Frontend Message History

- Replace `StreamService._seq` and `_buffers` with `XADD/XRANGE/XREVRANGE`.
- Store frontend message sequence as a field in the stream entry.
- Keep websocket subscribers process-local, but replay and snapshot come from Redis.
- Persist drop counts in Redis.

At the end of Phase 2:

- Backend restart does not lose stream history.
- Browser reconnect gets the same messages from Redis.

### Phase 3: Prompt And Decision State

- Move active prompts and request decisions to Redis.
- Decision endpoint accepts exactly once using request_id state.
- Timeout worker writes fallback commands through Redis.
- Runtime no longer depends on in-memory prompt state to know whether it is waiting.

At the end of Phase 3:

- Human prompt can survive backend/runtime restart.
- Duplicate decisions are rejected by Redis state.

### Phase 4: Engine Checkpointing

- Create versioned `GameState` serializer/deserializer, including RNG state and deck order.
- Commit canonical state after every emitted event group.
- Add recovery tests that kill/recreate runtime service and resume from Redis.

At the end of Phase 4:

- Engine state is recoverable, but the internal execution loop may still be long-running.

### Phase 5: Resumable Transition Engine

- Refactor `GameEngine.run()` into transition steps.
- Runtime workers claim a session lease, execute until prompt/turn boundary, commit, and release or wait.
- AI/human commands wake the runtime by appending to `commands`.

At the end of Phase 5:

- No in-memory engine state is required between transitions.
- Multiple backend/runtime processes can coordinate through Redis.

### Phase 6: Operations And Retention

- Add Redis persistence docs for dev/prod.
- Add stream trimming/export policies.
- Define hot retention windows for waiting, running, finished, and abandoned sessions.
- Implement archive workers that write finished session outputs to backend-local JSON files.
- Define the local archive directory layout and rotation policy.
- Add metrics:
  - command latency
  - Redis RTT
  - event stream lag
  - prompt timeout skew
  - lease renew failures
  - recovery count
- Add admin debug endpoints backed by Redis, not local memory.

## Implementation Progress

Implemented in the first Redis migration batch:

- `MRN_REDIS_URL`, `MRN_REDIS_KEY_PREFIX`, and Redis socket timeout settings.
- `RedisConnection` health check with `PING`, Redis version, key prefix, and DB reporting.
- Redis-backed room and session stores behind existing service interfaces.
- Redis-backed stream history using Redis Streams for `publish`, `snapshot`, `replay_from`, `replay_window`, `latest_seq`, and drop counts.
- Redis-backed prompt state for pending prompts, resolved request ids, and submitted decisions.
- Redis-backed runtime status, recent fallback history, and session worker lease ownership.
- Redis-backed live game checkpoint, latest current-state snapshot, and latest projected view state.
- Redis-backed command stream for accepted human decisions and accepted AI/runtime decisions, with `request_id` dedupe.
- `PromptTimeoutWorker` service that resolves expired Redis-backed prompts once, executes the fallback through `RuntimeService`, and emits ack/resolved/timeout events.
- Standalone prompt timeout worker entrypoint:
  `python -m apps.server.src.workers.prompt_timeout_worker_app --once`
  or continuous mode without `--once`.
- Standalone command wakeup worker entrypoint:
  `python -m apps.server.src.workers.command_wakeup_worker_app --once`
  or continuous mode without `--once`.
- Docker Compose local stack wiring for Redis, FastAPI server, the standalone prompt timeout worker, and the command wakeup worker.
- Runtime recovery checkpoint fixture that exposes latest Redis checkpoint/current_state/view_state after service reconstruction.
- Restart integration coverage for Redis-backed replay/status/checkpoint/command continuity.
- Lua-backed atomic command append and runtime lease refresh/release when the Redis client supports `EVAL`, with Python fallbacks for tests.
- Versioned `GameState` checkpoint serializer/deserializer for canonical engine state, including tiles, players, deck order, discard piles, weather, active cards, and turn/round fields.
- `GameEngine.run(initial_state=...)` can start from a hydrated turn-boundary state instead of always creating a fresh game.
- `GameEngine.run()` now delegates to explicit `prepare_run()` and `run_next_transition()` boundaries, so tests and runtime recovery can execute one checkpoint-backed transition without a process-owned long-running engine state.
- Runtime service attempts to hydrate engine state from Redis `current_state` when a canonical engine checkpoint is available.
- Runtime service has a recovery transition path that hydrates canonical Redis state, executes one engine transition, and writes the updated `current_state` plus checkpoint back to Redis.
- When Redis game-state storage is configured, the default runtime execution path now uses the resumable transition loop instead of the legacy full-game `engine.run()` loop. The legacy path remains available for non-Redis in-memory/json-file execution.
- Command wakeup now treats `waiting_input` as resumable runtime state and advances the command consumer offset only after the runtime wakeup/start call succeeds.
- `RedisGameStateStore.commit_transition()` writes canonical state, checkpoint, and optional projected view state through one commit boundary, using Lua when the client supports `EVAL` and a Redis transaction pipeline fallback in tests.
- Redis JSON serialization normalizes nested dict keys to strings before storage so canonical engine checkpoints with integer-indexed maps can safely flow through Redis streams and state keys.
- Command wakeup worker offsets are persisted in Redis per consumer/session, so worker restarts do not reprocess old command entries.
- Local JSON archive export for finished sessions with hot-state cleanup after the retention window.

Still intentionally incomplete:

- The engine has a tested one-transition boundary and Redis-backed runtime uses it by default. The remaining runtime work is to make every human prompt a true continuation boundary rather than a blocking call inside the current engine stack.
- Redis stores the latest canonical snapshot emitted by the engine stream and runtime can hydrate from it when it has the engine checkpoint shape. True mid-transition resume, inside an individual effect chain before the next committed boundary, is still out of scope.
- Prompt timeout and command wakeup handling have standalone worker entrypoints plus local Docker Compose services. Production deployment still needs environment-specific process manager or orchestration settings.
- Runtime lease refresh/release, command append, and game-state transition commit use Lua where available. Complete decision acceptance plus engine state mutation still needs one higher-level atomic command-processing envelope that covers command consumption, prompt resolution, event append, state commit, and offset update together.
- The first command-processing envelope is now implemented for state/checkpoint/view-state commit plus command consumer offset update. `RuntimeService.process_command_once()` can process a command-triggered transition and commit `processed_command_seq`/consumer metadata with the state checkpoint, while `CommandStreamWakeupWorker` prefers this hook when available.
- Prompt reentry integration coverage now verifies: prompt boundary commit, human decision command append, command-triggered runtime processing, submitted decision consumption, no duplicate prompt event for the same request id, and command offset commit.
- `StreamService` deduplicates `prompt` and `decision_requested` publishes by `request_id`, adding a second guard against replayed prompt-boundary event duplication.

## Human Prompt Continuation Boundary Design

Target behavior:

1. The runtime loads canonical `GameState` from Redis.
2. The engine advances until it can commit a transition or reaches a human prompt.
3. If a human prompt is reached, the server publishes the prompt, records it in Redis, raises a `PromptRequired` boundary signal, commits the current canonical state and checkpoint with `waiting_prompt_*` metadata, releases the runtime lease, and reports runtime status `waiting_input`.
4. When the human submits a decision, `PromptService.submit_decision()` appends a deduplicated `decision_submitted` command to Redis.
5. `CommandStreamWakeupWorker` sees the command, restarts the runtime for `waiting_input` sessions, and the next runtime pass rehydrates from Redis.
6. When the engine reaches the same prompt boundary again, the decision bridge should consume the submitted decision immediately and return the parsed choice instead of publishing a duplicate prompt.

Implementation constraints:

- Legacy non-Redis execution may continue to use blocking human prompts.
- Redis-backed transition execution must use non-blocking human prompts.
- Prompt request ids must become stable across rehydration. The preferred shape is to persist prompt sequence/pending prompt metadata in the canonical checkpoint and reuse the same request id on replay.
- The first implementation slice adds `PromptRequired` and commits `waiting_prompt_request_id`, `waiting_prompt_type`, and `waiting_prompt_player_id` in the checkpoint.
- `DecisionGateway` now supports non-blocking human prompts. In that mode it publishes/stores the prompt and raises `PromptRequired` instead of blocking in `wait_for_decision()`.
- `DecisionGateway` also checks for an already submitted decision for the same request id before creating a new prompt. This lets replayed prompt boundaries consume the decision and return the parsed choice without creating a duplicate pending prompt.
- Prompt ids are stable when prompt metadata includes round, turn, player, type, and prompt instance.
- Canonical `GameState` now persists `prompt_sequence`, `pending_prompt_request_id`, `pending_prompt_type`, `pending_prompt_player_id`, and `pending_prompt_instance_id`. Runtime rehydrates this sequence into the human policy bridge before executing the next transition.
- `GameEngine.prepare_run()` exposes the last prepared state to the runtime so a prompt raised during initial round setup still has a canonical state to commit.
- Remaining hardening: move all prompt request id generation onto the canonical state fields even when public context is sparse, then expand the command-processing envelope to cover prompt resolution/deletion and event stream append in the same atomic boundary.

## Action Pipeline / Movement Boundary

The resumable engine migration should treat rule effects as serializable actions rather than nested immediate function calls.

Core rule:

```text
movement source -> apply move -> optional resolve arrival
```

`resolve_arrival` must never roll dice, calculate movement values, or change position except through explicit follow-up actions produced by landing effects. This keeps cards such as `수상한 음료` clear: the fortune effect rolls dice first, then schedules movement, then schedules arrival. `이사가세요`, `끼어들기`, and `추노꾼` should all share the same target-move primitive with different `schedule_arrival` and `lap_credit` flags.

Implemented seed:

- `GameState.pending_actions` now checkpoints serializable `ActionEnvelope` records.
- The engine has `apply_move` and `resolve_arrival` helpers.
- Fortune `[도착]` movement, fortune `[이동]` movement, target-movement trick effects, and hunter forced landing now route through the shared target-move helper.
- `run_next_transition()` now drains one queued action before normal turn advancement. A queued `apply_move` with `schedule_arrival=true` updates position and queues `resolve_arrival`; the following transition resolves the tile.
- Queued `apply_move` now supports `move_value` for forward step movement. It applies path/total-step/lap-reward state in the move transition while leaving tile effects to the next `resolve_arrival` transition.
- A standard-move adapter now converts resolved `move` + `movement_meta` into a queued `apply_move` action. Default turn execution uses this queued movement boundary and is verified against simple, card-metadata, obstacle slowdown, encounter boost, and zone-chain `_advance_player()` compatibility cases.
- `pending_action_log` checkpoints the in-progress movement summary while `apply_move` and `resolve_arrival` are split across transitions. Final arrival emits a legacy-compatible `turn` log row for the covered standard-move path.
- Queued `apply_move` uses a separate `action_move` visual event when it emits movement. `player_move` stays reserved for the ordinary dice-paired turn movement, while backend `view_state` board/reveal/turn/scene selectors treat `action_move` as movement for projection.
- Normal turn movement now enters the same queued movement boundary: `_take_turn()` resolves the movement source and schedules `apply_move -> resolve_arrival`, then `pending_turn_completion` emits the turn-end snapshot and advances the turn cursor only after the queued actions finish. The external visual contract remains `dice_roll -> player_move -> landing_resolved -> turn_end_snapshot`.
- Turn-start mark effects now have the first scheduled-action implementation. `scheduled_actions` stores target/phase/priority `ActionEnvelope` records; target-player `turn_start` actions are materialized into `pending_actions` before that player's normal turn begins.
- `resolve_mark` is now an action handler. Immediate mark effects mutate state atomically inside the action, while hunter pull enqueues `apply_move -> resolve_arrival` follow-up actions.
- `극심한 분리불안` now queues its target movement as `apply_move -> resolve_arrival`, so trick-card resolution does not mutate position inline.
- Built-in movement fortune cards now act as action producers on the fortune-tile path. They resolve the card draw immediately, then enqueue `apply_move` with `schedule_arrival` according to the card effect; global/non-movement effects still mutate immediately inside the fortune handler.
- Custom fortune producers can register `fortune.card.produce` and return a `QUEUE_TARGET_MOVE` contract; the engine maps that hook result into the same queued movement primitive.
- Backward takeover fortune cards now enqueue movement first and then `resolve_fortune_takeover_backward`, separating position changes from ownership mutation.
- Decision-bearing effects are starting to become actions too. `request_purchase_tile` runs purchase decision/mutation through the action iterator; if the decision bridge raises a prompt boundary, the action is put back at the front of `pending_actions` so replay after Redis recovery resumes the same purchase request rather than skipping or duplicating it. State mutations that are part of the purchase, including one-shot free-purchase flags, must happen only after a decision is returned.
- Queued unowned-land arrivals now split into `resolve_arrival -> request_purchase_tile -> resolve_unowned_post_purchase`. This prevents a human purchase prompt from being raised inside arrival resolution and gives adjacent-buy/same-tile/weather post-processing its own checkpointable action.
- Queued rent landings can split rent payment from follow-up land effects as `resolve_arrival -> resolve_landing_post_effects`, so adjacent-buy decisions and same-tile bonuses can recover independently after the rent mutation is committed.
- Zone-chain landings now enqueue follow-up movement as `apply_move -> resolve_arrival` instead of nesting the extra move inside arrival resolution.
- Decision-bearing fortune effects should produce actions instead of opening prompts during fortune draw resolution. Migrated cards now include subscription-style empty-block purchase, land thief, donation angel, forced trade, and pious marker tile gain.
- Runtime recovery checkpoints expose `pending_action_count`, `scheduled_action_count`, `pending_action_types`, `scheduled_action_types`, `next_action_type`, `next_scheduled_action_type`, `has_pending_actions`, `has_scheduled_actions`, and `has_pending_turn_completion`, while the canonical `current_state` stores the full action, scheduled-action, and turn-completion envelopes.
- Direct fortune/forced-move callers still execute inline for compatibility until their call sites are migrated to enqueue actions.

Next action-pipeline hardening:

- audit remaining direct compatibility helpers (`_advance_player()`, `_apply_fortune_arrival()`, and extension hooks) and explicitly mark the surviving callers as test/plugin-only APIs
- expand the prompt-resumable pattern to any future human decisions that still appear during effect resolution

## Testing Strategy

Unit:

- Redis key encoder/decoder tests.
- Serialization round-trip for Session, Room, GameState, Prompt, StreamMessage.
- Lua script behavior tests for duplicate joins/decisions/starts.

Integration:

- Start Redis container in test setup.
- Create room, join, ready, start, reconnect after server restart.
- Submit duplicate prompt decision; verify exactly one command accepted.
- Simulate prompt timeout from `prompt_deadlines`.
- Run a short game, restart backend, verify snapshot and stream replay.

Runtime recovery:

- Start session, stop runtime worker at:
  - before first prompt
  - waiting human prompt
  - after decision accepted but before event projection
  - mid-turn after movement
- New worker resumes from Redis and emits no duplicate irreversible events.

Frontend contract:

- Frontend should not know Redis exists.
- Existing websocket message shape remains stable unless a separate API migration is explicitly planned.

Performance:

- 1, 10, 100 concurrent sessions smoke benchmark.
- Redis memory growth per turn.
- Redis memory growth per active room/session cohort.
- `XRANGE` reconnect latency.
- Lua commit latency.

## Data Safety Rules

- Redis is not used as a disposable cache for active game state. It is the primary online datastore for live sessions.
- Enable AOF and RDB in production-like environments.
- Export finished game streams and summaries to backend-local JSON files in the first rollout.
- Move that archive target to colder persistent storage later if long-term replay, analytics, or audit retention requires it.
- Never put raw auth tokens in logs, streams, or analysis payloads.
- Every key must have a schema version or be decodable by a versioned parser.
- Finished/aborted sessions may get TTL only after export and after frontend replay window expires.

## Implementation Risks

- Refactoring `GameEngine.run()` into resumable transitions is large and riskier than replacing server stores.
- Redis Cluster compatibility is easiest if session-scoped keys share a hash tag. The proposed names should be revised to include `{session_id}` hash tags before cluster deployment.
- Large JSON snapshots are simple and safe for migration, but later may need field-level hashes for hot data.
- Streams are excellent for ordered logs, but projection from full history on every event is expensive. Store latest view_state and incremental checkpoints.
- Distributed locks require careful timeouts. Lease expiry must be longer than worst-case transition time, and transitions must remain idempotent.
- If JSON archive handoff is missing or delayed, finished-session keys may accumulate and negate the operational benefit of Redis hot-state storage.

## Next Concrete Commit Scope

Recommended next implementation PR:

1. Split `GameEngine.run()` into explicit transition steps with commit points after each prompt/turn boundary.
2. Move full decision acceptance plus engine state mutation to one Redis transaction/Lua commit boundary.
3. Add real Redis restart smoke that kills/recreates backend service processes around a running game and verifies hydrated continuation.
4. Add production deployment settings for the timeout/command workers after the target hosting environment is chosen.
5. Define Redis Cluster hash-tag key names before multi-node Redis deployment.

This keeps the current incremental path honest: Redis now owns the live records, while resumable engine execution remains the next large refactor.
