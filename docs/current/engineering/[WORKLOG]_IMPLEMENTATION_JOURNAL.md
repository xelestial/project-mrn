# Implementation Journal

## 2026-05-13 Server Runtime Rebuild Phase 9 Command Boundary Finalizer

- Added `CommandBoundaryFinalizer` as the command-boundary finalization owner.
- Moved deferred commit copy, authoritative Redis commit, latest `view_commit` emission, waiting prompt materialization, and finalization timing log out of `RuntimeService._run_engine_command_boundary_loop_sync()`.
- Kept `_CommandBoundaryGameStateStore` intentionally. It is still the transitional adapter that prevents internal module transitions from committing mid-command; deleting it before SessionLoop owns atomic commit would reintroduce the write-boundary defect.
- Added focused tests for deferred commit finalization and no-op finalization when no deferred commit exists.

## Verification

- `python3 -m compileall apps/server/src/services/command_boundary_finalizer.py apps/server/src/services/runtime_service.py`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_boundary_finalizer.py apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_command_scope_loop_defers_internal_transition_commits apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_command_boundary_loop_uses_per_call_store_without_swapping_shared_store apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_command_boundary_loop_hydrates_and_prepares_engine_once -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_boundary_finalizer.py apps/server/tests/test_command_execution_gate.py apps/server/tests/test_command_processing_guard.py apps/server/tests/test_command_recovery.py apps/server/tests/test_runtime_service.py apps/server/tests/test_session_loop.py apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_command_router.py apps/server/tests/test_stream_api.py apps/server/tests/test_sessions_api.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests -q`

Result: focused finalizer and command-boundary tests passed, direct-impact server tests passed with `279 passed, 14 subtests passed`, and full server tests passed with `680 passed, 46 subtests passed`.

## 2026-05-13 Server Runtime Rebuild Phase 9 Command Execution Gate Ownership

- Added `CommandExecutionGate` as the in-process command execution gate. It owns active command session begin/end/active checks and active runtime task deferral.
- `RuntimeService` no longer stores `_active_command_sessions` or `_command_processing_lock` directly. Its `_begin_command_processing`, `_command_processing_active`, `_end_command_processing`, and `_runtime_task_processing_guard` methods now delegate to `CommandExecutionGate`.
- Updated runtime tests that previously mutated `RuntimeService` internals to use the transitional wrapper methods, and added direct execution-gate tests.

## Verification

- `python3 -m compileall apps/server/src/services/command_execution_gate.py apps/server/src/services/command_processing_guard.py apps/server/src/services/runtime_service.py`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_execution_gate.py apps/server/tests/test_command_processing_guard.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_defers_when_runtime_task_is_active apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_checks_active_command_before_stale_guard apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_skips_already_consumed_command -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_execution_gate.py apps/server/tests/test_command_processing_guard.py apps/server/tests/test_command_recovery.py apps/server/tests/test_runtime_service.py apps/server/tests/test_session_loop.py apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_command_router.py apps/server/tests/test_stream_api.py apps/server/tests/test_sessions_api.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests -q`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

Result: focused execution-gate and runtime entrypoint tests passed, direct-impact server tests passed with `277 passed, 14 subtests passed`, full server tests passed with `678 passed, 46 subtests passed`, and document/diff gates passed.

## 2026-05-13 Server Runtime Rebuild Phase 9 Command Processing Guard Ownership

- Added `CommandProcessingGuardService` as the command precondition/stale-terminal boundary. It owns consumer-offset guard checks, pending-command ordering decisions, stale command terminal classification, rejected/superseded/expired command state marking, and rejected command offset advancement.
- `RuntimeService.process_command_once()` still owns runtime lease acquisition, active command session locking, executor dispatch, runtime status persistence, and command-boundary engine execution. Its `_command_processing_guard`, `_mark_command_state`, `_save_rejected_command_offset`, and stale terminal helper methods are now transitional wrappers around the new service.
- Added direct tests for the new service and kept runtime command-processing tests proving existing behavior is preserved.

## Verification

