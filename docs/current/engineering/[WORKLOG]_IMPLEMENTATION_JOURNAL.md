# [WORKLOG] Implementation Journal

Status: ACTIVE  
Updated: 2026-05-04

## Rules

- Record every task summary regardless of size (small/large).
- For complex logic changes, write/update plan docs first, then implement.

## 2026-05-04 Canonical Effect Ownership And Prompt Surface Contract Pass

- What changed:
  - added backend canonical effect-owner payload fields (`effect_character_id`, `effect_card_no`, `effect_character_name`) for scheduled mark resolution, ability suppression visibility, and matchmaker adjacent purchase events
  - moved frontend event effect attribution into `domain/events/effectCharacter.ts` so canonical backend fields win before legacy compatibility inference
  - added shared backend/frontend prompt surface fixtures for `purchase_tile` and `trick_tile_target`
  - pinned the 1-5 round-combination regression pack and Redis continuation boundary in docs/tests
  - removed `docs/current/.DS_Store`
- Why:
  - effect attribution must not be reconstructed from localized display text or stale actor fields
  - backend prompt surfaces and Redis continuation checkpoints should define exactly where a resumed module continues, not frontend request ids or parent-turn replay
- Validation:
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest GPT/test_rule_fixes.py::RuleFixTests::test_scheduled_mark_resolves_before_target_turn_start GPT/test_rule_fixes.py::RuleFixTests::test_matchmaker_adjacent_purchase_event_carries_effect_owner_contract GPT/test_rule_fixes.py::TrickRuleAuditTests::test_eosa_suppressed_muroe_skill_is_visible_event apps/server/tests/test_view_state_prompt_selector.py tests/test_module_runtime_playtest_matrix_doc.py tests/test_redis_runtime_deployment_manifest.py -q`
  - `npm --prefix apps/web run test -- --run src/domain/events/effectCharacter.spec.ts src/domain/selectors/promptSelectors.spec.ts`
  - `npm --prefix apps/web run build`

## 2026-05-04 Frontend Effect Fallback Cleanup And Runtime Regression Pass

- What changed:
  - verified and pushed the runtime semantic guard catalog / Redis restart smoke commit
  - ran module-runtime e2e coverage for first prompt, fortune overlay, and matchmaker adjacent purchase behavior
  - ran regression coverage for runtime sequence modules, effect inventory, round modules, simultaneous modules, target judicator modules, semantic guard, prompt continuation, and Redis-backed simultaneous batch continuation
  - tightened frontend event effect attribution so it no longer scans localized detail text to infer 박수/만신/중매꾼 ownership
  - documented remaining frontend compatibility fallback branches and their removal conditions
- Why:
  - detail-text scanning can misattribute an effect when a target name appears in the rendered sentence
  - remaining fallback branches should stay explicit and bounded until backend prompt/event contracts cover every active runtime surface
- Validation:
  - `npm --prefix apps/web run e2e:module-runtime`
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest GPT/test_runtime_sequence_modules.py GPT/test_runtime_sequence_handlers.py GPT/test_runtime_effect_inventory.py GPT/test_runtime_round_modules.py GPT/test_runtime_simultaneous_modules.py GPT/test_runtime_target_judicator_modules.py apps/server/tests/test_runtime_semantic_guard.py apps/server/tests/test_prompt_module_continuation.py apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_simultaneous_batch_continuation_survives_service_reconstruction -q`
  - `npm --prefix apps/web test -- --run src/domain/selectors/promptSelectors.spec.ts src/hooks/useGameStream.spec.ts`
  - `npm --prefix apps/web run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/selectors/promptSelectors.spec.ts src/hooks/useGameStream.spec.ts`
  - `npm --prefix apps/web run build`
  - `git diff --check`

## 2026-05-04 Runtime Semantic Guard Catalog Derivation And Restart Smoke

- What changed:
  - changed backend runtime semantic guard module/action ownership tables to derive from the engine runtime module catalog instead of maintaining a parallel hardcoded backend list
  - added guard tests proving the backend imports the engine catalog without external `PYTHONPATH` and that semantic guard action mappings match engine `sequence_modules`
  - ran the production-like Redis runtime restart smoke against `deploy/redis-runtime/docker-compose.runtime.yml`
- Why:
  - backend stream validation should reject impossible module/frame/action combinations from the same source of truth the engine runner uses
  - Redis restart evidence should prove the current module-continuation path survives process restart without backend inference or stale local memory
- Validation:
  - `.venv/bin/python -c "import apps.server.src.domain.runtime_semantic_guard as g; print(len(g.MODULE_ALLOWED_FRAMES), len(g.ACTION_TYPE_REQUIRED_MODULES))"`
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest apps/server/tests/test_runtime_semantic_guard.py -q`
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest GPT/test_runtime_sequence_modules.py GPT/test_runtime_target_judicator_modules.py GPT/test_runtime_turn_handlers.py apps/server/tests/test_runtime_semantic_guard.py GPT/test_action_pipeline_contract.py tests/test_module_runtime_playtest_matrix_doc.py -q`
  - `.venv/bin/python -c "from apps.server.src.services.stream_service import StreamService; print(StreamService.__name__)"`
  - `MRN_REDIS_KEY_PREFIX='mrn:{runtime-compose-smoke}' python3 tools/scripts/redis_restart_smoke.py --compose-project project-mrn-runtime-smoke --compose-file deploy/redis-runtime/docker-compose.runtime.yml --topology-name local-runtime-compose --expected-redis-hash-tag runtime-compose-smoke`
  - restart smoke result: `ok=true`, topology `local-runtime-compose`,
    restart mode `compose`, session `sess_Sy5g28DI0GQWaK65VmxdEXDH`,
    prefix `mrn:{runtime-compose-smoke}`, status `waiting_input -> waiting_input`,
    replay events `11 -> 12`, worker health checks `4`
  - smoke cleanup check: no leftover Docker containers after script-managed `docker compose down`

## 2026-05-04 Platform Manifest Mapping And Native Effect Boundary Guard

- What changed:
  - added `deploy/redis-runtime/platform-managed.manifest.template.json` as the
    platform-managed deployment mapping for the Redis runtime process contract
  - added manifest contract tests proving the platform template covers the same
    server, prompt-timeout-worker, and command-wakeup-worker roles as
    `process-contract.json`
  - ran the restart smoke in `--skip-up` custom-command mode against the
    production-like local runtime topology to verify the platform-managed smoke
    path without relying on Compose-managed startup
  - strengthened native effect inventory validation so prompt effects must
    declare Redis resume contracts, runtime boundaries must be explicit, and
    native effects cannot name `LegacyActionAdapterModule` as their boundary
  - fixed the effect handler coverage checker to use the actual turn-handler
    registry for `TurnEndSnapshotModule` instead of importing a deleted
    compatibility constant
  - constrained the desktop draft/final-character prompt body so the four-card
    row cannot create a hidden vertical overflow in the main match viewport
  - changed theater payoff scene anchoring so a later rent-only fallback turn
    does not replace the earlier richer 운수/effect payoff scene while the rent
    event still remains visible in the board event feed
- Why:
  - the deployment contract should be copyable into a real platform manifest
    while remaining testable inside the repo
  - engine-native module migration should fail at inventory review time if a
    new character, trick, fortune, or simultaneous effect tries to re-enter via
    an implicit backend adapter
- Validation:
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest GPT/test_runtime_effect_inventory.py GPT/test_runtime_sequence_modules.py GPT/test_runtime_round_modules.py apps/server/tests/test_runtime_semantic_guard.py tests/test_redis_runtime_deployment_manifest.py tests/test_module_runtime_playtest_matrix_doc.py -q`
  - `npm --prefix apps/web test -- --run src/domain/selectors/promptSelectors.spec.ts src/hooks/useGameStream.spec.ts src/infra/ws/StreamClient.spec.ts src/features/theater/coreActionScene.spec.ts`
  - `npm --prefix apps/web run build`
  - `npm --prefix apps/web run e2e:human-runtime`
  - `python3 tools/plan_policy_gate.py`
  - `git diff --check`
  - `python3 -m json.tool deploy/redis-runtime/platform-managed.manifest.template.json >/dev/null`
  - `MRN_REDIS_KEY_PREFIX='mrn:{runtime-compose-smoke}' docker compose -p project-mrn-runtime-smoke -f deploy/redis-runtime/docker-compose.runtime.yml config --quiet`
  - `python3 tools/scripts/redis_restart_smoke.py --skip-up --compose-project project-mrn-runtime-platform-smoke --compose-file deploy/redis-runtime/docker-compose.runtime.yml --topology-name local-runtime-platform-managed --expected-redis-hash-tag runtime-platform-smoke --restart-command 'docker compose -p project-mrn-runtime-platform-smoke -f deploy/redis-runtime/docker-compose.runtime.yml restart server prompt-timeout-worker command-wakeup-worker' --worker-health-command 'docker compose -p project-mrn-runtime-platform-smoke -f deploy/redis-runtime/docker-compose.runtime.yml exec -T prompt-timeout-worker python -m apps.server.src.workers.prompt_timeout_worker_app --health' --worker-health-command 'docker compose -p project-mrn-runtime-platform-smoke -f deploy/redis-runtime/docker-compose.runtime.yml exec -T command-wakeup-worker python -m apps.server.src.workers.command_wakeup_worker_app --health'`
  - restart smoke result: `ok=true`, topology `local-runtime-platform-managed`,
    restart mode `custom-command`, session `sess_puHzrvjLOoEdawsov5ef0m-K`,
    prefix `mrn:{runtime-platform-smoke}`, status `waiting_input -> waiting_input`,
    replay events `11 -> 12`, worker health checks `4`

## 2026-05-04 Recommended 1-5 Follow-Up Execution

- What changed:
  - ran the production-like Redis runtime restart smoke against `deploy/redis-runtime/docker-compose.runtime.yml`
  - audited remaining legacy/compat runtime paths and confirmed `LegacyActionAdapterModule` execution, orphan `pending_turn_completion`, and uncatalogued action payloads are rejected by runner/semantic-guard contract tests
  - audited prompt-resume/effect boundaries and confirmed production `_request_decision()` sites are inventory-classified for Redis continuation
  - audited frontend prompt selectors, confirming backend `view_state` precedence, phase-progress prompt closure, continuation fields, and active runtime owner handling are covered by selector/e2e tests
  - refreshed the Redis deployment contract evidence and removed stale Redis-state-plan language that implied fortune/forced-move helpers still belonged to module-runner execution
- Why:
  - the remaining instability class should be handled as explicit module ownership and replay continuation, not by reintroducing backend inference or name-based guardrails
  - handoff docs must match the current structural state before the next migration slice or browser playtest begins
- Validation:
  - `MRN_REDIS_KEY_PREFIX='mrn:{runtime-compose-smoke}' python3 tools/scripts/redis_restart_smoke.py --compose-project project-mrn-runtime-smoke --compose-file deploy/redis-runtime/docker-compose.runtime.yml --topology-name local-runtime-compose --expected-redis-hash-tag runtime-compose-smoke`
  - restart smoke result: `ok=true`, topology `local-runtime-compose`, session `sess_Lg6Pa5oX8kLUxx_ZFsfXxArD`, prefix `mrn:{runtime-compose-smoke}`, status `waiting_input -> waiting_input`, replay events `11 -> 12`, worker health checks `4`

## 2026-05-04 Turn Completion Ownership Cutover

- What changed:
  - removed the legacy sequence payload handler path that promoted `pending_turn_completion` into a `SequenceFrame`
  - made `TurnEndSnapshotModule` turn-owned only in the engine catalog and backend semantic guard
  - changed `DiceRollModule` completion so legacy turn-completion envelopes are consumed into the active `TurnFrame`'s existing `TurnEndSnapshotModule.payload.turn_completion`
  - added `TurnEndSnapshotModule` turn-handler logic for turn-end snapshot emission, control-finisher bookkeeping, end checks, turn cursor advance, and parent `PlayerTurnModule` completion
  - made module-runner sessions reject orphan `pending_turn_completion` checkpoints before promotion/execution
  - updated the engine/backend/frontend source map, runtime control matrix, Redis state plan, and module notes to document the cutover
- Why:
  - turn end is a turn boundary, not nested follow-up work
  - backend/Redis retry must resume the exact active module owner instead of synthesizing a hidden turn-completion adapter
  - this structurally prevents the old shape that allowed turn-end/card-flip boundaries to appear as if they were sequence work
- Validation:
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest GPT/test_runtime_sequence_modules.py::test_turn_completion_is_owned_by_turn_end_snapshot_module_not_sequence_adapter GPT/test_runtime_sequence_modules.py::test_module_runner_rejects_orphan_pending_turn_completion_checkpoint GPT/test_runtime_sequence_modules.py::test_module_runner_has_no_legacy_turn_body_adapter_after_cutover GPT/test_runtime_sequence_handlers.py::test_sequence_handler_registry_covers_trick_modules_and_payload_boundaries -q`
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest GPT/test_runtime_sequence_modules.py GPT/test_runtime_sequence_handlers.py GPT/test_runtime_turn_handlers.py GPT/test_runtime_turn_modules.py -q`
  - `.venv/bin/python -m pytest GPT/test_runtime_module_contracts.py GPT/test_runtime_prompt_continuation.py GPT/test_runtime_round_modules.py GPT/test_runtime_sequence_modules.py GPT/test_runtime_simultaneous_modules.py GPT/test_rule_fixes.py -q`
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_runtime_semantic_guard.py apps/server/tests/test_view_state_runtime_projection.py -q`
  - `PYTHONPATH=.:GPT .venv/bin/python -m pytest tests/test_module_runtime_playtest_matrix_doc.py GPT/test_doc_integrity.py -q`
  - `npm --prefix apps/web test -- --run src/domain/selectors/promptSelectors.spec.ts src/hooks/useGameStream.spec.ts src/infra/ws/StreamClient.spec.ts`
  - `npm --prefix apps/web run e2e:parity`
  - `npm --prefix apps/web run build`
  - `python3 tools/plan_policy_gate.py`
  - `git diff --check`

## 2026-05-04 Supply Threshold Simultaneous Runtime Promotion

- What changed:
  - made `resolve_supply_threshold` invalid inside `ActionSequenceFrame` construction and documented it as a simultaneous-only action
  - verified pending supply-threshold work is promoted into `SimultaneousResolutionFrame -> ResupplyModule` before regular sequence actions
  - changed `ResupplyModule` initialization to honor `eligible_burden_deck_indices_by_player` and processed burden snapshots from the action payload instead of recomputing the chain from the current hand on resume
  - expanded backend reconstruction coverage so stored `runtime_active_prompt_batch` preserves eligibility snapshots across service recreation
  - added frontend action-possible matrix coverage for `burden_exchange` under `ResupplyModule`/`simultaneous`
  - extended the playtest matrix with the eligible-snapshot regression scenario
- Why:
  - 재보급 is a simultaneous response boundary, not a turn-local sequential adapter
  - replay/Redis continuation must resume the exact chain the engine already started; newly drawn burden cards must not enter an older threshold chain
  - frontend stale prompt gating should follow the same active runtime owner as engine/backend state
- Validation:
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_sequence_modules.py GPT/test_runtime_simultaneous_modules.py tests/test_module_runtime_playtest_matrix_doc.py apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_simultaneous_batch_continuation_survives_service_reconstruction`
  - `npm --prefix apps/web run test -- src/domain/selectors/promptSelectors.spec.ts --run`
  - `python3 tools/plan_policy_gate.py`
  - `git diff --check`

## 2026-05-04 Runtime Compose Manifest, Fortune Boundary, And Prompt Matrix

- What changed:
  - added `deploy/redis-runtime/docker-compose.runtime.yml` and `deploy/redis-runtime/.env.example` as a production-like local topology for the Redis-authoritative runtime roles
  - extended `tools/scripts/redis_restart_smoke.py` with repeatable `--compose-file` support so the same restart smoke can target the runtime manifest instead of only the root developer compose file
  - changed fortune action module routing from a wildcard `resolve_fortune_*` rule to an explicit `FORTUNE_ACTION_TYPE_TO_MODULE_TYPE` inventory; unknown fortune actions now remain legacy until catalogued and documented
  - expanded the round action control matrix and its regression test so explicit fortune actions are part of the engine/backend/frontend contract
  - added frontend prompt action-possible matrix coverage for draft, final character, trick, hidden hand, hand choice, active flip, and superseded request-id prompts
- Why:
  - production readiness should be verified against the same role topology and Redis hash-tag contract that operators deploy
  - wildcard fortune routing made new 운수 effects too easy to slip into native runtime without a documented module boundary
  - stale frontend prompts are the browser-facing symptom of backend/runtime continuation drift; the selector now has matrix coverage for each special prompt family
- Validation:
  - `PYTHONPATH=.:GPT uv run pytest -q tests/test_redis_restart_smoke_script.py tests/test_redis_runtime_deployment_manifest.py`
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_sequence_modules.py tests/test_module_runtime_playtest_matrix_doc.py tests/test_redis_restart_smoke_script.py tests/test_redis_runtime_deployment_manifest.py`
  - `npm --prefix apps/web run test -- src/domain/selectors/promptSelectors.spec.ts --run`
  - `MRN_REDIS_KEY_PREFIX='mrn:{runtime-compose-smoke}' docker compose -p project-mrn-runtime-smoke -f deploy/redis-runtime/docker-compose.runtime.yml config --quiet`
  - `MRN_REDIS_KEY_PREFIX='mrn:{runtime-compose-smoke}' python3 tools/scripts/redis_restart_smoke.py --compose-project project-mrn-runtime-smoke --compose-file deploy/redis-runtime/docker-compose.runtime.yml --topology-name local-runtime-compose --expected-redis-hash-tag runtime-compose-smoke`
  - `python3 tools/plan_policy_gate.py`
  - `git diff --check`
  - restart smoke result: `ok=true`, topology `local-runtime-compose`, session `sess_THboINwsY0oZMonItGJh7Apm`, prefix `mrn:{runtime-compose-smoke}`, status `waiting_input -> waiting_input`, replay events `11 -> 12`, worker health checks `4`

## 2026-05-04 Production-Like Restart Smoke And Runtime Boundary Matrix

- What changed:
  - committed the previous Redis restart recovery/readiness stabilization batch as `7f4b25b Harden Redis runtime recovery smoke`
  - extended `tools/scripts/redis_restart_smoke.py` so operators can run the same smoke against production-like topologies with `--skip-up`, `--topology-name`, `--restart-command`, `--worker-health-command`, and `--expected-redis-hash-tag`
  - added retrying worker readiness checks around restart so transient container/process startup timing does not mask the actual Redis recovery contract
  - added `deploy/redis-runtime/process-contract.json` and `docs/current/engineering/[CONTRACT]_REDIS_RUNTIME_DEPLOYMENT.md` as the server/worker/process deployment contract
  - expanded `docs/current/runtime/round-action-control-matrix.md` into a test-enforced inventory for all runtime modules, action adapter mappings, virtual effect modules, and declared character/trick/fortune/simultaneous effects
- Why:
  - local Compose restart coverage was useful but not enough; production-like deployment must prove the same shared Redis hash tag, restart ordering, and worker health gates
  - deployment manifests should be generated from an explicit role contract instead of implicit README prose
  - the modular runtime migration needs a hard guard that every new module/action/effect has an engine/backend/frontend boundary contract before it can silently enter gameplay
- Validation:
  - `PYTHONPATH=.:GPT uv run pytest -q tests/test_redis_restart_smoke_script.py`
  - `python3 tools/scripts/redis_restart_smoke.py --help`
  - `PYTHONPATH=.:GPT uv run pytest -q tests/test_module_runtime_playtest_matrix_doc.py`
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_module_contracts.py GPT/test_runtime_effect_inventory.py`
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_sequence_modules.py GPT/test_runtime_turn_handlers.py GPT/test_runtime_simultaneous_modules.py`
  - `PYTHONPATH=.:GPT uv run pytest -q tests/test_redis_restart_smoke_script.py tests/test_module_runtime_playtest_matrix_doc.py GPT/test_runtime_module_contracts.py GPT/test_runtime_effect_inventory.py GPT/test_runtime_sequence_modules.py GPT/test_runtime_turn_handlers.py GPT/test_runtime_simultaneous_modules.py`
  - `python3 tools/plan_policy_gate.py`
  - `git diff --check`
  - `python3 tools/scripts/redis_restart_smoke.py`
  - restart smoke result: `ok=true`, topology `local-compose`, restart mode `compose`, session `sess_X91aaZGHyemwkbaV_D0284Dw`, prefix `mrn:{restart-smoke-1777821787}`, status `waiting_input -> waiting_input`, replay events `11 -> 12`, worker health checks `4`

## 2026-05-03 Redis Command Commit / Restart Smoke / Payoff Scene Hardening

- What changed:
  - added `command_commit_envelope` metadata to command-triggered runtime transitions so checkpoint and runtime stream events record the accepted command seq plus state/checkpoint/event/offset commit participation
  - exposed Redis Cluster hash-tag parsing in `/health` via `cluster_hash_tag` and `cluster_hash_tag_valid`
  - made Docker Compose accept `MRN_REDIS_KEY_PREFIX` for server and worker roles instead of hard-coding `mrn:dev`
  - added `tools/scripts/redis_restart_smoke.py` to start Redis-backed backend roles, create a live human+AI session, restart backend/worker processes, and verify health/runtime/replay continuity
  - ran the actual local Redis restart smoke; it exposed a REST recovery gap where authenticated `/runtime-status?token=...` could remain `recovery_required` after process restart even though WebSocket recovery already restarted the runtime
  - fixed authenticated seat runtime-status recovery so REST polling also starts the recoverable runtime from Redis using the session runtime seed/policy
  - added process-local `--health` readiness modes for `prompt-timeout-worker` and `command-wakeup-worker`
  - fixed theater payoff grouping so the newest payoff turn owns the scene instead of an older 운수 effect stealing the final 결정/구매 payoff surface
- Why:
  - accepted decisions need auditable Redis continuation evidence at the same boundary that advances command offsets
  - Redis Cluster safety must be visible before production rollout, not discovered as a runtime cross-slot failure
  - live restart recovery must be available from both browser WebSocket reconnects and authenticated REST status/replay polling
  - production supervisors need a non-looping worker readiness command before routing sessions to the deployment
  - frontend payoff grouping should reflect the newest engine payoff, not an older effect in the same retained event window
- Validation:
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_redis_persistence.py::RedisPersistenceTests::test_health_check_reports_version_and_database apps/server/tests/test_redis_persistence.py::RedisPersistenceTests::test_cluster_hash_tag_prefix_is_preserved_inside_all_keys apps/server/tests/test_redis_persistence.py::RedisPersistenceTests::test_cluster_hash_tag_prefix_rejects_unbalanced_braces`
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_runtime_process_command_once_commits_state_and_command_offset`
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_command_wakeup_worker.py::CommandStreamWakeupWorkerTests::test_cli_parser_supports_health_mode apps/server/tests/test_command_wakeup_worker.py::CommandStreamWakeupWorkerTests::test_health_mode_reports_redis_readiness apps/server/tests/test_prompt_timeout_worker.py::PromptTimeoutWorkerLoopTests::test_cli_parser_supports_health_mode apps/server/tests/test_prompt_timeout_worker.py::PromptTimeoutWorkerLoopTests::test_health_mode_reports_redis_readiness apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_runtime_process_command_once_commits_state_and_command_offset`
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_sessions_api.py::SessionsApiTests::test_authenticated_runtime_status_starts_recovery_runtime apps/server/tests/test_stream_api.py::StreamApiTests::test_seat_stream_connection_recovers_runtime_when_in_progress`
  - `npm --prefix apps/web test -- coreActionScene.spec.ts`
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_redis_persistence.py apps/server/tests/test_redis_realtime_services.py`
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_action_pipeline_contract.py apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_valid_module_continuation_passed_to_engine_transition apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_stale_module_continuation_rejected_without_engine_advance apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_module_resume_rejects_module_type_mismatch_without_engine_advance apps/server/tests/test_prompt_module_continuation.py`
  - `npm --prefix apps/web run build`
  - `python3 tools/plan_policy_gate.py`
  - `PYTHONPATH=.:GPT python3 -m apps.server.src.workers.prompt_timeout_worker_app --help`
  - `PYTHONPATH=.:GPT python3 -m apps.server.src.workers.command_wakeup_worker_app --help`
  - `python3 tools/scripts/redis_restart_smoke.py`
  - restart smoke result: `ok=true`, session `sess_nLQ64iczvkr5tOSbqRA6iVci`, prefix `mrn:{restart-smoke-1777821085}`, status `waiting_input -> waiting_input`, replay events `11 -> 12`

## 2026-05-03 Simultaneous Resupply And Redis Continuation Contract Hardening

- What changed:
  - updated continuation classification so `choose_burden_exchange_on_supply` is explicitly a `simultaneous_prompt_batch_boundary`, not an atomic single-prompt effect boundary
  - added backend reconstruction coverage proving a stored `runtime_active_prompt_batch` survives service recreation and is passed back to the engine with its original `batch_id`, frame, module cursor, existing responses, and missing participant list
  - added documentation regression coverage to prevent stale “rent payment still needs action split” language from reappearing after `resolve_rent_payment` / `RentPaymentModule`
  - documented the production Redis Cluster hash-tag contract in `apps/server/README.md` and the beginner Redis handoff
  - added Redis key coverage showing `MRN_REDIS_KEY_PREFIX=mrn:{project-mrn-prod}` is preserved in generated keys
- Why:
  - simultaneous resupply must resume from the engine-owned batch continuation, not backend inference or sequential prompt reconstruction
  - stale docs were making completed rent actionization look like remaining migration work
  - Redis Cluster deployments need a single shared hash slot for the current Lua/transaction envelope across server and worker roles
- Validation:
  - `PYTHONPATH=.:GPT uv run pytest -q tests/test_module_runtime_playtest_matrix_doc.py GPT/test_action_pipeline_contract.py apps/server/tests/test_redis_persistence.py::RedisPersistenceTests::test_cluster_hash_tag_prefix_is_preserved_inside_all_keys`
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_simultaneous_modules.py apps/server/tests/test_prompt_module_continuation.py apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_active_simultaneous_batch_publishes_module_prompts_for_missing_players apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_simultaneous_batch_continuation_survives_service_reconstruction`

## 2026-05-03 Beginner Developer Handoff

- What changed:
  - added `docs/current/HANDOFF_FOR_BEGINNER_DEVELOPERS.md` as a beginner-friendly Korean handoff covering game rules, engine, backend, Redis, WebSocket, frontend, API flow, feature mapping, lobby, and game logs
  - linked the handoff from `docs/README.md` so it appears in the primary current-doc reading path
  - split the handoff into `docs/current/handoff-beginner/` so numbered items such as `1-1`, `2-2`, and `3-3-3` are standalone documents
  - expanded each numbered document with detailed handoff sections for related files, runtime/API flow, implementation cautions, validation commands, and beginner debugging questions
  - corrected engine references so the docs teach the current module-first runtime structure instead of implying every engine task starts from `GPT/engine.py` and the whole runtime module directory
  - narrowed engine-related links to specific module files such as `contracts.py`, `runner.py`, `round_modules.py`, `turn_modules.py`, `sequence_modules.py`, `simultaneous.py`, and `prompts.py`
  - removed repeated generic "read the flow" guidance from all beginner handoff documents and replaced it with topic-specific `actual processing flow and expected values` sections
  - added `docs/current/handoff-beginner/5-6.md` as a screen-action trigger map that ties lobby buttons, WebSocket decisions, backend routes/services, runtime modules, and expected UI/log values together
  - expanded rule/API/Redis/WebSocket/frontend caution subdocuments with concrete trigger, processing path, and expected value checks instead of abstract debugging advice
- Why:
  - new human developers need one guided document that explains how the game moves from lobby to engine runtime to WebSocket events and frontend rendering
  - the intended handoff format is one document per numbered section, not a single long document with nested headings
  - the runtime is modularized, but `engine.py` still exists as a semantic helper/bridge for behavior that has not been fully migrated into native modules
  - screen actions, REST calls, WebSocket decisions, service boundaries, runtime modules, and frontend selectors are too far apart for a beginner to connect from generic reading instructions alone
- Validation:
  - documentation-only change; verified by cross-reading current game rules, runtime contracts, API spec, server routes/services, Redis persistence, and frontend stream/API entry points
  - repeated generic flow-guidance phrase search across `docs/current` and `docs/README.md` returned no body-text matches
  - `python3 tools/plan_policy_gate.py`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py -q`

## 2026-05-03 Documentation Current/Archive Reorganization

- What changed:
  - moved active docs into `docs/current/` by area: API, backend, engineering, frontend, planning, rules, and runtime
  - moved expired, superseded, duplicate, or already-implemented docs into `docs/archive/`
  - added `docs/README.md` and `docs/archive/README.md` as the new documentation map
  - refreshed `docs/current/planning/PLAN_STATUS_INDEX.md` and `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md` so they point only to current sources of truth
  - updated repo README, package READMEs, server test notes, and `tools/plan_policy_gate.py` for the new paths
- Why:
  - current execution docs were mixed with completed plans and old handoff notes, causing stale frontend/runtime plans to look active
  - the 2026-05-02 modular runtime migration is implemented, so those planning docs now belong in archive while `docs/current/runtime/` owns the contract
- Validation:
  - `rg` check for old live paths returned no matches outside `docs/archive/`
  - `python3 tools/plan_policy_gate.py`

## 2026-05-02 Initial Trick Hand Draft Visibility Fix

- What changed:
  - updated web hand-tray fallback matching so engine `initial_public_tricks.players[].player` is treated as the player id
  - kept initial trick-hand setup events out of the generic live board snapshot path when they do not contain full `player_id` player state
  - added trick-hand snapshots to draft and final-character prompt contexts in the server decision gateway and local `HumanHttpPolicy`
  - extended browser parity coverage so the draft prompt must show both active character faces and the bottom 잔꾀 hand tray before any card flip events arrive
- Why:
  - the 잔꾀 hand is initial setup/player state, not a UI surface that only exists while a 잔꾀 prompt is active
  - the frontend could not read the engine's initial setup payload shape, so a draft prompt without `full_hand` made the bottom hand tray disappear
  - the same initial setup payload carried a lightweight `players` list that could be mistaken for a full board snapshot and briefly blank active character slots
- Validation:
  - `npm --prefix apps/web run test -- src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts --run`
  - `.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_draft_context_exposes_phase_and_offered_candidates apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_final_character_context_keeps_trick_hand_for_bottom_tray apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_local_human_prompt_merges_gateway_public_context_for_draft GPT/test_human_policy_prompt_payloads.py::test_draft_prompt_contains_character_ability_payload -q`
  - `npm --prefix apps/web run e2e -- --project=chromium --grep "draft prompt keeps active strip hydrated before any flip events arrive"`

## 2026-05-03 Trick Sequence Frame / Redis Continuation Fix

- What changed:
  - moved the active turn's trick window into an explicit child `TrickSequenceFrame`; `TrickWindowModule` now opens/suspends that child sequence instead of directly executing the legacy trick prompt path
  - made `TrickChoiceModule` the prompt owner for trick selection and set module cursors before any prompt-capable legacy bridge call
  - attached active module continuation metadata from `_LocalHumanDecisionClient` when a prompt is created inside the module runner, including `resume_token`, `frame_id`, `module_id`, `module_type`, and `module_cursor`
  - added Redis persistence coverage proving a transition commits current state, checkpoint, latest sequence, command offset, runtime stream event, and the module prompt continuation in one pipeline batch
- Why:
  - live play could produce `산적 지목 -> 잔꾀 -> 다시 지목 -> 잔꾀` because a trick prompt was resumed from the parent turn context instead of a nested trick sequence cursor
  - a consumed/accepted trick decision must return to the same child sequence, then back to the parent `TurnFrame`; it must not re-enter `PendingMarkResolutionModule`, `CharacterStartModule`, or `TargetJudicatorModule`
  - Redis should preserve the exact suspended frame/module/cursor snapshot; backend recovery may validate and deliver that continuation, but it must not reconstruct gameplay flow with card-name branches
