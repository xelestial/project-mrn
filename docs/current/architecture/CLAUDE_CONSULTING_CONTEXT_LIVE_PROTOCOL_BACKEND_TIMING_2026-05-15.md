# Claude Consulting Context - Live Protocol Backend Timing Failure

Status: consulting input, not an adopted implementation plan
Date: 2026-05-15
Repository: `/Users/sil/Workspace/project-mrn`
Branch at capture: `codex/external-topology-protocol-ops`
Recent published commit: `3ffd1ee3 Preserve inbound primary decision identity`

## Purpose

This document packages the current MRN game/server architecture, implementation state,
test procedure, and the latest live protocol failure evidence for an independent
Claude review.

The review target is not "make the test green by weakening the gate." The target is
to identify whether the current runtime/prompt/server structure has an ownership or
design problem, and what the smallest non-patchwork next investigation or redesign
step should be.

## Questions for Claude

1. Is `PromptService.create_prompt()` doing too much under one runtime-critical path
   or lock?
2. Are prompt persistence concerns split correctly between `RuntimeService`,
   `DecisionGateway`, `PromptService`, and `RedisPromptStore`?
3. Is the current prompt boundary materialization model structurally sound, or is it
   a patchwork around earlier runtime responsibilities?
4. Does the live timing evidence point to Redis prompt alias/lifecycle/debug writes,
   Python lock contention, container cold path, or another bottleneck?
5. What additional instrumentation should be added before changing behavior?
6. Should prompt creation be moved out of engine transition timing, or is it correct
   for prompt materialization to count as part of the transition SLO?
7. Which current responsibilities should be merged, moved, or deleted to prevent
   further patchwork?

## Current Game Model

MRN is a turn-based multiplayer board/card game. The engine is the authority for
rules. The browser and server are transport, persistence, visibility, and input
coordination layers.

Core game sequence:

1. A lobby/session is created and players take seats.
2. The game starts after the required seats are ready.
3. Each round reveals weather.
4. A character draft runs for four players. The first draft proceeds in turn order,
   then a reverse second draft, then each player chooses one of two drafted
   characters.
5. Turn order is determined by selected character priority.
6. Each turn runs targeted character effects, character ability, trick card choice,
   dice, movement, landing effects, and any resulting prompts.
7. Round end updates doctrine direction/markers, flips active characters after the
   final turn, then proceeds to the next weather/draft phase.

Important rule source:

- `/Users/sil/Workspace/project-mrn/docs/current/Game-Rules.md`

Important recent failing module:

- `DraftModule`
- request type: `draft_card`
- failure reason: `prompt_required`

## Architecture Ownership

The intended authority boundaries are:

- `engine/`: final rule authority. It owns legal transitions, module execution,
  prompt requirements, game state semantics, and rule validation.
- `apps/server/`: runtime orchestration, persistence, prompt lifecycle, command
  inbox, WebSocket fanout, external AI callback handling, and view projection.
- `apps/web/`: display and player input only. It must not decide game legality.
- Redis: authoritative continuation/checkpoint/read-model storage for the server
  runtime. Redis is not a rule engine.

Canonical architecture guide:

- `/Users/sil/Workspace/project-mrn/docs/current/architecture/GUIDE_GAME_FLOW_AND_MODULE_VISUALIZATION.md`

End-to-end runtime contract:

- `/Users/sil/Workspace/project-mrn/docs/current/runtime/end-to-end-contract.md`

## Runtime Flow

The live protocol flow under test is:

1. Browser/headless test creates or joins a session through REST.
2. Server starts the session and drives runtime execution.
3. `SessionLoop` / command execution invokes the engine.
4. Engine modules run until they either commit a completed transition or return a
   prompt boundary.
5. For a prompt boundary, server materializes prompt metadata and stores a pending
   prompt.
6. Server publishes `view_commit` and prompt state over WebSocket.
7. Browser/headless client chooses an action and sends the decision.
8. Server resolves public protocol identity to internal numeric engine seat.
9. `PromptService.submit_decision()` validates request/player identity and records
   the accepted decision.
10. Command inbox/wakeup/runtime resumes the engine from the prompt continuation.
11. Server commits the next Redis checkpoint/view commit and broadcasts the result.

