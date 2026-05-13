# Implementation Journal

This journal is current-state context, not an exhaustive historical log. Keep
entries only when they help a future implementation session decide:

- what changed recently,
- what responsibility moved or intentionally stayed,
- what verification already proved,
- what remaining work should be picked next.

Older detailed phase logs should be removed once their conclusions are reflected
in the active plans, status index, tests, or canonical contract documents.

## 2026-05-13 Prompt Identity Cleanup

- Removed `DecisionGateway`'s process-local request id fallback for prompt
  creation errors.
- Blocking human prompt replay now reuses an existing pending prompt with the
  same deterministic `request_id`; it does not create a new per-process/random
  request id and supersede the original prompt.
- AI decision events now use a deterministic protocol id derived from request
  type, player id, and public context fingerprint. This only removes local
  random identity from the current in-process AI event path; it does not replace
  the still-open external AI worker/callback redesign.
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
- `RuntimeService.process_command_once()` remains as a compatibility wrapper
  over the `SessionCommandExecutor` path. It remains because existing
  runtime/route/stream tests still use it as a diagnostic compatibility
  entrypoint; the production `SessionLoop` path does not require it.
- `SessionLoop` no longer has a fallback to
  `RuntimeService.process_command_once()` when a runtime boundary lacks the
  lifecycle interface. Loop tests now exercise the lifecycle boundary path.

Important remaining responsibility:

- Remove process-local prompt sequence ownership entirely by moving prompt
  boundary creation out of the runtime policy/engine adapter path.
- Remove the `RuntimeService.process_command_once()` compatibility wrapper
  after direct test and diagnostic callers are migrated. The production
  `SessionLoop` fallback has already been removed.
- Keep Redis authoritative and `view_commit` as read model; do not reintroduce
  route-level runtime execution or heartbeat-driven repair.

Representative verification already passed during this phase:

- focused service tests for command recovery, processing guard, execution gate,
  boundary finalizer, boundary store, session loop, router, stream, and wakeup
  worker
- full `apps/server/tests` passes through the Phase 9 checkpoints
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
