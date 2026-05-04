# Human Game Pipelines And Runtime Reference

Status: ACTIVE  
Updated: 2026-05-05

## 1. Round Pipeline

Round work is scheduled as modules:

1. weather setup
2. draft
3. turn order scheduling
4. player turns
5. simultaneous responses when required
6. round-end card flip

The scheduler advances only after the active module and all child frames complete.

## 2. Player Turn Pipeline

A player turn is a `PlayerTurnModule` with child work:

1. marker-before effects
2. character start module
3. target adjudication
4. dice/movement
5. arrival/tile effects
6. fortune/trick follow-ups
7. turn-end snapshot

Child `SequenceFrame` modules may add follow-up work, but completed parent turn modules are not re-run.

## 3. Prompt Pipeline

Prompt exposure is backend-mediated:

1. engine reaches a prompt-capable module
2. backend stores the continuation checkpoint in Redis
3. backend publishes the prompt
4. frontend renders legal choices
5. backend validates the submitted decision against Redis
6. engine resumes the module cursor

## 4. Simultaneous Response Pipeline

All-player responses use `SimultaneousResolutionFrame` and `SimultaneousPromptBatchContinuation`.

The batch completes when every required player response is stored, then the engine resolves the batch once.

## 5. Current Source Map

- engine modules: `engine/runtime_modules/`
- rule/effect handlers: `engine/effect_handlers.py`, `engine/tile_effects.py`
- prompt contracts: `engine/viewer/prompt_contract.py`
- backend runtime service: `apps/server/src/services/runtime_service.py`
- backend semantic guard: `apps/server/src/domain/runtime_semantic_guard.py`
- frontend stream selectors: `apps/web/src/domain/selectors/`
- runtime contract fixtures: `packages/runtime-contracts/ws/examples/`

## 6. Verification

Use the focused runtime/server/web suites before declaring runtime structure complete.
