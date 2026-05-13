# Implementation Journal

This journal is current-state context, not an exhaustive historical log. Keep
entries only when they help a future implementation session decide:

- what changed recently,
- what responsibility moved or intentionally stayed,
- what verification already proved,
- what remaining work should be picked next.

Older detailed phase logs should be removed once their conclusions are reflected
in the active plans, status index, tests, or canonical contract documents.

## 2026-05-14 Runtime Protocol Identity Continuation

- Added opaque prompt identity companions while keeping legacy request IDs as
  the canonical prompt storage/resume key for compatibility.
- `PromptService` now accepts a submitted `public_request_id` at the protocol
  boundary, resolves it to the legacy prompt key internally, and preserves the
  submitted public id in the decision payload.
- Module decision commands now carry explicit `prompt_instance_id`, and runtime
  resume matching and prompt sequence seeding prefer that explicit field before
  falling back to legacy request-id parsing.
- Active batch prompt enrichment now prefers explicit `batch_id` plus submitted
  player identity before using the legacy `batch:*:pN` shape as fallback.
- WebSocket human decision ACKs now include the accepted decision
  `command_seq`, matching the REST/external-AI decision callback boundary and
  letting clients correlate an accepted prompt decision with the queued runtime
  command.
- `PromptService.wait_for_decision()` now resolves already-submitted public
  request aliases through lifecycle metadata for both in-memory and Redis
  stores. Zero-timeout missing-decision probes still avoid pending/resolved hash
  scans.
- `PromptService.get_prompt_lifecycle()` now accepts the same public request
  alias and returns the legacy-key lifecycle record, which keeps debug/status
  reads usable before the canonical prompt key migration.
- `PromptService.get_pending_prompt()` now accepts public request aliases for
  active pending prompts. It resolves only against active pending records, so
  completed prompts do not reappear as pending through lifecycle metadata.
- `PromptService.mark_prompt_delivered()` and
  `record_external_decision_result()` now resolve submitted public request
  aliases before lifecycle writes, and `PromptService.expire_prompt()` resolves
  active pending aliases before deletion/resolution. Delivered, external-result,
  and expired states therefore update the same legacy-key lifecycle record
  instead of creating or missing a parallel public-key record.
- Redis-backed `PromptService` coverage now proves the same public request
  alias adapter at pending-read, accept, wait, lifecycle-read, and expire
  boundaries. That keeps the Redis path aligned with the in-memory service
  tests instead of relying on one backend's behavior as evidence for both.
- Decision command materialization now copies prompt player identity companions
  (`public_player_id`, `seat_id`, `viewer_id`, and display aliases) into normal
  decision commands, simultaneous batch collector responses, and timeout
  fallback responses. Numeric `player_id` remains the compatibility routing
  alias.
- `BatchCollector` completion commands now expose
  `responses_by_public_player_id` as an additive companion derived from
  collected response payloads. Numeric `responses_by_player_id` remains the
  canonical resume map for compatibility.
- `RuntimeDecisionResume` now accepts public-only `batch_complete`
  `responses_by_public_player_id` payloads by resolving public player IDs
  through `SessionService` and materializing the numeric engine bridge map.
  Legacy numeric `responses_by_player_id` payloads are still accepted.
- Responsibility moved: prompt continuation matching no longer relies first on
  semantic `request_id` strings. Compatibility storage and replay still keep
  the legacy request id key until the canonical opaque prompt-key migration is
  done as a separate, larger change.

Verification:

- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_from_batch_complete_command_uses_collected_response apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_resume_from_batch_complete_command_accepts_public_response_map apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_collected_batch_responses_are_applied_before_primary_resume -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py::PromptServiceTests::test_mark_prompt_delivered_resolves_public_request_id_alias apps/server/tests/test_prompt_service.py::PromptServiceTests::test_external_decision_result_resolves_public_request_id_alias -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_batch_collector.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py::SessionsApiTests::test_external_ai_decision_callback_accepts_public_player_and_request_identity -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_accepts_public_request_id_with_redis_prompt_store apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_expires_public_request_id_with_redis_prompt_store -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_sequence.py apps/server/tests/test_redis_realtime_services.py -q -k "runtime_prompt_sequence_seed or prompt_sequence"`
- `./.venv/bin/python tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-13 Prompt Identity Cleanup

- Removed `DecisionGateway`'s process-local request id fallback for prompt
  creation errors.
