# React/FastAPI Release Playbook

Status: `ACTIVE`  
Updated: `2026-03-31`  
Scope: `apps/server`, `apps/web`, runtime contract docs

## Purpose

Provide one release-time runbook for:

- contract/runtime safety gates
- replay/live parity gates
- documentation synchronization gates

This playbook is the operational closure for P4 migration polish.

## Release Flow

1. Sync branch with latest `main`.
2. Run guardrails (encoding, legacy path, manifest snapshot).
3. Run backend reliability batch.
4. Run frontend reconnect/manifest/projection batch.
5. Run replay substrate/parity checks.
6. Confirm parity checklist evidence paths.
7. Confirm docs/PLAN mirror synchronization.
8. Merge.

## Command Gates (Required)

## A. Guardrails

- `python tools/parameter_manifest_gate.py --check`
- `python tools/encoding_gate.py`
- `python tools/legacy_path_audit.py --roots apps packages tools --strict`

## B. Backend Reliability

- `python -m pytest apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py`

## C. Frontend Reconnect/Manifest/Projection

- `cmd /c npm run test -- --run src/infra/ws/StreamClient.spec.ts src/domain/manifest/manifestRehydrate.spec.ts src/domain/manifest/manifestReconnectFlow.spec.ts src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts`

## D. Replay/Substrate Parity

- `python -m pytest GPT/test_visual_runtime_substrate.py`
- `python GPT/test_replay_viewer.py`

## E. Optional Full Browser Parity

- `cmd /c npm run e2e`

## Documentation Gates (Required)

Before merge, verify:

1. `docs/*` canonical specs are updated first.
2. matching `PLAN/[PLAN]_...` mirrors are synchronized in the same PR.
3. `PLAN/PLAN_STATUS_INDEX.md` reflects the latest closure/progress state.
4. `docs/architecture/legacy-vs-react-parity-checklist.md` is updated if parity-impacting behavior changed.

## Evidence Recording

Attach command outputs (summary lines) to PR body.

Minimum evidence:

- guardrail pass summary
- backend test summary
- frontend test summary
- replay/substrate parity summary

If any gate is skipped, include explicit reason and follow-up owner.

## Latest Execution Log (`2026-03-31`)

- Guardrails:
  - `parameter_manifest_gate --check`: pass
  - `encoding_gate --check`: pass
  - `legacy_path_audit --strict`: pass (`GPT/`, `CLAUDE/`, `frontend/` all zero)
- Backend reliability batch:
  - `14 passed, 9 skipped`
- Frontend reconnect/manifest/projection batch:
  - `23 passed`
- Replay/substrate parity batch:
  - `GPT/test_visual_runtime_substrate.py`: `2 passed`
  - `GPT/test_replay_viewer.py`: `Phase 2: ALL TESTS PASSED`

## Rollback Rule

If release gate fails after runtime/API/schema changes:

1. revert the failing merge candidate branch changes (not ad-hoc file edits on `main`)
2. reopen with corrected contract/tests/docs in one PR
3. re-run the full gate sequence