The current command boundary rule is that Redis checkpoint and `view_commit` are
committed only at terminal command boundary states such as success, refused, failed,
waiting input, or completed.

## Server Runtime Implementation State

The current server rebuild is partially complete and active. The main state from
`PLAN_STATUS_INDEX.md` is:

- Direct runtime execution fallback was removed from wakeup code.
- Command recovery, processing guards, execution gate, finalizer, staging store,
  and runner have been extracted out of `RuntimeService`.
- `SessionLoop` owns lifecycle flow through `SessionCommandExecutor`.
- `RuntimeService.process_command_once()` compatibility wrapper was removed.
- HTTP external AI stops at provider=`ai` prompt boundary and callbacks re-enter
  through `PromptService` / command inbox.
- Simultaneous batch ownership is handled through `BatchCollector`.
- Single-server capacity evidence says 5 and 8 concurrent games passed, while 10
  games first breached the 5 second backend SLO. The documented direction is
  horizontal server instance scaling, not Redis fan-out.

Main status index:

- `/Users/sil/Workspace/project-mrn/docs/current/planning/PLAN_STATUS_INDEX.md`

Server rebuild plan:

- `/Users/sil/Workspace/project-mrn/docs/current/architecture/PLAN_SERVER_RUNTIME_REBUILD_2026-05-12.md`

## Protocol Identity Implementation State

The current identity migration is compatibility-first:

- External/public protocol IDs are string IDs.
- Internal engine actor/seat IDs still use numeric aliases.
- The server has one canonical resolution boundary:
  `SessionService.resolve_protocol_player_id()`.
- WS decisions and external-AI callbacks normalize public identity to a numeric
  internal seat before calling prompt submission.
- Numeric `player_id` aliases intentionally remain for compatibility until all
  protocol consumers are migrated.
- Recent work preserved inbound `primary_player_id` and
  `primary_player_id_source` through the HTTP/WS routes, instead of dropping them.
- `PromptService` now accepts cross-source primary identity when the legacy bridge
  resolves to the same seat, and rejects same-source mismatches.

Relevant plan:

- `/Users/sil/Workspace/project-mrn/docs/current/planning/PLAN_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md`

Recent verification before the live failure:

```bash
./.venv/bin/python -m pytest \
  apps/server/tests/test_prompt_service.py::PromptServiceTests::test_submit_decision_accepts_cross_source_primary_identity_when_legacy_bridge_matches \
  apps/server/tests/test_prompt_service.py::PromptServiceTests::test_submit_decision_rejects_same_source_primary_identity_mismatch \
  -q

./.venv/bin/python -m pytest tests/test_protocol_identity_consumer_inventory_doc.py -q
python3 tools/plan_policy_gate.py
./.venv/bin/python -m pytest engine/test_doc_integrity.py -q
git diff --check
./.venv/bin/python -m pytest \
  apps/server/tests/test_stream_api.py \
  apps/server/tests/test_sessions_api.py \
  apps/server/tests/test_prompt_service.py \
  -q
```

Observed result before commit:

- focused prompt tests: passed
- protocol identity inventory doc test: passed
- plan policy gate: passed
- engine doc integrity: passed
- diff whitespace check: passed
- server prompt/session/stream suite: `119 passed`

## Process Topology

Live protocol tests use `docker-compose.protocol.yml`.

Services:

- `redis`
- `server`
- `prompt-timeout-worker`
- `command-wakeup-worker`

Important defaults:

- Server host port: `${MRN_PROTOCOL_SERVER_PORT:-9091}:9090`
- Server health route: `/health`
- Redis URL inside compose: `redis://redis:6379/0`
- Redis key prefix: `mrn:protocol`
- Redis maxmemory default: `2gb`
- Redis policy default: `noeviction`
- `MRN_RUNTIME_ENGINE_WORKERS` default: `8`
- `MRN_STREAM_OUTBOX_MODE` default: `dual`
- `MRN_COMMAND_WAKEUP_WORKER_RUNTIME_PROCESSING_ENABLED` default: `0`

Docker compose file:

- `/Users/sil/Workspace/project-mrn/docker-compose.protocol.yml`

## Key Code Paths

Runtime and prompt boundary:

