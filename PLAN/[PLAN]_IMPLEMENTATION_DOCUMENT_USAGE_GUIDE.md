# [PLAN] Implementation Document Usage Guide

Status: `ACTIVE`  
Owner: `Shared`  
Updated: `2026-03-31`  
Purpose: prevent document mixing during implementation

## Why This Exists

We now have legacy plans, active execution plans, and reference/proposal documents in parallel.
Without a strict reading order, implementation can drift or mix old assumptions.

This guide defines exactly:

- which document to read first
- which document is authoritative per topic
- which documents are reference-only

## Mandatory Reading Order (Before Coding)

Read in this exact order:

1. `PLAN/PLAN_STATUS_INDEX.md`
2. `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
3. `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
4. `docs/architecture/react-online-game-detailed-execution.md`
5. Task-specific spec:
   - UI/component work: `docs/frontend/react-component-structure-spec.md`
   - DI/interface work: `docs/backend/online-game-interface-spec.md`
   - transport/API work: `docs/api/online-game-api-spec.md`
   - gameplay parameter decoupling work: `docs/architecture/parameter-driven-runtime-decoupling.md`
   - pipeline consistency/coupling audit work: `docs/architecture/pipeline-consistency-and-coupling-audit.md`
   - frontend state-store architecture changes: `PLAN/[DECISION]_REACT_STATE_STORE_STRATEGY.md`
   - UI stack/styling architecture changes: `PLAN/[DECISION]_REACT_UI_STACK_STRATEGY.md`
   - release/cutover parity validation: `docs/architecture/legacy-vs-react-parity-checklist.md`
   - directory/file placement: `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`
   - legacy-path cleanup policy: `docs/architecture/legacy-reference-cleanup-policy.md`

If a task touches multiple areas, read all relevant task-specific specs.

## Authority Matrix

| Concern | Primary Source | Secondary Source |
|---|---|---|
| canonical active plan set | `PLAN/PLAN_STATUS_INDEX.md` | this guide |
| runtime/public event contract | `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md` | API/interface specs |
| phase order and milestones | `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md` | detailed execution plan |
| granular implementation backlog | `docs/architecture/react-online-game-detailed-execution.md` | plan status index |
| frontend component boundaries | `docs/frontend/react-component-structure-spec.md` | React top-level plan |
| backend/frontend DI ports | `docs/backend/online-game-interface-spec.md` | contract doc |
| REST/WS payloads | `docs/api/online-game-api-spec.md` | interface spec |
| gameplay parameter change impact | `docs/architecture/parameter-driven-runtime-decoupling.md` | API/interface specs |
| coupling/inconsistency/missing-test audit baseline | `docs/architecture/pipeline-consistency-and-coupling-audit.md` | decoupling plan + detailed execution |
| frontend state-store direction | `PLAN/[DECISION]_REACT_STATE_STORE_STRATEGY.md` | React top-level plan + detailed execution |
| UI stack/styling direction | `PLAN/[DECISION]_REACT_UI_STACK_STRATEGY.md` | React top-level plan |
| release parity/cutover readiness | `docs/architecture/legacy-vs-react-parity-checklist.md` | detailed execution + status index |
| where code should be placed | `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md` | React top-level plan |

## Conflict Resolution Rule

If documents conflict, resolve in this order:

1. Engine code and runtime truth (`GPT/engine.py`, `GPT/effect_handlers.py`)
2. `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
3. `docs/api/online-game-api-spec.md` and `docs/backend/online-game-interface-spec.md`
4. `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md` and detailed execution/component specs
5. proposal/reference documents

When conflict is found, fix docs in the same PR that implements code changes.

## Do-Not-Drive List (Reference Only)

The following can inform discussion but must not directly drive implementation tasks:

- `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md`
- `PLAN/[PROPOSAL]_VISUALIZATION_RUNTIME_DIRECTION.md`
- `PLAN/VISUALIZATION_GAME_PLAN.md`
- `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- all `[COMPLETE]_*.md`
- `PLAN/[SUPERSEDED]_GPT_ARCHITECTURE_REVIEW_AND_IMPROVEMENTS.md`

## Implementation Start Checklist

Before starting a coding task:

1. Confirm task scope in `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`.
2. Confirm data/contract fields in `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`.
3. Confirm API/interface shape in the relevant `[PLAN]_...SPEC.md`.
4. Confirm target directory in `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`.
5. If any ambiguity remains, update plan docs first, then implement.

## Migration Compatibility Rule

- Canonical detailed specs now live under `docs/*`.
- Existing `PLAN/[PLAN]_...` spec files are compatibility mirrors only.
- When updating a migrated spec, update `docs/*` first and then sync the matching `PLAN/` mirror in the same PR.

## Encoding Policy (Mandatory)

- `cp949` / `euc-kr` text encoding is not allowed.
- All tracked text files must be `UTF-8` without BOM.
- Enforcement:
  - `.editorconfig` sets UTF-8 baseline.
  - CI runs `python tools/encoding_gate.py` as a hard gate.

If a file is detected as non-UTF-8 or UTF-8 BOM, convert it in the same PR before merge.

## PR Checklist (Documentation Guard)

For each implementation PR:

1. Mention which spec documents were used.
2. Update changed spec files in the same PR.
3. If status changes, update `PLAN/PLAN_STATUS_INDEX.md`.
4. Avoid introducing new behavior based only on proposal/reference docs.
5. Keep text files UTF-8(no BOM); pass `tools/encoding_gate.py`.

## Validation Command Map (No-Ambiguity)

Use the following command families as canonical validation entrypoints:

- Contract/substrate validator path:
  - `python -m pytest GPT/test_visual_runtime_substrate.py`
- Replay renderer parity path (script-style runner, not pytest fixture mode):
  - `python GPT/test_replay_viewer.py`
- Backend runtime reliability batch:
  - `python -m pytest apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py`
- Frontend P2 reconnect/manifest/projection batch:
  - `cmd /c npm run test -- --run src/infra/ws/StreamClient.spec.ts src/domain/manifest/manifestRehydrate.spec.ts src/domain/manifest/manifestReconnectFlow.spec.ts src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts`
- Guardrails:
  - `python tools/parameter_manifest_gate.py --check`
  - `python tools/encoding_gate.py`
  - `python tools/legacy_path_audit.py --roots apps packages tools --strict`