- `python3 -m compileall apps/server/src/services/command_processing_guard.py apps/server/src/services/runtime_service.py`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_processing_guard.py apps/server/tests/test_command_recovery.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_skips_already_consumed_command apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_reprocesses_offset_conflict_when_checkpoint_still_waits_for_command apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_reprocesses_checkpoint_match_when_pending_lookup_races apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_skips_command_that_no_longer_matches_waiting_prompt apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_advances_offset_when_older_command_precedes_active_prompt apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_defers_newer_command_until_earlier_pending_is_consumed -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_processing_guard.py apps/server/tests/test_command_recovery.py apps/server/tests/test_runtime_service.py apps/server/tests/test_session_loop.py apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_command_router.py apps/server/tests/test_stream_api.py apps/server/tests/test_sessions_api.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests -q`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

Result: focused command guard and runtime command-processing tests passed, direct-impact server tests passed with `274 passed, 14 subtests passed`, full server tests passed with `675 passed, 46 subtests passed`, and document/diff gates passed.

## 2026-05-13 Server Runtime Rebuild Phase 9 Command Recovery Query Ownership

- Added `CommandRecoveryService` as the read-side command recovery boundary. It owns `pending_resume_command`, `has_unprocessed_runtime_commands`, command seq lookup, and resume-command matching against the recovery checkpoint.
- Wired server state to expose `command_recovery_service` from the existing runtime facade during the transition.
- Updated authenticated runtime-status recovery and WebSocket connect recovery to call `CommandRecoveryService` instead of `RuntimeService` for durable command inbox queries.
- Kept `RuntimeService` wrapper methods temporarily because `RuntimeService.process_command_once()` still uses the same recovery checks inside its command guard. Those wrappers now delegate to `CommandRecoveryService`; they are compatibility surface, not the route-level owner.
- Added direct command recovery tests and moved session route tests to monkeypatch the new service boundary.

## Verification

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_recovery.py apps/server/tests/test_sessions_api.py::SessionsApiTests::test_authenticated_runtime_status_defers_recovery_when_commands_are_unprocessed apps/server/tests/test_sessions_api.py::SessionsApiTests::test_authenticated_runtime_status_defers_pending_command_before_plain_recovery apps/server/tests/test_sessions_api.py::SessionsApiTests::test_authenticated_runtime_status_does_not_start_recovery_for_waiting_checkpoint apps/server/tests/test_sessions_api.py::SessionsApiTests::test_authenticated_runtime_status_defers_waiting_input_pending_command -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_has_unprocessed_runtime_commands_checks_consumer_offset apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_pending_resume_command_returns_unconsumed_matching_command apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_resolved_timeout_fallback_command_can_resume_waiting_checkpoint -q`
- `python3 -m compileall apps/server/src/services/command_recovery.py apps/server/src/services/runtime_service.py apps/server/src/routes/sessions.py apps/server/src/routes/stream.py apps/server/src/state.py`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_recovery.py apps/server/tests/test_runtime_service.py apps/server/tests/test_sessions_api.py apps/server/tests/test_stream_api.py apps/server/tests/test_session_loop.py apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_command_router.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests -q`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

Result: focused command recovery/session recovery tests passed, transitional `RuntimeService` wrapper tests passed, direct-impact server tests passed with `271 passed, 14 subtests passed`, full server tests passed with `672 passed, 46 subtests passed`, and document/diff gates passed.

## 2026-05-13 Server Runtime Rebuild Phase 9 CommandRouter Ownership

- Removed the manager-less direct runtime fallback from `CommandRouter`.
- `CommandRouter` now only validates accepted command references and delegates execution wakeup to `SessionLoopManager.wake()`.
- If `CommandRouter` has no `SessionLoopManager`, it logs `runtime_wakeup_command_skipped` with `reason=missing_session_loop_manager` and does not call `RuntimeService.process_command_once()`.
- Removed the WebSocket decision route fallback that constructed `CommandRouter` from `session_service` and `runtime_service`. Missing route-level router injection now skips the wakeup instead of creating a local executor.
- Updated stream and router tests so accepted decisions prove session-loop wake signaling, not direct runtime execution.
- Left `RuntimeService.process_command_once()` in place as the transitional runtime boundary adapter called by `SessionLoop`. Command guard, stale command terminal handling, offset storage, and atomic state/prompt/view/command commit still need to move before `_CommandBoundaryGameStateStore` and `_runtime_prompt_sequence_seed` can be removed.

## Verification

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_router.py apps/server/tests/test_stream_api.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_router.py apps/server/tests/test_stream_api.py apps/server/tests/test_session_loop.py apps/server/tests/test_command_wakeup_worker.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_rebuild_contract.py apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_prompt_timeout_worker.py apps/server/tests/test_stream_api.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests -q`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