- Blocking human prompt replay now reuses an existing pending prompt with the
  same deterministic `request_id`; it does not create a new per-process/random
  request id and supersede the original prompt.
- AI decision events now use a deterministic protocol id derived from request
  type, player id, and public context fingerprint. At the time of this cleanup
  it did not replace the external AI worker/callback redesign; the HTTP
  external AI path was later moved to a pending prompt plus callback command
  boundary, while local/loopback AI remains a separate test-profile concern.
- Responsibility moved: request identity is no longer owned by a
  `DecisionGateway` in-memory counter. Prompt identity is owned by protocol
  boundary data, and duplicate pending prompts remain owned by the existing
  prompt lifecycle.
- Server `_LocalHumanDecisionClient` no longer reads or writes engine
  `HumanHttpPolicy._prompt_seq`. Runtime prompt sequence is seeded from
  checkpoint/domain logic and held by the server adapter while the engine
  transition is running.
- Responsibility intentionally remains: process-local runtime `_prompt_seq`
  ownership is still open and requires prompt boundary creation to move out of
  the policy adapter path. Engine standalone `HumanHttpPolicy._prompt_seq`
  remains for non-server human play.

Verification:

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_gateway_reuses_pending_prompt_id_when_blocking apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_decision_gateway_has_no_process_local_request_seq_fallback -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q -k 'decision_gateway or runtime_prompt_boundary'`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_prompt_module_continuation.py::test_local_human_client_prompt_sequence_is_owned_by_server_adapter apps/server/tests/test_prompt_module_continuation.py::test_local_human_prompt_created_inside_module_attaches_active_continuation -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_human_bridge_prompt_sequence_can_resume_from_checkpoint_value apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_seeds_prompt_sequence_from_previous_same_module_decision -q`

## 2026-05-13 Runtime Matrix Coverage Sync

- Fixed `tests/test_module_runtime_playtest_matrix_doc.py` failures caused by
  stale coverage artifacts, not runtime rule changes.
- Added frontend prompt selector coverage for serial prompt request types already
  present in `round-combination.regression-pack.json`: `trick_to_use`,
  `specific_trick_reward`, `lap_reward`, `purchase_tile`, and
  `coin_placement`.
- Added `InitialRewardModule` to the RoundFrame module inventory in
  `docs/current/runtime/round-action-control-matrix.md`, matching
  `engine/runtime_modules/catalog.py`.
- Responsibility did not move: runtime contracts remain owned by the catalog and
  regression pack; the frontend spec and runtime matrix now track those
  contracts again.

Verification:

- `./.venv/bin/python -m pytest tests/test_module_runtime_playtest_matrix_doc.py -q`
- `npm --prefix apps/web test -- src/domain/selectors/promptSelectors.spec.ts`
- `python3 tools/plan_policy_gate.py`
- `git diff --check`

## 2026-05-13 Documentation Hygiene

- Renamed current documentation files under `docs/current` so filenames no
  longer contain shell-special square brackets.
- Preserved prefix semantics with plain names such as `PLAN_`, `ACTIVE_`, and
  `WORKLOG_`.
- Updated in-repo references, README pointers, tests, and
  `tools/plan_policy_gate.py`.
- Added policy that forbids square brackets in `docs/current` filenames and
  requires reference/policy gate updates in the same rename change.
