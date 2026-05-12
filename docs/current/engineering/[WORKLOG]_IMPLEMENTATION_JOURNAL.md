# Implementation Journal

## 2026-05-12 Server-Split Shared-Redis Protocol Gate Validation

- Started one shared Redis at port `6390` under compose project `project-mrn-protocol-a-shared-redis`.
- Started five server stacks on ports `9111` through `9115`, all pointed at the shared Redis with per-server key prefixes:
  - game 1: server `9111`, prefix `mrn:protocol:a:g1`
  - game 2: server `9112`, prefix `mrn:protocol:a:g2`
  - game 3: server `9113`, prefix `mrn:protocol:a:g3`
  - game 4: server `9114`, prefix `mrn:protocol:a:g4`
  - game 5: server `9115`, prefix `mrn:protocol:a:g5`
- Ran a 5-game concurrent protocol gate at `tmp/rl/full-stack-protocol/headless-5-server-split-redis-shared-20260512`.
- Result: all five games passed. Maximum protocol command latency was `2224ms`, well below the `5000ms` threshold. Maximum decision route `ack_publish_ms` was `786ms`.
- Shared Redis post-check stayed clean: `evicted_keys=0`, `total_error_replies=0`.
- This isolates the earlier failure away from Redis-only saturation: splitting the server side while keeping one Redis removed the `5225ms` ACK failure.

## 2026-05-12 Single-Server Multi-Redis Validation Blocker

- A valid "one server, five Redis" test cannot be produced by compose wiring alone.
- Current server state construction creates one global `RedisConnection` at startup in `apps/server/src/state.py`, then shares it across session, room, stream, prompt, runtime, game-state, and command stores.
- Supplying five Redis containers without changing server routing would only leave four Redis instances unused, which is a fake test.
- A real validation requires a session/request-aware Redis routing layer shared consistently by the API server and workers.

## 2026-05-12 Per-Game Redis Protocol Gate Validation

- Made `docker-compose.protocol.yml` accept `MRN_REDIS_URL` from the environment while preserving the default `redis://redis:6379/0`.
- Added per-game runner templates to `apps/web/src/headless/runProtocolGateGames.ts`:
  - `--base-url-template`
  - `--redis-url-template`
  - `--backend-docker-compose-project-template`
- Started five isolated compose projects, each with its own server and Redis:
  - game 1: server `9101`, Redis `6381`, compose project `project-mrn-protocol-g1`
  - game 2: server `9102`, Redis `6382`, compose project `project-mrn-protocol-g2`
  - game 3: server `9103`, Redis `6383`, compose project `project-mrn-protocol-g3`
  - game 4: server `9104`, Redis `6384`, compose project `project-mrn-protocol-g4`
  - game 5: server `9105`, Redis `6385`, compose project `project-mrn-protocol-g5`
- Ran a 5-game concurrent protocol gate at `tmp/rl/full-stack-protocol/headless-5-isolated-redis-20260512`.
- Result: all five games passed. Maximum protocol command latency was `976ms`, well below the `5000ms` threshold. Maximum decision route `ack_publish_ms` was `231ms`.
- Redis post-check stayed clean for all five Redis instances: `evicted_keys=0`, `total_error_replies=0`.

## Verification

- `npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts`
- `npm --prefix apps/web run build`
- `git diff --check`
- `npm --prefix apps/web run rl:protocol-gate:games -- --games 5 --concurrency 5 --quiet-progress --run-root tmp/rl/full-stack-protocol/headless-5-isolated-redis-20260512 --seed-base 2026051250 --base-url-template 'http://127.0.0.1:910{game}' --redis-url-template 'redis://127.0.0.1:638{game}/0' --backend-docker-compose-project-template 'project-mrn-protocol-g{game}' -- --profile live --timeout-ms 600000 --idle-timeout-ms 120000 --progress-interval-ms 10000 --raw-prompt-fallback-delay-ms off --require-backend-timing --max-backend-command-ms 5000 --max-backend-transition-ms 5000 --max-backend-redis-commit-count 1 --max-backend-view-commit-count 1 --max-protocol-command-latency-ms 5000 --backend-docker-compose-file ../../docker-compose.protocol.yml --backend-docker-compose-service server`

## 2026-05-12 Headless Protocol Gate Log Hygiene

- Added `--quiet-progress` to the multi-game protocol gate runner so repeated `PROTOCOL_GATE_GAME_PROGRESS` lines stay in artifact files instead of filling the AI conversation context.
- Kept start/end/failure pointer lines visible on stderr; progress remains persisted under each game's `raw/progress.ndjson` and `summary/progress.json`.
- Ran a 5-game concurrent headless protocol gate at `tmp/rl/full-stack-protocol/headless-5-concurrent-quiet-20260512`.
- Result: gate failed fast on game 2 due protocol command latency `5225ms` exceeding the `5000ms` limit; games 1, 3, 4, and 5 were aborted by fail-fast.
- Redis post-check stayed clean: `evicted_keys=0`, `total_error_replies=0`.

## Verification

- `npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts`
- `npm --prefix apps/web run build`
- `npm --prefix apps/web run rl:protocol-gate:games -- --games 5 --concurrency 5 --quiet-progress --run-root tmp/rl/full-stack-protocol/headless-5-concurrent-quiet-20260512 --seed-base 2026051250 -- --base-url http://127.0.0.1:9091 --profile live --timeout-ms 600000 --idle-timeout-ms 120000 --progress-interval-ms 10000 --raw-prompt-fallback-delay-ms off --require-backend-timing --max-backend-command-ms 5000 --max-backend-transition-ms 5000 --max-backend-redis-commit-count 1 --max-backend-view-commit-count 1 --max-protocol-command-latency-ms 5000 --backend-docker-compose-project project-mrn-protocol --backend-docker-compose-file ../../docker-compose.protocol.yml --backend-docker-compose-service server`

## 2026-05-05 Runtime Cleanup

- Active runtime execution is owned by module frames, native sequence handlers, and explicit prompt continuation contracts.
- Removed stale metadata shims, prompt mirrors, replay aliases, and fallback policy bodies from the active tree.
- Current prompt payloads use `request_type`, `legal_choices`, `public_context`, and `choice_id`.
- View recovery emits `view_state_restored` as a UI restoration event, not a game transition.
- Character suppression, trick flow, fortune follow-ups, arrival handling, LAP rewards, and simultaneous resupply now flow through module-owned contracts.
- Remaining audit checks detect forbidden module checkpoint shapes in imported debug logs without exposing them as executable runtime modules.

## Verification

- Python focused runtime/server tests: 419 passed, 14 subtests passed.
- Web focused selector/replay tests: 206 passed.
- Python compile check passed for touched engine, server, policy, and audit modules.
- `git diff --check` passed.