Result: focused router/stream tests passed, direct-impact router/stream/session-loop/wakeup-worker tests passed, broader runtime/Redis/prompt-timeout/stream tests passed, full server test suite passed with `669 passed, 46 subtests passed`, and document gates passed.

## 2026-05-13 Server Runtime Rebuild Phase 9 Wakeup Worker Ownership

- Removed the transitional direct runtime fallback from `CommandStreamWakeupWorker`.
- The worker now only observes Redis pending/resumable commands and hands execution to `SessionLoopManager.wake()`.
- If no `SessionLoopManager` is configured, the worker logs `command_wakeup_worker_session_loop_manager_missing` and leaves the `runtime_wakeup` consumer offset untouched. This preserves the command for the real session loop instead of silently consuming it.
- Updated wakeup worker tests to assert manager handoff, no direct `RuntimeService.process_command_once()` / `start_runtime()` calls, stale command offset advancement only for stale commands, and consumed-command rescan throttling.

## Verification

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_wakeup_worker.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_session_loop.py apps/server/tests/test_command_router.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_rebuild_contract.py apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_prompt_timeout_worker.py apps/server/tests/test_stream_api.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests -q`
- `python3 tools/plan_policy_gate.py`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `git diff --check`

Result: focused worker/session-loop/router tests passed, broader runtime/Redis/prompt-timeout/stream tests passed, and full server test suite passed with `671 passed, 46 subtests passed`.

## 2026-05-12 Server Runtime Rebuild SessionLoop Yield Fix And Bottleneck Evidence

- Fixed a command-loss edge in the transitional wakeup path: when `CommandStreamWakeupWorker` is configured with runtime processing disabled, it now leaves the `runtime_wakeup` consumer offset untouched instead of marking accepted commands as consumed.
- Fixed `SessionLoopManager` yielded-drain handling. A manager task no longer stops when `SessionLoop.run_until_idle()` returns `status=yielded` because `max_commands_per_wakeup` was exhausted. It immediately drains again until idle, blocked, or retry deadline.
- Added regression coverage proving a manager with `max_commands_per_wakeup=1` continues through three durable `decision_submitted` commands after deduping wakeups for the same session.
- Rebuilt five server stacks on ports `9111` through `9115` against one shared Redis on `6390`, with per-server key prefixes `mrn:protocol:s1` through `mrn:protocol:s5`.
- Ran the 5-server/1-Redis protocol gate at `tmp/rl/full-stack-protocol/server-rebuild-5server-1redis-yieldfix-20260512`.
- Result: all five games passed.
- Ran the single-server/20-game stress gate at `tmp/rl/full-stack-protocol/server-rebuild-1server-20game-yieldfix-20260512`.
- Result: failed fast on backend timing. The first failure pointer was game 3, `failure_type=backend_timing`, `runtime_status=running_elsewhere`, with `InitialRewardModule` transition `total_ms=5677`.
- Parsed the game 3 backend timing log. Across 125 `runtime_transition_phase_timing` events, three exceeded `5000ms`, all in `InitialRewardModule`.
- Slowest transition evidence: `total_ms=6386`, `engine_transition_ms=6238`, `redis_commit_ms=53`, `view_commit_build_ms=11`.
- Module aggregate evidence:
  - `InitialRewardModule`: count 20, total p50 2073ms, p95 6247ms, max 6386ms, engine max 6238ms.
  - `WeatherModule`: max total 1985ms, Redis max 102ms.
  - `DraftModule`: max total 1390ms.
  - `RoundStartModule`: max total 990ms.
- Conclusion: the 20-game single-server failure is not a Redis commit, view projection, missing ACK, or command inbox loss symptom. It is server-side engine transition wall-clock saturation under one Python server process.

## Verification

- `python3 -m compileall apps/server/src/services/session_loop_manager.py`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_session_loop.py apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_command_router.py -q`
- `npm --prefix apps/web run rl:protocol-gate:games -- --games 5 --concurrency 5 --quiet-progress --run-root tmp/rl/full-stack-protocol/server-rebuild-5server-1redis-yieldfix-20260512 --seed-base 2026051600 --base-url-template 'http://127.0.0.1:911{game}' --backend-docker-compose-project-template 'project-mrn-protocol-s{game}' -- --profile live --timeout-ms 600000 --idle-timeout-ms 120000 --progress-interval-ms 10000 --raw-prompt-fallback-delay-ms off --require-backend-timing --max-backend-command-ms 5000 --max-backend-transition-ms 5000 --max-backend-redis-commit-count 1 --max-backend-view-commit-count 1 --max-protocol-command-latency-ms 5000 --backend-docker-compose-file ../../docker-compose.protocol.yml --backend-docker-compose-service server`
- `npm --prefix apps/web run rl:protocol-gate:games -- --games 20 --concurrency 20 --quiet-progress --run-root tmp/rl/full-stack-protocol/server-rebuild-1server-20game-yieldfix-20260512 --seed-base 2026051700 -- --profile live --timeout-ms 600000 --idle-timeout-ms 120000 --progress-interval-ms 10000 --raw-prompt-fallback-delay-ms off --require-backend-timing --max-backend-command-ms 5000 --max-backend-transition-ms 5000 --max-backend-redis-commit-count 1 --max-backend-view-commit-count 1 --max-protocol-command-latency-ms 5000 --base-url http://127.0.0.1:9121 --backend-docker-compose-project project-mrn-protocol-single20 --backend-docker-compose-file ../../docker-compose.protocol.yml --backend-docker-compose-service server`