- `/Users/sil/Workspace/project-mrn/apps/server/src/services/runtime_service.py`
  - `_materialize_prompt_boundary_sync`
  - `_publish_prompt_boundary_sync`
- `/Users/sil/Workspace/project-mrn/apps/server/src/services/session_loop.py`
  - `SessionCommandExecutor`
- `/Users/sil/Workspace/project-mrn/apps/server/src/services/decision_gateway.py`
  - `DecisionGateway`
  - `runtime_decision_gateway_prompt_timing` log emission

Prompt lifecycle:

- `/Users/sil/Workspace/project-mrn/apps/server/src/services/prompt_service.py`
  - `PromptService.create_prompt()`
  - `PromptService.submit_decision()`
  - `PromptService.wait_for_decision()`

Redis prompt persistence:

- `/Users/sil/Workspace/project-mrn/apps/server/src/services/realtime_persistence.py`
  - `RedisPromptStore`
  - `save_pending()`
  - `accept_decision_with_command()`

Identity normalization:

- `/Users/sil/Workspace/project-mrn/apps/server/src/services/session_service.py`
  - `resolve_protocol_player_id()`
- `/Users/sil/Workspace/project-mrn/apps/server/src/routes/stream.py`
- `/Users/sil/Workspace/project-mrn/apps/server/src/routes/sessions.py`
- `/Users/sil/Workspace/project-mrn/apps/server/src/routes/prompts.py`

Workers:

- `/Users/sil/Workspace/project-mrn/apps/server/src/workers/command_wakeup_worker_app.py`
- `/Users/sil/Workspace/project-mrn/apps/server/src/workers/prompt_timeout_worker_app.py`

Headless protocol runner:

- `/Users/sil/Workspace/project-mrn/apps/web/package.json`
  - `rl:protocol-gate`
  - `rl:protocol-gate:games`

## Test Stack Startup

Start or rebuild the live protocol stack:

```bash
docker compose -p project-mrn-protocol \
  -f docker-compose.protocol.yml \
  up -d --build
```

Health check:

```bash
curl -fsS http://127.0.0.1:9091/health
```

Redis checks:

```bash
docker compose -p project-mrn-protocol \
  -f docker-compose.protocol.yml \
  exec redis redis-cli CONFIG GET maxmemory

docker compose -p project-mrn-protocol \
  -f docker-compose.protocol.yml \
  exec redis redis-cli CONFIG GET maxmemory-policy

docker compose -p project-mrn-protocol \
  -f docker-compose.protocol.yml \
  exec redis redis-cli INFO stats
```

## Canonical Full-Stack Protocol Gate

The authoritative stability gate is documented here:

- `/Users/sil/Workspace/project-mrn/docs/current/ai/rl-evaluation-gate.md`

Single live game example:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run rl:protocol-gate -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --seed 20260525 \
  --timeout-ms 1800000 \
  --idle-timeout-ms 120000 \
  --out /tmp/mrn_protocol_trace_live_20260525.jsonl \
  --replay-out /tmp/mrn_rl_replay_live_20260525.jsonl \
  --progress-interval-ms 30000
```

Repeated game example with backend timing gates:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run rl:protocol-gate:games -- \
  --games 5 \
  --run-root tmp/rl/full-stack-protocol/backend-timing-gate \
  --seed-base 2026051100 \
  -- \
  --base-url http://127.0.0.1:9091 \
  --profile live \
  --timeout-ms 600000 \
  --idle-timeout-ms 120000 \
  --progress-interval-ms 10000 \
  --raw-prompt-fallback-delay-ms off \
  --require-backend-timing \
  --max-backend-command-ms 5000 \
  --max-backend-transition-ms 5000 \
  --max-backend-redis-commit-count 1 \
  --max-backend-view-commit-count 1 \
  --max-protocol-command-latency-ms 5000 \
  --backend-docker-compose-project project-mrn-protocol \
  --backend-docker-compose-file ../../docker-compose.protocol.yml \
  --backend-docker-compose-service server
```

Artifact reading order:

1. `summary/`
2. `pointers/`
3. `raw/`, only for targeted evidence

The runner is quiet by default. Successful multi-game runs should not flood chat or
console output; detailed evidence should live in files.

## Acceptance Bar