- Validation:
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_sequence_modules.py::test_trick_window_spawns_child_sequence_instead_of_replaying_turn_modules`
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_prompt_module_continuation.py::test_local_human_prompt_created_inside_module_attaches_active_continuation`
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_game_state_store_commits_module_prompt_resume_snapshot_atomically`

## 2026-05-03 Nested Trick/Fortune Module Boundary Hardening

- What changed:
  - changed `TrickChoiceModule` so completing a trick choice no longer skips the rest of the trick sequence
  - added a `TrickResolveModule` handoff payload for the selected trick result and deferred follow-up flag
  - added same-sequence follow-up scheduling so a trick effect that asks for another trick choice inserts a new `TrickChoiceModule` inside the active `TrickSequenceFrame` instead of re-entering turn-start modules
  - replaced the temporary `roll_and_arrive` placeholder with explicit `FortuneResolveModule -> MapMoveModule -> ArrivalTileModule` sequence boundaries
  - attached applicable modifier ids to turn/sequence modules immediately before execution so character/trick/fortune effects can flow through module contracts instead of card-name special cases
  - strengthened backend semantic validation so `trick_used` is only valid from `TrickResolveModule` sequence context
- Why:
  - the earlier child-frame patch stopped prompt ownership from living on the parent turn, but `TrickChoiceModule` still collapsed the sequence after selection
  - effects such as 잔꾀 follow-ups and 운수 extra movement need to remain in their own nested module frames; if they bounce back to `CharacterStartModule` or `TargetJudicatorModule`, accepted prompts can appear to loop
  - modifier propagation must be structural: modules should receive the modifiers targeted at them, and individual character abilities should not be reimplemented as scattered if/else guards
- Validation:
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_sequence_modules.py`
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_module_contracts.py GPT/test_runtime_sequence_modules.py GPT/test_runtime_round_modules.py GPT/test_runtime_prompt_continuation.py`
  - `PYTHONPATH=.:GPT uv run pytest -q apps/server/tests/test_runtime_semantic_guard.py`
  - `PYTHONPATH=.:GPT uv run pytest -q GPT/test_runtime_sequence_modules.py GPT/test_runtime_module_contracts.py GPT/test_runtime_round_modules.py GPT/test_runtime_prompt_continuation.py apps/server/tests/test_runtime_semantic_guard.py apps/server/tests/test_prompt_module_continuation.py apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_game_state_store_commits_module_prompt_resume_snapshot_atomically`

## 2026-05-02 Turn-Start Mark / Trick Replay Loop Fix

- What changed:
  - updated `RuntimeService` prompt-sequence seeding so a pending `trick_to_use` prompt rewinds through a prior turn-start `mark_target` prompt when the current character requires one
  - updated pending `movement` replay to rewind through `mark_target -> trick_to_use -> movement` rather than only the normal `trick_to_use -> movement` pair
  - kept the hidden-trick synced movement shortcut unchanged because that path intentionally replays only the movement prompt
  - documented the new replay-boundary lesson in the Redis runtime playtest lessons
- Why:
  - live play produced `지목 -> 느슨함 혐오자 -> 지목 -> 느슨함 혐오자 -> 지목 -> 잔꾀 사용안함` loops
  - the engine was not re-running a new rule phase; replay was starting after the already-issued mark prompt, so stored trick decisions no longer matched the prompt request-id chain
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_turn_start_mark_prompt_replay_seed_matches_character_rule_cases apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_turn_start_mark_replay_rewinds_before_pending_trick_and_movement_prompts -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q`

## 2026-05-01 REDIS-UI-10 Effect/Spectator Closure

- What changed:
  - restored non-prompt match spectator panel rendering and kept the legacy `core-action-*` verification contract available
  - added reveal markers for spotlighted latest public events
  - prioritized spectator/core-action cause/effect sequences so worker fallback, marker/flip, and fortune resolution are not displaced by weather, character, `turn_start`, or later rent
  - capped character/draft prompt width and removed desktop overflow; restored projected economy text shadow
  - updated REDIS-UI-10 report and first-read gate from open to resolved
- Why:
  - the runtime was progressing, but the UI had drifted away from stable effect/spectator selectors and machine-verifiable cause attribution
  - a screen that looks playable is not enough when browser QA cannot prove the user can read weather, worker, rent/payoff, fortune, trick, and passive effect causality
- Validation:
  - `npm --prefix apps/web run build`
  - `npm --prefix apps/web run e2e:human-runtime` (`18 passed`)
  - `cd apps/web && npm exec -- playwright test e2e/parity.spec.ts --project=chromium --workers=1 --grep "trick use advances to tile target without resurrecting the stale trick picker|extreme separation trick closes picker while queued movement resolves"` (`2 passed`)

## 2026-05-01 REDIS-UI-10 Documentation Sync

- What changed:
  - promoted the updated `REDIS-UI-10` report finding into the first-read stabilization guide and frontend README
  - made `npm run e2e:human-runtime` the explicit effect-display closure gate in the playtest checklist and lessons doc
  - documented that the latest Redis/browser retest is a UI contract/readability failure, not a Redis boot/storage failure
- Why:
  - the pre-fix live `1 human + 3 AI` session reached round 2 without console/page/network failures, but the human-runtime suite failed on spectator/effect selectors and desktop prompt overflow
  - future work should not close the issue based only on visual playability or smaller selector/parity tests
- Validation:
  - documentation-only change; verified by reading the updated report and syncing the affected guide/checklist/lesson entry points

## 2026-05-01 Trick Prompt Lifecycle Closure

- What changed:
  - closed stale `trick_to_use` prompts when a same-player `trick_used` or `trick_window_closed` event appears after the prompt
  - applied the same lifecycle rule in backend `view_state.prompt` projection and the frontend fallback prompt selector
  - added regression coverage for the `긴장감 조성` path where using a trick queues a follow-up `trick_tile_target` prompt
- Why:
  - the card effect was not rolling the engine back to character selection; the old prompt could remain selectable while the runtime moved from `trick_used` to the queued tile-target decision
  - relying only on `decision_ack` / `decision_resolved` is too fragile during command wakeup, replay, and reconnect ordering
- Validation:
  - `npm --prefix apps/web run e2e -- parity.spec.ts -g "trick use advances"`
  - `npm --prefix apps/web run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `.venv/bin/python -m pytest apps/server/tests/test_view_state_prompt_selector.py -q`

## 2026-05-01 Queued Trick Turn Continuation Closure

- What changed:
  - when a regular trick queues runtime actions, append `continue_after_trick_phase` behind those actions so the same `turn_index` resumes after the trick phase instead of starting the turn again
  - covered `극심한 분리불안` with a backend regression where another usable trick remains in hand and must not be prompted after the queued movement/arrival resolves
  - added a browser click regression for `극심한 분리불안` confirming the trick picker closes while queued movement and landing events arrive
- Why:
  - the priority action queue executed `apply_move -> resolve_arrival` correctly, but no turn continuation token remained after the queue drained
  - once pending actions became empty, `run_next_transition()` re-entered the same player's turn start, which could reopen `trick_to_use` for any remaining trick card
- Validation:
  - `.venv/bin/python -m pytest GPT/test_rule_fixes.py -k 'queued_trick_action_resumes_after_effect_without_second_trick_prompt or hidden_trick_prompt_resumes_after_applied_trick' -q`
  - `.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'extreme_separation' -q`
  - `npm --prefix apps/web run e2e -- parity.spec.ts -g "extreme separation"`
  - `npm --prefix apps/web run e2e -- parity.spec.ts -g "trick use advances"`

## 2026-04-30 Visibility Projection Foundation

- Scope: start the Redis/frontend visibility split so private data is projected by backend viewer context instead of hidden by frontend UI.
- Done:
  - documented the Redis visibility/projection plan
  - added `ViewerContext` and visibility selector checks
  - moved stream message filtering behind `project_stream_message_for_viewer`
  - kept the existing route-level `_filter_stream_message` as a compatibility wrapper
  - added tests for player-only prompts, private decision events, draft redaction, and embedded `view_state` hand/prompt redaction
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_visibility_projection.py apps/server/tests/test_stream_api.py -k 'visibility or filter_stream_message or private_draft'`
  - `./.venv/bin/python -m pytest apps/server/tests/test_stream_service.py apps/server/tests/test_view_state_hand_selector.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests -q`
- Follow-up:
  - make `project_view_state` accept viewer context and rebuild view state after stream filtering
  - add Redis keys for public/player/spectator/admin view-state caches

## 2026-04-30 Public-Safe Stream View State

- Scope: prevent canonical stream payloads from carrying view-state projections built from private prompt/hand messages.
- Done:
  - `StreamService.publish()` now builds attached `view_state` from spectator-safe projected records
  - private prompt payloads are still delivered to their target player as raw prompt messages, but embedded `view_state` no longer contains `prompt` or `hand_tray` from private history
  - added a stream-service regression test for public-safe attached view state
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_stream_service.py apps/server/tests/test_visibility_projection.py apps/server/tests/test_stream_api.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -q`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py -q`
- Follow-up:
  - add player-specific view-state reconstruction at websocket delivery time so target clients can still receive backend-projected prompt surfaces without exposing them in canonical stream storage

## 2026-04-30 Viewer-Specific Stream View State

- Scope: continue visibility projection by rebuilding frontend `view_state` for the authenticated websocket viewer at delivery time.
- Done:
  - extended `project_view_state(messages, viewer=...)`
  - added `StreamService.project_message_for_viewer()`
  - websocket live send and resume replay now use viewer-specific projection instead of the compatibility route wrapper
  - target-player prompt delivery can include backend-projected `prompt` and `hand_tray` view-state surfaces without storing them in public/canonical stream payloads
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_stream_service.py apps/server/tests/test_visibility_projection.py apps/server/tests/test_stream_api.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_view_state_player_selector.py apps/server/tests/test_view_state_scene_selector.py apps/server/tests/test_view_state_prompt_selector.py apps/server/tests/test_stream_service.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests -q`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py -q`
- Follow-up:
  - add Redis `view_state:public/player/spectator/admin` cache keys and serializers
  - convert the route compatibility `_filter_stream_message()` tests to visibility service tests once downstream callers are migrated

## 2026-04-30 Redis Projection Cache Keys

- Scope: add Redis storage interfaces for viewer-specific projected view-state caches.
- Done:
  - added `save_projected_view_state()` / `load_projected_view_state()`
  - added `save_projection_checkpoint()` / `load_projection_checkpoint()`
  - kept legacy `save_view_state()` / `load_view_state()` as the public projection alias for compatibility
  - `commit_transition()` now writes the legacy view-state key and `view_state:public`
  - session cleanup removes public, spectator, admin, and checkpoint-listed player projection caches
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_stream_service.py apps/server/tests/test_visibility_projection.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests -q`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py -q`
- Follow-up:
  - wire websocket projection writes into these cache keys once projection freshness/versioning is finalized
  - include projection checkpoint fields such as `generated_at_ms` and `projection_schema_version` in runtime commits

## 2026-04-30 Stream Projection Cache Writes

- Scope: wire viewer-safe stream projections into Redis projection caches.
- Done:
  - `StreamService.publish()` caches the spectator-safe projection generated for canonical stream payloads
  - `StreamService.project_message_for_viewer()` caches the player/spectator/admin projection generated for websocket delivery
  - projection checkpoints now track `latest_seq`, `generated_at_ms`, `projection_schema_version`, and the set of projected viewer labels
  - added tests for spectator cache writes and target-player prompt/hand projection cache writes
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_stream_service.py apps/server/tests/test_visibility_projection.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -q`
- Failed validation / lesson:
  - initial spectator-cache test expected `board` from a snapshot without `board.tiles`; board projection intentionally requires tile data, so projection cache tests must use selector-valid fixtures instead of partial snapshots.
- Follow-up:
  - let reconnect/API paths read these projected cache keys before rebuilding from stream history
  - decide whether `view_state:public` and `view_state:spectator` should remain aliases or diverge once true spectator-only surfaces exist

## 2026-04-30 Projection Cache Read Path

- Scope: use Redis/viewer projection caches as the first source for latest frontend view-state reads.
- Done:
  - added `StreamService.latest_view_state_for_viewer()`
  - added per-viewer projection freshness tracking through `projected_viewer_seqs`
  - stale viewer caches are rebuilt from stream history and written back to projection cache
  - `/api/v1/sessions/{session_id}/replay` now returns a top-level spectator-safe latest `view_state` in addition to replay events
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_stream_service.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py -k replay -q`
- Follow-up:
  - add authenticated replay/export variants for player-specific latest `view_state`
  - migrate recovery/archive readers to explicitly prefer projected `view_state:public` once backward compatibility with legacy `view_state` is no longer needed

## 2026-04-30 Authenticated Replay Projection

- Scope: make replay/export respect the same backend visibility boundary as websocket delivery.
- Done:
  - `/api/v1/sessions/{session_id}/replay` accepts an optional session token
  - spectator replay now projects every event through spectator visibility before returning it
  - authenticated seat replay projects events and latest `view_state` for that player
  - invalid replay tokens return `INVALID_SESSION_TOKEN`
  - added regression coverage proving private prompt/hand data is hidden from spectators and visible to the target seat
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_sessions_api.py -k replay -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_stream_service.py apps/server/tests/test_visibility_projection.py -q`
- Follow-up:
  - expose admin replay only behind an explicit admin auth context instead of overloading seat/session tokens
  - audit archive/recovery outputs so they do not accidentally become browser-facing canonical state exports

## 2026-04-30 Recovery And Archive Projection Boundary

- Scope: prevent recovery/status outputs that can be returned to browsers from exposing canonical Redis game state.
- Done:
  - added `RuntimeService.public_runtime_status()` for browser/API status output
  - `/runtime-status` now strips canonical `current_state` from `recovery_checkpoint`
  - recovery checkpoint view-state loading prefers Redis `view_state:public` and falls back to legacy `view_state`
  - local JSON archives keep canonical `final_state` as backend-local export data, but `final_view_state` now explicitly prefers public projected view-state
  - added regression tests for public runtime status redaction and archive public projection preference
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k public_runtime_status -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_archive_service.py -q`
- Follow-up:
  - split canonical archive and redacted replay-export schemas if archive files ever become downloadable from browser-facing routes
  - add admin-only auth before exposing canonical recovery state through any API endpoint

## 2026-04-30 Canonical Archive And Redacted Replay Schemas

- Scope: make backend-local canonical archives and browser-facing replay exports impossible to confuse at the payload level.
- Done:
  - canonical JSON archives now declare `schema_name: mrn.canonical_archive`, `visibility: backend_canonical`, and `browser_safe: false`
  - `/replay` responses now declare `schema_name: mrn.redacted_replay_export`, viewer `visibility`, `browser_safe: true`, and the projected viewer identity
  - documented both schemas and the rule that browser-facing replay must never include canonical `final_state`, analysis, raw commands, or private data
  - added regression checks for archive schema flags and spectator/player replay schema flags
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_archive_service.py apps/server/tests/test_sessions_api.py -k 'archive or replay' -q`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py -q`
- Follow-up:
  - keep expanding redacted replay contract tests as new browser-facing fields are introduced

## 2026-04-30 Admin Canonical Recovery Gate

- Scope: introduce an explicit admin-only path for canonical recovery data without overloading player session tokens.
- Done:
  - added `MRN_ADMIN_TOKEN` runtime setting
  - added `/api/v1/admin/sessions/{session_id}/recovery`
  - admin auth accepts `X-Admin-Token` or `Authorization: Bearer <token>`
  - admin recovery payload declares `schema_name: mrn.admin_recovery`, `visibility: admin`, and `browser_safe: false`
  - empty admin token disables admin APIs with `ADMIN_AUTH_DISABLED`
  - documented admin canonical access rules
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_admin_api.py apps/server/tests/test_runtime_settings.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'public_runtime_status' -q`
- Follow-up:
  - add admin-only canonical archive read/download endpoint after deciding retention and path traversal hardening rules

## 2026-04-30 Admin Canonical Archive Read

- Scope: add admin-only JSON access to backend-local canonical archive files.
- Done:
  - added `/api/v1/admin/sessions/{session_id}/archive`
  - archive reads require the same `MRN_ADMIN_TOKEN` gate as admin recovery
  - endpoint checks the session id through `SessionService` before reading an archive file
  - endpoint resolves the file through `LocalJsonArchiveService.archive_path_for(session_id)` and never accepts raw path parameters
  - endpoint returns canonical archive JSON only when the file exists and parses as a JSON object
  - documented admin-only archive read rules
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_admin_api.py -q`
- Follow-up:
  - add operator pagination/listing for archives only if retention grows beyond direct session-id lookup

## 2026-04-30 Admin Auth Dependency Refactor

- Scope: keep admin endpoint auth/error behavior reusable as more admin routes are added.
- Done:
  - extracted admin token parsing, configured-token lookup, constant-time comparison, and admin error payloads into `apps/server/src/core/admin_auth.py`
  - updated admin recovery/archive routes to use the shared `require_admin` dependency
  - added token extraction contract coverage for `X-Admin-Token` and `Authorization: Bearer`
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_admin_api.py -q`
  - `./.venv/bin/python -m compileall -q apps/server/src/core/admin_auth.py apps/server/src/routes/admin.py`
- Failed validation / lesson:
  - `python -m compileall ...` failed because this environment does not expose a bare `python` command; use the project venv Python for local checks.
- Follow-up:
  - keep admin-only auth in this shared dependency when adding future operator endpoints

## 2026-04-30 Redis UI Playtest Findings

- Scope: validate the Redis-backed gameplay migration through the actual browser screen, not only API or fast-check rule tests.
- Evidence:
  - added `docs/current/engineering/[REPORT]_REDIS_UI_PLAYTEST_FINDINGS_2026-04-30.md`
  - local health confirmed Redis-backed `sessions`, `rooms`, and `streams`
  - browser lobby and match screens rendered successfully with no console warnings/errors in the captured run
  - P1 draft decision was accepted through the UI
- Findings:
  - P1 `Do not use a trick` was accepted but looped back into repeated `trick_to_use` prompts instead of advancing to movement
  - match-screen runtime-status polling omitted the session token and repeatedly hit `SPECTATOR_NOT_ALLOWED`
  - the background command wakeup worker did not visibly consume accepted UI decisions until a manual one-shot wakeup was run
- Validation:
  - `npm --prefix apps/web test -- src/domain/rules/engineCore.rules.spec.ts src/features/board/boardProjection.rules.spec.ts src/domain/characters/prioritySlots.rules.spec.ts src/test/harness/gameRuleHarness.spec.ts`
- Result:
  - fast-check rule specs passed, but the Redis UI gameplay path is not release-ready until the repeated trick prompt loop and authenticated runtime-status polling are fixed.

## 2026-04-30 Redis Pending Prompt Replay Fix

- Scope: root-cause and fix REDIS-UI-01 and REDIS-UI-02 from the Redis UI playtest report.
- Root cause:
  - runtime transition replay hydrated a checkpoint from before the pending human prompt, then seeded prompt sequence to the already-emitted instance id
  - the replay therefore generated a new stable request id (`trick_to_use:3`) instead of the accepted pending id (`trick_to_use:2`)
  - the accepted `Do not use a trick` decision could not be replayed, so the engine repeated the same turn-start/trick prompt path
  - runtime-status polling also omitted the active session token because the web HTTP helper did not accept one and the match polling effect did not depend on `token`
- Done:
  - `RuntimeService` now seeds prompt sequence from `pending_prompt_instance_id - 1` when replaying a checkpoint with a pending prompt
  - added a regression test proving accepted stable prompt ids are replayed once and the next prompt advances to the next instance id
  - `getRuntimeStatus(sessionId, token)` now attaches authenticated viewer tokens to runtime-status reads
  - updated the Redis UI playtest report with the fix note and lesson
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'pending_prompt_replay_reuses_stable_request_id_then_advances_sequence or prompt_sequence_can_resume_from_checkpoint_value or human_bridge_can_raise_prompt_required_without_blocking' -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -q`
  - `npm --prefix apps/web run build`
- Lesson:
  - Redis replay prompt ids are continuation state. Stable prompt ids must be regenerated deterministically until the accepted decision is consumed.
  - viewer-scoped browser polling helpers should take credentials explicitly at the API helper boundary, even for redacted status payloads.
- Follow-up:
  - rerun the full browser Redis playtest to confirm the UI reaches movement and landing resolution
  - address REDIS-UI-03 worker cadence separately

## 2026-04-30 Redis Movement Replay And Worker Wakeup Fix

- Scope: root-cause and fix updated REDIS-UI-04 and REDIS-UI-05 from the Redis UI playtest report.
- Root cause:
  - movement replay was seeded from the pending prompt id instead of the start of the same-turn deterministic prompt prefix; replay therefore opened `trick_to_use:2` before consuming accepted `movement:2`
  - accepted prompt decisions were popped on first replay, so repeated runtime wakeups could no longer read prior accepted decisions needed to reconstruct the turn
  - the command wakeup worker scanned a startup-time `SessionService` cache and missed Redis sessions created after worker startup
  - standalone workers inherited the server restart recovery default unless explicitly configured, even though worker roles should not abort in-progress sessions
- Done:
  - movement pending prompts now seed replay before the earlier same-turn trick prompt
  - `PromptService` keeps accepted decisions readable until resolved prompt TTL cleanup, including Redis-backed `get_decision()`
  - `SessionService.refresh_from_store()` lets workers reload sessions from Redis before scans
  - command wakeup worker refreshes session state before active-session discovery and command processing
  - worker entrypoints and Compose worker services default `MRN_RESTART_RECOVERY_POLICY=keep`
  - updated the Redis UI playtest report and server process contract
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_pending_prompt_replay_reuses_stable_request_id_then_advances_sequence apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_pending_movement_replay_replays_prior_trick_prompt_before_movement -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_prompt_service.py apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_uses_redis_store_for_decision_flow apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_accepts_decision_with_single_redis_transaction -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_command_wakeup_worker.py -q`
- Lesson:
  - deterministic prompt replay must preserve the whole replay prefix, not just the pending prompt's own id
  - accepted human decisions are replay log entries and should be idempotently readable until their retention window closes
  - long-lived Redis workers need an explicit refresh boundary before active-session scans

## 2026-04-30 Redis Command Transition Drain And Live Play Verification

- Scope: actually play the Redis-backed browser flow and fix the remaining live runtime blocker found during that playthrough.
- Root cause:
  - command-driven wakeup consumed the accepted movement command and ran exactly one engine transition
  - that transition emitted `dice_roll` and committed a checkpoint with queued pending actions still present
  - because the command offset had already advanced and no new human command existed, the runtime became `idle` before `player_move`, landing resolution, or purchase prompt setup
- Done:
  - `RuntimeService.process_command_once()` now runs the engine transition loop for command wakeups
  - only the first loop iteration records command consumer/sequence metadata; later deterministic queued transitions run without re-recording the same command offset
  - added regression coverage proving command wakeup continues after the command transition until the next prompt boundary
  - updated the Redis UI playtest report, release gate notes, and server process contract
- Live verification:
  - played from the browser against Redis prefix `mrn:ui-live:1777548299`
  - session `sess_i_4YOXJeO4L-sO_Znf8fnJ1_` reached draft, trick skip, movement, landing, and purchase prompt through background workers
  - declining purchase cleared the prompt, processed AI turns, and returned to P1 with a round-2 draft prompt
  - captured `/tmp/mrn-ui-live-play-fixed.png` and `/tmp/mrn-ui-live-play-after-purchase.png`
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_continues_after_command_transition_until_prompt apps/server/tests/test_command_wakeup_worker.py apps/server/tests/test_redis_realtime_services.py -q`
- Lesson:
  - a Redis command is a wakeup edge, not the entire unit of runtime work
  - accepted-command offsets must be recorded once while deterministic queued engine actions drain until `waiting_input`, `finished`, or `unavailable`

## 2026-04-30 Tile Trait Action Pipeline Design

- Scope: document a consistent tile trait/modifier/action architecture before implementation.
- Done:
  - added `[PLAN]_TILE_TRAIT_ACTION_PIPELINE.md`
  - defined `TileEffectContext`, `PurchaseContext`, `RentContext`, and `ScoreTokenContext`
  - documented trait and modifier responsibilities
  - defined purchase, rent, score-token, fortune, and trick integration flows
  - documented anti-hardcoding rules for future tile/economy effects
  - linked the new design from the Redis authoritative state plan
- Next:
  - implement the first small slice: purchase context skeleton plus free-purchase modifier

## 2026-04-30 Purchase Context Modifier Seed

- Scope: implement the first tile-trait action-pipeline slice.
- Done:
  - added `GPT/tile_effects.py` with `TileEffectContext`, `PurchaseContext`, and purchase modifier interfaces
  - routed `_resolve_purchase_tile_decision()` through `build_purchase_context()`
  - added `BuilderFreePurchaseModifier` and `FreePurchaseModifier`
  - made one-shot free purchase flags consume only after successful ownership mutation
  - added purchase context payloads to purchase results
  - added tests for trick free purchase context, builder/free precedence, successful flag consumption, and skipped purchase preservation
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_tile_effects.py GPT/test_engine_resumable_checkpoint.py -k 'purchase or prompt_action'`
  - `./.venv/bin/python -m pytest GPT/test_rule_fixes.py -k 'purchase or matchmaker or madangbal or same_tile'`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py GPT/test_tile_effects.py GPT/test_engine_resumable_checkpoint.py -k 'doc_integrity or purchase or prompt_action'`
  - `./.venv/bin/python -m pytest GPT`
- Next:
  - split final purchase mutation into an explicit `resolve_purchase_tile` action
  - migrate rent calculation into `RentContext`

## 2026-04-30 Purchase Resolution Action Split

- Scope: continue the tile-trait action pipeline by separating purchase decision from purchase mutation.
- Done:
  - added `resolve_purchase_tile` as a queued action handler
  - changed `request_purchase_tile` so it performs precheck/decision and queues mutation only on an affirmative purchase decision
  - kept prompt interruption replay-safe: interrupted purchase prompts leave `request_purchase_tile` queued and preserve one-shot free-purchase flags
  - moved cash/shard payment, ownership transfer, first-purchase token placement, one-shot consumption, AI decision logging, and `tile_purchased` visualization into the purchase-resolution step
  - updated queued unowned-land arrival tests so the buying path is `resolve_arrival -> request_purchase_tile -> resolve_purchase_tile -> resolve_unowned_post_purchase`
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_tile_effects.py -k 'purchase or prompt_action'`
  - `./.venv/bin/python -m pytest GPT/test_rule_fixes.py -k 'purchase or matchmaker or madangbal or same_tile'`
- Follow-up:
  - run doc integrity and full engine suites after this documentation update
  - migrate rent calculation into `RentContext`
  - migrate score-token placement into resumable actions

## 2026-04-30 Rent Context Modifier Seed

- Scope: continue the tile-trait action pipeline by moving rent calculation into a deterministic context/modifier builder.
- Done:
  - added `RentContext`, `RentModifier`, and ordered rent modifiers to `GPT/tile_effects.py`
  - moved weather/color doubling, global rent modifiers, personal rent half effects, and normal-rent waivers into the rent context pipeline
  - updated normal rent payment to use `RentContext.final_rent` and consume normal-rent waiver counts through context consumptions
  - preserved non-rent derived pricing by making `_effective_rent()` call the rent context with `include_waivers=False`
  - added rent context tests for weather doubling, waiver consumption, and waiver exclusion
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_tile_effects.py GPT/test_rule_fixes.py -k 'rent or weather_color or trade_pass or purchase or matchmaker or same_tile'`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'queued_arrival_on_rent or purchase or prompt_action'`
- Follow-up:
  - run doc integrity and full engine suites after this documentation update
  - migrate score-token placement into resumable actions

## 2026-04-30 Score Token Placement Context Seed

- Scope: continue the tile-trait action pipeline by moving score-token placement calculation into a deterministic context.
- Done:
  - added `ScoreTokenPlacementContext` to `GPT/tile_effects.py`
  - routed `_place_hand_coins_on_tile()` through `build_score_token_placement_context()`
  - kept the existing mutation semantics intact while adding structured placement payloads
  - added tests for placement amount limits and blocked placement reasons
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_tile_effects.py GPT/test_rule_fixes.py -k 'score_token or coin or purchase_places or rent or trade_pass'`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'purchase or queued_arrival_on_rent or prompt_action'`
- Follow-up:
  - run doc integrity and full engine suites after this documentation update
  - split score-token placement into `resolve_score_token_placement` after landing/purchase result aggregation is adjusted

## 2026-04-30 Purchase Score Token Placement Action

- Scope: split first-purchase automatic score-token placement into a queued action.
- Done:
  - added `resolve_score_token_placement` action handling
  - changed `resolve_purchase_tile` so ownership/payment is committed before automatic score-token placement is queued
  - kept first-purchase placement before `resolve_unowned_post_purchase`, preserving landing post-effect result aggregation
  - updated pending purchase result aggregation so `placed` contains the final placement payload after the token action runs
  - added checkpoint tests for purchase-only placement and full arrival purchase flow with placement
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'purchase or score_token or prompt_action'`
  - `./.venv/bin/python -m pytest GPT/test_rule_fixes.py GPT/test_tile_effects.py -k 'purchase_places or score_token or coin or rent or trade_pass'`
- Follow-up:
  - run doc integrity and full engine suites after this documentation update
  - split own-tile visit placement into request/resolve actions because it has a policy decision boundary

## 2026-04-30 Own Tile Score Token Request Split

- Scope: split policy-selected own-tile score-token placement into replayable request/resolve actions.
- Done:
  - added `request_score_token_placement`
  - changed queued own-tile landing so it no longer calls `choose_coin_placement_tile` inside `resolve_arrival`
  - reused `resolve_score_token_placement` for the final mutation
  - preserved final landing result aggregation by carrying the own-tile base event through the score-token actions
  - added prompt interruption coverage proving the request action remains queued and tile tokens are not placed early
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'own_tile or score_token or purchase or prompt_action'`
  - `./.venv/bin/python -m pytest GPT/test_rule_fixes.py GPT/test_tile_effects.py -k 'coin or score_token or purchase_places or rent or trade_pass'`
- Follow-up:
  - run doc integrity and full engine suites after this documentation update
  - audit remaining inline economic mutations and split only where a real decision, animation, or recovery boundary exists

## 2026-04-30 Inline Economic Mutation Audit

- Scope: review remaining resource/ownership mutations after purchase, rent context, and score-token action splits.
- Done:
  - documented the split rule: actionize only for prompts, animation/presentation beats, Redis recovery boundaries, or shared modifier contexts
  - classified already split paths, context-backed paths, intentionally inline atomic effects, and watch-list candidates
  - added a contract test preventing default landing handlers from reopening purchase or score-token placement prompts inline
- Decision:
  - historical at the time: rent payment was left atomic because `RentContext` already isolated calculation. Superseded on 2026-05-03 by `resolve_rent_payment` / `RentPaymentModule`.
  - do not split weather/trick/F/S/MALICIOUS same-tile resource effects yet; they are deterministic atomic effects without a prompt boundary
- Validation:
  - pending after documentation update
- Follow-up:
  - run doc integrity and full engine suites
  - next implementation should target a concrete boundary, not add action layers speculatively

## 2026-04-30 Score Token Redis Recovery Coverage

- Scope: verify the new score-token request/resolve actions at the server Redis checkpoint boundary.
- Done:
  - added Redis recovery coverage for `resolve_score_token_placement` running before `resolve_unowned_post_purchase`
  - verified `pending_landing_purchase_result.placed` is updated after recovery drains the placement action
  - added human prompt recovery coverage for `request_score_token_placement`
  - verified checkpoint metadata preserves `pending_action_types` and `next_action_type` for score-token actions
- Validation:
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -k 'score_token_request or score_token_placement or purchase_actions_after_unowned or purchase_action_queued or post_purchase_action'`
- Follow-up:
  - run full engine checks and relevant server recovery checks before next commit

## 2026-04-30 Score Token Frontend Exposure Check

- Scope: verify whether the new score-token action types need UI labels.
- Result:
  - `request_score_token_placement` and `resolve_score_token_placement` are internal engine action types and are not included in backend scene `CORE_EVENT_CODES`.
  - Public UI continues to see `coin_placement` prompts plus existing public events such as `landing_resolved` and `tile_purchased`.
  - No new i18n/event label is needed unless a future feature deliberately emits score-token placement as its own public event.
- Validation:
  - inspected backend scene selector and web stream selectors for raw action-type exposure
- Follow-up:
  - if score-token placement becomes a public event later, add event tone, timeline/core-action labels, and selector tests at that time

## 2026-04-30 Trick Tile Target Action Split