## 2026-05-12 Server Runtime Rebuild Phase 9 Runtime Cleanup

- Removed the production-code branch on `PYTEST_CURRENT_TEST` for AI decision delay defaults.
- Added explicit `RuntimeSettings.runtime_ai_decision_delay_ms`, loaded from `MRN_RUNTIME_AI_DECISION_DELAY_MS`, and wired it into `RuntimeService`.
- Centralized runtime AI delay resolution in `RuntimeService._resolve_ai_decision_delay_ms()`. Session runtime parameters still override the service default.
- Reviewed `_CommandBoundaryGameStateStore`, `_runtime_prompt_sequence_seed`, and `CommandStreamWakeupWorker`.
- Did not remove `_CommandBoundaryGameStateStore`: it still provides the current command-boundary deferred commit adapter used by `RuntimeService._run_engine_command_boundary_loop_sync()`.
- Did not remove `_runtime_prompt_sequence_seed`: prompt instance sequencing still depends on recovery seeding until prompt boundary ownership moves out of `RuntimeService`.
- Did not delete `CommandStreamWakeupWorker`: it is now wired to `SessionLoopManager` and acts as Redis pending-command recovery/poll wakeup. The direct runtime fallback was removed in the later Phase 9 wakeup-worker ownership pass.

## Verification

- `python3 -m compileall apps/server/src/config/runtime_settings.py apps/server/src/state.py apps/server/src/services/runtime_service.py`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q`

## 2026-05-12 Server Runtime Rebuild Phase 8 Prompt Identity

- Added stable prompt request id generation to `apps/server/src/domain/protocol_ids.py`.
- Kept the old `session:rX:tY:pZ:type:N` shape as the fallback adapter when a prompt has no runtime boundary identity. This preserves current external/simple payload compatibility.
- Added boundary-aware ids for module prompts using `frame_id`, `module_id`, `module_cursor`, optional `batch_id`, `player_id`, `request_type`, and `prompt_instance_id`.
- Updated `DecisionGateway._stable_prompt_request_id()` to delegate to the shared protocol id helper instead of inlining the old round/turn-only shape.
- Updated `_LocalHumanDecisionClient._attach_active_module_continuation()` so module boundary fields are present before the request id is generated.
- Added collision and determinism tests for same round/turn/player/request_type prompts in different module frames.
- Left process-local prompt sequence removal open. The new id no longer depends only on `_prompt_seq`, but `prompt_instance_id` is still seeded by existing runtime recovery code until the session loop owns prompt boundaries end to end.

## Verification

- `python3 -m compileall apps/server/src/domain/protocol_ids.py apps/server/src/services/decision_gateway.py apps/server/src/services/runtime_service.py`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_protocol_ids.py apps/server/tests/test_prompt_module_continuation.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q`