- Added the mandatory pre-implementation contract to
  `docs/current/engineering/MANDATORY_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
  and root `AGENTS.md`.

Verification:

- bracket filename/reference check: `files=0`, `refs=0`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-13 Server Runtime Rebuild Phase 9 Current State

Phase 9 is reducing `RuntimeService` from command lifecycle owner to runtime
boundary adapter. The current split is:

- `SessionLoop` owns command lifecycle control flow through
  `SessionCommandExecutor`.
- `CommandRouter` only validates accepted command references and wakes
  `SessionLoopManager`.
- `CommandStreamWakeupWorker` observes Redis pending/resumable commands and
  wakes `SessionLoopManager`; it no longer directly calls runtime execution.
- `CommandRecoveryService` owns read-side command recovery queries.
- `CommandProcessingGuardService` owns consumer-offset checks, stale terminal
  classification, rejected/superseded/expired marking, and rejected offset
  advancement.
- `CommandExecutionGate` owns in-process active command/session gating and
  active runtime task deferral.
- `CommandBoundaryFinalizer` owns deferred commit finalization, latest
  `view_commit` emission, waiting prompt materialization, and finalization
  timing logs.
- `CommandBoundaryGameStateStore` owns command-boundary staging/deferred commit
  behavior and prevents internal module transitions from committing
  authoritatively mid-command.
- `CommandBoundaryRunner` owns command-boundary per-call store creation,
  transition repetition, terminal detection, finalizer call, module trace, and
  timing result assembly. `RuntimeService` only injects engine/persistence
  callables for that boundary.
- `runtime_prompt_sequence_seed()` lives in
  `apps/server/src/domain/prompt_sequence.py`, not `runtime_service.py`.
- Final command-boundary commit rechecks runtime lease ownership before
  authoritative Redis/view/prompt side effects.
- `RuntimeService.process_command_once()` has been removed. Production
  `SessionLoop` paths and diagnostic tests now use `SessionCommandExecutor`
  directly, while `RuntimeService` exposes only runtime-boundary lifecycle
  methods for command execution.
- `SessionLoop` no longer has a fallback to
  `RuntimeService.process_command_once()` when a runtime boundary lacks the
  lifecycle interface. Loop tests now exercise the lifecycle boundary path.

Important remaining responsibility:

- Remove process-local prompt sequence ownership entirely by moving prompt
  boundary creation out of the runtime policy/engine adapter path.
- Keep `CommandBoundaryGameStateStore` as the explicit command atomicity staging
  boundary until a future UnitOfWork-style owner exists in `SessionLoop` or
  `SessionCommandExecutor`.
- Keep Redis authoritative and `view_commit` as read model; do not reintroduce
  route-level runtime execution or heartbeat-driven repair.

Representative verification already passed during this phase:

- focused service tests for command recovery, processing guard, execution gate,
  boundary finalizer, boundary store, session loop, router, stream, and wakeup
  worker
- full `apps/server/tests` passes through the Phase 9 checkpoints
- `npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

## 2026-05-12 Runtime Rebuild Evidence To Preserve

- The valid scaling baseline is `5 server instances + 1 Redis`, not
  `1 server + 5 Redis`. Current server state construction uses one global
  `MRN_REDIS_URL`, so multiple Redis containers behind one server are unused
  unless a session-aware routing layer is built.
- A 5-game isolated server/Redis run passed with per-game server and Redis.
- A 5-server/1-Redis run passed, isolating earlier concurrent failures away from
  Redis-only saturation.
- A single-server/20-game stress run failed on backend timing, not command loss:
  `InitialRewardModule` transition wall-clock dominated, with evidence showing
  engine transition time far above Redis commit and view commit time.
- Conclusion: the observed 20-game single-server bottleneck was server-side
  engine transition saturation under one Python server process, not Redis
  commit, view projection, missing ACK, duplicate view commit, or command inbox
  loss.

This evidence remains useful because it explains why server-instance count and
runtime ownership matter more than Redis fan-out for the current architecture.

## 2026-05-13 Phase 10 Prompt Replay Probe Fix

- Removed the nonblocking prompt replay wait from human prompt creation.
  `DecisionGateway.resolve_human_prompt(blocking_human_prompts=False)` now uses
  `PromptService.wait_for_decision(timeout_ms=0)` as an immediate resolved
  decision probe. That probe does not create a pending waiter and does not scan
  the full resolved hash for TTL pruning on every wait call.
- Pre-fix 5-server evidence showed `WeatherModule` prompt creation spending
  6773ms in `replay_wait_ms`, with Redis commit/view commit still bounded.
  Post-fix 5-server evidence completed all games with max transition 538ms and
  max command 1224ms.
- Restart, pending-prompt reconnect, and duplicate decision smokes passed.
  Duplicate decision replay returned `stale/already_resolved`.
- 20-game/1-server remains a capacity bottleneck by design of the test: after
  the prompt replay wait was removed, fail-fast showed command wall-clock
  5357ms under one server process while prompt timing count was 0 and
  Redis/view commit counts stayed at 1.

Responsibility result: prompt lifecycle replay probing no longer blocks prompt
materialization. The remaining 20-game/1-server failure belongs to single-server
runtime scheduling/capacity, not prompt identity, Redis commit, view projection,
ACK delivery, or command inbox dedupe.

## 2026-05-13 Protocol Gate Output Hygiene