- Scope: continue the fortune/trick audit by moving target-selecting trick rent modifiers to action boundaries.
- Done:
  - added `resolve_trick_tile_rent_modifier`
  - changed `재뿌리기` to queue the action instead of opening `choose_trick_tile_target` inline
  - changed `긴장감 조성` to queue the action instead of opening `choose_trick_tile_target` inline
  - added prompt interruption coverage proving the rent modifier action stays queued and does not mutate early
  - extended the action-pipeline contract so default effect handlers cannot reintroduce inline purchase/token/trick-target prompts
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_rule_fixes.py -k 'trick_tile_rent_modifier or trade_pass or rent_double or rent_zero or prompt_action or purchase'`
  - `./.venv/bin/python -m pytest GPT/test_action_pipeline_contract.py -q`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -k 'trick_tile_rent_modifier'`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py GPT/test_action_pipeline_contract.py GPT/test_engine_resumable_checkpoint.py -k 'doc_integrity or landing_effect_handlers or trick_tile_rent_modifier or score_token or purchase or prompt_action'`
  - `./.venv/bin/python -m pytest GPT`
- Follow-up:
  - continue auditing trick/fortune effects only where a real decision boundary remains

## 2026-04-29 Redis Action Pipeline Seed

- Scope: begin modular movement/arrival execution for the Redis-resumable engine path.
- Done:
  - added serializable `ActionEnvelope` and `GameState.pending_actions` checkpoint round-trip support
  - added engine action helpers for `apply_move` and `resolve_arrival`
  - routed fortune arrival movement, fortune move-only movement, and hunter forced landing through the shared target-move helper
  - preserved the rule boundary that movement sources calculate dice/fixed/target movement before arrival, while arrival only resolves the current tile
  - documented the action pipeline rule in the Redis authoritative state plan and module notes
  - extended `run_next_transition()` so pending queued actions are drained before normal turn advancement
  - verified queued `apply_move` can commit position change first, then queue `resolve_arrival` for a later transition
  - expanded queued `apply_move` to accept `move_value` for forward step movement, including path, total-step, and lap-reward handling before a separate arrival transition
  - added `_build_standard_move_action()` / `_enqueue_standard_move_action()` as the first normal-movement adapter from resolved `move` + `movement_meta` to queued actions
  - added a simple parity test showing the queued adapter reaches the same position/resources/F state as `_advance_player()` for a one-step lap+arrival case
  - expanded standard-move adapter parity coverage to card movement metadata, obstacle slowdown, and encounter boost
  - added zone-chain follow-up queueing from `resolve_arrival`, so a landing result can enqueue `apply_move -> resolve_arrival` instead of immediately nesting the extra movement
  - added checkpointed `pending_action_log` aggregation so queued movement can emit a legacy-compatible `turn` log summary after final arrival
  - defined the movement visual split: queued/follow-up movement emits `action_move`, while `player_move` remains the dice-paired regular turn movement
  - updated visual stream validation and backend board/reveal/turn/scene selectors so `action_move` is accepted and projected as movement without breaking the `dice_roll -> player_move` contract
  - migrated normal turn movement into the queued `apply_move -> resolve_arrival` path while preserving the public `dice_roll -> player_move` visual contract
  - added `pending_turn_completion` checkpoint state so turn-end snapshot emission, control-finisher bookkeeping, end checks, and turn/round cursor advancement happen only after queued movement actions finish
  - extended runtime checkpoint metadata with pending-action and pending-turn-completion flags
  - added Redis recovery coverage proving a hydrated pending `apply_move` action is drained and persisted after service reconstruction
  - added `scheduled_actions` checkpoint state for phase-targeted actions
  - materialized target-player `turn_start` scheduled actions into `pending_actions` before normal turn execution
  - moved queued mark delivery onto `resolve_mark` scheduled actions
  - kept immediate mark effects atomic inside `resolve_mark`, while hunter pull now generates follow-up `apply_move -> resolve_arrival` actions when resolved through the scheduled-action path
  - extended Redis recovery metadata and tests for scheduled action materialization after service reconstruction
  - migrated built-in movement fortune cards on the fortune-tile path into action producers that enqueue `apply_move` follow-ups
  - preserved direct fortune movement helpers as immediate compatibility paths for existing tests and extension hooks
  - added `fortune.card.produce` custom producer hook support for queued target movement
  - split backward takeover fortune cards into queued movement plus `resolve_fortune_takeover_backward`
  - added `request_purchase_tile` as the first decision-bearing queued action
  - extracted purchase decision/mutation into one engine helper shared by legacy landing purchases and queued purchase actions
  - made queued action execution reinsert the current action when a prompt/interruption is raised, preserving the retry point for Redis recovery
  - delayed purchase-only free-flag consumption until after purchase decision return, so prompt interruption does not mutate replay state
  - clarified the Redis canonical-state plan so board runtime state, tile ownership, score coins, purchase/rent metadata, card draw-pile order, discard/graveyard order, player trick hands, and hidden-card identity are explicitly Redis-owned rather than backend-memory-owned
  - tightened checkpoint serialization coverage for fortune/trick/weather draw and discard pile order plus tile purchase/rent metadata
  - split queued unowned-land arrival into `resolve_arrival -> request_purchase_tile -> resolve_unowned_post_purchase`
  - kept direct `_resolve_landing()` compatibility intact while making action-pipeline purchase prompts resumable
  - added Redis recovery coverage for the three purchase split checkpoints: queued purchase actions immediately after arrival, human purchase prompt waiting with the purchase action still queued, and post-purchase follow-up recovery
  - split queued rent landing follow-ups into `resolve_landing_post_effects`, covering adjacent-buy and same-tile bonus handling after rent payment
  - added Redis recovery coverage for a pending rent post-landing action
  - migrated subscription-style fortune card resolution into `resolve_fortune_subscription` on the queued fortune path
  - added interruption coverage proving fortune subscription target prompts leave the action queued
  - migrated land thief, donation angel, forced trade, and pious marker target-selection fortune effects into resumable `resolve_fortune_*` actions
  - extended runtime recovery checkpoint metadata with pending/scheduled action type lists and next-action hints
  - introduced a shared target-move action enqueue helper and migrated `극심한 분리불안` from inline movement to queued `apply_move -> resolve_arrival`
  - added an action-pipeline contract test that prevents production effect modules from calling immediate movement compatibility helpers
- Validation:
  - `./.venv/bin/python -m pytest GPT/test_action_pipeline_contract.py`
  - `./.venv/bin/python -m pytest GPT/test_action_pipeline_contract.py GPT/test_doc_integrity.py`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'extreme_separation or fortune_arrival or fortune_move_only or fortune_takeover or fortune_subscription'`
  - `./.venv/bin/python -m pytest GPT/test_event_effects.py::EventEffectIntegrationTests::test_fortune_producer_hook_can_queue_target_move GPT/test_rule_fixes.py::RuleFixTests::test_fortune_arrival_moves_then_resolves_landing_without_lap_credit GPT/test_rule_fixes.py::RuleFixTests::test_fortune_move_only_does_not_resolve_arrival`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py GPT/test_engine_resumable_checkpoint.py GPT/test_event_effects.py GPT/test_rule_fixes.py -k 'doc_integrity or extreme_separation or fortune_producer or fortune_arrival or fortune_move_only or fortune_takeover or fortune_subscription or zone_chain or purchase or rent'`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'fortune_subscription or fortune_land_thief or fortune_donation or fortune_forced_trade or fortune_pious_marker or fortune_takeover or fortune_arrival or fortune_move_only'`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -k 'unowned_arrival_checkpoint or drains_pending_action or scheduled_turn_start_action'`
  - `./.venv/bin/python -m pytest GPT/test_doc_integrity.py GPT/test_engine_resumable_checkpoint.py GPT/test_event_effects.py GPT/test_rule_fixes.py -k 'doc_integrity or fortune_subscription or fortune_land_thief or fortune_donation or fortune_forced_trade or fortune_pious_marker or fortune_producer or fortune_takeover or fortune_arrival or fortune_move_only or purchase or rent or matchmaker or madangbal or same_tile'`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_restart_persistence.py`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest GPT/test_state_checkpoint_serialization.py GPT/test_rule_fixes.py::RuleFixTests::test_suspicious_drink_uses_single_die GPT/test_rule_fixes.py::RuleFixTests::test_fortune_arrival_moves_then_resolves_landing_without_lap_credit GPT/test_rule_fixes.py::RuleFixTests::test_fortune_move_only_does_not_resolve_arrival GPT/test_event_effects.py::EventEffectIntegrationTests::test_fortune_movement_can_be_overridden`
  - `./.venv/bin/python -m pytest GPT/test_rule_fixes.py GPT/test_event_effects.py GPT/test_state_checkpoint_serialization.py`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_state_checkpoint_serialization.py GPT/test_rule_fixes.py::RuleFixTests::test_fortune_arrival_moves_then_resolves_landing_without_lap_credit GPT/test_rule_fixes.py::RuleFixTests::test_fortune_move_only_does_not_resolve_arrival`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_event_effects.py::EventEffectIntegrationTests::test_fortune_producer_hook_can_queue_target_move`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_restart_persistence.py`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest GPT/test_visual_runtime_substrate.py apps/server/tests/test_view_state_reveal_selector.py apps/server/tests/test_view_state_scene_selector.py apps/server/tests/test_view_state_turn_selector.py`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_visual_runtime_substrate.py apps/server/tests/test_view_state_reveal_selector.py apps/server/tests/test_view_state_scene_selector.py apps/server/tests/test_view_state_turn_selector.py`
  - `./.venv/bin/python -m pytest GPT apps/server/tests/test_view_state_reveal_selector.py apps/server/tests/test_view_state_scene_selector.py apps/server/tests/test_view_state_turn_selector.py`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py GPT/test_engine_resumable_checkpoint.py GPT/test_state_checkpoint_serialization.py`
  - `./.venv/bin/python -m pytest GPT/test_state_checkpoint_serialization.py GPT/test_engine_resumable_checkpoint.py apps/server/tests/test_redis_realtime_services.py`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_restart_persistence.py`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_restart_persistence.py`
  - `./.venv/bin/python -m pytest GPT`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py apps/server/tests/test_restart_persistence.py apps/server/tests/test_view_state_reveal_selector.py apps/server/tests/test_view_state_scene_selector.py apps/server/tests/test_view_state_turn_selector.py`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_event_effects.py GPT/test_rule_fixes.py -k 'purchase or fortune_producer or scheduled or hunter or prompt_action'`
  - `./.venv/bin/python -m pytest GPT/test_state_checkpoint_serialization.py`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'purchase or unowned or queued_arrival'`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_event_effects.py GPT/test_rule_fixes.py -k 'purchase or matchmaker or madangbal or same_tile or unowned or queued_arrival'`
  - `./.venv/bin/python -m pytest apps/server/tests/test_redis_realtime_services.py -k 'unowned_arrival_checkpoint or purchase_action_queued or post_purchase_action'`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'queued_arrival_on_rent or queued_arrival or purchase'`
  - `./.venv/bin/python -m pytest GPT/test_rule_fixes.py -k 'rent or matchmaker or madangbal or same_tile'`
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'fortune_subscription or fortune_takeover or fortune_arrival or fortune_move_only'`
- Validation failure and lesson:
  - `./.venv/bin/python -m pytest GPT/test_action_pipeline_contract.py GPT/test_doc_integrity.py` initially failed because `engine.py` received compatibility-helper docstrings without a paired `engine.md` update.
  - Lesson: even non-behavioral source annotations are source changes under the module-doc integrity rule, so update the paired module doc in the same slice.
  - `./.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py GPT/test_visual_runtime_substrate.py apps/server/tests/test_view_state_reveal_selector.py apps/server/tests/test_view_state_scene_selector.py apps/server/tests/test_view_state_turn_selector.py` initially failed in the new action-move visual test.
  - Cause: the test assumed the stream was empty after `prepare_run()`, but the engine correctly emits setup events such as `session_start`, `round_start`, and draft events before the queued move.
  - Lesson: movement-event assertions in resumable transition tests must filter the relevant semantic event type, because the visual stream is append-only and may already contain setup/replay context.
  - `./.venv/bin/python -m pytest GPT` initially failed after `pending_turn_completion` because module docs were older than `engine.py`/`state.py`.
  - Lesson: checkpoint-shape changes must update the paired module docs in the same slice, not after the broad test run.
  - The new purchase-prompt recovery test initially expected `_run_engine_transition_once_for_recovery()` to open a human prompt, but that helper intentionally runs without an event loop and therefore uses the AI policy path.
  - Lesson: human prompt recovery assertions must execute through the runtime transition loop with an event loop and stream service, because the non-blocking `DecisionGateway` is only installed on that path.
- Next:
  - keep expanding Redis recovery tests around prompt + pending action combinations

## 2026-04-26

### Entry 011

- Scope: match board top-view diamond stabilization and responsive HUD compaction.
- Done:
  - replaced the quarter-view ring projection with a symmetric top-view diamond coordinate model
  - derived ring tile side length from board projection spacing so edge and finish tiles lock into the same diamond geometry
  - removed rail/guide visuals from the ring board and made the board scale from viewport-constrained square dimensions
  - moved round/turn/marker into the session summary bar and repositioned weather to the top-left HUD slot
  - compacted player cards, active-character rows, and character standees so HUD panels waste less space and pawns render at a consistent size
  - rebuilt ring tile contents around a fixed flex layout for header, value/special body, owner/score, and pawn slots
  - moved the weather HUD out of the player-grid flow and anchored it to the visual board container's top-left area
  - redesigned the match HUD grid so player, active-character, event, and prompt panels occupy fixed rail areas without overlap
  - let the central prompt/waiting panel use the full prompt map column width and removed the old absolute center/calc width positioning
  - reduced match shell padding and viewport budgets to recover more board size
  - redesigned the active-character strip as a responsive eight-slot roster with character marks, names, and status text
  - tightened player-card rails and match overlay gutters so board tiles can render larger inside the viewport
  - reduced player-to-map gutter and expanded top-view ring spread so tiles use more of the available map container
  - documented the next flattened-quarterview board expansion plan, including split x/y projection, derived tile angle, rectangular tile sizing, HUD adaptation, tests, and rollback criteria
  - implemented flattened-quarterview geometry with split x/y spreads, aspect-ratio-aware tile angle derivation, rectangular tile sizing, and CSS variables from `BoardPanel`
  - corrected the first disconnected rectangular-tile pass by switching to projection-derived compressed diamond cells with visual join overlap
  - restored a subtle continuous board base under the real tiles so the ring reads as one connected map surface rather than separated cards
  - updated match board CSS so ring tiles render as wider, lower information cells while preserving the fixed internal tile content slots
  - retuned flattened-quarterview x/y spread and board aspect ratio to improve tile information readability without breaking the connected map surface
  - removed the active-character roster icon column so each entry gives more width to character name/status text
- Validation:
  - `cd apps/web && npm run test -- src/features/board/boardProjection.spec.ts`
  - `cd apps/web && npm run build`
  - in-app browser check at `http://127.0.0.1:9000/#/match` after Vite selected port 9000
- Post-evaluation failure note:
  - The 2026-04-26 strict tile-principle pass is visually wrong against the user's two tile rules.
  - Rule breach 1: a tile lane still reads as many independent rotated cards rather than one continuous straight-edged lane. Even if the mathematical centers line up, the visible surfaces, outlines, shadows, and per-tile rendering make the lane look segmented instead of a single straight exterior line.
  - Rule breach 2: the board is not fully protected from HUD intrusion. The weather panel still enters the upper-left board/tile visual area, so the board cannot be treated as an always-visible, unobscured play surface.
  - Why this mistake happened:
    - I optimized the existing absolute-positioned tile cards instead of changing ownership of the visual surface. That was the wrong abstraction: independent absolute tiles cannot reliably guarantee a continuous row exterior once transforms, outlines, shadows, antialiasing, and responsive scaling are involved.
    - I treated "40 tile DOM nodes rendered with no console errors" and "roughly inside the viewport" as sufficient validation. That ignored the user's stricter visual invariants: straight lane exterior, complete tile adjacency, and no HUD covering the board.
    - I compensated for clipping by shrinking and shifting the board with viewport-safe constants, which preserved technical fit but made the board smaller and left excessive unused space. This improved containment while damaging usability and did not address the underlying lane-continuity problem.
  - Corrective requirement for the next pass:
    - Render each lane from a lane-owned continuous geometry layer, then place tile information inside that lane. The visible lane exterior must be owned by the row/side, not by forty individually transformed tile cards.
    - HUD panels must be placed outside board-safe bounds, with weather/prompt collision tested visually against the actual tile area.
  - Follow-up redesign document:
    - `docs/current/engineering/[PLAN]_LANE_OWNED_BOARD_REDESIGN.md`
  - Implementation validation failure during lane-owned pass:
    - In-app browser check at `http://127.0.0.1:9000/#/match` rendered 4 lane strips and 40 lane cells with no console errors, but the visible board failed because the right and lower board areas were clipped outside the viewport.
    - The lane-owned surface fixed the worst "floating individual cards" read for the visible portion, but the board-safe size was still based on inherited viewport compensation constants. That means the geometry ownership was improved while containment ownership remained wrong.
    - Lesson: after changing the board surface owner, size/safe bounds must be recalculated from the full lane extents. Reusing the old board container width budget can still clip the continuous lanes because a rotated strip extends beyond the center-to-center diamond points.
    - Corrective action: tune the board safe width/height around the lane strip extents, then browser-verify clipping before judging visual success.

## 2026-04-15

### Entry 010

- Scope: GPT-only cleanup pass after excluding CLAUDE from the verification target.
- Done:
  - aligned GPT survival hard-blocking so only true expansion faces are vetoed, fixing `객주` draft/final-character regressions
  - aligned `박수` shard checkpoints across survival guard and purchase exceptions (`5` online / `7` more stable)
  - updated GPT regression fixtures for new `V2ProfileInputs` fields, real marker card ids, and rule-injection lap reward budgets
  - removed `PytestReturnNotNoneWarning` noise from the legacy human-play/live-server/replay suites by wrapping error-list tests with assert-based pytest adapters
  - deduplicated GPT/CLAUDE test-root bootstrapping through shared `test_import_bootstrap.py`
  - suppressed third-party `uvicorn`/`websockets` deprecation warnings in the affected runtime-service integration tests
- Validation:
  - `./.venv/bin/python -m pytest GPT -q`
  - `./.venv/bin/python -m pytest apps/server/tests -q`
  - `cd apps/web && npm run test`
  - `cd apps/web && npm run build`

## 2026-04-04

## 2026-04-07

### Entry 009

- Scope: board-target visibility recovery + stronger-worker smoke-check hardening.
- Done:
  - purchase and trick tile targeting can now surface multiple candidate tiles through selector-derived board focus
  - board tiles now show secondary candidate highlights instead of collapsing every multi-target prompt to one tile
  - matchmaker adjacent-buy flow now requests a real tile choice when two adjacent land tiles are available instead of auto-picking the first candidate
  - purchase prompt context now exposes richer tile metadata and adjacent candidate tiles
  - added `tools/check_external_ai_endpoint.py` to verify worker readiness, adapter/profile compatibility, supported request types, and a real `/decide` round-trip
  - updated worker runbook and human playtest checklist with the stronger-worker smoke-check step
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py GPT/test_rule_fixes.py`
  - `.venv311/bin/python tools/check_external_ai_endpoint.py --base-url http://127.0.0.1:8011 --require-ready --require-profile priority_scored --require-adapter priority_score_v1 --require-policy-class PriorityScoredPolicy --require-decision-style priority_scored_contract --require-request-type movement --require-request-type purchase_tile`
- Next:
  - use real playtest evidence to decide which tile-target and movement reveals still need visual upgrades
  - keep stronger external worker changes rollout-oriented rather than reopening broad architecture work

### Entry 001

- Scope: external AI auth/identity hardening + mixed-seat regression extension.
- Done:
  - runtime external-AI transport now validates `expected_worker_id` even when custom sender/healthchecker seams are injected
  - worker app now honors configured auth header name/scheme/token on both `/health` and `/decide`
  - session/API/parameter tests now cover external participant auth/identity fields
  - frozen external-AI examples expanded with `mark_target` and `active_flip`
  - browser E2E now covers mixed-seat session metadata including `human_http + local_ai + external_ai`
- Validation:
  - server pytest suite for runtime/session/worker contract
  - web selector/build/e2e regression suite
- Next:
  - keep trimming selector-side wording ownership
  - extend external worker operational path beyond the reference service

### Entry 005

- Scope: remote-turn payoff continuity + external worker healthcheck policy hardening.
- Done:
  - remote-turn stage/spectator strips now surface worker outcome/status inside the same payoff sequence as purchase, rent, fortune, and lap-reward beats
  - external participant parameters now include `healthcheck_policy` with `auto|required|disabled`
  - runtime HTTP transport can require health preflight even when a custom sender seam is injected
  - health-check cache scoping now includes the policy/requirement shape
  - reference worker capability metadata now advertises scored/preferred-choice behavior more explicitly
- Validation:
  - targeted server pytest for parameter/runtime worker transport
  - web selector/build/e2e regression suite
- Next:
  - only keep polishing remote-turn visuals where live evidence still reads like a feed
  - reserve broader worker upgrades for the next stronger-service slice

### Entry 006

- Scope: canonical decision-context surfacing + participant-parameter propagation proof.
- Done:
  - selector-side decision event detail now includes canonical tile/choice-count context and worker status through locale helpers
  - current turn stage keeps that richer decision context inside the active beat detail
  - added frozen WS example for an external-AI `decision_requested` event payload
  - added propagation coverage showing external participant parameter changes alter the public manifest hash
- Validation:
  - targeted web selector regression
  - targeted server contract/parameter propagation pytest
- Next:
  - keep any further decision-detail polishing locale-owned
  - widen browser coverage only when a new mixed-seat continuity case appears

### Entry 002

- Scope: selector locale ownership follow-up + timeout/fallback turn visibility.
- Done:
  - moved more actor-prefixed stream phrasing into locale helpers
  - made `decision_timeout_fallback` detail formatting locale-owned
  - kept `decision_requested` / `decision_resolved` / `decision_timeout_fallback` visible inside current-turn stage/spectator summaries
  - added selector regression and browser E2E coverage for remote timeout fallback continuity
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/selectors/promptSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`
- Next:
  - continue shrinking the remaining `uiText.ts` compatibility bridge
  - keep closing visual parity gaps only where replay/live evidence still drifts

### Entry 003

- Scope: default-text bridge reduction + external worker hardening follow-up.
- Done:
  - introduced `apps/web/src/i18n/defaultText.ts` so label/selector defaults no longer depend on `uiText.ts` as the primary source
  - kept `uiText.ts` as a smaller compatibility shim
  - simplified prompt header chrome to always use compact meta pills
  - external HTTP transport now surfaces worker diagnostic metadata into canonical public context on fallback paths
  - reference worker heuristics now explicitly cover `mark_target`, `coin_placement`, and `active_flip`
  - added a production-shaped external worker session payload example and deployment checklist
- Validation:
  - targeted web and server regression suites
- Next:
  - continue shrinking the remaining bridge callers
  - replace or extend the reference worker with a stronger policy/service implementation

### Entry 004

- Scope: remote-turn worker status continuity + mixed-seat regression hardening.
- Done:
  - current-turn stage/spectator selectors now preserve external-worker status from `decision_resolved` as well as timeout-fallback payloads
  - mixed-seat browser coverage now keeps worker-success then local-fallback continuity visible across adjacent turns
  - runtime transport diagnostics now expose external worker attempt counts for retry visibility
- Validation:
  - targeted selector regression
  - mixed-seat browser E2E
- Next:
  - keep trimming the remaining selector-owned wording
  - use live/replay evidence only for the last remote-turn visual polish gaps

### Entry 001

- Scope: policy guardrail hard-fix and mandatory reading stabilization.
- Done:
  - Added CI gate workflow for policy checks.
  - Added `tools/plan_policy_gate.py`.
  - Linked mandatory docs in PLAN index and backend README.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Start P0-1: Unified Decision API contract/order audit and runtime alignment.

### Entry 002

- Scope: mandatory principle update + P0-1 kickoff implementation.
- Done:
  - Added mandatory rules:
    - small/large work must be summarized into work journal
    - complex logic changes must start from plan doc
  - Rewrote mandatory/priority docs in UTF-8 to avoid encoding ambiguity.
  - Started P0-1 implementation in server runtime:
    - emit `decision_requested` on prompt registration
    - emit `decision_resolved` on accepted/timeout-fallback/parser-fallback
  - Added runtime unit-test assertions for decision request/resolve ordering.
- Next:
  - Continue P0-1 contract parity audit for remaining decision lanes.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (6/6).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventToneCatalog.spec.ts` passed (12/12).

### Entry 003

- Scope: P0-1 decision-lane parity expansion (timeout lane + selector visibility).
- Done:
  - Added `decision_resolved` emission before `decision_timeout_fallback` in websocket timeout lane.
  - Expanded stream API test to assert timeout resolution ordering:
    - `decision_resolved` appears before `decision_timeout_fallback`.
  - Rewrote web event label catalog/spec in UTF-8 and added decision event labels.
  - Added selector test coverage for `decision_requested` / `decision_resolved` timeline details.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py -q` passed (`6 passed, 10 skipped`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/eventToneCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`16 passed`).
- Next:
  - Continue P0-1 with remaining decision submit/ack ordering audit for non-timeout branches.

### Entry 004

- Scope: P0-1 deterministic ordering hardening (bridge timeout path).
- Done:
  - Added runtime bridge timeout test:
    - `decision_requested` -> `decision_resolved` -> `decision_timeout_fallback` ordering assertion.
  - Synced server timeout lane to emit `decision_resolved` before timeout fallback.
  - Stabilized web decision-event label/spec coverage.
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`7 passed`).
  - `python -m pytest apps/server/tests/test_stream_api.py -q` passed (`10 skipped`, no failures).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/eventToneCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`16 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-1 non-timeout branch audit in mixed runtime/reconnect conditions.

### Entry 005

- Scope: P0-1 validation planning under local dependency constraints.
- Done:
  - Updated decision API detailed plan with explicit local validation note.
  - Documented FastAPI-gated skip reality and CI-first verification path for non-timeout stream branch.
- Next:
  - Implement/verify non-timeout branch ordering fixture in FastAPI-enabled matrix.

### Entry 006

- Scope: P0-1 non-timeout stream branch CI fixture.
- Done:
  - Added stream API test for normal accepted decision path:
    - seat-authenticated decision submission
    - `decision_ack` accepted verification
  - This fixture is FastAPI-gated and will run in dependency-enabled CI.
- Validation:
  - `python -m pytest apps/server/tests/test_stream_api.py -q` (no failures, FastAPI-gated skips in current local env).

### Entry 007

- Scope: P0-1 decision resolution de-duplication and parser-fallback correctness.
- Done:
  - Fixed runtime bridge ordering bug:
    - accepted `decision_resolved` is now emitted only after parser success.
    - parser failure path emits a single `decision_resolved` with `resolution=parser_error_fallback`.
  - Expanded runtime tests:
    - accepted path asserts exactly one `decision_resolved`.
    - timeout path asserts exactly one `decision_resolved`.
    - parser-error path asserts exactly one `decision_resolved` and fallback return.
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`15 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - P0-1 reconnect/retry mixed-lane audit for non-timeout accepted branch.

### Entry 008

- Scope: P0-1 retry branch determinism (non-timeout).
- Done:
  - Added stream API test fixture for duplicate decision submission on same `request_id`.
  - Expected behavior fixed by test contract:
    - first submit -> `decision_ack: accepted`
    - second submit(retry) -> `decision_ack: stale (already_resolved)`
- Validation:
  - `python -m pytest apps/server/tests/test_stream_api.py -q` (FastAPI-gated skips in current local env, no failures).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
- Next:
  - Extend reconnect/resume scenario to include decision-event replay consistency.

### Entry 009

- Scope: P0-1 reconnect/resume ordering fixture.
- Done:
  - Added stream replay contract test for decision/domain ordering:
    - `decision_requested -> decision_resolved -> player_move` must remain ordered after resume replay.
- Validation:
  - `python -m pytest apps/server/tests/test_stream_api.py -q` (FastAPI-gated skips in current local env, no failures).
- Next:
  - Finalize P0-1 by wiring CI-visible coverage status and preparing P0-2 entry.

### Entry 010

- Scope: P0-1 CI visibility hardening.
- Done:
  - Added dedicated CI workflow:
    - `.github/workflows/backend-decision-contract-tests.yml`
  - CI now runs:
    - `apps/server/tests/test_runtime_service.py`
    - `apps/server/tests/test_stream_api.py`
  - This closes the local FastAPI-gated skip blind spot by validating in CI environment.
- Validation:
  - Workflow file created and tracked.
- Next:
  - Start P0-2 lane separation implementation (core/prompt/system) in web projection path.

### Entry 011

- Scope: P0-2 lane separation kickoff in turn theater.
- Done:
  - Added theater lane classification in selector path:
    - `core` / `prompt` / `system`
  - Reflected lane in theater item model + rendering.
  - Updated incident card UI with lane badge and lane-specific visual styling.
  - Added selector assertions for lane classification.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`15 passed`).
- Next:
  - Continue P0-2 by splitting timeline/feed render blocks by lane priority and visibility policy.

### Entry 012

- Scope: P0-2 lane-aware theater rendering.
- Done:
  - Updated theater component to render lane groups:
    - 핵심 진행
    - 선택/응답
    - 시스템
  - Added lane badge and lane-specific visual styling.
  - Preserved tone badges and recent-event emphasis.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`15 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 visibility policy: promote other-player core actions to always-visible top block.

### Entry 013

- Scope: P0-2 lane contract test expansion.
- Done:
  - Added selector test to ensure:
    - `decision_requested` and `decision_resolved` are classified as `prompt` lane in theater feed.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`13 passed`).
- Next:
  - Continue P0-2 visibility policy and actor-priority rendering for non-human core actions.

### Entry 014

- Scope: P0-2 theater visibility policy (prompt flood resilience).
- Done:
  - Added lane-aware quota policy in `selectTheaterFeed`:
    - core/prompt/system caps with fallback fill.
  - Ensured feed is still filled to requested limit while preserving core visibility.
  - Added test for prompt-heavy traffic:
    - core event remains visible.
  - Updated theater UI to grouped lane rendering and badges.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`14 passed`).
  - `npm run build` passed (`apps/web`).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 by adding actor-focus priority strategy (non-human core actions + human prompt clarity).

### Entry 015

- Scope: P0-2 actor-focus priority strategy.
- Done:
  - Added `focusPlayerId` binding from app context to theater component.
  - Prioritized non-focus(core) actor events before focus actor events in core lane.
  - Preserved lane grouping and tone/lane badges.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`17 passed`).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 with turn-theater visibility tuning for passive prompts vs actionable prompts.

### Entry 016

- Scope: P0-2 prompt visibility tuning in theater.
- Done:
  - Added prompt-lane priority ordering:
    - `decision_resolved` > `decision_timeout_fallback` > `decision_ack` > `decision_requested` > `prompt`
  - Applied focus actor context so local actionable prompt context is surfaced earlier in prompt lane.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`17 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 by connecting lane visibility policy to match-level collapsible controls (operator UX).

### Entry 017

- Scope: P0-2 operator UX controls for lane visibility.
- Done:
  - Added per-lane collapse controls in turn theater:
    - 핵심 진행 / 선택응답 / 시스템 각각 접기/펼치기
  - Added lane header and toggle styling.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`17 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 with passive/non-actionable prompt demotion tuning in theater + timeline.

### Entry 018

- Scope: P0-1 closure reinforcement (mixed-path runtime contracts + human-play regression safety).
- Done:
  - Added ordered sequence contract fixtures:
    - `packages/runtime-contracts/ws/examples/sequence.decision.accepted_then_domain.json`
    - `packages/runtime-contracts/ws/examples/sequence.decision.timeout_then_domain.json`
  - Added runtime contract test coverage for ordered decision/domain sequences:
    - `apps/server/tests/test_runtime_contract_examples.py`
  - Expanded backend contract CI workflow to include runtime contract fixture tests.
  - Added selector regression coverage for mixed human-play decision flow:
    - decision lane remains visible
    - core progression (`dice_roll`, `player_move`, `landing_resolved`) remains visible
    - raw prompt is system lane noise, not blocking core.
  - Updated plan docs with latest P0-1 status snapshot.
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_contract_examples.py -q` passed (`2 passed`).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`19 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Push and verify CI result of `backend-decision-contract-tests`.
  - Continue P0-2 live screen UX parity corrections.

### Entry 019

- Scope: P0-2 live-screen UX parity pass (board readability + turn visibility).
- Done:
  - Reworked board tile presentation for human readability:
    - compact tile text (`색상`, `구매/렌트`), reduced debug-like wording
    - larger pawn tokens with per-player color for position visibility
    - stronger special tile presentation path retained for `운수`, `종료`
  - Added `TurnStagePanel` to the match main column so non-local actor progress is always visible.
  - Updated responsive board sizing to reduce fixed-size overflow behavior:
    - ring board now uses responsive max width + aspect-ratio layout
    - line board keeps horizontal scroll fallback but reduced minimum size.
  - Added turn-stage styles (badge/cards/grid) for immediate timeline comprehension.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts src/features/board/boardProjection.spec.ts` passed (`24 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - run web test/build and policy gates.
  - continue P0-2 prompt placement/action narration parity fixes.

### Entry 020

- Scope: P0-2 action narration visibility reinforcement.
- Done:
  - Added `실시간 진행` banner in match main column using latest core-lane event.
  - Keeps actor + action label + detail visible even when prompt/theater sections are long.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`21 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue prompt placement parity and non-local turn readability polish.

### Entry 021

- Scope: P0-2 lobby usability parity (collapsible controls).
- Done:
  - Rebuilt `LobbyView` with collapsible sections:
    - 로비 제어
    - 스트림 연결
    - 세션 목록
  - Added shared `panel-head` layout styles for consistent fold controls.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`21 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue prompt placement/action narration parity fixes in match flow.

### Entry 022

- Scope: P0-2 prompt payload parity (engine->web) and human-readable prompt options.
- Done:
  - Updated `GPT/viewer/human_policy.py` decision envelopes for human seat prompts:
    - draft/final character choices now include `character_ability` payload.
    - mark target / purchase / geo bonus / coin placement / burden exchange labels localized.
    - hidden-trick prompt now also carries `full_hand` context for unified card rendering.
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx`:
    - movement submit is disabled until valid card-selection combination exists in card mode.
    - trick prompt shows single unified hand summary (`손패 전체`, `히든` count).
    - mark-target card now renders explicit target summary (`대상 인물 / 플레이어`).
- Validation:
  - `python -m py_compile GPT/viewer/human_policy.py` passed.
  - `python -m pytest GPT/test_human_policy_prompt_payloads.py -q` passed (`2 passed`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`21 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 live match UX parity: non-local turn narration/overlay positioning and prompt ergonomics.

### Entry 023

