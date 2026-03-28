# [COMPLETE] GPT Refactor Polish

## Scope
- Final polish after the helper/wrapper, scoring/evaluator, runtime-bridge, and legacy-body cleanup phases.

## Final State
- Active `choose_*` decision paths are delegated through runtime bridge helpers.
- Active scoring paths are delegated through evaluator/runtime-bridge layers.
- Shadowed monolithic `choose_*` bodies inside `GPT/ai_policy.py` are explicitly marked as dead where they are no longer authoritative.
- The remaining contents of `GPT/ai_policy.py` are no longer architecture blockers; they are optional maintenance cleanup only.

## What Counts As Done
- No active gameplay decision path depends on the dormant monolithic `choose_*` implementations.
- Runtime regression coverage continues to pass after the cleanup.
- The architecture task can now treat the refactor as complete rather than in-progress.

## Optional Follow-Up
- Physical deletion of dead legacy bodies
- Additional file shrinking / import cleanup
- Cosmetic organization of large files

## Verification
- `py_compile` passed
- Target regression suite passed: `147 passed`
- Remaining warning is the existing `.pytest_cache` permission warning only
