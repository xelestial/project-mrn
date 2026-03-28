# [COMPLETE] GPT Legacy Body Cleanup

## Intent
- Finish the post-bridge cleanup stage after helper/wrapper and scoring/evaluator refactors.
- Make it explicit that dormant monolithic `choose_*` bodies in `GPT/ai_policy.py` are no longer authoritative live paths.

## What Changed
- Active `choose_*` live paths already delegated through `policy/decision/runtime_bridge.py`.
- Shadowed legacy `choose_*` bodies inside `GPT/ai_policy.py` were neutralized with explicit dead-body guards:
  - `raise NotImplementedError("legacy body removed; live path delegates later")`
- This was applied to the dormant monolithic bodies that remained after runtime-bridge extraction, including the old:
  - trick use
  - specific trick reward
  - burden exchange on supply
  - hidden trick selection
  - movement
  - lap reward
  - coin placement
  - purchase
  - draft card
  - final character
  - mark target
  - active flip
  - geo bonus

## Why This Is Safe
- The authoritative live decision path is now the later runtime-bridge delegate methods.
- The guarded bodies are shadowed/dormant and are no longer the active implementation surface.
- Guarding them is safer than large mojibake-prone deletions inside `GPT/ai_policy.py`.

## Result
- `GPT/ai_policy.py` is less ambiguous: active logic is bridge-backed, dormant monolithic bodies are clearly marked dead.
- Future cleanup can delete dead sections incrementally without risking behavior changes.

## Verification
- `py_compile` passed for `GPT/ai_policy.py`
- Target regression suite passed: `147 passed`
- Remaining warning is the existing `.pytest_cache` permission warning only
