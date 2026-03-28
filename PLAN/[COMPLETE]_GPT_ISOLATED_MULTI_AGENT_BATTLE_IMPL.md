# [COMPLETE] GPT Isolated Multi-Agent Battle Implementation

## Intent
Allow Claude-strengthened AI and GPT-strengthened AI to coexist as independent player runtimes inside the same engine process without changing the engine contract.

The specific goal for this completed step was:
- implement `claude vs gpt` battle support under `GPT/`
- follow the Claude-side multi-agent wrapper/dispatcher shape
- prevent GPT-only policy logic such as `CleanupStrategyContext` from leaking into the Claude runtime
- keep engine-facing model types shared so runtime compatibility remains intact

## Scope
Implemented under:
- `GPT/`
- `PLAN/`

Not modified:
- `CLAUDE/`
- engine runtime behavior

## Design Decision
The runtime boundary is intentionally split in two:

Shared engine-contract modules:
- `config`
- `state`
- `characters`
- `trick_cards`
- `weather_cards`

Isolated policy-runtime modules:
- `ai_policy`
- `survival_common`
- `policy_hooks`
- `policy_groups`
- `policy_mark_utils`

Reason:
- duplicating engine-contract modules risks enum/type mismatch against the active engine
- sharing policy-runtime modules risks Claude/GPT strategy leakage in the same process

## Implemented Files
### GPT multi-agent runtime
- `GPT/multi_agent/base_agent.py`
- `GPT/multi_agent/dispatcher.py`
- `GPT/multi_agent/agent_loader.py`
- `GPT/multi_agent/gpt_agent.py`
- `GPT/multi_agent/claude_agent.py`
- `GPT/multi_agent/runtime_loader.py`
- `GPT/multi_agent/__init__.py`

### GPT battle runner
- `GPT/battle.py`

### Tests
- `GPT/test_multi_agent.py`

### Planning updates
- `PLAN/GPT_ARCHITECTURE_ALIGNMENT_TASK.md`
- `PLAN/GPT_MODULE_API_INDEPENDENCE_PLAN.md`

## What Was Implemented
### 1. Claude-vs-GPT battle runner
Added a GPT-side battle runner using:
- `AbstractPlayerAgent`
- `MultiAgentDispatcher`
- `make_agent(spec)`

Supported lineup examples:
- `claude:v3_claude`
- `gpt:v3_gpt`

### 2. Isolated policy-runtime loader
Added `GPT/multi_agent/runtime_loader.py`.

This loader:
- loads policy-local modules under runtime-specific alias names
- temporarily maps plain module names only during import resolution
- restores the host module table after runtime load completes
- caches loaded runtimes for reuse

Result:
- Claude policy logic can keep its own `survival_common` and `ai_policy`
- GPT policy logic can keep its own `survival_common` and `ai_policy`
- host `survival_common` remains GPT-owned after Claude agent creation

### 3. Agent wrappers moved to runtime handles
`ClaudePlayerAgent` and `GptPlayerAgent` now instantiate `HeuristicPolicy` through isolated runtime handles instead of relying on direct path insertion shortcuts.

### 4. Regression coverage for module isolation
Added tests that verify:
- host `survival_common` remains the GPT version after loading a Claude agent
- Claude and GPT policy classes come from different isolated module namespaces
- dispatcher construction still works
- one full game can run with Claude and GPT mixed in the same match
- battle summary output still includes the multi-agent lineup

## Verification
Executed with Python 3.14:

### Multi-agent tests
- `GPT/test_multi_agent.py`
- Result: `12 passed`

### Existing GPT regression tests
- `GPT/test_ai_policy_v3_gpt_strategy_model.py`
- `GPT/test_ai_policy_cleanup_model.py`
- `GPT/test_policy_profile_registry.py`
- `GPT/test_text_encoding.py`
- Result: `16 passed`

### Smoke battle
- command equivalent: `python GPT/battle.py --simulations 1 --seed 42 --output-dir GPT/_codex_runs/battle_isolated_smoke`
- Result: success

Output:
- `GPT/_codex_runs/battle_isolated_smoke/summary.json`

## Smoke Battle Result Snapshot
- lineup:
  - player 1: `claude:heuristic_v2_v3_claude`
  - player 2: `gpt:heuristic_v3_gpt`
  - player 3: `gpt:heuristic_v3_gpt`
  - player 4: `gpt:heuristic_v3_gpt`
- games: `1`
- end reason: `F_THRESHOLD`
- winner seat: player `3`
- summary recorded `policy_mode = multi_agent`
- summary recorded `agent_lineup`

## Result
This step is complete.

Completed outcome:
- GPT now has a working Claude-vs-GPT multi-agent battle path
- Claude and GPT policy logic can coexist more safely in one process
- the known `survival_common` drift risk is addressed at the policy-runtime layer

Still intentionally not claimed as complete:
- full package-level namespace isolation for every module in both repos
- long-run statistical validation beyond smoke coverage
- PR/merge bookkeeping