## 2026-05-12 Server Runtime Rebuild Phase 7 External AI Boundary Review

- Reviewed the current external AI path before forcing it into `CommandInbox`.
- Confirmed `apps/server/src/external_ai_app.py` is the external worker API. Its `/decide` endpoint returns a worker choice to the game server; it is not a game-server callback endpoint that accepts completed AI decisions.
- Confirmed `_LocalAiDecisionClient`, `_LoopbackExternalAiTransport`, and `_HttpExternalAiTransport` in `apps/server/src/services/runtime_service.py` resolve AI decisions during the runtime execution call stack through `DecisionGateway.resolve_ai_decision()`.
- Did not insert `CommandInbox.accept()` into the transport path. That would preserve the current synchronous AI decision publish while also appending a second command for the same choice.
- Kept external AI command unification blocked on a real prompt boundary: `SessionLoop` must stop at a pending AI prompt, release execution, and accept the worker result later through the same decision command intake used by human and timeout decisions.

## 2026-05-12 Server Runtime Rebuild Phase 5 WebSocket Recovery

- Added `PromptService.list_pending_prompts()` so reconnect/resume repair can read authoritative pending prompt state without inspecting `view_commit`.
- Added WebSocket connect/resume pending prompt repair for authenticated seat viewers. The route projects the prompt through the existing visibility projector, marks the prompt lifecycle as `delivered`, and records the request id in a connection-local delivered set.
- Suppressed queued prompt events whose request id was already repaired on the same connection, preventing duplicate prompt delivery after a missed event is repaired.
- Kept spectators out of pending prompt repair. They still receive liveness heartbeat and projected public commits only.
- Kept heartbeat as liveness/diagnostics only. It does not fetch latest view commits, run prompt timeout recovery, or repair prompts.
- Chose explicit latest `view_commit` fetch plus authoritative pending prompt repair for this phase. A durable per-viewer outbox remains future work, not a hidden assumption of this implementation.

## Verification

- `python3 -m compileall apps/server/src/services/prompt_service.py apps/server/src/routes/stream.py`
- `./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py::StreamApiTests::test_connect_resends_pending_prompt_to_matching_seat_without_stream_event apps/server/tests/test_stream_api.py::StreamApiTests::test_resume_resends_pending_prompt_created_without_stream_event apps/server/tests/test_stream_api.py::StreamApiTests::test_spectator_does_not_receive_pending_prompt_repair -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py apps/server/tests/test_prompt_service.py -q`

## 2026-05-12 Server Runtime Rebuild Phase 3 SessionLoop Skeleton

- Added `apps/server/src/services/session_loop.py` to drain durable Redis command inbox entries by seq order for one session.
- Added `apps/server/src/services/session_loop_manager.py` to own one scheduled drain task per session and dedupe concurrent wakeups.
- Wired `CommandRouter` to delegate accepted command wakeups to `SessionLoopManager` when available.
- Wired `CommandStreamWakeupWorker` to use the manager as its execution handoff while preserving the older direct runtime fallback for tests and non-wired callers.
- Preserved the existing `running_elsewhere` retry behavior inside the manager so a temporary lease conflict does not turn a wake signal into a no-op.
- Kept `consumer_name="runtime_wakeup"` during transition so the old worker and new loop share the same Redis offset instead of observing the same command through two consumers.
- Kept lease/commit authority inside `RuntimeService.process_command_once()` for this phase. This is intentional transitional scaffolding, not the final ownership split.

