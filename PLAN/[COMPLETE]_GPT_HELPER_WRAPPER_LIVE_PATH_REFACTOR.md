# [COMPLETE] GPT Helper/Wrapper Live-Path Refactor

## Intent
Finish the GPT-side refactor axis that moves live decision paths out of monolithic inline logic in `GPT/ai_policy.py` and into helper/wrapper modules under `GPT/policy/`.

This completion only covers the `helper/wrapper live-path extraction` axis.
It does **not** mean the entire GPT architecture refactor is complete.

## Completed Scope

### Decision-layer live paths
The active runtime paths now route through shared helpers for:
- character choice packaging
- trick usage resolution
- movement choice resolution
- lap reward resolution
- purchase benefit/window/result/debug packaging
- mark target filtering, weighting, and resolution
- active flip resolution
- hidden trick resolution
- trick reward resolution
- support-style choices such as doctrine relief, burden exchange, geo bonus, and distress/escape decisions

### Trait / environment indirection
The active runtime paths now rely on helper-backed trait and environment modules for:
- character face / role predicates
- low-cash role grouping
- money-drain detection
- weather / fortune cleanup tables
- live cleanup-related environment checks

### Live-path shell reduction
`GPT/ai_policy.py` remains the orchestration center, but active end-of-path selection and packaging logic is now substantially routed through:
- `GPT/policy/decision/`
- `GPT/policy/character_traits.py`
- `GPT/policy/environment_traits.py`
- `GPT/policy/context/`

### Purchase / lap reward completion for this axis
The active branches of:
- `choose_purchase_tile(...)`
- `choose_lap_reward(...)`

now route through shared helper chains strongly enough that the remaining work in those areas is primarily:
- legacy scoring cleanup
- evaluator extraction
- residual inline body reduction

rather than more helper/wrapper packaging work.

## Main Files Involved
- `GPT/ai_policy.py`
- `GPT/policy/character_traits.py`
- `GPT/policy/environment_traits.py`
- `GPT/policy/context/turn_plan.py`
- `GPT/policy/context/survival_context.py`
- `GPT/policy/decision/active_flip.py`
- `GPT/policy/decision/character_choice.py`
- `GPT/policy/decision/coin_placement.py`
- `GPT/policy/decision/hidden_trick.py`
- `GPT/policy/decision/lap_reward.py`
- `GPT/policy/decision/mark_target.py`
- `GPT/policy/decision/movement.py`
- `GPT/policy/decision/purchase.py`
- `GPT/policy/decision/scored_choice.py`
- `GPT/policy/decision/support_choices.py`
- `GPT/policy/decision/trick_reward.py`
- `GPT/policy/decision/trick_usage.py`
- `GPT/test_policy_runtime_modules.py`
- `PLAN/GPT_ARCHITECTURE_ALIGNMENT_TASK.md`

## Verification
Verified with:

```powershell
& "C:\Users\SIL-EDITOR\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m py_compile GPT/ai_policy.py
& "C:\Users\SIL-EDITOR\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m pytest -q GPT/test_policy_runtime_modules.py GPT/test_ai_policy_v3_gpt_strategy_model.py GPT/test_multi_agent.py GPT/test_ai_policy_survival_guardrails.py GPT/test_policy_profile_registry.py
```

Result:
- `131 passed`
- `1 warning`

Known warning:
- `.pytest_cache` creation permission warning in the workspace root

## Outcome
The `helper/wrapper live-path extraction` topic is complete enough to close as a refactor track.

The next architectural work should be treated as a different track:
- evaluator / legacy scoring extraction
- remaining monolith reduction inside `_character_score_breakdown*`
- residual mojibake-heavy inline body cleanup where safe