The gate is expected to fail if any of these occur:

- runtime failure
- illegal action
- timeout
- rejected ACK
- raw prompt fallback
- stale ACK
- send/client/stream error
- non-monotonic view commit
- reconnect repair failure
- Redis `evicted_keys` or `total_error_replies`
- protocol command latency over 5000ms
- backend command/transition timing over 5000ms when timing gates are enabled
- duplicate Redis/view commits above the expected count

The current failure must not be solved by relaxing the 5000ms backend timing gate
without evidence that the gate itself is wrong.

## Latest Live Failure

Run root:

- `/Users/sil/Workspace/project-mrn/tmp/rl/full-stack-protocol/identity-route-live-20260515`

Command:

```bash
cd /Users/sil/Workspace/project-mrn/apps/web
npm run rl:protocol-gate:games -- \
  --games 1 \
  --run-root tmp/rl/full-stack-protocol/identity-route-live-20260515 \
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

Runner output summary:

```text
PROTOCOL_GATE_GAME_END index=1 status=1 dir=.../identity-route-live-20260515/game-1
PROTOCOL_GATE_FAILURE_POINTER game=1 type=backend_timing status=1 \
session=sess_YSOf75ft6J23igWa-SLLmP-q \
request_id=req_83d495c0-4818-5221-a9a3-e35c1d3f371c \
command_seq=unknown commit_seq=4 \
summary=.../game-1/summary/summary.json \
pointer=.../game-1/pointers/failure_pointer.json
PROTOCOL_GATE_FAIL_FAST
```

`summary/summary.json` distilled:

```json
{
  "ok": false,
  "runtime_status": "running_elsewhere",
  "aborted": true,
  "abort_reason": "backend_timing_gate",
  "backend_timing": {
    "eventCount": 8,
    "commandTimingCount": 1,
    "transitionTimingCount": 5,
    "decisionRouteTimingCount": 1,
    "promptTimingCount": 1,
    "maxCommandMs": 72,
    "maxTransitionMs": 6772,
    "maxDecisionRouteMs": 7,
    "maxPromptMs": 6735,
    "maxRedisCommitCount": 1,
    "maxViewCommitCount": 1,
    "slowCommandCount": 0,
    "slowTransitionCount": 1
  }
}
```

`pointers/failure_pointer.json` distilled:

```text
failure type: backend_timing
session: sess_YSOf75ft6J23igWa-SLLmP-q
request: req_83d495c0-4818-5221-a9a3-e35c1d3f371c
commit_seq: 4
elapsed_ms: 7529
runtime_status: running_elsewhere
message: backend transition exceeded 5000ms:
  value=6772
  module=DraftModule
  request_type=draft_card
  request_id=req_83d495c0-4818-5221-a9a3-e35c1d3f371c
  reason=prompt_required
```

`summary/slowest_transition.json` distilled:

```text
max_transition_ms: 6772
max_command_ms: 72
max_redis_commit_count: 1
max_view_commit_count: 1
```

## Targeted Log Evidence

Before ACK, the protocol runner saw the expected pending prompt state:

```text
runtime_status=waiting_input
commit_seq=4
latestDecisionRequestId=req_83d495c0-4818-5221-a9a3-e35c1d3f371c
pending_age_ms=0
```

The final decision path was accepted quickly:

```text
latestAckStatus=accepted
promptToDecisionMs=1
decisionToAckMs=65
totalMs=66
```

Server timing before the slow transition:

```text
RoundStartModule: total_ms=98, redis_commit_ms=79
InitialRewardModule: total_ms=124, redis_commit_ms=95
WeatherModule: total_ms=117, redis_commit_ms=87
```

Critical prompt timing:

```text
runtime_decision_gateway_prompt_timing:
  create_prompt_ms=6681
  replay_wait_ms=53
  total_ms=6735
  request_type=draft_card
  player_id=1
  blocking_human_prompts=false
```

Critical transition timing:

```text
runtime_transition_phase_timing:
  module_type=DraftModule
  engine_transition_ms=6735
  prompt_materialize_ms=1
  prompt_publish_ms=3
  redis_commit_ms=12
  view_commit_build_ms=6
  total_ms=6772
  result_status=waiting_input
  reason=prompt_required