- The direct full-stack protocol gate and repeated-game protocol gate runner now
  suppress compact progress output by default. Pass `--verbose-progress` only
  when live progress lines are useful enough to spend terminal/chat context.
- `--verbose-progress` is the explicit opt-in for investigation runs where
  progress lines are worth the terminal/chat context cost.
- In repeated runs, raw child stdout/stderr and progress remain persisted under
  each `game-N/raw/` directory, and failure diagnosis still starts from
  `PROTOCOL_GATE_FAILURE_POINTER` plus `summary/failure_reason.json`.

Responsibility result: long-run evidence ownership stays with file artifacts and
failure pointers. Chat/terminal output is no longer responsible for carrying
successful progress details.

## 2026-05-13 Session Loop Recovery Status Closure

- Closed stale Phase 2/3 checklist items in the active server-runtime rebuild
  plan against existing implementation evidence.
- The selected wake policy is lazy wake start: session start does not create a
  long-lived loop; accepted durable commands wake `SessionLoopManager` through
  `CommandRouter` or `CommandStreamWakeupWorker`.
- The loop is a bounded drain task, not an idle daemon. Lease ownership is scoped
  to each command execution and released in `SessionCommandExecutor.finally`;
  the manager task exits once the Redis inbox is idle.
- Restart recovery is covered by Redis command inbox plus worker polling, not
  by process-local queue state or a separate remote-owner pub/sub signal.

Responsibility result: no runtime responsibility moved in this checkpoint. The
plan now matches the already implemented ownership: Redis inbox is durable
authority, router/worker are wake paths, and `SessionLoopManager` owns one
process-local drain task per session. External AI command-boundary unification
remains open.

## 2026-05-13 HTTP External AI Command Boundary

- HTTP external AI transport no longer invokes the worker sender/healthchecker
  inside the session loop. It materializes a provider=`ai` pending prompt and
  stops at `PromptRequired`.
- Added an external AI decision callback route. Accepted callbacks go through
  `PromptService.submit_decision()` and `CommandInbox.accept_prompt_decision()`,
  then wake the session loop through `CommandRouter.wake_after_accept()`.
- Preserved provider=`ai` through pending prompt payload, submitted decision
  payload, persisted `decision_submitted` command, runtime decision resume, and
  stream ACK.
- Removed obsolete runtime-service tests that asserted the old forbidden
  behavior: direct in-loop HTTP worker calls, retry loops, and local AI fallback
  from the HTTP transport path. Worker API and helper validation remain covered
  outside the session-loop transport contract.

Responsibility result: HTTP external AI provider execution moved out of the
session loop. Decision acceptance remains in `PromptService`/`CommandInbox`.
Wake remains in `CommandRouter`. Redis command inbox remains the durable
authority. Local and loopback AI transports intentionally remain outside this
checkpoint.

## 2026-05-13 Simultaneous Batch Command Boundary

- `PromptService.submit_decision()` now routes simultaneous batch prompt
  responses through `BatchCollector` instead of appending one
  `decision_submitted` command per player.
- `PromptService.record_timeout_fallback_decision()` uses the same collector for
  simultaneous batch timeout fallback decisions, so human and timeout races are
  resolved by the collector's atomic completion primitive.
- Incomplete batch responses return accepted decision state with no command
  sequence. `PromptTimeoutWorker` now wakes the command router only when the
  accepted decision state contains a positive command sequence.
- `SessionLoop` accepts `batch_complete` as a runtime command, and
  `RuntimeService` reconstructs a `RuntimeDecisionResume` from the collected
  responses. Non-primary collected responses are applied to the active batch
  before the primary resume continues the engine transition.

Responsibility result: simultaneous batch completion ownership moved out of
route/timeout-side command append paths and into `BatchCollector`. The session
loop remains the only command execution path. `RuntimeService` still performs
the engine resume and state mutation, but it no longer decides whether a batch
is complete or creates per-response commands.

## 2026-05-13 One-Server Five-Game Baseline

- Live protocol gate with one server, one Redis, five concurrent games passed:
  `tmp/rl/full-stack-protocol/server-rebuild-live-5game-20260513-205642`.
- All five sessions completed with no stale ACK, rejected ACK, failed command,
  or raw-prompt fallback counts.
- Backend timing stayed inside the 5s gate: max command 1875ms and max
  transition 1232ms. Redis commit count and view commit count stayed at 1.
