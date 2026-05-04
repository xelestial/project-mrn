# Prompt Effect Context Projection Plan

## 1. Goal

Carry the immediate cause/effect context of a decision prompt from backend decision construction through backend view_state and frontend prompt rendering.

This closes the remaining modular boundary where the UI had to infer prompt cause from recent event history. Prompts created by movement, character marks, trick cards, supply/burden handling, or lap rewards should describe their cause in the prompt payload itself.

## 2. Contract

`public_context.effect_context` is authored by the backend decision gateway. Backend `prompt.view_state.active.effect_context` normalizes and projects it. The frontend selector parses it into camelCase and `App` prefers it over event-history fallback context.

Minimum fields:

- `label`: short source label.
- `detail`: readable reason or outcome.
- `attribution`: optional family label.
- `tone`: `move`, `effect`, or `economy`.
- `source`: machine source family.
- `intent`: machine intent.
- `enhanced`: whether the prompt was explicitly enriched.

Optional fields:

- `source_player_id`
- `source_family`
- `source_name`
- `resource_delta`

## 3. Verification

1. Add backend selector coverage that `effect_context` survives prompt view_state projection.
2. Add backend decision gateway coverage for lap reward and trick tile target prompts.
3. Add frontend selector coverage that backend view_state `effect_context` becomes a prompt view model.
4. Run focused Python and frontend tests.

## 4. Completed Implementation

1. Backend prompt payloads now project `public_context.effect_context` for effect-driven prompts.
   Covered prompt types include lap reward, trick tile target, mark target, purchase tile, pabal dice mode, doctrine relief, active flip, specific trick reward, burden exchange, geo bonus, and runaway step choice.
2. Backend `effect_context` includes compact machine-readable source metadata plus human-readable labels/details so the frontend does not infer cause from recent event history.
3. Frontend prompt selectors now treat backend `view_state.prompt.active.effect_context` as backend-owned data.
   They no longer synthesize backend active prompt context from `public_context.effect_context` when the normalized active field is absent.
4. Shared selector fixtures were updated so projected prompt surfaces preserve backend-authored `effect_context`.

## 5. Structural Guards Added

1. `specific_trick_reward` is now declared in the runtime effect inventory as a `TrickResolveModule` sequence-bound prompt.
2. Runtime resume matrix coverage no longer uses fake module names such as `MovementDecisionModule` or `SpecificTrickRewardModule`.
   Movement resumes through `DiceRollModule`, and specific trick rewards resume through `TrickResolveModule`.
3. The resume matrix now covers `pabal_dice_mode` and round-frame `active_flip`.
   This verifies that active card flipping stays tied to `RoundEndCardFlipModule` rather than a turn frame.
4. Effect inventory tests assert that all effect prompt contracts used by this path have explicit resumable module boundaries.

## 6. Verification Log

1. `.venv/bin/python -m pytest GPT/test_human_policy_prompt_payloads.py -q`
   Result: 7 passed.
2. `.venv/bin/python -m pytest GPT/test_runtime_effect_inventory.py -q`
   Result: 14 passed.
3. `.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k "lap_reward_context or trick_tile_target_context or matchmaker_purchase_context or effect_context_covers_remaining or module_resume_prompt_boundary_matrix or module_resume_preserves_purchase_sequence or module_resume_preserves_lap_reward_sequence" -q`
   Result: 7 passed, 111 deselected, 14 subtests passed.
4. `npm --prefix apps/web test -- promptSelectors.spec.ts`
   Result: 79 passed.
5. `npm --prefix apps/web run build`
   Result: passed. Vite reported the existing large chunk warning for bundled assets.