```

Decision acceptance timing:

```text
decision_ack_direct_sent
decision_received status=accepted
decision_route_timing submit_decision_ms=4 ack_publish_ms=2 total_ms=7
```

The next `DraftModule` prompt after the accepted decision was fast:

```text
base_commit_seq=4
commit_seq=5
module_type=DraftModule
engine_transition_ms=5
redis_commit_ms=9
view_commit_build_ms=5
total_ms=29
```

## Current Interpretation

This live failure is not evidence that the latest protocol identity route change
failed. The browser sent a decision, the server accepted it, the ACK was accepted,
and no mismatch/rejected/stale/fallback signal was observed.

The failure is a backend timing failure concentrated in the first `DraftModule`
`draft_card` prompt creation path:

- `maxCommandMs` was only 72ms.
- `maxDecisionRouteMs` was only 7ms.
- `maxRedisCommitCount` was 1.
- `maxViewCommitCount` was 1.
- `create_prompt_ms=6681` dominated the slow path.
- `replay_wait_ms=53` was not the dominant cost.
- The next prompt from the same module after the first accepted decision was fast.

Therefore the strongest current hypothesis is that the bottleneck is inside or
immediately below `PromptService.create_prompt()` / `RedisPromptStore` prompt
creation work, not browser decision latency and not duplicate Redis/view commits.

Candidate areas to inspect:

- lock scope inside `PromptService.create_prompt()`
- `_prune_resolved`
- `_has_recently_resolved_request`
- existing pending prompt lookup
- `_supersede_pending_for_player`
- `_set_pending`
- lifecycle record write
- prompt alias writes
- debug record write
- Redis client cold path or connection establishment
- container CPU scheduling/cold startup on the first draft prompt

The evidence is not yet sufficient to choose one. It is sufficient to say the next
step should be sub-phase instrumentation before behavior changes.

## Similar Historical Signal

An earlier live protocol gate failure family existed around prompt-required
boundaries after the server rebuild. In that earlier case, logs pointed at
`PromptService.wait_for_decision(timeout_ms=1)` after a prompt-required module and a
roughly 6.7 second live transition. The current failure is similar in shape because
it is a prompt-required live transition near 6.7 seconds, but different in measured
cause because the current log says `create_prompt_ms=6681` while `replay_wait_ms=53`.

Treat these as possibly related, not proven identical.

## Recommended Immediate Investigation

Add structured sub-phase timing around prompt creation before changing behavior:

1. `PromptService.create_prompt()` total and per-step timing:
   - lock wait time
   - `_prune_resolved`
   - identity normalization
   - scoped key build
   - existing pending lookup
   - recent resolved lookup
   - continuation validation
   - supersede previous pending prompts
   - `_set_pending`
   - lifecycle record write
   - waiter/event setup
2. `RedisPromptStore` timing:
   - pending HSET/write
   - alias writes
   - lifecycle write
   - debug/upsert write
   - recently resolved scan/read
3. Repeat exactly the failing one-game seed.
4. Compare:
   - first `DraftModule` prompt in fresh stack
   - second `DraftModule` prompt in same session
   - same seed after stack restart
   - same seed without stack restart

The expected useful outcome is not only "pass/fail." The expected outcome is a
single dominant sub-phase or a clear indication of lock/cold-start behavior.

## What Not To Do Yet

Do not:

- relax `--max-backend-transition-ms 5000`
- remove the protocol identity compatibility bridge
- blame Redis scaling without evidence
- treat `1 server + multiple Redis` as a valid current-code baseline
- introduce another helper that leaves `RuntimeService` or `PromptService` with the
  same unclear ownership
- move prompt persistence out of the critical path without deciding which component
  owns prompt boundary atomicity

## Useful Review Lens

The main design question is whether prompt creation is one coherent responsibility
or several responsibilities currently bundled together:

- protocol identity adaptation
- prompt continuation validation
- pending prompt replacement
- Redis persistence
- lifecycle/debug audit trail
- replay/recovery support
- WebSocket-visible prompt boundary materialization
- command boundary timing accountability

If these must remain atomic, the code should make the transaction boundary explicit
and fast. If they do not need to be atomic, the current structure may be forcing too
much non-critical work into the live transition SLO.