- Redis state inspector reported diagnostic `ok` for all five sessions.

Responsibility result: the current rebuild is not dependent on one server per
game for a five-game live smoke. The remaining one-server question is capacity
boundary measurement, not a known Redis/view-commit/prompt-lifecycle violation.

## 2026-05-13 One-Server Capacity Boundary

- Committed local reproducibility cleanup as `f1a24ead`
  (`chore: stabilize protocol gate local artifacts`): ignored `.playwright-mcp/`
  and passed `MRN_ADMIN_TOKEN` through the protocol compose file.
- One server plus one Redis with eight concurrent games passed:
  `tmp/rl/full-stack-protocol/server-rebuild-capacity-8game-1server-20260513-211035`.
  All eight sessions completed; max command was 3943ms, max transition was
  2159ms, Redis/view commit counts stayed at 1, and slow command/transition
  counts were 0.
- One server plus one Redis with ten concurrent games found the first measured
  SLO boundary:
  `tmp/rl/full-stack-protocol/server-rebuild-capacity-10game-1server-20260513-211951`.
  Game 3 failed `backend_timing` because command seq 1 took 5886ms for
  `reason=prompt_required`, above the 5000ms command SLO.
- The failure did not show a rule-flow or persistence contract break. For the
  failing command, `engine_loop_total_ms=203`, `redis_commit_count=1`,
  `view_commit_count=1`, and max transition stayed 1273ms. The excess was
  `executor_overhead_ms=5680`, which points to single-server runtime scheduling
  contention under concurrent command execution.

Responsibility result: no game-rule, Redis authority, `view_commit`, prompt
identity, ACK, or command-inbox responsibility moved or failed in this
checkpoint. The measured boundary is capacity/SLO ownership: a single server is
inside the current 5s command SLO at eight concurrent games and outside it at
ten concurrent games. Further 12/15-game one-server runs would characterize
overload, not find the first boundary, so they were not run.

## 2026-05-13 Protocol Evidence And Remote Gate Closure

- Committed and pushed fail-closed remote evidence gates as `fe882c7c`
  (`Harden external evidence gates`) on
  `codex/external-topology-protocol-ops`.
- Confirmed missing remote inputs are blocked by design: local Redis platform
  manifests fail with `--require-external-topology`, loopback worker URLs fail
  with `--require-non-local-endpoint`, and loopback game-server URLs fail with
  `--require-non-local-server`.
- Synchronized the runtime protocol plan status with actual evidence. Phase 0
  additive identity, Redis debug retention, baseline prompt lifecycle, and
  Redis viewer-outbox debug/indexing are implemented; globally opaque prompt
  request IDs, UUID prompt instance IDs, first-class stale/resolved lifecycle
  states, and real outbox read mode remain explicit residual work.
- Local validation passed: 190 server protocol/lifecycle/outbox tests, 76
  frontend headless/stream tests, smoke workflow gate, live protocol gate,
  bounded UI full-game progress, and full-stack live RL smoke at
  `tmp/rl/full-stack-protocol/codex-all-20260513`.

Responsibility result: no runtime ownership was silently moved in this
checkpoint. Evidence classification moved into scripts and status docs:
loopback/local runs are local evidence only, while remote/external evidence
requires non-local endpoint URLs, auth, and platform-filled Redis commands.
Protocol-plan responsibility also became explicit: completed additive/debug
foundations are separated from residual identity and outbox migration work.

## 2026-05-12 Runtime Rebuild Baseline

- The active rebuild plan is
  `docs/current/architecture/PLAN_SERVER_RUNTIME_REBUILD_2026-05-12.md`.
- Rejected directions included direct local queue command acceptance,
  pub/sub-only outbound delivery, non-atomic batch completion, weak deterministic
  prompt ids, and further expansion of `RuntimeService`.
- Accepted direction: Redis remains authoritative, accepted decisions become
  durable command references, `SessionLoop` drains commands, and external
  boundaries publish state through explicit commits and projected `view_commit`
  records.

## Journal Maintenance Rule

When adding to this file:

- Add only the current checkpoint and its responsibility result.
- Prefer one consolidated entry over one entry per micro-change.
- Remove old details once the active plan, tests, or status index carries the
  durable conclusion.
- Do not keep raw protocol logs here. Store bulky evidence under the run
  artifact directory and keep only decision-grade conclusions in this journal.