## Verification

- `python3 -m compileall apps/server/src/services/session_loop.py apps/server/src/services/session_loop_manager.py apps/server/src/services/command_router.py apps/server/src/services/command_wakeup_worker.py apps/server/src/state.py`
- `./.venv/bin/python -m pytest apps/server/tests/test_session_loop.py apps/server/tests/test_command_router.py apps/server/tests/test_command_wakeup_worker.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_stream_api.py apps/server/tests/test_prompt_timeout_worker.py -q`

## 2026-05-12 Server Runtime Rebuild Phase 1/2 Contract Closure

- Added Redis command-store tests proving duplicate request ids are not reprocessed and do not consume a new command seq.
- Added Redis command-store tests proving command seq is monotonic per session, not globally shared across sessions.
- Added wakeup-worker coverage proving Redis inbox polling can hand a pending command to `SessionLoopManager` without using process-local route memory.

## Verification

- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_command_store_rejects_duplicate_request_id_without_advancing_seq apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_command_store_sequence_is_monotonic_per_session apps/server/tests/test_command_wakeup_worker.py::CommandStreamWakeupWorkerTests::test_wakeup_worker_hands_pending_command_to_session_loop_manager apps/server/tests/test_session_loop.py apps/server/tests/test_command_router.py -q`

## 2026-05-12 Server Runtime Rebuild Phase 2/7 Router Boundary

- Added `apps/server/src/services/command_router.py` as the wakeup boundary for durable command references. It accepts only already-accepted command refs, dedupes same session/seq wakeups, and retries `running_elsewhere` until the configured deadline.
- Wired WebSocket human decision wakeup and stream reconnect recovery through `CommandRouter` instead of direct route-owned runtime processing.
- Wired `PromptTimeoutWorker` to wake runtime only after `PromptService.record_timeout_fallback_decision()` returns an accepted command reference.
- Did not force external AI into `CommandInbox` in this pass. The current external AI path is synchronous inside `RuntimeService` transports and calls `DecisionGateway.resolve_ai_decision()` during runtime execution; without the Phase 3 `SessionLoop` prompt boundary, appending that result as a command would create two execution paths for one AI decision.
- Kept cross-process/restart recovery on the existing Redis command stream wakeup worker until `SessionLoop` and inbox drain are introduced.

## Verification

- `python3 -m compileall apps/server/src/services/command_router.py apps/server/src/services/prompt_timeout_worker.py apps/server/src/services/prompt_service.py apps/server/src/routes/stream.py apps/server/src/state.py`
- `./.venv/bin/python -m pytest apps/server/tests/test_command_router.py apps/server/tests/test_prompt_timeout_worker.py apps/server/tests/test_stream_api.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_command_inbox.py apps/server/tests/test_batch_collector.py apps/server/tests/test_runtime_rebuild_contract.py -q`

## 2026-05-12 Server Runtime Rebuild Phase 1/6 Hardening

- Added fail-closed production Redis command acceptance: default Redis clients must support Lua for durable command append and atomic prompt acceptance. Test fakes with explicit client factories keep fallback coverage.
- Added command terminal state transitions for prompt-lifecycle stale commands: superseded prompts mark commands `superseded`, and prompt timeout/orphan cleanup marks commands `expired`.
- Added `BatchCollector` with one Redis atomic primitive for response record, remaining-player calculation, batch completion idempotency, command append, and accepted command state.
- Added tests for missing Lua fail-closed behavior, stale superseded/expired command states, and single `batch_complete` emission under concurrent responses.

## Verification

- `python3 -m compileall apps/server/src/services/batch_collector.py apps/server/src/services/realtime_persistence.py apps/server/src/services/runtime_service.py apps/server/src/services/command_inbox.py apps/server/src/infra/redis_client.py`
- `./.venv/bin/python -m pytest apps/server/tests/test_batch_collector.py apps/server/tests/test_command_inbox.py apps/server/tests/test_runtime_rebuild_contract.py apps/server/tests/test_redis_realtime_services.py -q`

## 2026-05-12 Server Runtime Rebuild Phase 0/4/5 Start

- Removed `view_commit` from the human decision accept/reject path in `apps/server/src/routes/stream.py`.
- Removed pending prompt reconstruction from latest `view_commit`; missing pending prompt now stays stale and must be recovered through the authoritative prompt/checkpoint path.
- Removed heartbeat-driven latest `view_commit` lookup/send repair. Heartbeat remains liveness and diagnostics only.
- Added `apps/server/tests/test_runtime_rebuild_contract.py` and rewrote the old view-commit decision contract tests around the new boundary.
- Added `apps/server/src/services/command_inbox.py` as the accepted-command boundary and routed `PromptService` decision command appends through it.
- Added `apps/server/tests/test_command_inbox.py` to lock the rule that an accepted command reference is returned only after the durable append path has produced it.
- Added Redis command state tracking in `RedisCommandStore`: accepted commands now get a durable state row, and `RuntimeService` updates it to `processing`, `committed`, or `rejected` at the runtime boundary.
- Added `CommandState` and terminal state definitions in `apps/server/src/domain/command_state.py`; Redis command state writes now reject unknown state values instead of persisting arbitrary strings.
- Fixed the non-atomic prompt fallback so a failed command append does not delete the pending prompt or return an accepted decision ack.

## Verification

- `./.venv/bin/python -m pytest apps/server/tests/test_command_inbox.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_runtime_rebuild_contract.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_view_commit_decision_contract.py apps/server/tests/test_stream_api.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_view_commit_decision_contract.py apps/server/tests/test_stream_api.py -q`
- `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_command_store_lists_recent_commands_and_falls_back_after_gap apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_accepts_decision_with_single_redis_transaction apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_runtime_process_command_once_commits_state_and_command_offset -q`
- `python3 tools/plan_policy_gate.py && ./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`

## 2026-05-12 Server Runtime Rebuild Plan

- Reviewed the current server audit and Claude server redesign proposals.
- Rejected direct local queue command acceptance, pub/sub-only outbound delivery, non-atomic batch completion, weak deterministic prompt ids, and further expansion of `RuntimeService`.
- Created the active rebuild plan at `docs/current/architecture/[PLAN]_SERVER_RUNTIME_REBUILD_2026-05-12.md`.
- Updated the plan index so new server runtime work starts from the rebuild plan instead of reopening older umbrella migration documents.

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

## 2026-05-13 Pre-Implementation Completion Criteria Rule

- Added a mandatory pre-implementation contract to `docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`.
- The contract requires every implementation task to state goal, completion criteria, non-goals, protected boundaries, verification commands, and responsibility check before code edits.
- Added `P-09 Completion Criteria Discipline` so architecture work is checked for actual responsibility movement, not only test success.
- Added the same execution rule to root `AGENTS.md` so future sessions inherit it immediately.

## Verification

- Documentation-only change; no runtime tests required.
- `git diff --check`

## 2026-05-13 Command-Boundary Final Commit Lease Guard

- Added a `commit_guard` hook to `CommandBoundaryFinalizer`.
- Connected `RuntimeService._run_engine_command_boundary_loop_sync()` to the runtime lease owner check before authoritative command-boundary finalization.
- If another runtime worker owns the lease before the final write, the command-boundary path returns `status=stale` / `reason=runtime_lease_lost_before_commit`.
- In that blocked state, the staged boundary store may record internal commit attempts, but the authoritative Redis state commit, latest `view_commit` emit, and prompt materialization do not run.
- This is not the full SessionLoop ownership migration. `RuntimeService` still provides the transitional lease adapter until the command execution loop is moved.

## Verification

- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_boundary_finalizer.py apps/server/tests/test_runtime_service.py -k 'command_boundary_loop_blocks_final_commit_when_runtime_lease_is_lost or commit_guard_blocks_deferred_commit_side_effects' -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_command_boundary_finalizer.py -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'command_boundary_loop or runtime_lease_lost_before_commit' -q`
- `PYTHONPATH=engine ./.venv/bin/python -m pytest apps/server/tests -q`
- `./.venv/bin/python -m pytest engine/test_doc_integrity.py -q`
- `python3 tools/plan_policy_gate.py`
- `git diff --check`