- Scope: P0-2 live match visibility reinforcement (non-local core actions + weather effect fallback).
- Done:
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts`:
    - added safer weather fallback helper (`weatherEffectFallbackText`) so weather effect no longer collapses to `-` when payload effect is omitted.
    - weather reveal/situation persistence now use the fallback helper.
  - Updated `apps/web/src/App.tsx`:
    - added `selectCoreActionFeed(...)` usage in match screen.
    - added a new `최근 핵심 행동 목록` strip (latest 8 core actions) so other players’ moves/purchases/rent flow remains visible in real time.
  - Updated `apps/web/src/styles.css`:
    - added core-action-strip panel/card styles with responsive fallback.
  - Added selector regressions in `apps/web/src/domain/selectors/streamSelectors.spec.ts`:
    - weather fallback text test (missing explicit weather effect payload).
    - core action feed local/non-local actor classification test.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`18 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2/P0-3 parity fixes: replace remaining prompt text corruption and restore human-centric interaction wording.

### Entry 024

- Scope: P0-2 prompt UX readability normalization (human-friendly copy + interaction clarity).
- Done:
  - Rewrote `apps/web/src/features/prompt/PromptOverlay.tsx` with normalized Korean copy and consistent interaction flow:
    - movement prompt now clearly split into `주사위 굴리기` / `주사위 카드 사용`
    - card selection uses concise chip list (`[1] [2] ...`) with max-card guidance
    - trick/hidden-trick cards render in one unified hand view with hidden-state and usability badges
    - draft/final character prompts now display explicit guidance and ability text block
    - mark target prompt renders explicit `[대상 인물 / 플레이어: ...]` description
    - busy/feedback text rewritten to user-facing wording
  - Replaced corrupted prompt label/helper catalogs with UTF-8 clean definitions:
    - `apps/web/src/domain/labels/promptTypeCatalog.ts`
    - `apps/web/src/domain/labels/promptHelperCatalog.ts`
- Validation:
  - `npm run test -- --run src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`24 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2/P0-3: turn-theater narrative polish and prompt/request sequencing parity against engine flow.

### Entry 025

- Scope: P0-3 turn-theater readability normalization.
- Done:
  - Rewrote `apps/web/src/features/theater/IncidentCardStack.tsx` with clean user-facing copy:
    - lane section titles normalized (`핵심 진행`, `선택 / 응답`, `시스템`)
    - tone/lane badges normalized (`이동/경제/중요/진행`, `핵심/선택/시스템`)
    - per-lane fold controls renamed to `접기/펼치기`
    - actor/action row format unified to `Pn - 이벤트`
  - Kept existing lane prioritization logic and focus-player ordering behavior intact.
- Validation:
  - `npm run test -- --run src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`29 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue match-screen copy polish and remaining sequence parity checks (weather/fortune/turn narration consistency).

### Entry 026

- Scope: P0-2 board readability normalization (human-facing copy).
- Done:
  - Rewrote `apps/web/src/features/board/BoardPanel.tsx` while preserving projection logic:
    - tile/zone/cost/owner labels now use player-facing Korean wording
    - special tile labels normalized (`운수`, `종료 - 1`, `종료 - 2`, `고급 토지`)
    - board header summary normalized (`라운드/턴/징표 소유자/종료 시간`)
    - recent move line normalized (`최근 이동: Px a -> b`)
    - pawn rendering and move highlight behavior preserved
  - Kept DI/selectors boundary unchanged (presentation-only refactor).
- Validation:
  - `npm run test -- --run src/features/board/boardProjection.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`29 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2/P0-3 sequence parity and narration quality (weather/fortune/turn theater continuity).

### Entry 027

- Scope: P0-2 prompt-submit reliability hardening (prevent stuck `처리 중` state).
- Done:
  - Updated websocket client send contract:
    - `StreamClient.send(...)` now returns `boolean` success/failure.
    - `StreamClient.requestResume(...)` now returns `boolean` success/failure.
  - Updated hook contract:
    - `useGameStream.sendDecision(...)` now returns `boolean`.
  - Updated match prompt handling in `App.tsx`:
    - prompt busy state is enabled only after a successful decision send.
    - when send fails, immediate user-facing feedback is shown.
    - if prompt is busy and stream transitions to non-connected/error, busy state is released with retry guidance.
- Validation:
  - `npm run test -- --run src/infra/ws/StreamClient.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`16 passed`).
  - `npm run test -- --run src/infra/ws/StreamClient.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts` passed (`23 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2 human-play UX parity pass (prompt narrative clarity + non-local turn continuity polish).

### Entry 028

- Scope: P0-2 prompt choice-card normalization (request-type specific human wording).
- Done:
  - Updated `PromptOverlay` generic choice rendering to apply request-specific text normalization:
    - `lap_reward`: `현금/조각/승점 선택` + 실제 보상 수치 표시
    - `purchase_tile`: `토지 구매` / `구매 없이 턴 종료` 문구 고정
    - `active_flip`: `뒤집기 종료` 및 `A -> B` 변환 문구 고정
    - `burden_exchange`: `지 카드 제거` / `유지` 문구 고정
  - Rewrote `promptSelectors.spec.ts` in clean UTF-8 Korean for readability/maintainability.
- Validation:
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/infra/ws/StreamClient.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts` passed (`26 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
- Next:
  - Continue P0-2/P1 with turn-theater continuity polish and observer/non-local turn visibility flow.

### Entry 029

- Scope: P0-1/P0-2 decision lifecycle visibility cleanup in React selectors.
- Done:
  - Updated `apps/web/src/domain/selectors/promptSelectors.ts`:
    - active prompts now close not only on `decision_ack(accepted|stale)` but also on canonical runtime events:
      - `decision_resolved`
      - `decision_timeout_fallback`
    - this prevents resolved non-local/AI prompts from lingering as if still actionable.
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts`:
    - situation headline now ignores prompt/system noise when selecting the current narrative event:
      - `prompt`
      - `decision_ack`
      - `decision_requested`
      - `decision_resolved`
      - `decision_timeout_fallback`
      - `parameter_manifest`
      - all `error` messages
    - result: `현재 상황` follows core rule progression instead of getting replaced by prompt/ack/runtime warning chatter.
  - Added selector regression coverage:
    - prompt closes when the same request is resolved by event without local ack
    - prompt closes when timeout fallback event arrives
    - situation headline remains pinned to the latest core turn event even if prompt/decision messages arrive later
  - Updated `apps/web/src/features/theater/IncidentCardStack.tsx`:
    - system lane now defaults to collapsed so runtime/debug chatter does not dominate the live match screen by default
- Validation:
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`18 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2 with lane rendering/UI so the cleaned selector behavior is reflected as distinct core/prompt/system panels during human play.

### Entry 030

- Scope: P0-2 core-turn action lane wiring in the React match screen.
- Done:
  - Added `apps/web/src/features/theater/CoreActionPanel.tsx`.
    - promotes non-local/public turn actions into a dedicated panel
    - keeps the latest visible action as a larger hero card
    - keeps a short grid of recent public actions underneath
  - Wired `CoreActionPanel` into `apps/web/src/App.tsx` directly under `TurnStagePanel`.
  - Updated `apps/web/src/styles.css`:
    - added dedicated `core-action-panel` / hero / feed-card styles
    - hid legacy `live-action-banner` and `core-action-strip-panel` blocks so the old strip UI does not duplicate the new lane
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue P0-2 with viewport-scale layout, prompt placement, and motion/board readability recovery.

### Entry 031

- Scope: P0-2 viewport-scale match layout and prompt overlay sizing recovery.
- Done:
  - Updated `apps/web/src/styles.css` so the live match screen uses the viewport more aggressively:
    - wider `match-layout` split
    - sticky side column on desktop
    - board scroll region capped against viewport height instead of forcing oversized page growth
    - ring board now scales by viewport height/width rather than a fixed `980px` ceiling
  - Prompt overlay now opens closer to full viewport width/height instead of the previous narrower fixed ceiling.
  - Added hover/transition polish for tile cards and prompt choice cards to improve scanability/click affordance.
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - remove the remaining duplicated legacy action JSX from `App.tsx`
  - continue prompt placement separation and theater-grade movement/purchase/fortune rendering

### Entry 032

- Scope: P0-2 prompt presentation separation polish.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so the overlay root carries a request-type class (`prompt-overlay-${requestType}`).
  - Updated `apps/web/src/styles.css`:
    - prompt modal now behaves more like a bottom-sheet layer instead of always centering over the full board
    - request-type overlays (`movement`, `trick_to_use`, `hidden_trick_card`, `mark_target`) can now size differently
    - choice cards and primary action buttons received clearer hover affordances
    - desktop prompt choice density was increased while keeping mobile single-column fallback
- Validation:
  - `npm run build` passed (`apps/web`).
- Remaining:
  - remove leftover duplicated legacy action JSX in `App.tsx`
  - continue actor-turn / movement / purchase / fortune theater rendering

### Entry 033

- Scope: P0-2 turn-theater readability uplift.
- Done:
  - Rewrote `apps/web/src/features/theater/IncidentCardStack.tsx` in clean UTF-8 Korean labels.
  - Added a hero-style top card for the latest core/public action.
  - Reframed lane labels to player-facing wording:
    - `턴 진행`
    - `선택 요청`
    - `시스템 기록`
  - Updated `apps/web/src/styles.css` for stronger incident theater hierarchy:
    - hero card
    - clearer card spacing
    - stronger emphasis state for current/high-priority core events
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue movement / purchase / fortune / rent visualization upgrades
  - clean remaining legacy duplicated JSX in `App.tsx`

### Entry 034

- Scope: P0-2 stage summary hierarchy and board pawn readability.
- Done:
  - Rewrote `apps/web/src/features/stage/TurnStagePanel.tsx` in clean UTF-8 Korean with a stronger hierarchy:
    - hero card for current actor/turn
    - dedicated weather card
    - separate movement / landing / card-effect summaries
  - Updated `apps/web/src/features/board/BoardPanel.tsx` so pawn tokens now render the player number directly inside the token.
  - Updated `apps/web/src/styles.css`:
    - larger pawn tokens
    - stronger stage-panel layout and card hierarchy
    - mobile fallback for the stage hero card
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue theater-grade rendering for movement / purchase / fortune / rent
  - remove remaining duplicated legacy action JSX in `App.tsx`

### Entry 035

- Scope: P0-2 public-action wording cleanup and event tone alignment.
- Done:
  - Rewrote `apps/web/src/features/theater/CoreActionPanel.tsx` in clean UTF-8 Korean.
  - Clarified public-action copy so the panel explicitly describes visible shared actions.
  - Updated `apps/web/src/domain/labels/eventToneCatalog.ts`:
    - `rent_paid`, `fortune_drawn`, `fortune_resolved` now follow economy tone
    - `trick_used` now follows critical tone for stronger visibility in theater cards
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue movement / purchase / fortune / rent card-specific rendering
  - remove remaining duplicated legacy action JSX in `App.tsx`

### Entry 036

- Scope: P0-2 public-action card scanning aids.
- Done:
  - Updated `apps/web/src/features/theater/CoreActionPanel.tsx`:
    - added a lightweight action-type classifier for player-facing chips
    - cards now surface `이동 / 경제 / 효과 / 선택 / 진행` categories directly in metadata
  - Updated `apps/web/src/styles.css` with `core-action-chip` styling for faster card scanning
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue per-action rendering improvements
  - remove remaining duplicated legacy action JSX in `App.tsx`

### Entry 037

- Scope: P0-2 theater component UTF-8 recovery and stronger action differentiation.
- Done:
  - Rewrote these files in clean UTF-8 Korean:
    - `apps/web/src/features/theater/CoreActionPanel.tsx`
    - `apps/web/src/features/theater/IncidentCardStack.tsx`
  - Added action-kind differentiation in public action cards:
    - `move`
    - `economy`
    - `effect`
    - `decision`
    - `system`
  - Added matching border-accent styling in `apps/web/src/styles.css`.
  - In `apps/web/src/App.tsx`, duplicated legacy action render paths were disabled from actual rendering (`false ? (...) : null`) so only the new panels remain visible.
- Validation:
  - `npm run build` passed (`apps/web`).
- Remaining:
  - physically remove the disabled legacy JSX block from `App.tsx`
  - continue per-event bespoke rendering for movement / purchase / fortune / rent

### Entry 038

- Scope: P0-2 duplicated action render cleanup and theater card differentiation.
- Done:
  - Physically removed the remaining disabled legacy public-action JSX blocks from `apps/web/src/App.tsx`.
  - Rewrote these files in clean UTF-8 with player-facing Korean copy:
    - `apps/web/src/features/theater/CoreActionPanel.tsx`
    - `apps/web/src/features/theater/IncidentCardStack.tsx`
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
  - Strengthened public-action cards so movement / economy / effect / decision / system items now render with different copy structure and detail blocks.
  - Added theater lane subtitles so `turn progress / prompt flow / system log` remain visually distinct.
  - Updated `apps/web/src/styles.css` with:
    - `core-action-detail-list`
    - `core-action-detail-item`
    - `incident-lane-subtitle`
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue actor-flow continuity so other-player turns feel more cinematic
  - keep reducing replay-like feeling in the live match screen

### Entry 039

- Scope: current-work snapshot organization + string externalization planning.
- Done:
  - Added active plan at the historical old top-level plan path `[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`.
  - Linked the plan into priority/status/mandatory reading docs.
  - Recorded the reason for the new plan: repeated mojibake risk and inline-string regression across React runtime surfaces.
  - Kept the current snapshot push-oriented rather than pretending the live UX recovery is complete.
- Validation:
  - existing `apps/web` build remains passing from the current UI slice.
- Next:
  - extract critical live-view strings from `App.tsx`, theater, stage, prompt, and lobby components before further UX reshaping.

### Entry 040

- Scope: P0-string phase 1 implementation and verification.
- Done:
  - Added centralized typed resource ownership in `apps/web/src/domain/text/uiText.ts`.
  - Migrated major visible React strings to shared catalogs in:
    - `App.tsx`
    - `LobbyView.tsx`
    - `PromptOverlay.tsx`
    - `CoreActionPanel.tsx`
    - `IncidentCardStack.tsx`
    - `TurnStagePanel.tsx`
    - `BoardPanel.tsx`
    - `ConnectionPanel.tsx`
  - Replaced remaining direct join-seat error text in `App.tsx` with catalog-driven wording.
  - Normalized lobby chrome wording to player-facing Korean labels.
