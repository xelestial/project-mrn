# [COMPLETE] GPT Scoring / Evaluator Refactor

## Intent
Finish the `scoring/evaluator` refactor axis by making the active character-scoring paths run through `policy/evaluator` instead of relying on the legacy inline scoring bodies in `GPT/ai_policy.py`.

## Scope
- `GPT/ai_policy.py`
- `GPT/policy/evaluator/character_scoring.py`
- `PLAN/GPT_ARCHITECTURE_ALIGNMENT_TASK.md`

## What Was Completed
- Added evaluator imports for the active character-scoring path inside `GPT/ai_policy.py`
- Added `GPT/policy/evaluator/runtime_bridge.py` so the active scoring bodies can live outside `GPT/ai_policy.py`
- Replaced the active `_character_score_breakdown(...)` live path with a late-override implementation that composes:
  - `evaluate_v1_character_structural_rules(...)`
  - existing mark-risk and rent-pressure helpers
- Replaced the active `_character_score_breakdown_v2(...)` live path with a late-override implementation that composes:
  - `evaluate_v2_expansion_rules(...)`
  - `evaluate_v2_route_rules(...)`
  - `evaluate_v2_profile_rules(...)`
  - `evaluate_v3_character_rules(...)`
  - `evaluate_v2_tactical_rules(...)`
  - `evaluate_v2_emergency_risk_rules(...)`
  - `evaluate_v2_post_risk_rules(...)`
  - `evaluate_v2_tail_threat_rules(...)`
  - `evaluate_v2_rent_tail_rules(...)`
  - `evaluate_v2_uhsa_tail_rules(...)`
- Replaced the active `_target_score_breakdown(...)` and `_target_score_breakdown_v2(...)` live paths with runtime-bridge implementations so target scoring also runs outside the main monolith
- Kept the old monolithic scoring bodies in place as legacy fallback/history, but removed them from the active runtime path by overriding the methods later in the class

## Result
- The active GPT character-scoring runtime now routes through the evaluator layer
- The active GPT target-scoring runtime now also routes through the evaluator/runtime-bridge layer
- `GPT/ai_policy.py` still contains legacy scoring bodies, but they are no longer the live scoring implementation
- The remaining architecture work is now mainly:
  - legacy-body cleanup
  - final monolith reduction
  - composition polish

## Verification
- `py_compile` passed for:
  - `GPT/ai_policy.py`
  - `GPT/policy/evaluator/character_scoring.py`
  - `GPT/test_policy_runtime_modules.py`
- Regression suite passed:
  - `GPT/test_policy_runtime_modules.py`
  - `GPT/test_ai_policy_v3_gpt_strategy_model.py`
  - `GPT/test_multi_agent.py`
  - `GPT/test_ai_policy_survival_guardrails.py`
  - `GPT/test_policy_profile_registry.py`
- Result:
  - `131 passed, 1 warning`

## Residual Note
- The remaining warning is the existing `.pytest_cache` permission warning and is unrelated to the scoring/evaluator refactor itself.
