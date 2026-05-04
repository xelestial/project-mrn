# Runtime Contract And External Checks Evidence - 2026-05-04

Status: CURRENT EVIDENCE
Owner: Codex

## Scope

This records the verification pass for the requested remaining items:

1. external platform Redis topology verification
2. effect-cause visibility final confirmation
3. runtime contract maintenance
4. external AI endpoint verification
5. playtest evidence documentation

The final long-form manual 2H+2AI and 4-human playtests were not part of this
pass and remain a separate closure item.

## 1. Redis Platform Topology

Result: local contract path is valid; actual external topology is still blocked
until a filled platform manifest exists.

Evidence:

```bash
python3 tools/scripts/redis_platform_smoke_from_manifest.py --validate-only
```

Outcome:

- passed against `deploy/redis-runtime/local-platform-managed.smoke.json`
- `target_topology_kind`: `local_smoke`
- `rollout_scope`: `local_contract_proof`
- `external_topology_ready`: `false`
- roles: `server`, `prompt-timeout-worker`, `command-wakeup-worker`
- worker health command count: `2`
- expected Redis hash tag: `runtime-platform-decision-smoke`

External-topology guard:

```bash
python3 tools/scripts/redis_platform_smoke_from_manifest.py --validate-only --require-external-topology
```

Outcome:

- failed as expected with:
  `external platform manifest is required; local smoke manifests only prove the contract locally`

Repository manifests present:

- `deploy/redis-runtime/local-platform-managed.smoke.json`
- `deploy/redis-runtime/platform-managed.manifest.template.json`
- `deploy/redis-runtime/process-contract.json`

Conclusion:

- the local platform-managed smoke manifest cannot be mistaken for production or
  staging evidence
- actual external Redis topology verification requires a filled manifest copied
  from `platform-managed.manifest.template.json` with the target platform's
  restart and worker exec commands

## 2. Effect-Cause Visibility

Result: automated backend, frontend, and Playwright gates pass.

Backend projection:

```bash
PYTHONPATH=.:GPT .venv/bin/python -m pytest \
  apps/server/tests/test_view_state_prompt_selector.py::ViewStatePromptSelectorTests::test_build_prompt_view_state_projects_effect_context \
  apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_effect_context_covers_remaining_effect_prompt_boundaries \
  -q
```

Outcome: `2 passed, 5 subtests passed`

Frontend selector and overlay:

```bash
npm --prefix apps/web test -- --run \
  src/features/prompt/promptEffectContextDisplay.spec.ts \
  src/domain/selectors/promptSelectors.spec.ts
```

Outcome: `2 passed`, `87 passed`

Human runtime UI gate:

```bash
npm --prefix apps/web run e2e:human-runtime
```

Outcome: `18 passed`

Relevant covered examples include:

- fortune cash loss cause readability
- innkeeper lap bonus breakdown readability
- Manshin successful mark readability
- Baksu burden-transfer readability
- matchmaker adjacent purchase prompt cause and double-price context
- mixed participant worker success and fallback continuity

Conclusion:

- backend-projected `effect_context` survives into frontend prompt rendering
- automated browser evidence now covers the main effect-cause UI classes
- manual long-form play remains useful for human comprehension, but the
  contract path itself is passing

## 3. Runtime Contract Maintenance

Result: current modular-runtime and backend semantic contract regressions pass.

```bash
PYTHONPATH=.:GPT .venv/bin/python -m pytest \
  GPT/test_runtime_sequence_modules.py \
  GPT/test_runtime_simultaneous_modules.py \
  GPT/test_runtime_sequence_handlers.py \
  GPT/test_runtime_effect_inventory.py \
  GPT/test_runtime_prompt_continuation.py \
  apps/server/tests/test_prompt_module_continuation.py \
  apps/server/tests/test_runtime_semantic_guard.py \
  apps/server/tests/test_stream_module_idempotency.py \
  tests/test_module_runtime_playtest_matrix_doc.py \
  tests/test_redis_runtime_deployment_manifest.py \
  -q
```

Outcome: `132 passed`

Additional prompt/runtime contract examples:

```bash
PYTHONPATH=.:GPT .venv/bin/python -m pytest \
  apps/server/tests/test_runtime_contract_examples.py \
  apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_purchase_tile_method_spec_keeps_request_context_and_choice_in_sync \
  apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_specific_reward_and_runaway_specs_keep_specialized_contracts \
  -q
```

Outcome: `19 passed`

Conclusion:

- sequence modules, simultaneous modules, semantic guards, prompt continuation,
  stream idempotency, and runtime playtest matrix documentation are in sync
- no new action/prompt ownership drift was detected in this pass

## 4. External AI Endpoint

Result: real localhost HTTP worker path and runbook endpoint smoke pass.

Runtime-service real worker coverage:

```bash
PYTHONPATH=.:GPT .venv/bin/python -m pytest \
  apps/server/tests/test_external_ai_worker_api.py \
  apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_http_external_transport_reaches_real_worker_over_localhost \
  apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_http_external_transport_reaches_real_priority_worker_over_localhost \
  -q
```

Outcome: `13 passed`

Runbook priority worker:

```bash
.venv/bin/python tools/run_external_ai_worker.py \
  --host 127.0.0.1 \
  --port 8011 \
  --worker-id local-priority-bot \
  --policy-mode heuristic_v3_gpt \
  --worker-profile priority_scored \
  --worker-adapter priority_score_v1
```

Endpoint smoke:

```bash
.venv/bin/python tools/check_external_ai_endpoint.py \
  --base-url http://127.0.0.1:8011 \
  --require-ready \
  --require-profile priority_scored \
  --require-adapter priority_score_v1 \
  --require-policy-class PriorityScoredPolicy \
  --require-decision-style priority_scored_contract \
  --require-request-type movement \
  --require-request-type purchase_tile
```

Outcome:

- `OK: external AI endpoint passed smoke checks`
- health reported:
  - `worker_id`: `local-priority-bot`
  - `ready`: `true`
  - `policy_class`: `PriorityScoredPolicy`
  - `worker_profile`: `priority_scored`
  - `worker_adapter`: `priority_score_v1`
  - `decision_style`: `priority_scored_contract`
  - supported transports include `http`
  - supported request types include `movement` and `purchase_tile`
- decision smoke returned legal choice `yes` for the purchase-tile request

Conclusion:

- local real HTTP external AI endpoint behavior is verified
- a remote non-local external AI endpoint still requires its actual base URL and
  credential/config values before it can be called evidence

## 5. Remaining Closure Items

1. Fill a real platform Redis manifest and run:

```bash
python3 tools/scripts/redis_platform_smoke_from_manifest.py \
  --manifest <filled-platform-manifest.json> \
  --validate-only \
  --require-external-topology
```

Then run the same manifest with `--run --evidence-output <artifact>.json`.

2. Run final long-form manual playtests:

- 2 human + 2 AI with external AI configured for at least one AI seat
- 4 human where all blocking prompts are manually resolved

3. Attach the resulting screenshots/logs/evidence artifacts to a follow-up
playtest evidence document.