- Validation:
  - `npm run test -- --run src/domain/labels` passed (`17 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P1 string migration into selector-generated visible summaries (`streamSelectors.ts` and adjacent runtime-facing summary helpers).

### Entry 041

- Scope: P0-string phase 2 selector-summary migration.
- Done:
  - Added shared `STREAM_TEXT` helpers to `apps/web/src/domain/text/uiText.ts`.
  - Migrated selector-facing visible phrases in `apps/web/src/domain/selectors/streamSelectors.ts`:
    - generic event fallback
    - weather effect fallback text
    - move/dice summaries
    - landing result labels
    - heartbeat detail text
    - runtime stalled warning text
    - tile purchase / marker transfer summaries
    - bankruptcy / game-end winner summaries
    - lap reward summary pieces
    - manifest sync / mark resolved / marker flip / 종료 시간 변경 text
    - prompt waiting summary in turn-stage projection
  - Fixed `decision_ack` non-event label regression back to `선택 응답`.
- Validation:
  - `npm run test -- --run src/domain/labels src/domain/selectors` passed (`35 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue remaining string ownership cleanup in theater classification heuristics and any leftover board/runtime display literals.

### Entry 042

- Scope: priority reference UTF-8 recovery.
- Done:
  - Rewrote `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md` in clean UTF-8.
  - Re-aligned the document with current actual priorities:
    - Unified Decision API stability
    - Human Play live UI recovery
    - latest game-rule alignment
    - string externalization / encoding stability
- Validation:
  - document rewritten as plain UTF-8 text and now usable as the current start-order reference.
- Next:
  - continue remaining P0-string cleanup and then return to live human-play UI recovery tasks using the refreshed priority reference.

### Entry 043

- Scope: P0-string phase 3 prompt/auxiliary catalog consolidation.
- Done:
  - Expanded `apps/web/src/domain/text/uiText.ts` with:
    - `PLAYERS_TEXT`
    - `TIMELINE_TEXT`
    - `PROMPT_TYPE_TEXT`
    - `PROMPT_HELPER_TEXT`
  - Rewired these modules to consume centralized text resources:
    - `apps/web/src/domain/labels/promptTypeCatalog.ts`
    - `apps/web/src/domain/labels/promptHelperCatalog.ts`
    - `apps/web/src/features/players/PlayersPanel.tsx`
    - `apps/web/src/features/timeline/TimelinePanel.tsx`
  - Recovered corrupted spec files in clean UTF-8:
    - `promptTypeCatalog.spec.ts`
    - `promptHelperCatalog.spec.ts`
    - `uiText.spec.ts`
  - Removed remaining direct mark-target helper copy in `PromptOverlay.tsx` and routed it through prompt helper text.
- Validation:
  - pending local test/build run after this consolidation pass.
- Next:
  - run `apps/web` test/build verification
  - continue remaining selector-string cleanup
  - then return to live human-play UI recovery

### Entry 044

- Scope: P0-string phase 4 leftover selector/display cleanup.
- Done:
  - Removed duplicated weather fallback ownership from `streamSelectors.ts` so selector weather fallback now depends only on `STREAM_TEXT`.
  - Moved board zone-color CSS aliases into `BOARD_TEXT.zoneColorCss`.
  - Rewired `BoardPanel.tsx` to consume the centralized board color catalog.
- Validation:
  - pending local test/build run after this leftover cleanup.
- Next:
  - re-run `apps/web` tests/build
  - if clean, shift focus back to human-play live UI recovery

### Entry 045

- Scope: P0-2 situation panel readability recovery.
- Done:
  - Added `SITUATION_TEXT` to the shared UI text catalog.
  - Rebuilt `apps/web/src/features/status/SituationPanel.tsx` as a card-based summary panel:
    - 행동자
    - 라운드 / 턴
    - 현재 이벤트
    - 이번 라운드 날씨
    - 날씨 효과
  - Added matching layout styles in `apps/web/src/styles.css` so the situation area reads like a live match summary instead of raw stacked lines.
- Validation:
  - pending local build/test after the panel rewrite.
- Next:
  - verify `apps/web` build/test
  - continue human-play theater/live-flow improvements

### Entry 046

- Scope: P0-string UTF-8 catalog recovery and selector label stabilization.
- Done:
  - Rebuilt `apps/web/src/domain/text/uiText.ts` in clean UTF-8 with restored Korean wording for:
    - app/lobby/connection/board/player/timeline/situation text
    - prompt type/helper text
    - stream/theater/turn-stage/prompt text
  - Rebuilt `apps/web/src/domain/labels/eventLabelCatalog.ts` in clean UTF-8.
  - Recovered corrupted spec files in clean UTF-8:
    - `uiText.spec.ts`
    - `eventLabelCatalog.spec.ts`
    - `promptTypeCatalog.spec.ts`
    - `promptHelperCatalog.spec.ts`
    - `streamSelectors.spec.ts`
- Validation:
  - `npm run test -- --run src/domain/text src/domain/labels src/domain/selectors` passed (`43 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - continue remaining string ownership cleanup by moving event labels into the shared catalog layer
  - keep pushing live human-play stage continuity

### Entry 047

- Scope: P0-string shared event-label ownership + P0-2 turn-stage continuity.
- Done:
  - Added `EVENT_LABEL_TEXT` to `apps/web/src/domain/text/uiText.ts`.
  - Rewired `apps/web/src/domain/labels/eventLabelCatalog.ts` to consume shared text resources instead of owning inline labels.
  - Extended `selectTurnStage` in `apps/web/src/domain/selectors/streamSelectors.ts` with:
    - `currentBeatLabel`
    - `currentBeatDetail`
    - turn-progress trail seeded from `turn_start`
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` to render:
    - current live beat card
    - prompt/current-action summary
    - visible turn-progress trail chips
  - Added matching trail/wide-card styles in `apps/web/src/styles.css`.
- Validation:
  - `npm run test -- --run src/domain/text src/domain/labels src/domain/selectors` passed.
  - `npm run build` passed (`apps/web`).
- Next:
  - keep reducing “replay/debug wall” feel by making other-player turn beats more theatrical
  - continue prompt UX tightening and board/readability recovery

### Entry 048

- Scope: P0-string UTF-8 catalog hard recovery + browser quick-start parity lock.
- Done:
  - Fully restored `apps/web/src/domain/text/uiText.ts` in clean UTF-8 Korean/English.
  - Recovered corrupted spec files in clean UTF-8:
    - `apps/web/src/domain/text/uiText.spec.ts`
    - `apps/web/src/domain/labels/promptTypeCatalog.spec.ts`
    - `apps/web/src/domain/labels/promptHelperCatalog.spec.ts`
    - `apps/web/src/domain/labels/eventLabelCatalog.spec.ts`
    - `apps/web/src/domain/selectors/streamSelectors.spec.ts`
  - Extended `apps/web/e2e/parity.spec.ts` with a real `1 human + 3 AI quick start` browser flow:
    - `POST /sessions`
    - `POST /join`
    - `POST /start`
    - runtime polling
    - stream replay
    - first human prompt visibility
  - Updated existing browser parity assertions so they match the current Korean lobby/match UI instead of stale English/raw-debug assumptions.
- Validation:
  - `npm run test -- --run src/domain/text src/domain/labels src/domain/selectors` passed (`43 passed`).
  - `npm run e2e -- e2e/parity.spec.ts` passed (`4 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - keep pushing P0-2 live-play UX so prompt surfaces feel like a game, not a debug inspector
  - add more mixed-session browser coverage for follow-up human decisions (`movement`, `purchase_tile`, `mark_target`)

### Entry 049

- Scope: mandatory encoding-safety rule reinforcement.
- Done:
  - Rewrote `docs/current/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md` in clean UTF-8.
  - Added an absolute start rule so every task must open the mandatory reading document first.
  - Strengthened the encoding policy:
    - Korean text must stay UTF-8
    - CP-949 is forbidden
    - PowerShell mojibake must not trigger ad-hoc file re-encoding
  - Updated `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md` so every future task explicitly re-checks:
    - mandatory principles
    - string/externalization plan
- Validation:
  - documentation update only
- Next:
  - continue P0-2 live-play UX recovery on top of the stabilized encoding/documentation rules

### Entry 050

- Scope: P0-2 prompt-surface recovery for movement / purchase / mark, plus browser parity lock.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so key human prompts render as dedicated game-style cards instead of falling back to one generic choice wall:
    - `movement`
      - now parses both runtime-contract `dice_*` ids and `card_values` payloads
      - shows context cards (`현재 위치`, `사용 가능 카드`, `선택 카드`, `현재 날씨`)
      - exposes stable `data-testid` hooks for browser verification
    - `purchase_tile`
      - now renders a dedicated decision layout with tile/cost/cash/zone summary cards
      - action cards are emphasized as `토지 구매` vs `구매 없이 턴 종료`
    - `mark_target`
      - now renders actor/candidate/location context cards
      - target cards stay explicit about `대상 인물 / 플레이어`
    - `lap_reward`
      - now renders a dedicated reward-choice surface with current resource summaries
  - Updated `apps/web/src/styles.css` with prompt context grids and stronger dedicated choice layouts for target/purchase/reward decisions.
  - Extended `apps/web/e2e/parity.spec.ts` with new browser coverage:
    - movement prompt contract path using `dice_1_4`
    - purchase decision prompt
    - mark target prompt
- Validation:
  - `npm run test -- --run src/domain/selectors src/domain/labels src/domain/text` passed (`43 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - continue P0-2 on non-local turn choreography so other-player actions feel live, not replay-like
  - keep shrinking prompt inspector feel by moving more context into stage/theater cards and less into large static walls

### Entry 051

- Scope: P0-2 non-local turn continuity recovery between stage, board, and core-action summaries.
- Done:
  - Extended `apps/web/src/domain/selectors/streamSelectors.ts` so `selectTurnStage` now carries:
    - `currentBeatKind`
    - `focusTileIndex`
  - Beat kind is now projected from canonical event codes:
    - `move`
    - `economy`
    - `effect`
    - `decision`
    - `system`
  - Tile focus is now derived from canonical payload fields for:
    - `player_move`
    - `landing_resolved`
    - `tile_purchased`
    - `rent_paid`
    - `fortune_drawn`
    - `fortune_resolved`
    - `trick_used`
    - actionable prompt context with `public_context.tile_index`
  - Updated `apps/web/src/features/board/BoardPanel.tsx` so the board can render a live focus summary and focus-ring overlay that follows the current turn beat.
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` and `apps/web/src/styles.css` so hero/current-beat cards change emphasis by beat kind instead of always looking identical.
  - Filled a real selector UX hole:
    - `rent_paid` details are now summarized explicitly instead of falling through as empty text
    - `fortune_drawn` / `fortune_resolved` now also emit explicit summary strings through the shared text catalog
  - Added selector regression coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts` for:
    - purchase focus
    - rent focus
    - prompt-driven focus carry-over
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`19 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - keep pushing P0-2 by making the other-player turn read more like `actor start -> move -> landing -> result` instead of isolated cards
  - strengthen weather / fortune persistence so it feels like live board state, not just one summary field

### Entry 052

- Scope: P0-2 focused board readability follow-up.
- Done:
  - Added an in-tile live action tag to `apps/web/src/features/board/BoardPanel.tsx` so the currently focused board tile now shows the active beat label directly on the square.
  - Added beat-colored focus styling in `apps/web/src/styles.css` so the board summary and the focused tile share the same move/economy/effect/decision language.
  - Updated `pickMessageDetail` in `apps/web/src/domain/selectors/streamSelectors.ts` so `turn_start` no longer produces an empty detail line in stage/theater summaries.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`14 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - keep reducing the gap between "highlighted tile" and "felt turn flow" by chaining actor start / move / landing / result more explicitly across stage and theater

### Entry 053

- Scope: P0-2 turn-flow visibility + board-weather persistence + browser regression coverage.
- Done:
  - Added persistent board weather summary to `apps/web/src/features/board/BoardPanel.tsx` so the current round weather remains visible near the board even when the user is focused on turn actions.
  - Added a per-tile live action tag for the currently focused board tile so the player can see not just which tile is active, but what kind of beat is being processed there.
  - Extended `apps/web/src/features/theater/CoreActionPanel.tsx` with a same-turn flow panel:
    - it now shows the latest turn's public sequence as a short ordered strip instead of only isolated recent cards
  - Extended `CoreActionItem` with canonical event metadata (`eventCode`, `round`, `turn`) so the UI can group public actions by actual turn boundaries.
  - Added browser test coverage in `apps/web/e2e/parity.spec.ts` so the quick-start smoke now verifies:
    - `board-weather-summary`
    - `core-action-flow-panel`
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`19 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - continue toward full human-play feel by making non-local turns animate/read as one continuous scene instead of a better-organized live log

### Entry 054

- Scope: P0-string UTF-8 catalog recovery + P0-2 spectator continuity.
- Done:
  - Rewrote `apps/web/src/domain/text/uiText.ts` as a clean UTF-8 resource catalog.
  - Rewrote `apps/web/src/domain/text/uiText.spec.ts` so string-catalog regression checks now assert human-readable Korean instead of mojibake snapshots.
  - Added `apps/web/src/features/stage/SpectatorTurnPanel.tsx`.
  - Replaced the old waiting-only panel in `apps/web/src/App.tsx` with the spectator turn panel so non-local turns now keep showing:
    - current weather
    - current beat
    - latest public action
    - move / landing / economy / effect summaries
    - turn progress trail
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
- Next:
  - continue recovering prompt-surface copy/layout so the movement / trick / mark / purchase prompts stop inheriting legacy broken inline strings
  - add browser-level coverage for spectator-side continuity when it is not the local player's turn

### Entry 055

- Scope: bilingual string architecture planning.
- Done:
  - Added the historical old top-level plan `[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`.
  - Defined a locale-split architecture so Korean/English strings can be stored outside components and injected through a provider layer.
  - Covered:
    - target directory layout under `apps/web/src/i18n/`
    - locale bundle composition
    - translator/provider usage model
    - selector detachment from locale-specific sentence ownership
    - migration order
    - parity/e2e test requirements
- Next:
  - after the current prompt-surface cleanup, start the i18n foundation:
    - `apps/web/src/i18n/`
    - `ko/en` locale skeletons
    - `uiText.ts` compatibility bridge

### Entry 056

- Scope: priority-board resync + locale-boundary execution start.
- Done:
  - Re-synced active plan documents so current implementation is no longer driven by already-completed "add i18n foundation" tasks.
  - Updated the live priority order to:
    - selector/resource locale detachment
    - prompt cleanup on top of locale resources
    - non-local turn continuity
    - rule-parity visual fixes
  - Marked `apps/web/src/i18n/` foundation as already active and narrowed the string plan to:
    - selector-visible phrasing
    - compatibility-bridge reduction
    - locale-aware resource ownership
  - Prepared the next execution slice around `streamSelectors.ts` so visible wording can stop depending on the Korean bridge by default.
- Validation:
  - document/status resync only
- Next:
  - add locale-aware text injection path to `streamSelectors.ts`
  - wire `App.tsx` to pass current locale resources into selector formatting
  - keep browser/test coverage green while reducing `uiText.ts` ownership

### Entry 057

- Scope: P0-4 selector locale-boundary implementation.
- Done:
  - Added locale-aware text injection to `apps/web/src/domain/selectors/streamSelectors.ts`.
  - Added `StreamSelectorTextResources` and kept a default compatibility path for existing tests/callers.
  - Moved runtime selector formatting away from forced Korean bridge ownership for:
    - timeline
    - theater feed
    - critical alerts
    - situation
    - turn stage
    - core action feed
  - Updated `apps/web/src/App.tsx` so live runtime selectors receive the current locale resources from `useI18n()`.
  - Re-synced the active string/priority plans to reflect that selector locale injection is now in place.
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/text/uiText.spec.ts` passed (`33 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
- Next:
- continue shrinking selector-owned visible sentence composition
- keep prompt/theater/runtime surfaces aligned with locale resources
- move further toward human-play-first match UX on top of the locale-safe selector path

### Entry 058

- Scope: P0-2 browser-level human-play recovery hardening.
- Done:
  - Added stable test ids for:
    - quick-start lobby button
    - turn notice banner
    - spectator turn detail cards
  - Added `apps/web/e2e/human_play_runtime.spec.ts` with dedicated UTF-8-safe browser coverage for:
    - quick start -> first local prompt visible
    - remote actor turn -> spectator panel visible and no local prompt
- Why:
  - core human-play flow should not depend on brittle direct locale text matching
  - this protects against regressions in:
    - local actionable prompt visibility
    - remote turn continuity
    - turn-start feedback visibility
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 059

- Scope: P0-2 prompt surface cleanup and spectator continuity uplift.
- Done:
  - Reworked `apps/web/src/features/prompt/PromptOverlay.tsx` so the local decision surface now separates:
    - header/instruction
    - choice body
    - low-priority request metadata/footer
  - Added section wrappers and stronger choice-surface styling in `apps/web/src/styles.css` to reduce the remaining inspector/debug feel.
  - Upgraded `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now shows:
    - current weather
    - weather effect
    - current character
    - current beat
    - latest public action
  - Extended browser coverage in `apps/web/e2e/human_play_runtime.spec.ts` to assert the spectator character card is present.
- Why:
  - human play still suffered from a "form inspector" feeling during prompts
  - remote turns needed faster comprehension of "who is acting as what under which weather"
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 060

- Scope: P0-2 top-shell cleanup and passive/observer guidance polish.
- Done:
  - Reworked `apps/web/src/features/status/ConnectionPanel.tsx` into a compact status-card grid so the connection shell reads like a game HUD instead of a debug paragraph block.
  - Updated `apps/web/src/App.tsx` passive-prompt surface so other-player decision waiting is shown as a compact observer card with a spinner badge instead of plain text.
  - Extended `apps/web/src/styles.css` to support:
    - connection HUD cards
    - cleaner sticky top shell background
    - stronger passive prompt presentation
  - Kept the human-play browser/runtime regression green after the shell changes.
- Why:
  - the top area still pulled visual attention away from the actual board/gameplay scene
  - passive waiting feedback needed to feel like "someone else is deciding" rather than "a debug paragraph happened"
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 061

- Scope: P0-2 observer continuity follow-up.
- Done:
  - Extended `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now also surfaces:
    - current weather effect
    - current prompt/choice state
  - Added a stable `spectator-turn-prompt` browser hook.
  - Updated locale resources in:
    - `apps/web/src/i18n/locales/ko.ts`
    - `apps/web/src/i18n/locales/en.ts`
  - Kept browser coverage aligned in `apps/web/e2e/human_play_runtime.spec.ts`.
- Why:
  - remote-turn readability still dropped whenever there was a lull between public actions
  - human observers need to know whether the remote player is moving, resolving, or currently deciding
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 062

- Scope: P0-2 board scene readability follow-up.
- Done:
  - Upgraded the focused tile surface in `apps/web/src/features/board/BoardPanel.tsx` so the live tag now shows:
    - beat label
    - beat detail
  - Added pulsing emphasis by beat kind in `apps/web/src/styles.css` for:
    - move
    - economy
    - effect
    - decision
- Why:
  - board focus previously showed that a tile mattered, but not clearly why it mattered
  - human observers need the board itself to explain the scene, not only the side/theater panels
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 063

- Scope: P0-2 board actor/move scene follow-up.
- Done:
  - Extended `apps/web/src/features/board/BoardPanel.tsx` so the focused board scene now exposes:
    - explicit move-start badge
    - explicit move-end badge
    - current active-turn actor banner on the relevant tile
  - Added locale-backed board strings in:
    - `apps/web/src/i18n/locales/ko.ts`
    - `apps/web/src/i18n/locales/en.ts`
    for:
    - move start
    - move end
    - active actor tag
  - Expanded `apps/web/src/styles.css` so:
    - move badges are visually anchored to the tile corner
    - the active pawn pulses more strongly
    - the active-turn tile now carries a small live actor banner
  - Tightened browser regression in `apps/web/e2e/human_play_runtime.spec.ts` to verify:
    - `board-move-start-badge`
    - `board-move-end-badge`
    - `board-actor-banner`
- Why:
  - human observers still had to infer too much from side panels instead of reading the board directly
  - movement continuity is more legible when the board explicitly marks origin, destination, and active actor
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 064

- Scope: P0-2 movement/mark prompt simplification follow-up.
- Done:
  - Simplified the movement decision surface in `apps/web/src/features/prompt/PromptOverlay.tsx` so it now reads as:
    - short instruction
    - compact current context
    - mode switch
    - selected-state pills
    - execute button
    instead of repeating multiple context card blocks.
  - Added movement status-pill styling in `apps/web/src/styles.css` so card-mode selection no longer feels like a raw inspector dump.
  - Upgraded mark-target choice cards in `apps/web/src/features/prompt/PromptOverlay.tsx` to expose:
    - target character
    - target player id
    as direct choice pills instead of relying only on descriptive text.
- Why:
  - human decision prompts still spent too much vertical space on duplicated metadata
  - mark-target selection needed more glanceable "who exactly is this target" information
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 065

- Scope: P0-2 public turn-flow choreography follow-up.
- Done:
  - Upgraded `apps/web/src/features/theater/CoreActionPanel.tsx` so the latest same-turn public actions now render as a compact journey strip, not only as isolated cards.
  - Added journey-strip styling in `apps/web/src/styles.css` so move/economy/effect/decision beats read like a chained scene.
  - Extended browser regression in `apps/web/e2e/human_play_runtime.spec.ts` to lock `core-action-journey` during remote-turn viewing.
- Why:
  - remote turns still felt too much like a card log
  - same-turn public events need to read as one unfolding scene for human observers
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 066

- Scope: P0-2/P0-4 runtime stabilization in forced English mode.
- Done:
  - Switched `apps/web/src/i18n/index.ts` default locale to `en`.
  - Tightened `apps/web/src/i18n/I18nProvider.tsx` initial-locale resolution so the app now boots into English unless the stored locale is already `en`.
  - Preserved the in-progress turn-stage scene-strip / public-turn flow work while re-stabilizing runtime behavior.
  - Cleaned temporary Playwright output under `apps/web/test-results/`.
- Why:
  - the Korean locale recovery path is still in progress and should not block runtime verification
  - human-play validation needs one stable language mode that can keep build, selector tests, and browser parity green
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 067

- Scope: P0-2/P0-4 prompt readability cleanup and turn-scene continuity.
- Done:
  - Cleaned `apps/web/src/features/prompt/PromptOverlay.tsx` so visible prompt context no longer shows corrupted unit suffixes.
  - Reduced prompt inspector feel in English mode by:
    - removing bracket-heavy copy
    - simplifying request meta to actor/time information
    - making dice-card chips render as plain card numbers
  - Extended `apps/web/src/features/stage/TurnStagePanel.tsx` scene-strip so it now carries:
    - move
    - landing
    - purchase
    - rent
    - fortune
  - Added move-tone scene styling in `apps/web/src/styles.css`.
  - Updated `apps/web/src/i18n/locales/en.ts` so English-mode labels read naturally during:
    - trick selection
    - character selection
    - mark targeting
    - locale switching
- Why:
  - human-play prompts still contained debug-ish wording and broken suffix text
  - remote turns needed stronger continuous scene beats so they read less like isolated state cards
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 068

- Scope: P0-2 theater de-duplication and spectator readability follow-up.
- Done:
  - Removed the duplicate same-turn flow panel from `apps/web/src/features/theater/CoreActionPanel.tsx` so the public action area now relies on:
    - latest hero action
    - same-turn journey strip
    - older public action feed
    instead of rendering the same flow twice.
  - Added `data-testid="core-action-panel"` and updated browser coverage to anchor on the panel itself rather than requiring a journey strip in turn states that do not yet have one.
  - Refined `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so:
    - current beat title
    - current beat detail
    - latest public action title
    - latest public action detail
    render on separate lines instead of slash-joined inspector text.
  - Polished English prompt copy in `apps/web/src/i18n/locales/en.ts`:
    - lighter request meta
    - cleaner decision chip wording
    - less mechanical movement / trick / mark / purchase copy
    - simpler busy state text
  - Restyled prompt footer metadata in `apps/web/src/styles.css` into a compact HUD pill instead of raw footer text.
- Why:
  - the match screen still felt too much like a state inspector because the same turn flow was rendered more than once
  - spectator cards still packed multiple ideas into one slash-delimited line
  - prompt footer/status text still read more like transport metadata than live game UI
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 069

- Scope: P0-2 prompt HUD timing follow-up.
- Done:
  - Added a live countdown bar to `apps/web/src/features/prompt/PromptOverlay.tsx` so actionable prompts now show time pressure as a visible HUD element instead of only footer text.
  - Restyled the prompt footer in `apps/web/src/styles.css` so actor/time metadata reads as a compact pill plus timer bar instead of raw inspector text.
- Why:
  - even after wording cleanup, the prompt footer still felt like transport metadata rather than a live game decision surface
  - human testing benefits from seeing countdown pressure immediately, not reconstructing it from text
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 070

- Scope: P0-2/P0-3 weather selector parity follow-up.
- Done:
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so weather summaries now honor `effect_text` when the runtime payload provides it.
  - Added selector coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts` to lock `weather_reveal.effect_text` parity.
- Why:
  - weather cards must show the actual rule text from the runtime when it exists, not fall back to a generic effect label
  - this directly affects whether live human-play feels trustworthy during round start
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`28 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 071

- Scope: P0-1 unified decision runtime wrapper for AI seats.
- Done:
  - Added `apps/server/src/services/decision_gateway.py`.
  - Moved canonical human decision request/resolve publishing into `DecisionGateway`.
  - Replaced the human-only runtime bridge with `_ServerDecisionPolicyBridge` in `apps/server/src/services/runtime_service.py`.
  - Runtime now wraps both human and AI seats behind one decision contract at the server boundary.
  - AI decisions now emit:
    - `decision_requested`
    - `decision_resolved`
    with `provider="ai"`.
  - Human decision events now explicitly emit `provider="human"`.
  - Added backend regression coverage proving AI purchase decisions emit ordered request/resolve events.
- Why:
  - the runtime previously used one contract for human seats and direct policy calls for AI seats
  - this was the main P0-1 architectural gap still left open in live/runtime mode
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py` passed (`9 passed`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 072

- Scope: P0-2 human-play noise control after AI decision unification.
- Done:
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so AI-side decision lifecycle events are routed to the `system` lane instead of the `prompt` lane.
  - Added selector coverage to lock this behavior.
- Why:
  - AI now shares the same backend decision contract, but those internal request/resolve events should not visually compete with actionable human prompts
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 073

- Scope: P0-2 remote-turn board continuity / move-path visibility.
- Done:
  - Extended `selectLastMove()` in `apps/web/src/domain/selectors/streamSelectors.ts` so recent `player_move` state now preserves the emitted `path` tiles, not only start/end.
  - Updated `apps/web/src/features/board/BoardPanel.tsx` to render recent path-step markers on intermediate tiles during the latest move.
  - Added board styling in `apps/web/src/styles.css` for:
    - intermediate move-trail tiles
    - dashed recent-path emphasis
    - numbered path-step badges
  - Updated `apps/web/e2e/human_play_runtime.spec.ts` so remote-turn runtime coverage now asserts an intermediate path step is visible on the board.
  - Added selector coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts` to lock `pathTileIndices` extraction.
- Why:
  - remote turns still felt too much like card/log updates because only the source and destination tiles were highlighted
  - preserving and rendering the path makes other-player turns read more like spatial movement on a board
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 074

- Scope: P0-1 canonical decision payload follow-up for stream timeout/ack paths.
- Done:
  - Added shared decision payload builders to `apps/server/src/services/decision_gateway.py`:
    - `build_decision_ack_payload(...)`
    - `build_decision_requested_payload(...)`
    - `build_decision_resolved_payload(...)`
    - `build_decision_timeout_fallback_payload(...)`
  - Refactored `DecisionGateway` itself to use those builders instead of ad-hoc inline dictionaries.
  - Updated `apps/server/src/routes/stream.py` so:
    - websocket timeout fallback emission
    - seat decision acknowledgement emission
    now use the same canonical payload builders.
  - Human-side `decision_ack`, `decision_resolved`, and `decision_timeout_fallback` messages now explicitly carry `provider="human"` on the stream route path as well.
  - Added/updated backend regression coverage in:
    - `apps/server/tests/test_runtime_service.py`
    - `apps/server/tests/test_stream_api.py`
- Why:
  - AI-seat runtime wrapping was already emitting canonical lifecycle events, but stream timeout/ack code paths still hand-built similar payloads
  - centralizing those payloads lowers drift risk and moves the system closer to a true shared human/AI decision contract
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed (`9 passed, 13 skipped`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 075

- Scope: P0-2 turn-journey readability follow-up.
- Done:
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` so the scene strip now includes prompt/decision state in the same ordered journey as move / landing / purchase / rent / fortune.
  - Added scene-step numbering to the turn-stage strip.
  - Updated `apps/web/src/styles.css` to style the numbered scene-step badge.
- Why:
  - remote turns still needed a clearer read order for `choose -> move -> land -> resolve`
  - adding prompt state into the same strip makes the turn feel more like one continuous scene instead of disconnected cards
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 076

- Scope: P0-2 outcome-card staging and prompt HUD simplification follow-up.
- Done:
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` so purchase / rent / fortune / trick results now also render as a dedicated outcome strip instead of only living inside mixed summary cards.
  - Updated `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now includes a spotlight row for public economy/effect outcomes.
  - Updated `apps/web/src/features/theater/CoreActionPanel.tsx` so the latest economy/effect beat gets a dedicated result card in addition to the hero/journey/feed layout.
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so collapsed prompt chip text and footer meta use a shorter local HUD line instead of request/debug-heavy wording.
  - Extended browser parity in `apps/web/e2e/human_play_runtime.spec.ts` to lock:
    - `spectator-turn-spotlight`
    - `core-action-result-card`
    - `turn-stage-outcome-strip`
- Why:
  - remote/public turns still needed stronger scene payoff after movement finished
  - prompt surfaces still carried more metadata weight than necessary for human play
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 077

- Scope: P0-2 board move-trail animation follow-up.
- Done:
  - Updated `apps/web/src/features/board/BoardPanel.tsx` so recent path-step badges now carry a step-order CSS variable.
  - Updated `apps/web/src/styles.css` so intermediate move-trail tiles and path-step badges animate in a staggered wave instead of remaining static.
- Why:
  - remote turns still needed more motion/readability even before true token interpolation lands
  - staggered path emphasis makes board movement read more like a route in progress rather than only a set of highlighted boxes
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 078

- Scope: P0-2 weather/fortune staging and prompt-surface simplification follow-up.
- Done:
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` so live turns now expose a dedicated spotlight strip for:
    - weather
    - fortune
    - purchase
    - rent
  - Updated `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now starts with a larger scene card instead of only small status cards.
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so:
    - movement prompt no longer uses the old context-card grid
    - movement choices now read more like a compact game HUD
    - roll detection no longer depends on a hardcoded Korean title check
  - Updated `apps/web/src/App.tsx` so the raw/debug toggle no longer sits in the always-visible top command row and only appears after opening the match-top panel.
  - Updated `apps/web/src/styles.css` to support the new spotlight / hero treatments and lighter top-command presentation.
  - Extended browser coverage in `apps/web/e2e/human_play_runtime.spec.ts` to lock:
    - `spectator-turn-scene`
    - `turn-stage-spotlight-strip`
    - hidden raw/debug toggle by default
- Why:
  - remote turns still felt too much like reading scattered panels instead of watching one live scene
  - movement prompt still carried inspector-like context-card structure
  - raw/debug controls were still too visible in the main match shell
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 079

- Scope: P0-1 canonical AI/human request-type mapping follow-up.
- Done:
  - Added `METHOD_REQUEST_TYPE_MAP` and `decision_request_type_for_method(...)` to `apps/server/src/services/decision_gateway.py`.
  - Updated `apps/server/src/services/runtime_service.py` so AI decision dispatch now uses the shared request-type resolver instead of a bridge-local mapping table.
  - Added regression coverage in `apps/server/tests/test_runtime_service.py` for canonical request-type resolution.
- Why:
  - the runtime bridge still owned one more string-heavy mapping that could drift away from the gateway contract
  - moving request-type normalization into the canonical decision module reduces future AI/human contract skew
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed (`10 passed, 13 skipped`)

### Entry 080

- Scope: P0-2 prompt-surface flattening follow-up.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so:
    - movement prompt now uses summary pills instead of the previous context-card block
    - mark target prompt now uses summary pills instead of the previous context-card block
    - purchase prompt now uses summary pills instead of the previous context-card block
    - lap reward prompt now uses summary pills instead of the previous context-card block
  - Kept the same gameplay data visible while reducing the "inspector card" look.
- Why:
  - even after the first prompt cleanup pass, major human-choice surfaces still looked too much like debugging cards
  - flattening those context areas preserves information while making the prompt feel closer to a board-game HUD
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 081

- Scope: P0-2 board pawn-travel scene follow-up.
- Done:
  - Completed the in-flight board movement treatment in `apps/web/src/features/board/BoardPanel.tsx` by keeping the transient ghost pawn overlay wired to the latest move origin/destination coordinates.
  - Updated `apps/web/src/styles.css` so the board now renders a short-lived ghost pawn travel animation between move start and move end instead of relying on static badges alone.
  - Extended browser parity in `apps/web/e2e/human_play_runtime.spec.ts` to lock `board-moving-pawn-ghost`.
- Why:
  - recent path badges and tile pulses improved readability, but the board still lacked an obvious "piece moved here" moment
  - a lightweight ghost pawn animation adds scene continuity without needing full per-step interpolation yet
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed

### Entry 082

- Scope: P0-4 prompt locale-boundary cleanup follow-up.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so collapsed prompt chip text and footer request-meta text now come from locale resources instead of component-local string assembly.
  - Cleaned the English locale wording in `apps/web/src/i18n/locales/en.ts` for prompt collapse/meta lines so the default English mode no longer carries mojibake bullets in those surfaces.
  - Removed one leftover unused local helper after the locale-boundary handoff.
- Why:
  - prompt chrome still had a few direct user-facing literals inside the component, which breaks the bilingual/string-separation goal and makes encoding regressions easier to reintroduce
  - the user explicitly asked for clean KO/EN switching and stronger protection against string corruption
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed

### Entry 083

- Scope: P0-4 prompt choice-text locale cleanup extension.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so purchase-choice description text now also comes from locale resources instead of a component-local English fallback.
  - Normalized the English locale prompt wording in `apps/web/src/i18n/locales/en.ts` for:
    - collapsed chip
    - request meta
    - purchase choice description
- Why:
  - even after the first locale-boundary cleanup, purchase prompt wording still had one direct component-owned sentence
  - the default English mode still carried mojibake separators in a few prompt-facing strings
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed

### Entry 084

- Scope: P0-1 decision gateway lifecycle helper cleanup.
- Done:
  - Updated `apps/server/src/services/decision_gateway.py` so human and AI resolution paths now share internal helper methods for:
    - requested event publishing
    - resolved event publishing
    - timeout fallback event publishing
- Why:
  - even after canonical payload builders were introduced, the gateway still repeated nearly identical publish blocks in multiple branches
  - centralizing those publish paths lowers drift risk while continuing the "AI and human share one decision contract" track
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed

### Entry 085

- Scope: P0-2 remote-turn scene payoff and prompt simplification follow-up.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so the movement prompt now hides non-essential summary pills during normal dice mode and only surfaces selected-card state when the player is actually using dice cards.
  - Updated `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so spectator spotlight cards now use specific turn-stage labels (`purchase / rent / fortune / trick`) instead of generic `economy / effect` buckets, and the hero scene card now carries the latest public action headline together with the current beat summary.
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so:
    - tile purchase details now carry the acting player prefix
    - lap reward details now carry the acting player prefix
    - fortune draw / fortune resolution details now carry the acting player prefix
  - Re-stabilized `apps/web/src/i18n/locales/en.ts` after a broken legacy locale fragment in the board/weather fallback area was surfaced by build/e2e.
  - Normalized the English wording for:
    - tile purchase detail
    - rent detail
    - fortune draw / fortune resolution detail
    - movement prompt button text
- Why:
  - other-player turns still needed stronger "something just happened" payoff instead of flat status summaries
  - the movement prompt still exposed more bookkeeping than was useful during live play
  - build/e2e caught a legacy corrupted English locale fragment, so the string-stability track needed another hardening pass
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

## 2026-04-06 Locale Restore Follow-up

- What changed:
  - Exported `resolveLocaleFromStoredValue(...)` from `apps/web/src/i18n/I18nProvider.tsx` so locale restore behavior is explicit and testable.
  - Fixed the restore path so both `ko` and `en` survive reloads instead of only recognizing stored English.
  - Replaced the broken legacy `apps/web/src/i18n/i18n.spec.ts` content with a clean UTF-8 spec that asserts English default plus bidirectional locale restore.
  - Extended `apps/web/e2e/human_play_runtime.spec.ts` so remote-turn continuity now also requires the spectator payoff card.
- Why:
  - the bilingual string architecture is not complete if locale switching silently resets after refresh
  - the human-play UI contract should protect the spectator payoff surface that was just added
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/i18n/i18n.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`32 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`3 passed`)

## 2026-04-06 Prompt / Spectator / Decision Drift Follow-up

- What changed:
  - Reordered `none` / pass-style options to the end of display order in mark and generic prompt surfaces so primary actions appear first.
  - Added a dedicated spectator journey strip that now reads remote turns as:
    - current character
    - current choice beat
    - movement
    - landing
    - economy/effect payoff
  - Added backend coverage that AI `mark_target` decisions also emit the canonical:
    - `decision_requested`
    - `decision_resolved`
    lifecycle with the `mark_target` request type.
- Why:
  - prompt surfaces were still front-loading passive choices and reading more like inspectors than live game choices
  - spectator continuity still needed one stronger scene-oriented strip in addition to spotlight/payoff cards
  - the unified decision plan needed one more specialty-method guard beyond purchase/movement paths
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py`

## 2026-04-06 Prompt Surface / Spectator Result / Active Flip Follow-up

- What changed:
  - Moved prompt request-meta out of the footer and into the header chrome so the bottom area stays focused on feedback and the timer bar.
  - Promoted character, mark, and generic choices onto the stronger emphasis card surface so prompts read less like inspector lists.
  - Added a dedicated spectator result card so remote purchase/rent/fortune outcomes stay visible as a distinct payoff beat.
  - Added backend coverage that AI `active_flip` decisions also stay on the canonical decision lifecycle.
- Why:
  - the previous prompt footer still felt too much like a tool panel
  - remote-turn payoff still benefited from one more persistent result card
  - specialty decision coverage should keep expanding before later `DecisionPort` migration
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py`

## 2026-04-06 Weather / Specialty Prompt / Specific Reward Follow-up

- What changed:
  - Added stronger remote-turn weather payoff visibility:
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx` now includes weather in the spectator spotlight strip
    - spectator journey now sequences purchase / rent / fortune as separate beats instead of collapsing them into one generic economy/effect bucket
    - `apps/web/src/features/stage/TurnStagePanel.tsx` now keeps weather in the scene strip and uses weather effect as an outcome beat when no fortune outcome is present
  - Split remaining specialty prompts out of the generic inspector path:
    - `active_flip`
    - `burden_exchange`
    - `specific_trick_reward`
    now render on their own card sections in `apps/web/src/features/prompt/PromptOverlay.tsx`
  - Added backend specialty-decision guard coverage for AI `choose_specific_trick_reward` so another non-trivial path stays on the canonical:
    - `decision_requested`
    - `decision_resolved`
    lifecycle.
  - Tightened browser parity so remote-turn spotlight/result assertions now match the new scene-style payoff wording.
- Why:
  - weather and payoff visibility still needed to feel like a continuing scene instead of disconnected status cards
  - a few remaining specialty prompts were still falling back to the generic choice grid and reading too much like tooling UI
  - unified decision coverage needed one more specialty seam guarded before later provider/port migration
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`3 passed`)
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed (`13 passed, 13 skipped`)

## 2026-04-06 Remaining Prompt Specialization / Doctrine-Burden Coverage

- What changed:
  - Split four remaining prompt families out of the generic fallback grid in `apps/web/src/features/prompt/PromptOverlay.tsx`:
    - `runaway_step_choice`
    - `coin_placement`
    - `doctrine_relief`
    - `geo_bonus`
  - Each now renders on the emphasized live-choice surface with summary pills/context instead of the plain generic inspector list.
  - Added weather as the first visible spectator journey beat in `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote turns read more clearly as:
    - weather
    - character
    - current choice
    - movement
    - landing
    - payoff
  - Added backend canonical lifecycle coverage for AI:
    - `choose_doctrine_relief_target`
    - `choose_burden_exchange_on_supply`
- Why:
  - a few secondary human prompts were still falling back to the generic choice list and breaking the “game UI, not inspector UI” goal
  - spectator continuity still benefited from one stronger “weather starts the scene” beat
  - specialty decision drift needed to shrink further before later provider / `DecisionPort` migration
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` (`15 passed, 13 skipped`)

## 2026-04-06 Final Specialty Coverage / Payoff Animation Follow-up

- What changed:
  - Added backend canonical lifecycle coverage for the remaining specialty AI decisions:
    - `choose_runaway_slave_step`
    - `choose_coin_placement_tile`
    - `choose_geo_bonus`
  - Raised scene payoff one more step in `apps/web/src/styles.css` by adding a shared pulse animation to:
    - spectator payoff cards
    - spectator spotlight cards
    - turn-stage spotlight cards
    - turn-stage outcome cards
  - Result: purchase / rent / fortune outcomes now read more like active scene cards than flat status blocks.
- Why:
  - the unified decision boundary needed the remaining specialty seams covered before larger provider cleanup
  - human-play recovery still benefits from stronger event-card emphasis even before deeper animation/transition work
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` (`18 passed, 13 skipped`)
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-06 Human Pabal Dice Mode Recovery

- What changed:
  - Restored a missing human decision seam by implementing `choose_pabal_dice_mode(...)` in [GPT/viewer/human_policy.py](C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/viewer/human_policy.py).
  - Human seats now emit a real `pabal_dice_mode` prompt instead of silently falling through to the AI branch.
  - Added a dedicated `pabal_dice_mode` prompt surface in [apps/web/src/features/prompt/PromptOverlay.tsx](C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/apps/web/src/features/prompt/PromptOverlay.tsx).
  - Improved prompt choice parsing in [apps/web/src/domain/selectors/promptSelectors.ts](C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/apps/web/src/domain/selectors/promptSelectors.ts) so `value.description` is treated as a first-class fallback description source.
  - Added regression coverage for:
    - AI canonical lifecycle: `choose_pabal_dice_mode`
    - human prompt lifecycle: `choose_pabal_dice_mode`
    - prompt selector parsing of `value.description`
- Why:
  - this was a real human-play gap, not just a UI polish issue: the engine had a canonical request type, but the human bridge had no corresponding method
  - leaving it unfixed would have caused human seats to diverge from the unified decision contract exactly in a specialty ability branch
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` (`20 passed, 13 skipped`)

## 2026-04-06 Prompt HUD + Explicit Turn Event Labels

- What changed:
  - Reworked the prompt header in `apps/web/src/features/prompt/PromptOverlay.tsx` so the top meta now reads as compact HUD pills instead of a debug-style sentence.
  - Promoted explicit event naming in:
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx`
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
  - Purchase / rent / fortune reveal / fortune resolution / landing now use event-label wording where available, so the stage reads more like a live scene than a generic status board.
  - Updated `apps/web/src/styles.css` to style the new prompt-head HUD pills.
- Why:
  - the decision surface still carried a little too much inspector flavor
  - stage continuity became easier to read once payoff beats used explicit event names instead of generic field labels
- Validation:
  - pending local build/test pass after this patch

## 2026-04-06 Turn Handoff Scene Card

- What changed:
  - Added a dedicated end-of-turn handoff card to:
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx`
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
  - Added matching styles in `apps/web/src/styles.css` so turn-end handoff now pulses as a closing beat instead of being buried in generic summaries.
  - Extended `apps/web/e2e/human_play_runtime.spec.ts` so the remote-turn browser regression now explicitly checks:
    - spectator handoff visibility
    - turn-stage handoff visibility
    - turn-end summary text
- Why:
  - live human play still needed a stronger visual handoff between one actor finishing and the next public phase beginning
  - this is a scene-continuity improvement, not just a text polish change
- Validation:
  - pending local build/test pass after this patch

## 2026-04-06 Payoff Persistence After Turn End

- What changed:
  - Updated `apps/web/src/features/theater/CoreActionPanel.tsx` so the result card now follows the latest payoff event in the same turn, not just the latest event overall.
  - This keeps purchase / rent / fortune payoff visible even when `turn_end_snapshot` becomes the newest public event.
- Why:
  - the previous UI dropped the payoff card as soon as turn-end arrived, which weakened scene continuity and broke the browser regression added for handoff.
- Validation:
  - pending local build/test pass after this patch

## 2026-04-06 Prompt Surface Coverage Lock

- What changed:
  - Added `apps/web/src/features/prompt/promptSurfaceCatalog.ts` as the canonical list of prompt types that must render on specialized UI surfaces.
  - Updated `PromptOverlay.tsx` so the generic fallback path now explicitly means "unknown request type" instead of silently covering known request types.
  - Added `apps/web/src/features/prompt/promptSurfaceCatalog.spec.ts` to assert that every `KNOWN_PROMPT_TYPES` entry is covered by a specialized prompt surface.
- Why:
  - this is a direct regression guard against the old problem where a known human choice path could quietly fall back to a generic inspector-like list
- Validation:
  - `cmd /c npm run build`
  - `cmd /c npm run test -- --run src/features/prompt/promptSurfaceCatalog.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `cmd /c npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-06 Plan / Status Documentation Cleanup

- What changed:
  - Reclassified recently finished slices versus active carry-forward work in:
    - `docs/current/planning/PLAN_STATUS_INDEX.md`
    - `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
  - Explicitly marked the following as closed for the current slice:
    - prompt specialization lock
    - `pabal_dice_mode` human seam repair
    - turn-handoff payoff continuity
  - Explicitly carried forward the next three active slices:
    - fortune / purchase / rent scene payoff
    - specialized prompt simplification
    - provider-local drift reduction before typed `DecisionPort` cleanup
- Why:
  - the execution documents had become append-heavy, making it harder to tell what was already done versus what should actually drive the next coding slice
- Validation:
  - documentation-only update

## 2026-04-07 Payoff Scene Strip + Local Validation Pass

- What changed:
  - Bootstrapped local validation dependencies for this workspace:
    - created `.venv/` and installed server-side Python test dependencies
    - installed `apps/web` npm dependencies and Playwright Chromium
  - Verified the current web runtime path end-to-end, then upgraded the theater payoff UI:
    - added `apps/web/src/features/theater/coreActionScene.ts`
    - added `apps/web/src/features/theater/coreActionScene.spec.ts`
    - updated `apps/web/src/features/theater/CoreActionPanel.tsx`
    - updated locale resources in `apps/web/src/i18n/locales/ko.ts` and `apps/web/src/i18n/locales/en.ts`
    - updated theater styling in `apps/web/src/styles.css`
  - The core-action payoff area now renders same-turn payoff beats in sequence instead of compressing them into a single latest result card:
    - `tile_purchased`
    - `rent_paid`
    - `fortune_drawn`
    - `fortune_resolved`
    - `lap_reward_chosen`
  - Classification now uses canonical `eventCode` first before fallback keyword heuristics, reducing inspector-like ambiguity in payoff rendering.
- Why:
  - the active carry-forward slice in the execution plans calls for stronger fortune / purchase / rent scene payoff, and the old UI still flattened those beats into one summary card
  - local runtime validation was also needed to distinguish real implementation issues from machine/environment issues
- Validation:
  - `npm run test -- --run src/features/theater/coreActionScene.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - server-side note:
    - current local machine only exposes `python3` 3.9.6
    - `apps/server` currently imports `@dataclass(slots=True)` paths, so server import/test/runtime fail under 3.9 before app startup
    - `apps/server/tests/test_stream_api.py` also needs `httpx` in the local venv for FastAPI `TestClient`

## 2026-04-07 Python 3.11 Server Validation Recovery

- What changed:
  - Installed Homebrew `python@3.11` and created `.venv311/` for server validation.
  - Installed server dependencies plus `pytest` and `httpx` into `.venv311/`.
  - Re-ran the server validation batch with Python 3.11 and confirmed the FastAPI app binds successfully when sandbox port restrictions are lifted.
- Why:
  - the local machine defaulted to Python 3.9.6, which could not import the current server modules because `dataclass(slots=True)` requires Python 3.10+ in this codebase.
  - this was an environment blocker, not an app logic failure, so the execution path needed a valid interpreter before further server work.
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py` (`48 passed`)
  - `.venv311/bin/python -m uvicorn apps.server.src.app:app --host 127.0.0.1 --port 8001` (startup and bind confirmed)

## 2026-04-07 Prompt Head Locale Ownership Cleanup

- What changed:
  - Removed the remaining prompt-head meta pill string assembly from `apps/web/src/features/prompt/PromptOverlay.tsx`.
  - Added locale-owned `requestMetaPills` resources in:
    - `apps/web/src/i18n/locales/ko.ts`
    - `apps/web/src/i18n/locales/en.ts`
  - Extended `apps/web/src/i18n/i18n.spec.ts` to lock the Korean/English prompt-head pill output shape.
- Why:
  - prompt surface cleanup is still an active carry-forward slice, and the prompt head still had component-owned English literals even after the broader locale split work.
  - this keeps the prompt HUD aligned with the “locale resources outside components” rule and reduces inspector-style drift.
- Validation:
  - `npm run test -- --run src/i18n/i18n.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/features/theater/coreActionScene.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 PromptOverlay Specialized Surface Consolidation

- What changed:
  - Consolidated repeated emphasized-choice rendering in `apps/web/src/features/prompt/PromptOverlay.tsx` into shared local helpers:
    - `nonEmptyPills`
    - `choiceGridClass`
    - `EmphasisChoiceGrid`
  - Moved multiple specialized prompt surfaces onto the shared rendering path while preserving their existing test ids and context pills:
    - `purchase_tile`
    - `lap_reward`
    - `active_flip`
    - `burden_exchange`
    - `specific_trick_reward`
    - `runaway_step_choice`
    - `coin_placement`
    - `doctrine_relief`
    - `geo_bonus`
    - `pabal_dice_mode`
- Why:
  - this reduces repeated branch-local UI logic in the prompt layer and makes the remaining specialized prompts more consistent, which is directly aligned with the active prompt-surface simplification slice
  - it also makes follow-up prompt UX changes safer because layout behavior now flows through fewer duplicated blocks
- Validation:
  - `npm run test -- --run src/i18n/i18n.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Decision Gateway Method Spec Registry

- What changed:
  - Replaced the repeated method-name branching in `apps/server/src/services/decision_gateway.py` with a shared `DecisionMethodSpec` registry.
  - The registry now owns, per decision method:
    - canonical `request_type`
    - AI `choice_id` serialization
    - specialized `public_context` enrichment
  - Kept the existing `decision_request_type_for_method`, `serialize_ai_choice_id`, and `build_public_context` interfaces intact so runtime callers did not need a wider migration.
  - Added `prepare_decision_method(...)` and switched `apps/server/src/services/runtime_service.py` to consume the prepared contract directly instead of pulling request type, context, and serializer through three separate helper calls.
  - Extended `apps/server/tests/test_runtime_service.py` with focused contract checks for:
    - `choose_purchase_tile`
    - `choose_specific_trick_reward`
    - `choose_runaway_slave_step`
- Why:
  - provider-local drift was still concentrated in three separate helper branches inside the decision gateway, which made it easy for a specialty decision to update one surface but miss the others
  - a shared method-spec registry reduces that drift without prematurely forcing the larger `DecisionPort` migration
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py`

## 2026-04-07 Typed Provider Cleanup Follow-up

- What changed:
  - Split `_ServerDecisionPolicyBridge` dispatch responsibilities in `apps/server/src/services/runtime_service.py` across:
    - `_ServerHumanDecisionProvider`
    - `_ServerAiDecisionProvider`
  - Kept the bridge as the engine-facing adapter, but moved provider-specific execution behind explicit provider objects instead of concentrating human/AI logic in one branchy wrapper.
  - Added mixed-seat dispatch coverage in `apps/server/tests/test_runtime_service.py` to confirm:
    - human-seat prompt decisions do not fall through to the AI fallback provider
    - non-human seats still route through the AI provider even when a human provider is present
- Why:
  - this is the next smallest step in the plan's typed-provider cleanup track
  - it shrinks `_ServerDecisionPolicyBridge` toward provider selection and leaves provider-specific execution in narrower units ahead of a later `DecisionPort` migration
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Decision Provider Router Cleanup

- What changed:
  - Added `_ServerDecisionProviderRouter` in `apps/server/src/services/runtime_service.py` so the bridge no longer directly owns:
    - attribute target selection for engine policy access
    - seat-based provider selection for `choose_*` calls
  - Kept `__getattr__` only as the engine compatibility surface while moving its routing judgment into the dedicated router helper.
  - Added focused router tests in `apps/server/tests/test_runtime_service.py` covering:
    - human-policy attribute precedence
    - AI fallback attribute lookup
    - human-seat vs non-human-seat provider selection
- Why:
  - the engine still expects dynamic `choose_*` attributes, so `__getattr__` remains for now
  - moving the routing judgment out of the bridge keeps the remaining dynamic surface thinner and makes the eventual `DecisionPort` migration boundary easier to see
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Decision Invocation Prep Layer

- What changed:
  - Added `DecisionInvocation` plus `build_decision_invocation(...)` in `apps/server/src/services/decision_gateway.py`.
  - Updated runtime routing/provider execution so a normalized invocation object now carries:
    - `method_name`
    - raw `args` / `kwargs`
    - resolved `state`
    - resolved `player`
    - normalized `player_id`
  - Added `prepare_decision_method_from_invocation(...)` so provider execution no longer needs to re-thread raw method name and argument tuples through multiple helpers.
  - Extended `apps/server/tests/test_runtime_service.py` with focused invocation coverage.
- Why:
  - this is a small prep step toward a later engine-side `DecisionPort` migration
  - the engine still calls `choose_*`, but the server boundary now treats each decision as an explicit normalized invocation rather than a loose `(method_name, args, kwargs)` bundle
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Engine Decision Port Prep (Phase 1)

- What changed:
  - Added `DecisionRequest` and `DecisionPort` injection support to `GPT/engine.py`.
  - `GameEngine` now accepts an optional `decision_port=...` and otherwise wraps the legacy policy with the default port adapter.
  - Routed the PR-05 first-wave engine decision callsites through the injected port:
    - `choose_draft_card`
    - `choose_final_character`
    - `choose_movement`
    - `choose_trick_to_use`
    - `choose_purchase_tile`
  - Updated `GPT/effect_handlers.py` so landing purchase decisions also go through the engine decision port instead of calling policy methods directly.
  - Added `GPT/test_decision_port_contract.py` to verify those first-wave engine requests are emitted through the port.
- Why:
  - this creates the real engine-side injection seam promised by the plan without forcing the full `DecisionPort.request(...)` migration in one jump
  - the server/runtime cleanup from earlier is now matched by an engine boundary that can accept a future unified decision adapter
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`
  - note: `.venv311/bin/python -m pytest GPT/test_policy_hooks.py` still has an unrelated existing failure in `RuleScriptTests.test_default_rule_scripts_loaded` (`engine.rule_scripts.scripts == {}`), so it was not used as the gating pass for this slice

## 2026-04-07 Engine Decision Port Prep (Phase 2)

- What changed:
  - Routed the next engine decision slice through `GameEngine._request_decision(...)` as well:
    - `choose_mark_target`
    - `choose_lap_reward`
    - `choose_active_flip_card`
    - `choose_runaway_slave_step`
  - Extended `GPT/test_decision_port_contract.py` so the injected port now verifies both PR-05 and PR-06 style engine request emission.
- Why:
  - this keeps the engine migration moving in the plan's intended order without jumping straight to a fully rewritten `DecisionPort` API
  - with both the first and second decision waves routed through the port seam, the remaining work before later engine-side consolidation is much narrower
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`

## 2026-04-07 Engine Decision Port Prep (Phase 3)

- What changed:
  - Routed the remaining engine-side specialty decision callsites through `GameEngine._request_decision(...)`:
    - `choose_specific_trick_reward`
    - `choose_doctrine_relief_target`
    - `choose_burden_exchange_on_supply`
    - `choose_coin_placement_tile`
  - Expanded `GPT/test_decision_port_contract.py` so the injected port now verifies first-, second-, and third-wave engine decision requests.
  - `choose_geo_bonus` remains outside this wave because there is no direct engine/effect-handler callsite left to migrate in the current engine path.
- Why:
  - this completes the current engine-side callsite migration waves described before a later true `DecisionPort.request(...)` consolidation
  - at this point, the engine no longer directly calls the migrated `choose_*` methods from its core flow and instead relies on the injected request seam
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`

## 2026-04-07 Canonical Decision Request Alignment

- What changed:
  - Added `CanonicalDecisionRequest` plus `build_canonical_decision_request(...)` in `apps/server/src/services/decision_gateway.py`.
  - Updated the server AI provider path to consume canonical request metadata before publishing decision lifecycle events.
  - Expanded `GPT/engine.py`'s injected `DecisionRequest` so it now carries canonical request-shaped metadata:
    - `request_type`
    - `player_id`
    - `round_index`
    - `turn_index`
    - `public_context`
    - `fallback_policy`
  - Added coverage on both sides:
    - `GPT/test_decision_port_contract.py`
    - `apps/server/tests/test_runtime_service.py`
- Why:
  - server `DecisionInvocation` and engine `DecisionRequest` were structurally close but still named and shaped differently in ways that would complicate the next real adapter step
  - aligning the metadata shape now makes the later engine-to-server decision adapter much more mechanical
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py`
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Server Engine Decision-Port Adapter Hookup

- What changed:
  - Added `build_decision_invocation_from_request(...)` in `apps/server/src/services/decision_gateway.py` so server routing can consume engine-style decision request objects directly.
  - `_ServerDecisionPolicyBridge` now implements `request(request)` and routes the normalized request through the existing provider router.
  - `RuntimeService._run_engine_sync(...)` now passes `decision_port=policy` when the server bridge is mounted, so the engine's injected port seam is actually exercised by the runtime path.
  - Expanded `apps/server/tests/test_runtime_service.py` to assert:
    - `GameEngine` receives the bridge as `decision_port`
    - engine-style request objects are routed through the bridge's AI provider path
- Why:
  - the previous steps aligned shapes but had not yet connected the engine injection seam to the live server runtime
  - this closes that gap and turns the engine `DecisionPort` preparation into an actually used server adapter path
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Frontend Canonical Prompt Contract Cleanup

- What changed:
  - Removed the web selector fallback to legacy prompt `choices` and now parse only canonical `legal_choices` in `apps/web/src/domain/selectors/promptSelectors.ts`.
  - Updated prompt selector coverage in `apps/web/src/domain/selectors/promptSelectors.spec.ts` so active/unresolved prompt cases also use canonical prompt payloads.
  - Simplified `apps/web/src/features/prompt/PromptOverlay.tsx` to prioritize the current prompt contract keys:
    - `tile_index`
    - `tile_zone`
    - `tile_purchase_cost`
    - `player_cash`
    - `player_shards`
    - `player_hand_coins`
    - `owned_tile_indices`
    - `actor_name`
  - Reduced old prompt-surface fallback usage so the React layer now follows the same canonical request/public-context shape that the server bridge and engine seam were aligned around.
- Why:
  - frontend prompt parsing still tolerated older payload names that are no longer the canonical runtime contract
  - removing those legacy branches makes the prompt surface easier to reason about and keeps the client aligned with the current server/human-policy envelope
- Validation:
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts`
  - `npm run build`
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so turn-stage prompt focus uses canonical prompt data:
    - first `public_context.tile_index`
    - then `legal_choices[].value.tile_index`
  - Added `coin_placement` turn-stage coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts`.
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts`

## 2026-04-07 Open-Participant Decision Client Prep

- What changed:
  - Reframed runtime human/AI execution from provider-style branching toward decision-client adapters:
    - `_LocalHumanDecisionClient`
    - `_LocalAiDecisionClient`
    - `_ServerDecisionClientRouter`
    - `_ServerDecisionClientFactory`
  - The runtime router can now also resolve participant client type from session seat descriptors, not only from a bare `human_seats` list.
  - Added `RoutedDecisionCall` in `apps/server/src/services/decision_gateway.py` so both local clients consume the same normalized call object:
    - invocation
    - canonical request
    - choice serializer
  - Updated `_ServerDecisionPolicyBridge` so both `request(...)` and legacy `choose_*` wrappers route through the normalized decision-client seam.
  - Opened server-side DI one step further so client creation itself can be injected through a decision-client factory.
  - Extended `GPT/engine.py` with `decision_request_factory=...` injection so request construction is also open to adapters and not hard-wired to one server-local path.
  - Added coverage in:
    - `apps/server/tests/test_runtime_service.py`
    - `GPT/test_decision_port_contract.py`
- Why:
  - the next architectural target is not merely “AI and human use similar contracts”, but “AI can be treated like the same kind of multiplayer participant”
  - local AI still exists today, but it should already look like a client adapter at the server boundary so a later external AI client can mount on the same seam
  - opening request construction DI on the engine side keeps the engine boundary compatible with multiple participant adapters instead of only the current default builder
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py GPT/test_decision_port_contract.py`

## 2026-04-07 External AI Participant Descriptor Hookup

- What changed:
  - Extended `SeatConfig` with participant-level client metadata:
    - `participant_client`
    - `participant_config`
  - `SessionService` now validates and persists participant descriptors for seats:
    - human seats default to `human_http`
    - AI seats default to `local_ai`
    - AI seats can now explicitly declare `external_ai`
  - Session HTTP payloads now expose participant descriptors in create/public/start responses.
  - Runtime client selection now uses seat-level participant descriptors:
    - local AI seats route to the local AI decision client
    - `external_ai` seats route to an explicit external-AI client adapter
  - Added a default loopback external-AI transport seam:
    - `_ExternalAiDecisionClient`
    - `_LoopbackExternalAiTransport`
  - The default transport still resolves through the local gateway today, but it preserves:
    - explicit participant boundary
    - seat-specific config
    - transport-level upgrade seam for future real external workers/services
- Why:
  - the architecture goal is no longer just “AI and humans share similar decision events”; it is “AI can participate through the same kind of open multiplayer boundary”
  - seat descriptors are the smallest stable way to carry that participant intent from session creation through runtime routing
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_session_service.py apps/server/tests/test_runtime_service.py apps/server/tests/test_sessions_api.py`

## 2026-04-07 Remote-Turn Payoff, Prompt Chrome, and Participant Defaults Closure

- What changed:
  - Strengthened remote-turn payoff continuity on the React match surface:
    - `apps/web/src/features/theater/coreActionScene.ts` now builds richer payoff beats with a stable headline
    - `apps/web/src/features/theater/CoreActionPanel.tsx` renders same-turn payoff beats as numbered scene steps
    - `apps/web/src/features/stage/TurnStagePanel.tsx` adds scene-sequence annotations for purchase / rent / fortune phases
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx` now renders a payoff-beat strip instead of collapsing non-local resolution into a single card
  - Reduced prompt chrome drift in `apps/web/src/features/prompt/PromptOverlay.tsx`:
    - `none` / `no` style passive choices are now visually demoted into a secondary choice row
    - prompt-specific choice cards keep the same canonical request/public-context path but read as a more game-native action surface
  - Tightened locale ownership:
    - added scene-sequence and secondary-choice strings to `apps/web/src/i18n/locales/ko.ts`
    - added matching English coverage in `apps/web/src/i18n/locales/en.ts`
  - Closed more of the shared/open-participant contract follow-up:
    - `packages/runtime-contracts/ws/schemas/inbound.prompt.schema.json` now freezes canonical `legal_choices` as the primary prompt field
    - the prompt example fixture now follows that canonical field
    - `apps/server/src/services/parameter_service.py` resolves participant defaults, including external-AI transport config
    - `apps/server/src/services/session_service.py` merges resolved participant defaults into external-AI seat descriptors
    - `apps/server/src/services/runtime_service.py` now supports transport-shaped external AI routing:
      - loopback transport
      - http-shaped transport seam with injectable sender
      - explicit external decision envelope metadata
    - updated `tools/parameter_manifest_snapshot.json` for the new participant-default manifest shape
- Why:
  - the match needed to read more like a multiplayer scene and less like a log feed during non-local turns
  - canonical prompt/data ownership was already in place, so the next leverage point was better scene composition and less inspector-like skip/passive presentation
  - external AI had a seat-level seam already, but the runtime still needed transport-aware structure and parameter-driven defaults so the open-participant model would not stay ad-hoc
- Validation:
  - `npm run test -- --run src/features/theater/coreActionScene.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_service.py apps/server/tests/test_session_service.py apps/server/tests/test_sessions_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_runtime_contract_examples.py`
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_manifest_snapshot.py apps/server/tests/test_parameter_propagation.py apps/server/tests/test_prompt_service.py apps/server/tests/test_stream_api.py GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`

## 2026-04-07 External AI HTTP Transport Realization

- What changed:
  - Extended `apps/server/src/services/decision_gateway.py` so canonical decision calls now also carry:
    - `legal_choices`
    - per-method external choice parsers
  - Added method-specific legal-choice builders and response parsers for the current open-participant decision surface, so an external worker can answer with canonical `choice_id` values while the engine still receives native decision results.
  - Upgraded `apps/server/src/services/runtime_service.py` external AI transport from a seam-only placeholder into a real transport path:
    - stdlib HTTP POST sender
    - retry / backoff support
    - seat-level timeout config
    - `fallback_mode` handling
    - transport-aware external decision envelope
  - Added a frozen external AI contract artifact set under:
    - `packages/runtime-contracts/external-ai/README.md`
    - `packages/runtime-contracts/external-ai/schemas/request.schema.json`
    - `packages/runtime-contracts/external-ai/schemas/response.schema.json`
    - `packages/runtime-contracts/external-ai/examples/request.purchase_tile.json`
    - `packages/runtime-contracts/external-ai/examples/response.purchase_tile_yes.json`
  - Expanded participant default parameterization:
    - `retry_count`
    - `backoff_ms`
    - `fallback_mode`
  - Refreshed `tools/parameter_manifest_snapshot.json` because participant-default manifest shape changed again.
- Why:
  - the runtime had already opened an HTTP-shaped seam, but external AI still could not truly participate as a client because the server lacked:
    - canonical legal choices for workers
    - response parsing back into engine-native values
    - frozen request/response artifacts
    - operational retry/timeout/fallback policy
  - this closes the structural gap between “AI can eventually be external” and “AI can now be treated like a real external participant contract”
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_parameter_service.py apps/server/tests/test_session_service.py apps/server/tests/test_sessions_api.py apps/server/tests/test_runtime_contract_examples.py`
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_manifest_snapshot.py apps/server/tests/test_parameter_propagation.py apps/server/tests/test_prompt_service.py apps/server/tests/test_stream_api.py GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`
  - `.venv311/bin/python -m py_compile apps/server/src/services/decision_gateway.py apps/server/src/services/runtime_service.py apps/server/src/services/parameter_service.py apps/server/src/services/session_service.py`

## 2026-04-07 External AI Worker Mount

- What changed:
  - Added a reference worker service at `apps/server/src/services/external_ai_worker_service.py`
    - it consumes canonical external-AI request envelopes
    - it chooses one `choice_id` from `legal_choices`
    - it returns the matched `choice_payload` for easier inspection/debugging
    - it stays connected to the existing policy vocabulary through `PolicyFactory`
  - Added a runnable FastAPI worker app at `apps/server/src/external_ai_app.py`
    - `GET /health`
    - `POST /decide`
  - Added local developer tooling and documentation:
    - `tools/run_external_ai_worker.py`
    - `docs/current/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md`
  - Added worker-level and real transport-level regression coverage:
    - `apps/server/tests/test_external_ai_worker_api.py`
    - localhost HTTP round-trip coverage in `apps/server/tests/test_runtime_service.py`
  - Refreshed the frozen response example because worker responses now include `choice_payload` plus policy metadata.
- Why:
  - the previous slice proved the HTTP seam and frozen artifacts, but a real multiplayer-like participant model still needed an actual worker process/service to answer over HTTP
  - this closes that gap for local/runtime integration and makes `external_ai` a live participant path instead of a future-only placeholder
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_runtime_contract_examples.py`

## 2026-04-07 Selector / Effect Visibility / Worker Hardening Pass

- What changed:
  - Web selector and prompt cleanup:
    - `apps/web/src/domain/selectors/promptSelectors.ts` now marks canonical secondary choices explicitly
    - `apps/web/src/domain/selectors/streamSelectors.ts` moved more detail composition into locale resources for:
      - decision-requested detail
      - decision-resolved detail
      - weather detail
      - marker-flip detail
    - `apps/web/src/features/prompt/PromptOverlay.tsx` now uses compact prompt head metadata for specialized prompt surfaces
  - Rule-parity visual closure:
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx`
    - these now preserve and render:
      - weather summary
      - lap reward summary
      - mark summary
      - flip summary
  - External AI hardening:
    - `apps/server/src/services/parameter_service.py` now resolves:
      - `contract_version`
      - `healthcheck_path`
      - `healthcheck_ttl_ms`
      - `required_capabilities`
    - `apps/server/src/services/runtime_service.py` now preflights worker health/capability compatibility for HTTP participants
    - `apps/server/src/services/external_ai_worker_service.py` now publishes:
      - contract version
      - capability tags
      - supported request types
  - Frozen contract expansion:
    - added external-AI examples for:
      - movement
      - lap reward
  - Browser/runtime coverage:
    - added a Playwright remote-turn effect continuity case
- Why:
  - the previous slice mounted the worker, but the system still needed:
    - stronger worker compatibility checks
    - broader frozen artifacts
    - more complete remote-turn effect visibility
    - less selector-owned phrase assembly
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run test -- --run src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts src/features/theater/coreActionScene.spec.ts src/features/board/boardProjection.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `.venv311/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_parameter_service.py apps/server/tests/test_session_service.py apps/server/tests/test_sessions_api.py`
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_manifest_snapshot.py apps/server/tests/test_parameter_propagation.py apps/server/tests/test_prompt_service.py apps/server/tests/test_stream_api.py GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`
  - `.venv311/bin/python -m py_compile apps/server/src/services/runtime_service.py apps/server/src/services/parameter_service.py apps/server/src/services/external_ai_worker_service.py apps/server/src/external_ai_app.py`

## 2026-04-07 Default Text Shim + Locale Detail Closure

- What changed:
  - Web default-text ownership moved one step further away from the old compatibility bridge:
    - added `apps/web/src/i18n/defaultText.spec.ts` as the primary default-text regression surface
    - reduced `apps/web/src/domain/text/uiText.spec.ts` to shim-level compatibility checks only
  - selector-owned phrasing shrank again:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now routes:
      - decision-ack detail
      - generic error detail
      through locale helpers instead of selector-local string assembly
    - locale catalogs now own those formats in:
      - `apps/web/src/i18n/locales/ko.ts`
      - `apps/web/src/i18n/locales/en.ts`
  - regression coverage now explicitly fixes those seams:
    - `apps/web/src/domain/selectors/streamSelectors.spec.ts`
    - `apps/web/src/i18n/defaultText.spec.ts`
- Why:
  - the previous slices already removed most direct `uiText` callers, so the next useful cleanup was to make `uiText` truly a compatibility shim and keep selector detail formatting locale-owned
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/i18n/defaultText.spec.ts src/i18n/i18n.spec.ts`
  - `cd apps/web && npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-07 External Worker Status Surfacing + Generic Prompt Collapse

- What changed:
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now carries external worker diagnostics into timeout-fallback phrasing:
      - `external_ai_worker_id`
      - `external_ai_failure_code`
      - `external_ai_fallback_mode`
    - locale catalogs now own the richer timeout-fallback format in:
      - `apps/web/src/i18n/locales/ko.ts`
      - `apps/web/src/i18n/locales/en.ts`
    - `apps/web/src/features/prompt/PromptOverlay.tsx` now collapses secondary generic choices under a compact disclosure instead of always rendering them at full weight
  - Server:
    - `apps/server/src/services/runtime_service.py` now writes `external_ai_resolution_status` into canonical public context so downstream UI/stream consumers can distinguish:
      - worker success
      - worker failure
      - local fallback resolution
    - `apps/server/src/services/external_ai_worker_service.py` now handles additional contextual preferences for:
      - `specific_trick_reward`
      - `doctrine_relief`
  - Coverage:
    - worker/runtime tests now assert surfaced resolution status
    - browser E2E now checks worker-id visibility in timeout fallback continuity
- Why:
  - the multiplayer-like runtime structure was already in place, but fallback behavior still read too much like an opaque internal error instead of a visible participant handoff
  - generic prompt surfaces also still gave too much visual weight to passive/secondary choices
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/i18n/defaultText.spec.ts src/i18n/i18n.spec.ts`
  - `cd apps/web && npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `.venv311/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_service.py`

## 2026-04-07 Selector / Prompt Simplification Follow-up

- What changed:
  - `apps/web/src/domain/selectors/promptSelectors.ts` now centralizes canonical choice parsing through smaller helpers instead of redoing title/description/secondary inference inline
  - `apps/web/src/features/prompt/PromptOverlay.tsx` now reuses a shared `ChoiceSection` / `SummaryPills` wrapper for repeated specialized prompt layouts
  - generic fallback choices now continue to use the lighter collapsed-secondary treatment while repeated section chrome is reduced
- Why:
  - the next PLAN slice after locale-ownership cleanup was to finish trimming selector-owned parsing noise and remove the remaining repetitive prompt-section scaffolding
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/i18n/defaultText.spec.ts src/i18n/i18n.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-07 Worker Status Cards + Request-Type Hardening

- What changed:
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now keeps explicit external worker fields in the turn-stage model:
      - `external_ai_worker_id`
      - `external_ai_failure_code`
      - `external_ai_fallback_mode`
      - `external_ai_resolution_status`
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx`
    now render dedicated participant-status cards when an external AI seat is visible
    - browser coverage now includes a consecutive-turn mixed-seat case where:
      - one turn resolves by worker
      - the next turn falls back locally
  - Server:
    - `apps/server/src/services/runtime_service.py` now validates `supported_request_types` from worker health/response payloads when present
    - runtime public context now also records `external_ai_attempt_count`
    - `apps/server/src/services/external_ai_worker_service.py` now prefers usable non-secondary trick/character choices and supports richer contextual preferences
- Why:
  - the previous slices exposed worker diagnostics in raw prompt/event detail, but the UI still needed a first-class multiplayer-style participant status surface
  - operationally, workers also needed request-type compatibility checks in addition to contract/capability checks
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/text/uiText.spec.ts src/i18n/defaultText.spec.ts src/i18n/i18n.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `.venv311/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_service.py`

## 2026-04-07 Worker Detail Localization + Health Cache Hardening

- What changed:
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now preserves `external_ai_attempt_count` inside the turn-stage model
    - worker status cards and journey rows now rely on locale helpers for worker detail phrasing instead of inline `worker/failure/fallback` string assembly
    - mixed-seat E2E now asserts retry-attempt visibility alongside worker-id and fallback status
  - Server:
    - `apps/server/src/services/runtime_service.py` now keys external-worker health-cache entries by worker requirements as well as endpoint/path
    - this prevents stale health metadata reuse across different expected worker ids / required capabilities
- Why:
  - the previous slice made worker state visible, but some of that detail was still component-owned wording
  - operationally, cache reuse needed to reflect seat-specific worker requirements before the external participant seam could be treated as production-shaped
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_external_ai_worker_api.py`

## 2026-04-07 Prompt Section Reuse + Required Request-Type Hardening

- What changed:
  - Web:
    - `apps/web/src/features/prompt/PromptOverlay.tsx` now routes repeated specialized decision sections through a shared `DecisionChoiceSection`
    - worker participant cards on stage/spectator now get status-specific tone classes so success vs fallback reads more like a live multiplayer handoff
  - Server:
    - `apps/server/src/services/parameter_service.py` now accepts normalized `required_request_types` under external-AI participant defaults
    - `apps/server/src/services/runtime_service.py` validates those request types during worker health checks and includes them in health-cache scoping
    - `apps/server/src/services/external_ai_worker_service.py` now prefers explicit `preferred_choice_id` and `priority_score` hints when present
    - `tools/parameter_manifest_snapshot.json` was refreshed after the parameter shape change
- Why:
  - the prompt surface still had too much repeated section scaffolding even after specialization
  - the external worker seam already checked capability/version/identity, and the next useful hardening step was to make request-type support declarative and parameter-driven
- Validation:
  - `cd apps/web && npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_service.py apps/server/tests/test_runtime_service.py apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_parameter_propagation.py apps/server/tests/test_parameter_manifest_snapshot.py`

## 2026-04-07 Worker Readiness Gate + Attempt-Limit Hardening

- What changed:
  - Server:
    - `apps/server/src/services/parameter_service.py` now accepts external-AI participant defaults for:
      - `require_ready`
      - `max_attempt_count`
    - `apps/server/src/services/runtime_service.py` now:
      - rejects `/health` payloads that are reachable but not ready when `require_ready=true`
      - caps actual worker send attempts with `max_attempt_count`
      - records `external_ai_attempt_limit` alongside `external_ai_attempt_count`
      - scopes health-cache reuse by readiness requirements too
    - `apps/server/src/services/external_ai_worker_service.py` now advertises `ready: true` in both health metadata and decision responses
    - `apps/server/src/external_ai_app.py` now exposes that `ready` field through the worker API contract
    - `tools/parameter_manifest_snapshot.json` was refreshed after the participant parameter-shape change
  - Contracts / docs:
    - `packages/runtime-contracts/external-ai/schemas/response.schema.json` now includes `ready`
    - `packages/runtime-contracts/external-ai/examples/response.purchase_tile_yes.json` now includes `ready: true`
    - `packages/runtime-contracts/external-ai/README.md` and `docs/current/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md` now document:
      - readiness gating
      - attempt caps
      - surfaced attempt-limit diagnostics
  - Browser regression:
    - `apps/web/e2e/human_play_runtime.spec.ts` now covers a mixed-seat turn where:
      - weather continuity remains visible
      - the external worker reports not-ready
      - runtime falls back locally
      - payoff continuity still survives the handoff
- Why:
  - the external participant path was already auth/identity/capability-aware, but a production-shaped multiplayer seam also needs to distinguish:
    - worker is unreachable
    - worker is reachable but not ready
    - retry settings are higher than the seat should actually allow
  - the useful next step was to make those rollout constraints parameter-driven and visible in both runtime diagnostics and browser continuity coverage
- Validation:
  - `.venv311/bin/python tools/parameter_manifest_gate.py --write`
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_service.py apps/server/tests/test_runtime_service.py apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_parameter_propagation.py apps/server/tests/test_parameter_manifest_snapshot.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Worker Readiness Surfacing + Locale-Owned Stage Detail

- What changed:
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now preserves:
      - `external_ai_attempt_limit`
      - `external_ai_ready_state`
    - timeout-fallback timeline/stage detail now renders bounded attempt phrasing through locale helpers instead of selector-owned string assembly
    - `apps/web/src/features/stage/TurnStagePanel.tsx` and `apps/web/src/features/stage/SpectatorTurnPanel.tsx` now show:
      - readiness state
      - `attempt/limit`
      inside worker status cards
    - turn-stage weather spotlight formatting now also routes through locale helpers
  - Server:
    - `apps/server/src/services/runtime_service.py` now records readiness state into canonical `public_context`
    - `require_ready=true` now rejects both:
      - health payloads that are reachable but not ready
      - decision responses that explicitly report `ready=false`
    - runtime coverage now locks those cases, including response-level not-ready fallback
  - Browser regression:
    - `apps/web/e2e/human_play_runtime.spec.ts` now checks that a worker-not-ready fallback still keeps:
      - weather continuity
      - readiness visibility
      - bounded attempt visibility
      - payoff continuity
- Why:
  - after the previous worker hardening slice, the remaining gap was that readiness/attempt constraints were operationally real but not consistently visible at the same canonical UI surface
  - the next useful closure step was to make stage/spectator read the same bounded readiness seam that runtime already enforces
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_parameter_service.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Stronger Worker Metadata Gating + Spectator Summary Cleanup

- What changed:
  - Web:
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx` now routes spectator inline summaries through locale helpers instead of component-local join logic
    - spectator payoff sequence headers now use the actual payoff tone/title rather than always reading as a generic effect strip
    - `apps/web/src/domain/selectors/streamSelectors.ts` now routes:
      - dice total summaries
      - lap-reward bundle summaries
      through locale helpers instead of selector-local string assembly
  - Server:
    - `apps/server/src/services/parameter_service.py` now accepts stronger-worker compatibility requirements:
      - `required_policy_mode`
      - `required_decision_style`
    - `apps/server/src/services/runtime_service.py` now validates those fields against worker metadata as part of health/compatibility checks
    - mismatch cases now resolve through the same fallback diagnostics seam as other worker incompatibilities
  - Docs / plan:
    - external worker contract docs and runbook now describe stronger-worker metadata requirements
    - execution plans now record that stronger worker replacements can be gated on `policy_mode` / `decision_style`
- Why:
  - the remaining locale-ownership drift had narrowed to small but repeated join logic around spectator summaries and selector-side composed strings
  - in parallel, the next practical stronger-worker seam was not “new transport” work but “replacement compatibility” work, so requiring explicit worker policy metadata was the cleanest next guardrail
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_service.py apps/server/tests/test_runtime_service.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Turn-Scene Polish + Transport Compatibility Guard

- What changed:
  - Web:
    - `apps/web/src/features/stage/TurnStagePanel.tsx` now gives the scene strip and result strip dedicated headings instead of reusing generic beat/effect headers
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx` now keeps worker summary cards aligned with full attempt-limit / ready-state detail and payoff headers aligned to the actual payoff tone
    - browser coverage now includes a longer mixed-seat chain where:
      - one external worker turn resolves successfully
      - fortune resolves
      - the next external worker turn falls back locally
      - weather/payoff/handoff continuity stays readable
  - Server:
    - `apps/server/src/services/runtime_service.py` now validates worker-advertised `supported_transports` when the worker exposes that metadata
    - transport mismatch now surfaces as `external_ai_missing_transport_support` and follows the canonical local-fallback diagnostics path
- Why:
  - after the previous slices, the remaining visual drift was mostly about semantic framing rather than missing data
  - on the worker side, the next practical stronger-service guardrail was to ensure the runtime only accepts workers that explicitly advertise compatibility with the selected transport
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_service.py apps/server/tests/test_runtime_service.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Worker Metadata Surfaced Through Localized Stage Flows

- What changed:
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now keeps worker `policy_mode` / `decision_style` alongside ready-state and attempt data inside the current-turn model
    - stage/spectator worker summaries now compose those details through locale-owned helpers instead of selector-local string fragments
    - player labels inside the stream selector path now prefer locale-owned formatting helpers over direct `P${id}` joins
    - the longer mixed-seat browser scenario now asserts worker mode visibility remains readable through a worker-success -> fallback chain
  - Server:
    - `apps/server/src/services/runtime_service.py` now persists worker-advertised `policy_mode` / `decision_style` into canonical decision `public_context`
    - `apps/server/src/services/external_ai_worker_service.py` now echoes `decision_style` and `supported_transports` on `/decide` responses, matching `/health`
- Why:
  - the remaining selector locale-ownership drift had narrowed to small participant/worker formatting joins
  - the next stronger-worker replacement step needed the runtime to preserve more provenance than just worker id and failure code
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_service.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Policy-Class Gating + Repeated Fallback Coverage

- What changed:
  - Server:
    - `apps/server/src/services/parameter_service.py` now accepts `required_policy_class` for external AI participant defaults
    - `apps/server/src/services/runtime_service.py` now validates worker-advertised `policy_class` alongside:
      - `policy_mode`
      - `decision_style`
      - `supported_transports`
    - the runtime now also surfaces `external_ai_policy_class` into canonical decision `public_context`
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now keeps `external_ai_policy_class` in the current-turn model
    - stage/spectator worker summaries now render class provenance through locale-owned worker summary helpers
    - browser coverage now includes a repeated-fallback mixed-seat chain with weather + payoff continuity preserved across two consecutive fallback turns
- Why:
  - stronger worker replacement readiness needed one more explicit compatibility guard beyond worker id, mode, and decision style
  - the remaining playtest risk was no longer “missing data” but “does continuity stay readable when fallbacks repeat”
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_service.py apps/server/tests/test_runtime_service.py apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_parameter_propagation.py apps/server/tests/test_parameter_manifest_snapshot.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Worker Adapter Seam + Localized Spectator Summary Cleanup

- What changed:
  - Server:
    - `apps/server/src/services/external_ai_worker_service.py` now mounts the reference worker through an explicit adapter seam instead of hard-wiring the heuristic chooser directly into the service
    - the default adapter id is now `reference_heuristic_v1`
    - `apps/server/src/services/parameter_service.py` now accepts `required_worker_adapter` for external-AI participant defaults
    - `apps/server/src/services/runtime_service.py` now validates worker-advertised `worker_adapter` during compatibility checks and persists `external_ai_worker_adapter` into canonical `public_context`
    - `apps/server/src/external_ai_app.py` now exposes `worker_adapter` on both `/health` and `/decide`
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` now preserves `externalAiWorkerAdapter` in current-turn models
    - worker status cards in stage/spectator surfaces now render adapter provenance through locale-owned helpers, alongside:
      - readiness
      - attempt bounds
      - policy mode
      - policy class
      - decision style
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx` now routes more inline summary joins through locale helpers instead of component-local string assembly
    - longer mixed-seat browser coverage now asserts adapter provenance stays visible through repeated fallback chains
  - Docs / plan:
    - plan/runbook/contract docs now describe the explicit worker-adapter seam and `required_worker_adapter`
- Why:
  - the remaining stronger-worker follow-up was no longer about mounting a worker at all, but about making that worker explicitly replaceable without changing the frozen HTTP contract
  - in parallel, the remaining locale-ownership drift had narrowed to small spectator summary joins and worker-detail fragments
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_parameter_service.py apps/server/tests/test_runtime_service.py apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_parameter_propagation.py apps/server/tests/test_parameter_manifest_snapshot.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Stronger Scored Adapter + Final Mixed-Seat Coverage

- What changed:
  - Server:
    - `apps/server/src/services/external_ai_worker_service.py` now exposes a second built-in adapter:
      - `priority_score_v1`
    - that stronger adapter keeps the frozen HTTP contract but advertises different worker provenance:
      - `worker_adapter`
      - `policy_class`
      - `decision_style`
    - `tools/run_external_ai_worker.py` now accepts `--worker-adapter` so local runs can switch adapters without code changes
    - runtime/API coverage now locks the stronger adapter path in addition to the default reference heuristic path
  - Web:
    - `apps/web/src/domain/selectors/streamSelectors.ts` moved remaining weather-effect list joins behind locale helpers
    - selector/stage/browser coverage now proves that stronger worker provenance stays visible through:
      - worker-resolved turns
      - local-fallback turns
      - longer mixed-seat chains
  - Docs / plan:
    - runbook / contract docs now describe `priority_score_v1` as the built-in stronger adapter path
- Why:
  - the next useful closure step after opening the adapter seam was to prove that the seam supports more than one real adapter shape
  - that makes the eventual swap from built-in reference worker to stronger external service much more mechanical
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_parameter_service.py`
  - `cd apps/web && npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/i18n/i18n.spec.ts src/domain/text/uiText.spec.ts`
  - `cd apps/web && npm run build`
  - `cd apps/web && npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Worker Profile Presets + Localhost Priority Worker Round-Trip

- What changed:
  - Server:
    - `apps/server/src/services/parameter_service.py` now accepts `worker_profile` for external-AI participant defaults
    - `worker_profile=priority_scored` now expands to the stronger-worker compatibility bundle automatically:
      - `required_worker_adapter=priority_score_v1`
      - `required_policy_class=PriorityScoredPolicy`
      - `required_decision_style=priority_scored_contract`
      - scored-choice capability requirements
    - runtime localhost integration coverage now includes a real HTTP round-trip against a priority-scored worker adapter
  - Docs:
    - the external worker runbook and production-shaped session payload now show `worker_profile=priority_scored` as the higher-quality worker path
- Why:
  - after proving the stronger adapter seam at the code level, the next practical step was to make that seam easy to select from session/runtime config
  - that reduces manual config drift when swapping from the reference worker to a stronger worker/service
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_external_ai_worker_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_parameter_service.py apps/server/tests/test_parameter_propagation.py`

## 2026-04-07 Session/API Worker Profiles + Real Playtest Checklist

- What changed:
  - Session/API:
    - external-AI seats now have regression coverage showing that `worker_profile=priority_scored` survives through:
      - session creation
      - seat normalization
      - API response payloads
  - Docs:
    - `docs/current/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md` now captures the recommended local playtest path for:
      - human seats
      - local AI seats
      - external AI seats
      - stronger worker profile runs
- Why:
  - after closing the stronger-worker seam and localhost transport checks, the next practical value was to make real playtests reproducible from the same parameter/runtime contract
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_session_service.py apps/server/tests/test_sessions_api.py`

## 2026-04-07 Repo-Side Closure Reclassification

- What changed:
  - Reclassified the remaining internal plan queue from "active implementation" to:
    - operational stronger-worker hookup
    - evidence-only visual drift cleanup
    - evidence-only locale residue cleanup
  - Updated execution docs to reflect that:
    - stronger worker presets now reach real worker startup/runtime metadata
    - mixed-seat local playtests are the next meaningful gate
    - selector/prompt/stage carry-forward inside the repo is closed enough unless new evidence reopens it
- Why:
  - the remaining value is no longer broad code churn inside the repo
  - the next practical step is attaching a real stronger endpoint and collecting playtest evidence
- Validation:
  - doc/status refresh only

## 2026-04-07 Draft Context + Trick Tile Target + Lap Reward Contract Recovery

- What changed:
  - Engine / server:
    - restored player-facing trick tile selection for targeted trick cards instead of auto-picking tiles:
      - `재뿌리기`
      - `긴장감 조성`
    - added canonical `trick_tile_target` decision handling across:
      - engine request typing
      - human policy prompt publishing
      - server decision gateway context / choice parsing
    - expanded draft and final-character decision context so the UI can distinguish:
      - draft phase
      - offered candidate count
      - offered candidate names / abilities
      - final confirmation state
    - restored lap reward to the real point-budget bundle contract instead of a collapsed 3-choice variant
      - mixed `cash / shards / coins` bundles are now published to humans
      - lap reward public context now includes current actor resource state
  - Web:
    - `PromptOverlay` now renders:
      - draft phase-aware candidate prompts
      - trick tile target prompts
      - mixed lap reward bundles with budget/pool context
    - `TurnStagePanel` now shows a current-actor status card with:
      - cash
      - shards
      - hand points
      - placed points
      - total score
      - owned tile count
    - selector/state flow now preserves actor resource context from prompt / decision events into the turn-stage model
    - locale resources were updated so the new decision surfaces remain locale-owned
- Why:
  - the reported UX failures were not isolated copy issues; they came from human decision contracts being flattened below the actual game rules
  - restoring the real decision shapes was necessary to make:
    - draft flow legible
    - targeted trick cards actually playable
    - lap rewards explainable and rule-correct
  - adding actor status to the turn stage closes the missing “current situation” gap during reward and decision beats
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_human_policy_prompt_payloads.py GPT/test_event_effects.py apps/server/tests/test_runtime_service.py`
  - `cd apps/web && npm run test -- --run src/domain/labels/promptTypeCatalog.spec.ts src/features/prompt/promptSurfaceCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-07 Match Topline Simplification + Shared Movement Tempo

- What changed:
  - Web:
    - simplified the board overlay top line into:
      - compact weather card on the left
      - P1-P4 status strip on the right
    - removed the extra right-side detail drawer from the main match view
    - removed the duplicate scene/preparing block above the decision area so waiting text now lives in the main decision surface
  - Runtime:
    - `dice_roll` and `player_move` now linger for both human and AI turns instead of only spectator/AI pacing
    - this makes:
      - dice result
      - final movement value
      - actual movement
      visible as separate beats
- Why:
  - the previous layout wasted space with duplicated turn narration and a leftover side drawer
  - dice and movement still felt like instant jumps, especially on human turns, because only non-human turns were delayed
- Validation:
  - `cd apps/web && npm run build`

## 2026-04-09 Active Priority Slot Owner Recovery

- What changed:
  - Web:
    - restored an explicit priority-slot map for the active character strip instead of inferring slot ownership from the currently visible face name
    - fixed the strip owner resolution so a flipped face like `객주 -> 중매꾼` still stays attached to the player who owns card `#7`
    - added a focused unit test for front/back card pairs sharing one priority slot
- Why:
  - the in-progress active-strip patch had started reading `active_by_card`, but it still matched owners by active face text
  - that breaks as soon as `marker_flip` changes the face name, because slot ownership is tied to the original card number / priority, not to the temporary visible face label
  - this keeps the strip truthful during live play and aligns with the current P0/P1 recovery plan
- Validation:
  - `cd apps/web && npm run test -- src/domain/characters/prioritySlots.spec.ts src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`
  - note: full `cd apps/web && npm test` still reports the pre-existing `src/domain/store/gameStreamReducer.spec.ts` 50-message cap failure

## 2026-04-09 Mark Target Public Active-Face Recovery

- What changed:
  - Engine / policy:
    - added a shared ordered public mark-target helper based on future acting slots and `active_by_card`
    - mark-target coercion now validates against public active faces instead of hidden `current_character` assignments
  - Human / server decision contracts:
    - mark-target prompts and canonical legal choices now publish public active-face guesses like `#7 중매꾼`
    - canonical `choice_id` now matches the guessed character string instead of leaking player-id-shaped targets
    - draft/final canonical card-choice titles and parsing now follow the currently active face name for each card slot
  - Web:
    - `final_character_choice` compatibility prompts now hide stale actor character text just like `final_character`
- Why:
  - the live-play recovery plan requires mark prompts to behave like deduction over active priority cards, not over player avatars
  - the old contract mixed hidden player assignments into prompt choices and serialized mark choices against a shape that did not match AI return values
  - tightening the public guess path closes another P0 logic gap without reopening broader architecture work
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_rule_fixes.py -k 'mark_target or hunt_season or assassin_clears'`
  - `.venv311/bin/python -m pytest GPT/test_human_play.py -k 'final_character_returns_name or mark_target_uses_public_active_faces'`
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'mark_target_context_uses_public_active_faces_for_future_slots or ai_bridge_keeps_mark_target_on_canonical_decision_flow'`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`
  - note: broader Python/web suites still contain unrelated pre-existing collection/failure noise outside this slice

## 2026-04-09 Matchmaker Follow-up Purchase Anchoring

- What changed:
  - Server / human prompt context:
    - `purchase_tile` prompts for `matchmaker_adjacent` and `adjacent_extra` now publish `landing_tile_index` separately from the selected `tile_index`
    - adjacent candidate lists are now derived from the actual landing tile, so the prompt only advertises legal follow-up purchase targets in the same block
  - Web:
    - purchase prompt summaries now keep `현재 위치` pinned to the landing tile instead of jumping to the follow-up target tile
    - board focus ordering now prefers `landing tile -> selected target -> other legal targets`, which keeps the pawn location and follow-up purchase context readable during chained buy decisions
- Why:
  - the live-play recovery plan called out matchmaker / arrival / purchase ordering and “money changed before resolution” confusion
  - follow-up purchase prompts were overloading `tile_index` for both “where I landed” and “what I am buying next”, which made selector focus and prompt copy drift away from the real board state
  - splitting those meanings closes a concrete P0 clarity bug without changing the purchase rules themselves
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'purchase_context_exposes_tile_metadata_and_adjacent_candidates'`
  - `.venv311/bin/python -m pytest GPT/test_human_play.py -k 'matchmaker_purchase_context_keeps_landing_tile_and_legal_targets'`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-09 Trick Card Identity Safety

- What changed:
  - Server runtime context:
    - `trick_to_use` and `hidden_trick_card` prompts now publish the same `full_hand`, `hidden_trick_deck_index`, and per-card `deck_index` / hidden / usable flags that the direct human-policy prompt already used
    - `specific_trick_reward` context now exposes `reward_cards` with stable `deck_index` entries, and canonical choice titles now include the serial suffix like `보상 카드 #102`
  - Human prompt contract:
    - specific reward prompts now carry both `deck_index` and description payloads per choice, plus `reward_cards` in public context
  - Web:
    - hand-choice fallback rendering now preserves `is_hidden` from canonical choice payloads instead of flattening every card into a public visible card
    - specific reward cards now show `#deck_index` so duplicate-name rewards stay distinguishable in the prompt surface
- Why:
  - the live-play recovery plan requires every trick-card decision path to resolve against stable instance identity, not against duplicated names
  - runtime-served prompts had weaker trick-hand context than the direct human-policy path, and the web fallback renderer dropped hidden-card identity even when the canonical choice payload still had it
  - tightening both the prompt contract and the web render path closes the “same name card” ambiguity without changing trick rules
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'trick_hand_context_exposes_stable_deck_indexes_for_use_and_hidden_selection or specific_trick_reward_context_and_choices_keep_deck_index_identity or ai_bridge_keeps_specific_trick_reward_on_canonical_decision_flow'`
  - `.venv311/bin/python -m pytest GPT/test_human_play.py -k 'specific_trick_reward_prompt or trick_to_use_full_hand_context or hidden_trick_requires_selection'`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-09 Derived Player Selector Path

- What changed:
  - Web selectors:
    - added `selectCurrentActorPlayerId`, `selectDerivedPlayers`, and `selectActiveCharacterSlots`
    - the derived player path now combines snapshot player state, current-turn live deltas, active slot mapping, active face (`active_by_card`), marker ownership, local seat, and current actor flags in one place
    - base player normalization now keeps `public_tricks` and `trickCount` so visible player stats do not have to reconstruct trick totals ad hoc in the component
  - App:
    - the top player strip now reads `currentCharacterFace`, marker-owner/current-turn/local badges, and trick totals from the derived selector path
    - the active-character strip now reads selector-built slot ownership instead of rebuilding slot ownership inside `App.tsx`
- Why:
  - the recovery plan’s next priority was to stop scattering visible player truth across `snapshot.players`, ad hoc `playersById` maps, and separate active-strip ownership logic
  - before this change, the top strip and active strip were both correct-ish but not actually fed by one shared derived state path
  - moving those decisions into selectors gives us one place to keep current face, slot ownership, and visible player stats aligned
- Validation:
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-09 Hand Tray Truth And Tile Score Propagation

- What changed:
  - Prompt selectors:
    - added `selectCurrentHandTrayCards`, which now derives the local player hand tray from the unresolved active prompt when it belongs to that player, then falls back to the latest persisted prompt context for that same player
    - full-hand and burden trays now share one canonical parser for `deck_index`, hidden/private state, current-target flags, and burden removal cost copy
  - App:
    - removed the ad hoc `App.tsx` message walk that rebuilt hand tray state outside the selector layer
    - the bottom tray now reads directly from selector output, so used cards disappear and persisted burden cleanup stays tied to the same prompt-context truth source
  - Board / stream selectors:
    - tile view models now preserve `score_coin_count` / `score_coins` / `tile_score_coins`
    - live snapshot projection now updates tile score coins from current-turn event payloads and event public context when those counts are present
    - board tiles now render a score badge from the selector-fed tile model instead of dropping that state on the floor
- Why:
  - the recovery plan’s unified player/tile selector path explicitly called out the hand tray and tile-level board badges as still depending on parallel, component-local state paths
  - before this change, the hand tray lived in a second `App.tsx` replay loop and tile score coins were available upstream but silently discarded by the web tile model
  - moving both back into selector-owned models keeps the board HUD closer to the same live truth path as the player strip and prompt surfaces
- Validation:
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/manifest/manifestRehydrate.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-09 Board-Attached Decision Dock And Hand Tray Cleanup

- What changed:
  - Match board overlay layout:
    - split the in-board overlay into a top HUD layer and a bottom decision dock instead of one centered stack that floated across the middle of the board
    - weather, player strip, active-character strip, and turn banner now stay in the top overlay lane, while passive prompt, actionable prompt, waiting state, and hand tray render inside a shared bottom dock attached to the board edge
  - Board HUD docking:
    - the board overlay container now stretches across the board interior and spaces its children with `justify-content: space-between`, so decision surfaces read like table HUD chrome instead of a mid-board modal column
  - Hand tray cleanup:
    - the tray now lives inside the same bottom dock shell as the prompt surface
    - tray cards use an auto-fit grid and the tray itself renders as a dock continuation instead of a separate floating panel
  - Prompt shell sizing:
    - docked prompts now cap their height lower inside the board HUD lane so the board stays readable behind public state and movement highlights
- Why:
  - the recovery plan called out prompts and hand trays “fighting the board for space” and asked for attached HUD layers with no orphan trays
  - before this change, the whole interaction stack sat around the board center, which made the middle tiles harder to read and made the hand tray feel disconnected from the decision surface
  - anchoring prompt and tray to the bottom inner edge keeps the board legible while still preserving a single live interaction area
- Validation:
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-09 Weather And Active-Card HUD Pass

- What changed:
  - Weather HUD:
    - the top weather card now shows compact HUD pills for round/turn, current beat, and current actor alongside the real weather name/effect text
    - weather detail text now hides duplicate placeholder output and falls back to a simple pending headline when the current round weather has not been revealed yet
  - Active-character strip:
    - the strip header now reports how many active faces are currently revealed
    - active cards now render in a compact horizontal HUD row with scrolling overflow instead of expanding into a larger fixed grid
    - empty slots now render an explicit waiting state so the row stays readable without looking broken
- Why:
  - the recovery plan called for “weather + P1~P4” to read in one glance and for the active strip to stay compact and horizontally aligned
  - after the board-docked prompt pass, the overlay structure was better, but the top HUD still felt taller and more diffuse than it needed to be
  - tightening the weather summary and active strip presentation makes the board-top status line read more like one cohesive HUD pass instead of stacked independent panels
- Validation:
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-09 Current-Turn Public Event Reveal Stack

- What changed:
  - Web selectors:
    - added `selectCurrentTurnRevealItems`, which extracts the current turn’s publicly revealed events in order from `turn_start` onward
    - the selector currently tracks the plan’s targeted reveal events: `weather_reveal`, `dice_roll`, `player_move`, `landing_resolved`, `fortune_drawn`, and `fortune_resolved`
    - each row carries ordered sequence, formatted label/detail, tone, and focus tile so the board HUD can render these as one coherent timeline instead of relying on transient banners alone
  - App HUD:
    - added a `공개 이벤트 / Public events` row to the top board overlay
    - the row keeps event cards in current-turn order and highlights the newest reveal without hiding earlier public steps when prompts open afterward
- Why:
  - the recovery plan called out fortune reveal/effect, weather reveal, dice result, movement path, and landing outcome as major public effects that were resolving underneath later prompts
  - before this change, only a short-lived banner hinted at some events, and that banner could be replaced before the player had seen the whole public sequence
  - keeping a turn-local reveal stack in the board HUD preserves the public chain in visible order while staying inside the board-first layout
- Validation:
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-09 Purchase And Rent Reveal Continuity

- What changed:
  - Reveal stack:
    - extended `selectCurrentTurnRevealItems` so the board HUD now keeps `tile_purchased` and `rent_paid` in the same current-turn public sequence as movement, landing, weather, and fortune beats
    - added an `economy` reveal tone so purchase/rent cards read as payoff beats instead of blending into movement/effect cards
  - Core action continuity:
    - restored `decision_timeout_fallback` into the core-action feed so same-turn timeout fallback remains visible beside rent/purchase resolution instead of disappearing from the turn flow
  - Browser coverage:
    - updated runtime e2e scenarios so remote purchase turns now assert the purchase reveal card
    - updated mixed fallback turns so rent-only current turns assert the rent reveal card and the timeout fallback beat in the core-action panel
- Why:
  - the one-page UI priority still called for larger movement / landing / rent / purchase reveals, and the first reveal stack pass stopped one beat too early at landing
  - once a turn reached purchase or rent, the board HUD still lost the economic payoff beat even though that is the part players actually care about most
  - timeout fallback also needed to stay visible in the same turn flow so mixed human/external-AI turns do not collapse back into ambiguous logs
- Validation:
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run e2e -- --grep "mixed participant runtime keeps timeout fallback and weather continuity visible|remote turn keeps spectator continuity visible and does not open a local prompt|mixed participant runtime keeps a long worker-success to fallback chain readable"`
  - `cd apps/web && npm run build`

## 2026-04-09 Important-Only Turn Interrupt Banner

- What changed:
  - Banner policy:
    - kept the board-top turn banner for `turn_start`, but stopped later same-turn beat updates from re-emitting the same turn banner over and over
    - restricted reveal-triggered banner interrupts to only the high-signal public effects currently in scope: `weather_reveal`, `fortune_drawn`, and `fortune_resolved`
    - left movement / landing / purchase / rent visible in the current-turn reveal stack instead of letting those more frequent beats steal the banner
  - HUD styling:
    - added a separate interrupt visual treatment for the in-board turn banner so important public effects read differently from the ordinary “whose turn” notice
  - Runtime browser coverage:
    - remote purchase turn coverage now asserts that the banner stays on the acting player instead of flipping to the purchase event
    - repeated fallback fortune coverage now asserts that the banner promotes the fortune resolution while the rest of the turn stays visible in the reveal stack and core-action lane
- Why:
  - the one-page UI priority explicitly called for interrupt overlays only on truly important events, and the previous behavior promoted every latest reveal beat into the same banner slot
  - after the reveal stack recovery, that made ordinary movement / purchase / rent beats feel louder than they should and also let the turn-start banner get re-written multiple times during one turn
  - limiting interrupts to weather/fortune-level effects keeps the public sequence readable without turning the board HUD back into a stream of noisy popups
- Validation:
  - `cd apps/web && npm run e2e -- --grep "remote turn keeps spectator continuity visible and does not open a local prompt|mixed participant runtime keeps repeated fallback continuity readable across longer chains|mixed participant runtime keeps timeout fallback and weather continuity visible"`
  - `cd apps/web && npm run build`

## 2026-04-09 Board Reveal Spotlight Fallbacks

- What changed:
  - Board spotlight:
    - passed the latest current-turn reveal item into `BoardPanel` so the board can keep a stronger, larger reveal anchored to the actual play surface
    - added tile-attached reveal spotlight cards for the latest purchase / rent / fortune-style public beat when a focus tile is known
    - added a board-internal fallback reveal panel for cases where the public reveal has no explicit tile index, so the result still stays visible even when the stream payload cannot point to a specific tile
  - Reveal focus fallback:
    - when a reveal has no tile index but the actor pawn is known on the board, the spotlight now falls back to the acting pawn tile before using the board-wide fallback panel
  - Runtime browser coverage:
    - remote purchase continuity now asserts the board spotlight for the purchase result
    - rent fallback continuity now asserts the board spotlight for the rent payoff
    - repeated fallback fortune continuity now asserts the no-tile fallback spotlight path for the fortune result
- Why:
  - the reveal stack solved ordering, but the plan also called for larger movement / landing / rent / purchase reveals that still feel attached to the board itself
  - without a board-attached spotlight, the most important current-turn result could still feel like text in the HUD instead of something that happened on the board
  - no-tile public effects needed a graceful fallback so the stronger reveal treatment did not disappear just because a runtime payload omitted `tile_index`
- Validation:
  - `cd apps/web && npm run e2e -- --grep "remote turn keeps spectator continuity visible and does not open a local prompt|mixed participant runtime keeps timeout fallback and weather continuity visible|mixed participant runtime keeps repeated fallback continuity readable across longer chains"`
  - `cd apps/web && npm run build`

## 2026-04-09 Mixed Human + External-AI Playtest Smoke

- What changed:
  - Ran the real-playtest checklist path locally:
    - started the stronger external worker on `127.0.0.1:8011` with `worker_profile=priority_scored`
    - started the app server on `127.0.0.1:8001`
    - passed `tools/check_external_ai_endpoint.py` with the stronger-worker requirements
    - created a real mixed-seat session with:
      - seat 1 external AI over HTTP
      - seat 2 human
      - seat 3 local AI
    - joined the human seat and started the session successfully
  - Captured runtime evidence from the live replay/export path instead of only relying on browser mocks
- Why:
  - the active priority board explicitly says to move to real playtests once the board/HUD recovery became stable enough
  - the goal here was to verify that the stronger worker really attaches and that mixed human/external/local flow produces usable evidence for the next fixes
- Evidence:
  - stronger-worker health and contract smoke passed for:
    - `worker_id=local-priority-bot`
    - `worker_profile=priority_scored`
    - `worker_adapter=priority_score_v1`
    - `policy_class=PriorityScoredPolicy`
    - `decision_style=priority_scored_contract`
  - real mixed-seat session:
    - `session_id=sess_4eb68bd82792`
    - session creation, human join, and session start all succeeded
    - the external-AI seat immediately resolved an opening `hidden_trick_card` choice through `/decide`
    - the next blocking prompt was correctly issued only for the human seat, and runtime state moved to `waiting_input`
  - concrete drift found:
    - the real replay stream for that external-AI resolution did not include worker provenance fields on the emitted `decision_requested` / `decision_resolved` events
    - the follow-up human prompt also showed `round_index=null` / `turn_index=null` in the replay export for that opening choice path
    - this is now concrete playtest evidence for the next fix, rather than a speculative UI issue
- Validation:
  - `PYTHONPATH=/Users/sil/Workspace/project-mrn .venv311/bin/python tools/run_external_ai_worker.py --host 127.0.0.1 --port 8011 --worker-id local-priority-bot --policy-mode heuristic_v3_gpt --worker-profile priority_scored --worker-adapter priority_score_v1`
  - `.venv311/bin/python -m uvicorn apps.server.src.app:app --host 127.0.0.1 --port 8001`
  - `.venv311/bin/python tools/check_external_ai_endpoint.py --base-url http://127.0.0.1:8011 --require-ready --require-profile priority_scored --require-adapter priority_score_v1 --require-policy-class PriorityScoredPolicy --require-decision-style priority_scored_contract --require-request-type movement --require-request-type purchase_tile`

## 2026-04-09 Replay Decision Metadata Recovery

- What changed:
  - replay decision payloads:
    - taught the server `decision_requested` / `decision_resolved` event builders to persist the full `public_context` snapshot into replay/export payloads instead of only carrying top-level request metadata
    - kept the event-level `round_index` / `turn_index` mirrored from that same context so replay consumers can read turn identity without reparsing prompt envelopes
  - opening hidden-trick human prompt:
    - added `round_index` and `turn_index` to the human `hidden_trick_card` prompt contract so the first blocking human prompt in a live mixed-seat game no longer emits `null` turn metadata
  - regression coverage:
    - extended the prompt payload test to assert round/turn on hidden-trick prompts
    - extended runtime service bridge coverage to assert replay decision events carry the embedded `public_context` round/turn snapshot on canonical AI paths
- Why:
  - the first real mixed human + external-AI smoke found that opening replay events were losing decision context exactly where we needed it most: the live export could not explain which turn a human prompt belonged to, and external-worker provenance disappeared from replay because decision events dropped `public_context`
  - prompt mocks alone were no longer enough here because the failure only showed up after the real gateway -> replay path serialized the events
- Evidence:
  - targeted tests now pass for both sides of the fix:
    - hidden-trick human prompt payload includes `round_index=1` and `turn_index=1`
    - runtime bridge replay events keep embedded `public_context` for AI decision request/resolve payloads
  - reran the real mixed-seat smoke with:
    - seat 1 external AI over HTTP
    - seat 2 human
    - seat 3 local AI
  - live replay result from `session_id=sess_3762e0c923bd`:
    - the external-AI opening `decision_resolved` event now carries worker provenance in `public_context`, including `worker_id=local-priority-bot`, `worker_profile=priority_scored`, `worker_adapter=priority_score_v1`, `policy_class=PriorityScoredPolicy`, and `decision_style=priority_scored_contract`
    - the follow-up human `hidden_trick_card` `decision_requested` event now carries `round_index=1` and `turn_index=1` instead of `null`
    - the paired external-AI `decision_requested` event also now carries the serialized `public_context` snapshot; worker identity remains pending-placeholder state there by design because the request event is emitted before the worker response is available
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_human_policy_prompt_payloads.py -k 'hidden_trick_prompt_contains_full_hand_context'`
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'ai_bridge_keeps_purchase_tile_on_canonical_decision_flow or ai_bridge_keeps_mark_target_on_canonical_decision_flow'`
  - `.venv311/bin/python -m uvicorn apps.server.src.app:app --host 127.0.0.1 --port 8001`
  - `PYTHONPATH=/Users/sil/Workspace/project-mrn .venv311/bin/python tools/run_external_ai_worker.py --host 127.0.0.1 --port 8011 --worker-id local-priority-bot --policy-mode heuristic_v3_gpt --worker-profile priority_scored --worker-adapter priority_score_v1`
  - live mixed-seat replay smoke via `/api/v1/sessions`, `/join`, `/start`, `/runtime-status`, and `/replay`

## 2026-04-09 Live Stream Prompt Leakage Fix

- What changed:
  - websocket delivery filter:
    - updated the stream sender so `prompt` and `decision_ack` messages are no longer broadcast to every subscriber on the session
    - spectator sockets now skip those private message types entirely
    - seat-authenticated sockets only receive `prompt` / `decision_ack` when the payload `player_id` matches the authenticated seat player
  - regression coverage:
    - added a stream API test that opens both a spectator socket and a seat socket and verifies the seat receives private prompt/ack traffic while the spectator does not
- Why:
  - a real mixed-seat live stream check exposed that spectator sockets were incorrectly receiving human prompt traffic because the websocket sender was forwarding the shared stream queue without any per-role filtering
  - the online-game API spec says spectator mode receives events only, so this was a true privacy/UX leak, not just a cosmetic mismatch
- Evidence:
  - first live WS check on `session_id=sess_6afc51e67670` showed:
    - `spectator_prompt_count=1`
    - the leaked spectator message was the exact human `hidden_trick_card` prompt payload for player 2
  - after the sender filter fix, reran the live mixed-seat WS flow on `session_id=sess_d536403280e3` and observed:
    - `spectator_prompt_count=0`
    - `spectator_ack_count=0`
    - `seat_prompt_count=1`
    - human decision submission returned `decision_ack.status=accepted`
    - human `decision_resolved` landed with `round_index=1` / `turn_index=1`
    - external-AI opening resolution still preserved worker provenance with `worker_id=local-priority-bot`, `worker_profile=priority_scored`, `worker_adapter=priority_score_v1`, `policy_class=PriorityScoredPolicy`, and `decision_style=priority_scored_contract`
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_stream_api.py -k 'spectator_does_not_receive_prompt_or_decision_ack_for_seat or seat_decision_accepts_pending_prompt_with_ack'`
  - `.venv311/bin/python tools/check_external_ai_endpoint.py --base-url http://127.0.0.1:8011 --require-ready --require-profile priority_scored --require-adapter priority_score_v1 --require-policy-class PriorityScoredPolicy --require-decision-style priority_scored_contract --require-request-type movement --require-request-type purchase_tile`
  - live mixed-seat websocket smoke via `/api/v1/sessions`, `/join`, `/start`, seat `/stream?token=...`, spectator `/stream`, `/runtime-status`, and `/replay`

## 2026-04-09 Backend Selector / Middleware Migration Planning

- What changed:
  - added a new architecture plan:
    - `docs/current/engineering/[PLAN]_BACKEND_SELECTOR_AND_MIDDLEWARE_VIEWMODEL_MIGRATION.md`
  - documented a staged migration from frontend-owned selector truth to backend or middleware-owned view-state selectors
  - defined:
    - target server package boundary for reusable view-state selectors
    - projection responsibilities for players, active slots, mark targets, prompts, reveals, and board state
    - phased cutover order so the web can become a thin rendering layer instead of continuing to reconstruct gameplay state locally
    - validation gates across server unit tests, runtime integration tests, stream/replay contract tests, and live playtests
- Why:
  - the user explicitly requested a backend or middleware selector migration so frontend changes do not require re-implementing gameplay-derived UI truth
  - recent live-play regressions have repeatedly shown that too much canonical state assembly still lives in:
    - `apps/web/src/domain/selectors/streamSelectors.ts`
    - `apps/web/src/domain/selectors/promptSelectors.ts`
    - `apps/web/src/App.tsx`
  - this is therefore a user-requested exception to the normal “do not reopen broad architecture migration” rule in `docs/current/planning/PLAN_STATUS_INDEX.md`
- Evidence:
  - current selector burden was re-audited before writing the plan:
    - web side:
      - `selectTurnStage`
      - `selectCurrentTurnRevealItems`
      - `selectDerivedPlayers`
      - `selectActiveCharacterSlots`
      - `selectMarkTargetCharacterSlots`
      - `selectMarkerOrderedPlayers`
      - `selectCurrentHandTrayCards`
    - server-side seams already available for the migration:
      - `apps/server/src/services/runtime_service.py`
      - `apps/server/src/services/stream_service.py`
      - `apps/server/src/routes/stream.py`
- Validation:
  - documentation-only planning task
  - no implementation started yet

## 2026-04-09 Backend Selector Plan Compatibility Update

- What changed:
  - tightened the new backend selector migration plan so it explicitly targets portability beyond the current React client
  - added plan requirements that the selector/projector layer must remain reusable even if the frontend is replaced by:
    - Unity
    - Unreal
  - documented a DI-oriented selector/projector/transport-adapter boundary instead of allowing React-shaped projection logic to leak back into the contract
  - added an API documentation tracking requirement so any runtime contract change in this migration must update:
    - `docs/current/api/online-game-api-spec.md`
    - `docs/current/api/README.md`
    - relevant runtime contract examples and schemas
- Why:
  - the user clarified that this migration is only worthwhile if a future renderer swap can reuse the same selector set and DI structure by matching interfaces
  - without that explicit requirement, the plan could still drift into a web-specific “thin React but still React-shaped” projection layer
- Evidence:
  - the plan now includes:
    - a dedicated compatibility requirement section
    - a DI and client adapter contract section
    - explicit phase exit criteria that include contract-document updates
    - validation requirements for non-web client compatibility fixtures
- Validation:
  - documentation-only update
  - no API contract changed yet; this entry updates the migration requirements, not the live API

## 2026-04-10 Backend Selector Migration Phase 1 Start

- What changed:
  - started the first implementation slice of the backend selector / middleware migration instead of keeping player ordering logic only in the React client
  - created a new server-side selector package:
    - `apps/server/src/domain/view_state/__init__.py`
    - `apps/server/src/domain/view_state/types.py`
    - `apps/server/src/domain/view_state/snapshot_selector.py`
    - `apps/server/src/domain/view_state/player_selector.py`
    - `apps/server/src/domain/view_state/projector.py`
  - moved the canonical “marker owner + draft direction -> ordered player ids” logic into the server projector
  - updated `apps/server/src/services/stream_service.py` so every published stream payload can carry additive `payload.view_state.players`
  - updated the web selector path so `selectMarkerOrderedPlayers` prefers backend-projected ordering when `payload.view_state.players.ordered_player_ids` is present, while still keeping the old frontend reduction as fallback
  - tightened the live prompt/active-slot path so active mark-target choices rehydrate from the latest unresolved prompt even when later messages become the newest snapshot source
- Why:
  - phase 1 of the migration plan was to prove that a selector can move to the backend and be consumed as a renderer-agnostic view-model instead of staying React-only
  - player ordering was chosen as the first slice because it already had clear bugs around duplicated local logic and is small enough to migrate end-to-end without changing the full prompt stack yet
- API / contract impact:
  - additive only
  - `docs/current/api/online-game-api-spec.md` now documents `payload.view_state.players` on stream/replay payloads
  - no existing raw fields were removed
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_player_selector.py`
  - `python -m pytest apps/server/tests/test_sessions_api.py -k replay_endpoint_returns_buffered_messages`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 2 Active Slots / Mark Target

- What changed:
  - extended the new server-side `view_state` projector so it no longer publishes only player ordering
  - added backend prompt resolution and slot projection logic:
    - `apps/server/src/domain/view_state/prompt_selector.py`
    - expanded `apps/server/src/domain/view_state/player_selector.py`
  - server `view_state` now projects:
    - `view_state.players.items`
    - `view_state.active_slots.items`
    - `view_state.mark_target.candidates`
  - active slot projection now rehydrates from the latest unresolved prompt when prompt public context exposes:
    - `actor_name`
    - `target_pairs`
    - mark-target `legal_choices`
  - this keeps the canonical active strip and mark-target candidate list available even when later stream events become the newest snapshot source
  - frontend selectors were updated to prefer backend projections for:
    - `selectDerivedPlayers`
    - `selectActiveCharacterSlots`
    - `selectMarkTargetCharacterSlots`
  - the web fallback reducers still remain in place while the migration is incomplete
- Why:
  - the first migrated slice solved player ordering, but the highest-friction UI defects were still concentrated around:
    - stale / duplicated current faces
    - empty active slots during mark-target prompts
    - mark-target candidates drifting away from the active strip
  - moving active slot and mark-target derivation to the backend makes the transport contract portable for non-React clients and reduces frontend guesswork
- API / contract impact:
  - additive only
  - `docs/current/api/online-game-api-spec.md` now documents `view_state.active_slots` and `view_state.mark_target`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_player_selector.py`
  - `python -m pytest apps/server/tests/test_sessions_api.py -k replay_endpoint_returns_buffered_messages`
  - `python -m pytest apps/server/tests/test_stream_api.py -k 'spectator_does_not_receive_prompt_or_decision_ack_for_seat or seat_decision_accepts_pending_prompt_with_ack'`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 4 Reveal Stack / Board Movement

- What changed:
  - extended the server-side `view_state` projector again so the web no longer has to own current-turn public reveal ordering or latest board movement extraction
  - added:
    - `apps/server/src/domain/view_state/reveal_selector.py`
    - `apps/server/src/domain/view_state/board_selector.py`
  - server `view_state` now also publishes:
    - `view_state.reveals`
    - `view_state.board`
  - `view_state.reveals.items` is now the backend-owned current-turn public event stack with:
    - canonical order
    - reveal tone
    - interrupt-worthiness
    - focus tile index
  - `view_state.board.last_move` now carries the latest movement path projection
  - web selectors were updated so:
    - `selectCurrentTurnRevealItems` prefers `view_state.reveals`
    - `selectLastMove` prefers `view_state.board.last_move`
  - the web still formats labels/details locally from raw messages, but it no longer decides reveal ordering or movement ownership when backend projection is present
  - the app stopped re-sorting reveal items locally and now trusts backend reveal ordering directly
- Why:
  - the previous migration slice still left the reveal stack and latest board-move spotlight vulnerable to frontend-only truth drift
  - this slice moves the ordering and focus semantics into the same renderer-agnostic projection layer the future Unity / Unreal clients will consume
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `docs/current/api/README.md`
    - `packages/runtime-contracts/ws/examples/inbound.event.player_move.with_view_state.json`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_reveal_selector.py`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3 Prompt Surface Projection

- What changed:
  - added backend-owned prompt projection on top of the existing prompt liveness helper
  - `apps/server/src/domain/view_state/prompt_selector.py` now exposes `build_prompt_view_state(...)`
  - `apps/server/src/domain/view_state/projector.py` now publishes additive `view_state.prompt`
  - `view_state.prompt.active` carries:
    - `request_id`
    - `request_type`
    - `player_id`
    - `timeout_ms`
    - parsed canonical `choices`
    - `public_context`
  - web `selectActivePrompt(...)` now prefers backend `view_state.prompt.active`
  - if backend `view_state` is present and no prompt slice exists, the web now treats that as authoritative “no active prompt” instead of reviving an older raw prompt locally
  - this reduces prompt truth drift and makes prompt rendering less dependent on React-side replay reduction
- Why:
  - after player / slot / reveal migration, the next biggest remaining frontend-owned truth was “which prompt is actually active right now?”
  - stale prompt suppression and active prompt selection need to live in the transport-facing selector layer so non-React clients can render the same actionable prompt state
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/examples/inbound.prompt.movement.json`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_prompt_selector.py`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.1 Prompt Chain Behavior

- What changed:
  - extended `view_state.prompt.active` with backend-owned `behavior` metadata so clients do not need to infer prompt chain semantics from raw request types and ad hoc public-context fields
  - `apps/server/src/domain/view_state/prompt_selector.py` now projects:
    - `normalized_request_type`
    - `single_surface`
    - `auto_continue`
    - `chain_key`
    - `chain_item_count`
    - `current_item_deck_index`
  - `burden_exchange` is now explicitly exposed as a single-surface auto-continue chain via:
    - `normalized_request_type = burden_exchange_batch`
    - `single_surface = true`
    - `auto_continue = true`
  - web `selectActivePrompt(...)` now carries prompt behavior through to the renderer
  - `apps/web/src/App.tsx` burden-chain suppression and follow-up auto-send logic now keys off backend `prompt.behavior` instead of raw `request_type === burden_exchange`
- Why:
  - repeated burden prompts were still normalized with React-local rules
  - this slice moves prompt-chain semantics into the transport contract so alternate clients can implement the same UX without reverse-engineering web behavior
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/examples/inbound.prompt.movement.json`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_prompt_selector.py`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.2 Prompt Feedback Projection

- What changed:
  - extended `view_state.prompt` again so the server also projects recent prompt lifecycle feedback
  - `apps/server/src/domain/view_state/prompt_selector.py` now builds `last_feedback` from:
    - `decision_ack`
    - `decision_resolved`
    - `decision_timeout_fallback`
  - web `selectLatestDecisionAck(...)` now prefers backend `view_state.prompt.last_feedback`
  - this lets the client consume canonical prompt feedback from the backend projection instead of scanning raw `decision_ack` messages first
- Why:
  - prompt rendering still depended on direct raw-message inspection for rejection / stale feedback
  - pushing this into the selector layer keeps prompt lifecycle truth aligned across future non-React clients
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/examples/inbound.decision_ack.rejected.with_view_state.json`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_prompt_selector.py`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.3 Prompt Interaction Middleware Selector

- What changed:
  - added a renderer-adjacent middleware selector so React no longer hand-assembles prompt busy / timeout / rejection / stale / connection-loss behavior inline
  - `apps/web/src/domain/selectors/promptSelectors.ts` now exports `selectPromptInteractionState(...)`
  - the selector combines:
    - backend `view_state.prompt.last_feedback`
    - current active prompt projection
    - client-tracked in-flight request id
    - local timeout wall-clock state
    - stream connectivity
    - local manual send-failure feedback
  - the selector returns:
    - `busy`
    - `secondsLeft`
    - structured feedback kind
    - `shouldReleaseSubmission`
  - `apps/web/src/App.tsx` now uses that middleware selector instead of separate local effects for:
    - rejected prompt handling
    - stale prompt handling
    - timeout notice derivation
    - connection-loss release
- Why:
  - the previous slice moved prompt feedback truth into backend projection, but the React app still contained a mini state machine for interpreting it
  - this slice keeps only the truly local “submit started” state in React and moves the rest of the interaction logic into a reusable selector layer that another renderer can adapt with the same contract
- API / contract impact:
  - none
  - middleware-only consolidation on the client side
- Validation:
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.4 Hand Tray Projection

- What changed:
  - added backend-owned `view_state.hand_tray`
  - `apps/server/src/domain/view_state/hand_selector.py` now projects the canonical visible hand/burden tray from:
    - the current active prompt public context when present
    - otherwise the latest persisted prompt public context on that stream
  - `apps/server/src/domain/view_state/projector.py` now publishes additive `view_state.hand_tray`
  - web `selectCurrentHandTrayCards(...)` now prefers backend `view_state.hand_tray` and only falls back to raw prompt scanning during migration
- Why:
  - hand-tray truth was still rebuilt in React from seat-specific prompt history
  - this slice moves another seat-aware surface into the shared backend projection contract so future Unity / Unreal clients can consume the same tray semantics directly
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/examples/inbound.prompt.trick_to_use.with_view_state.json`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_hand_selector.py`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.5 Turn Stage Projection

- What changed:
  - added backend-owned `view_state.turn_stage`
  - `apps/server/src/domain/view_state/turn_selector.py` now projects:
    - current actor identity
    - round / turn coordinates
    - current beat kind
    - current beat event/request code
    - focus tile indices
    - external-ai decision status fields
    - actor resource snapshot fields
    - progress code trail
  - web `selectTurnStage(...)` now prefers backend `view_state.turn_stage` for the canonical beat / focus / actor / progress truth and only keeps localization + message-detail rendering on the client side
- Why:
  - the turn banner, waiting states, and prompt overlays still depended on the heaviest remaining React-side state reducer
  - this slice moves the “what stage are we actually in?” decision to the backend while preserving frontend-specific text rendering
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/examples/inbound.event.turn_start.with_view_state.json`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_turn_selector.py`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.6 Scene / Theater / Core-Action Projection

- What changed:
  - added backend-owned `view_state.scene`
  - `apps/server/src/domain/view_state/scene_selector.py` now projects:
    - `situation`
      - current actor player id
      - round / turn coordinates
      - latest headline message seq / code
      - persisted weather name / effect
    - `theater_feed`
      - capped lane-aware feed entries with backend-owned `tone` and `lane`
      - renderer-agnostic `message_type` / `event_code` / actor / round / turn fields
    - `core_action_feed`
      - capped core-event feed entries in backend-owned order
    - `timeline`
      - backend-owned recent message sequence projection for compact history surfaces
    - `critical_alerts`
      - backend-owned latest terminal warning / critical alert projection
  - `apps/server/src/domain/view_state/projector.py` now publishes additive `view_state.scene`
  - web `selectSituation(...)`, `selectTheaterFeed(...)`, `selectCoreActionFeed(...)`, `selectTimeline(...)`, and `selectCriticalAlerts(...)` now prefer backend `view_state.scene` and only keep:
    - seq-to-message lookup
    - localized label/detail rendering
    - local-player highlighting for core-action rows
- Why:
  - this was one of the last raw stream reduction islands still living in the frontend selector layer
  - moving it to backend projection keeps the transport contract reusable across React / Unity / Unreal while letting each renderer handle only presentation
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/examples/inbound.event.turn_start.with_view_state.json`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_scene_selector.py`
  - `python -m pytest apps/server/tests/test_sessions_api.py -k replay_endpoint_returns_buffered_messages`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.7 Shared Selector Fixture Contract

- What changed:
  - added shared selector fixture contract:
    - `packages/runtime-contracts/ws/examples/selector.scene.turn_resolution.json`
    - `packages/runtime-contracts/ws/schemas/selector.scene.fixture.schema.json`
  - the fixture now carries:
    - canonical mixed message history
    - expected `view_state.scene` projection
    - shared metadata for event ordering
  - backend tests now read the same fixture contract instead of ad-hoc inline scene samples:
    - `apps/server/tests/test_view_state_scene_selector.py`
    - `apps/server/tests/test_runtime_contract_examples.py`
  - frontend selector tests now read the same fixture contract:
    - `apps/web/src/domain/selectors/streamSelectors.spec.ts`
  - engine regression now reads the same metadata file for move -> landing -> rent ordering:
    - `GPT/test_rule_fixes.py`
  - runtime contract README now documents selector fixtures as a first-class shared contract artifact:
    - `packages/runtime-contracts/ws/README.md`
- Why:
  - the migration goal is not only moving selectors server-side, but ensuring multiple renderers and subsystems validate against the same truth source
  - this slice prevents frontend/backend/engine regressions from drifting into three different hand-written fixture universes
- API / contract impact:
  - no transport API change
  - additive test-contract + metadata contract only
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_scene_selector.py`
  - `python -m pytest apps/server/tests/test_runtime_contract_examples.py`
  - `python -m pytest GPT/test_rule_fixes.py -k vis_stream_emits_player_move_before_landing_and_rent`
  - `cd apps/web && npm run test -- src/domain/selectors/streamSelectors.spec.ts`
  - `cd apps/web && npm run build`
## Phase 3.8 Board Surface Truth Projection

- migrated dynamic board surface truth to backend `view_state.board.tiles`
- web live snapshot now prefers backend board tiles for `owner / score_coin / pawn` dynamic state and keeps static tile schema local
- added shared fixture + schema for board selector contract:
  - `packages/runtime-contracts/ws/examples/selector.board.live_tiles.json`
  - `packages/runtime-contracts/ws/schemas/selector.board.fixture.schema.json`
- added backend/frontend selector tests that read the same board fixture contract

## 2026-04-10 Backend Selector Migration Phase 3.9 Prompt Surface Projection Contract

- What changed:
  - backend `view_state.prompt.active` now owns renderer-agnostic prompt-surface truth through `surface`
  - `apps/server/src/domain/view_state/prompt_selector.py` now projects:
    - common prompt surface metadata:
      - `kind`
      - `blocks_public_events`
    - `lap_reward` surface:
      - budget / pools / point costs
      - canonical reward option units derived from legal choices
    - `burden_exchange_batch` surface:
      - burden count / current F / supply threshold
      - canonical burden-card tray with current-target identity
  - web prompt selectors and `PromptOverlay` now prefer backend `surface` for:
    - lap reward picker
    - burden exchange batch tray
    - prompt-vs-public-event blocking behavior
  - added shared prompt selector fixtures + schema:
    - `packages/runtime-contracts/ws/examples/selector.prompt.lap_reward_surface.json`
    - `packages/runtime-contracts/ws/examples/selector.prompt.burden_exchange_surface.json`
    - `packages/runtime-contracts/ws/schemas/selector.prompt.fixture.schema.json`
  - backend, frontend, and engine-adjacent tests now read the same shared prompt fixture metadata
- Why:
  - prompt choice surfaces were still one of the biggest React-owned interpretation islands
  - this keeps the transport contract reusable for React / Unity / Unreal adapters while letting tests assert the same output across backend projection, frontend adapters, and engine-adjacent gateway builders
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/README.md`
- Validation:
  - `python -m pytest apps/server/tests/test_view_state_prompt_selector.py`
  - `python -m pytest apps/server/tests/test_runtime_contract_examples.py`
  - `python -m pytest GPT/test_rule_fixes.py -k selector_prompt`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.10 Prompt Surface Choice-Card Expansion

- What changed:
  - backend `view_state.prompt.active.surface` now also projects canonical choice-card surfaces for prompt types that previously still depended on React-side interpretation:
    - `mark_target`
    - `draft_card` / `final_character` / `final_character_choice` via `surface.character_pick`
    - `purchase_tile`
    - `trick_tile_target`
    - `active_flip`
  - `apps/server/src/domain/view_state/prompt_selector.py` now derives these surfaces directly from prompt `legal_choices` and `public_context`, so adapters no longer need to infer ordering or card labels themselves
  - `apps/server/src/services/decision_gateway.py` now enriches `active_flip` legal choices with stable display metadata (`current_name`, `flipped_name`) so middleware and alternate clients can render the same transition text without duplicating card lookup logic
  - frontend prompt selectors and `PromptOverlay` now prefer backend-projected surface ordering/details for:
    - mark-target candidate trays
    - character pick trays
    - active-flip trays and finish action
  - shared prompt selector fixtures expanded with:
    - `packages/runtime-contracts/ws/examples/selector.prompt.mark_target_surface.json`
    - `packages/runtime-contracts/ws/examples/selector.prompt.active_flip_surface.json`
  - backend, frontend, and engine-adjacent tests now validate the same prompt-surface metadata for these specialized surfaces
- Why:
  - lap reward / burden exchange were no longer the only prompt-specific interpretation islands; mark-target and active-flip still leaked renderer-owned ordering and labeling logic
  - this keeps the prompt contract progressively closer to a renderer-agnostic selector module that React, Unity, Unreal, or any other client can consume with minimal UI-only adaptation
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/README.md`
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_view_state_prompt_selector.py apps/server/tests/test_runtime_contract_examples.py -q`
  - `.venv311/bin/python -m pytest GPT/test_rule_fixes.py -k 'selector_prompt or active_flip' -q`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-10 Backend Selector Migration Phase 3.11 Prompt Surface Reward / Target Expansion

- What changed:
  - extended backend `view_state.prompt.active.surface` so the remaining mid-weight prompt choice surfaces no longer depend on React-only summary/ordering logic:
    - `coin_placement`
    - `doctrine_relief`
    - `geo_bonus`
    - `specific_trick_reward`
    - `pabal_dice_mode`
  - `apps/server/src/domain/view_state/prompt_selector.py` now projects canonical renderer-agnostic option trays for those request types directly from `legal_choices` and decision `public_context`
  - `apps/server/src/services/decision_gateway.py` now enriches gateway choice/context payloads for these prompts so alternate clients do not need to rebuild titles/descriptions from raw ids:
    - coin placement choices now publish stable tile descriptions
    - doctrine relief choices now publish stable removal descriptions
    - geo bonus and pabal dice mode choices now publish stable descriptions
    - geo bonus now also carries actor/resource context in `public_context`
  - frontend prompt selectors and `PromptOverlay` now prefer backend-projected option ordering for:
    - character-target style decision grids
    - reward choice trays
    - pabal dice-mode chooser
  - added shared selector fixtures for:
    - `packages/runtime-contracts/ws/examples/selector.prompt.coin_placement_surface.json`
    - `packages/runtime-contracts/ws/examples/selector.prompt.geo_bonus_surface.json`
  - backend/frontend/engine tests now validate the same shared metadata for those prompt types, while direct selector tests cover:
    - `doctrine_relief`
    - `specific_trick_reward`
    - `pabal_dice_mode`
- Why:
  - after phases 3.9 and 3.10, React still owned too much interpretation for several remaining reward/target decision surfaces
  - this slice keeps pushing prompt rendering toward a transport contract that Unity, Unreal, or any other renderer can consume with UI-only adaptation
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/README.md`
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_view_state_prompt_selector.py apps/server/tests/test_runtime_contract_examples.py -q`
  - `.venv311/bin/python -m pytest GPT/test_rule_fixes.py -k 'selector_prompt or geo_bonus or coin_placement' -q`
  - `cd apps/web && npm run test -- src/domain/selectors/promptSelectors.spec.ts`
  - `cd apps/web && npm run build`

## 2026-04-26 Board HUD Grid Area Layout Stabilization

- What changed:
  - Reworked the live match HUD overlay in `apps/web/src/styles.css` so the main match surface uses fixed CSS grid areas instead of absolute-positioned HUD children.
  - Player cards, round weather, active character rail, prompt area, public event rail, and bottom hand tray now occupy named grid areas:
    - top-left / top-center / top-right
    - middle-left / middle-center / middle-right
    - bottom-left / bottom-center / bottom-right
  - Added responsive grid-area fallbacks for narrower desktop/tablet and mobile widths so the HUD stacks predictably while preserving component content behavior.
- Why:
  - the prior layout anchored every HUD panel with independent absolute offsets, making the reference-style structure fragile across viewport sizes
  - the new grid contract keeps placement stable and lets the viewport resize the layout through grid tracks instead of per-panel coordinates
- API / contract impact:
  - none; CSS-only layout change
- Validation:
  - `cd apps/web && npm run build`
  - local browser quick-start match at `http://127.0.0.1:5173/`

## 2026-04-26 Top-View Diamond Board Layout

- What changed:
  - Replaced the visible quarterview lane presentation with the real tile cards arranged directly on a top-view diamond projection.
  - Disabled the separate quarterview visual-lane layer and kept rails hidden, so the board is no longer built from an extra guide/rail surface.
  - Constrained the live ring board to a square-ish board area and adjusted the ring projection to a top-view diamond scale.
  - Kept existing tile card information, ownership, stage focus, and pawn/standee positioning on the same projected tile coordinates.
- Why:
  - the reference-style board should read as one top-view diamond made of the tiles themselves, not as a quarterview track laid over a guide rail
- API / contract impact:
  - none; frontend rendering/projection presentation only
- Validation:
  - `cd apps/web && npm run test -- src/features/board/boardProjection.spec.ts`
  - `cd apps/web && npm run build`
  - in-app browser quick-start match check at `http://127.0.0.1:5173/#/match`; console error list empty

## 2026-04-26 Quarterview Board Reference-Like Guide Cleanup

- What changed:
  - Removed the visible quarterview rail guide layer so the board reads as tile-to-tile connected lanes instead of tiles sitting on a separate guide strip.
  - Added a shared diamond clip and mitered lane ends to reduce corner overrun where the four board sides meet.
  - Kept the richer tile content layer intact: tile number, kind, purchase / rent, owner, and score metadata remain present on the visual tiles.
- Why:
  - the reference-like board shape depends on the four tile lanes reading as one diamond; the separate guide rail made the corners look like crossed, disconnected parts
- API / contract impact:
  - none; CSS presentation only
- Validation:
  - `cd apps/web && npm run test -- src/features/board/boardProjection.spec.ts`
  - `cd apps/web && npm run build`
  - in-app browser quick-start match check at `http://127.0.0.1:5173/#/match`; console error list empty

## 2026-04-26 Quarterview Board Diamond Track Connection

- What changed:
  - Updated the quarterview board track sizing so all four visual lanes share one projected diamond side length instead of sizing each side from `tileCount * fixedTileWidth`.
  - Increased the quarterview tile height and track height so each tile can carry more of the existing board information without collapsing.
  - Restored visible tile metadata on the quarterview layer:
    - tile index
    - kind label
    - purchase / rent label when applicable
    - owner label
    - score coin label when present
- Why:
  - the earlier quarterview lane layout produced four visually separate rail segments rather than one connected diamond-shaped board
  - the compact visual tile layer had dropped too much of the original tile information
- API / contract impact:
  - none; React markup and CSS presentation only
- Validation:
  - `cd apps/web && npm run build`
  - local browser quick-start match visual check at `http://127.0.0.1:5173/`

## 2026-04-26 Narrow Viewport Board Visibility Check

- What changed:
  - During in-app browser inspection, found that the stacked HUD layout at narrow viewport widths could still sit as an absolute overlay on top of the board.
  - Updated the `max-width: 980px` layout so `board-overlay-content` participates in normal document flow and the board scroll shell switches to a vertical flex layout.
  - The board now appears first, with the stacked HUD surfaces following underneath on narrow screens instead of hiding the board.
- Why:
  - the previous mobile override preserved the desktop overlay layer and caused the prompt/player HUD stack to cover the diamond board
- API / contract impact:
  - none; CSS-only responsive layout fix
- Validation:
  - `cd apps/web && npm run build`
  - in-app browser quick-start match screen check; console error list empty

## 2026-04-28 1920x1080 Board Reference Validation Failure

- Validation attempted:
  - restarted local web/server runtime on `127.0.0.1:9000` and `127.0.0.1:9090`
  - opened a quick-start match at `1920x1080`
  - captured `match-1920-board-initial.png`
- Failed result:
  - the lane-owned board stayed connected, but the board occupied only about `840x532` pixels and sat too far left
  - the collapsed decision prompt stretched across the map column and crossed the tile lanes, reducing tile readability
  - the right side of the viewport was mostly empty, so the layout did not match the reference goal of using the available horizontal space for a larger board
- Lesson:
  - the narrow-viewport clipping fix reused one right-safe budget for every desktop width; that over-reserves space on `1920x1080`
  - collapsed prompt placement must be treated like a reference-style central sign inside the board's empty center, not like a full-width HUD rail
- Corrective direction:
  - add a wide-desktop safe-space budget so the board can grow until it approaches the player-card rails
  - constrain collapsed prompt width/height and center it in the diamond's empty inner area without crossing the lane strips

## 2026-04-28 Projection-Owned Board And Character Portrait Pass

- What changed:
  - replaced the visible lane-owned board surface with a projection-owned SVG tile layer
  - added `quarterviewTilePolygons` so each visible board tile is calculated as a projected four-point polygon from one logical board plane
  - removed visible lane strip ownership from the active board render; browser validation now reports `40` projected tiles and `0` lane strips
  - kept the old tile card nodes as non-visual anchors for existing focus, HUD, and standee positioning during this transition
  - generated a sixteen-character 2:3 portrait sprite sheet for the full gameplay catalog and wired character-pick cards to use those illustrations instead of the old one-letter mark
  - mapped the previously missing faces (`탐관오리`, `산적`, `사기꾼`, and the rest of the catalog) and corrected the shaman portraits so `박수` reads as a male shaman while `만신` reads as a female shaman
  - adjusted character-pick prompt height and card sizing so the enlarged 2:3 portraits remain responsive without pushing the card body outside the prompt surface
- Why:
  - the reference board is not four independent guide rails; it is a single top-view board plane compressed through a quarterview-style projection
  - character choice cards need a real scalable visual asset, not a fixed text placeholder, while preserving choice metadata and ability text
- Validation:
  - `cd apps/web && npm run test -- src/features/board/boardProjection.spec.ts`
  - `cd apps/web && npm run build`
  - browser 1920x1080 AI-session check: `40` `.board-projected-tile`, `0` `.board-lane-strip`, no console errors
  - browser 1920x1080 human draft prompt check: character cards render generated 2:3 portraits and keep visible card metadata/ability text

## 2026-05-02 Round-End Marker Flip Timing

- What changed:
  - moved round-end marker flip resolution out of `_start_new_round()` and into the round-boundary turn completion path before the turn/round cursor advances
  - changed `marker_flip` visual events to use `public_phase='turn_end'`
  - aligned frontend and backend reveal ordering so `marker_transferred` appears before the final `marker_flip`
  - documented the rule/source-map contract that card flip is the just-finished turn's final event, not the next round's first prelude event
- Why:
  - live play showed card flips feeling like they happened at the beginning of the next round, before weather/draft
  - the engine was resolving `pending_marker_flip_owner_id` inside `_start_new_round()`, which stamped `marker_flip` with the next `round_index` and `weather` phase
- Validation:
  - `.venv/bin/python -m pytest GPT/test_rule_fixes.py::TrickSystemTests::test_round_end_marker_flip_is_last_event_of_previous_turn -q`

## 2026-05-02 Forced Draft Pick Auto-Resolution

- What changed:
  - updated `GPT/engine.py` so one-card draft pools are auto-resolved instead of routed through `choose_draft_card`
  - kept `draft_pick` event emission for forced picks so replay/order history still shows the full snake draft
  - added an engine regression asserting scheduled mark effects resolve before the target player's `turn_start`
  - promoted `mark_queued` to a first-class effect beat in the theater/stage UI and clarified the text as "target turn start first"
  - updated engine and runtime regression tests to expect final-character selection immediately after P1's first draft when P1's phase-2 draft has only one remaining card
  - clarified the game rules and Redis runtime playtest lessons: one-card draft pools are forced picks, not human prompts, and mark effects are target-turn-first effects
- Why:
  - live first-turn testing showed P1 choosing `만신`, then receiving a separate `건설업자` one-card draft prompt, then choosing between `만신/건설업자`
  - that second prompt was not a legal choice; it was the final remaining card in the reverse draft and should not interrupt priority iteration
  - mark selection could be recorded correctly but visually buried behind the next turn-start stage, making `만신`/`산적` targeting look like it had no payoff or had restarted the wrong actor
- Validation:
  - `.venv/bin/python -m pytest GPT/test_rule_fixes.py::TrickSystemTests::test_four_player_second_draft_uses_reverse_choice_order GPT/test_rule_fixes.py::TrickSystemTests::test_four_player_draft_starts_from_marker_owner_then_snakes_back -q`
  - `.venv/bin/python -m pytest GPT/test_rule_fixes.py::RuleFixTests::test_scheduled_mark_resolves_before_target_turn_start -q`
  - `.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_first_human_draft_resume_auto_resolves_forced_draft_before_final_character -q`
  - `npm --prefix apps/web run test -- src/features/theater/coreActionScene.spec.ts src/domain/selectors/streamSelectors.spec.ts --run`

## 2026-05-01 Turn / Draft Ordering And Mark Target Projection Fix

- What changed:
  - updated backend player `view_state` projection so the latest `round_order` owns visible player ordering after draft completes
  - updated the frontend raw stream fallback to apply the same `round_order` precedence when backend projection is absent
  - changed the match player strip to rank session seats by projected player order instead of always sorting by seat number
  - kept the explicit `none` / "지목 안 함" choice visible after mark-target candidate ordering
  - added server, web selector, and browser parity coverage for the order/projection path
- Why:
  - marker/draft order and actual turn order are different lifecycle contracts
  - the previous projection chain could show marker/draft order after the engine had already emitted a real turn order, and the final React layout could then erase the corrected order by sorting seats again
  - target candidate filtering was also too aggressive and made no-target selection disappear
- Validation:
  - `.venv/bin/python -m pytest apps/server/tests/test_view_state_player_selector.py -q`
  - `npm --prefix apps/web run test -- src/domain/selectors/streamSelectors.spec.ts --run`
  - `npm --prefix apps/web run e2e -- --project=chromium --grep "purchase and mark prompts render dedicated decision cards"`

## 2026-04-16 Room / Dedicated Server / Electron Client Architecture Plan

- What changed:
  - added the new cross-cutting architecture plan:
    - `docs/current/engineering/[PLAN]_ROOM_SERVER_CLIENT_ELECTRON_ARCHITECTURE.md`
  - the plan defines the next multiplayer product shape around:
    - dedicated server and client separation
    - room-first lifecycle above gameplay sessions
    - room number monotonic allocation and active-room title uniqueness
    - room-scoped auth / reconnection / token invalidation
    - ready/start custom-lobby flow with AI seats always ready
    - Electron standalone client packaging as the primary user-facing shell
    - nickname assignment on room create/join, with nickname as the primary in-game player-card identity
  - updated doc indexes so backend/frontend reading order now points to the new architecture plan
- Why:
  - the current session/bootstrap model is still optimized for local debugging and mixed host/join token flows rather than real human-vs-human multiplayer
  - the next implementation phase needs one canonical design source before code changes begin across server, transport, lobby UX, and desktop packaging
- API / contract impact:
  - design-only in this step
  - planned future public contract moves from raw session bootstrap toward:
    - `server -> rooms -> room membership -> game session`
- Validation:
  - no code tests run

## 2026-04-10 Backend Selector Migration Phase 3.12 Prompt Surface Core Action Completion

- What changed:
  - completed backend `view_state.prompt.active.surface` coverage for the last prompt-heavy action selectors that still leaked React-side interpretation:
    - `movement`
    - `trick_to_use` / `hidden_trick_card` via `surface.hand_choice`
    - `runaway_step_choice` via `surface.runaway_step`
  - `apps/server/src/domain/view_state/prompt_selector.py` now projects canonical movement card combinations, hand-choice trays, and runaway-step ids/targets directly from prompt `legal_choices` and `public_context`
  - `PromptOverlay` now prefers backend-projected movement / hand-choice / runaway-step surfaces before falling back to legacy local reconstruction, which keeps renderer logic closer to pure presentation
  - added shared selector fixtures for:
    - `packages/runtime-contracts/ws/examples/selector.prompt.movement_surface.json`
    - `packages/runtime-contracts/ws/examples/selector.prompt.hand_choice_surface.json`
    - `packages/runtime-contracts/ws/examples/selector.prompt.runaway_step_surface.json`
  - backend/frontend/engine tests now validate the same shared metadata for movement and runaway-step, while hand-choice uses the same backend/frontend shared fixture contract
- Why:
  - after earlier prompt-surface phases, the remaining complex React-owned interpretation islands were movement-card composition, trick-hand visibility/availability, and runaway-step ordering
  - this brings prompt rendering even closer to a reusable selector contract that alternate clients can consume with thin UI-only adapters
- API / contract impact:
  - additive only
  - updated:
    - `docs/current/api/online-game-api-spec.md`
    - `packages/runtime-contracts/ws/README.md`
