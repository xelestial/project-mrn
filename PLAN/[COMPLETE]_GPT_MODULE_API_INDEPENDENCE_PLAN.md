# GPT Module API Independence Plan

## Purpose
Raise module independence across `GPT/`, `CLAUDE/`, and future agents by treating the AI layer as an API surface instead of a single monolithic implementation.

This plan follows the Claude-side implementation direction in:
- `PLAN/CLAUDE_MULTI_AGENT_BATTLE_PLAN.md`
- `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`

The intent is:
- keep the engine stable
- allow per-player agent injection through a dispatcher
- reduce direct cross-module coupling inside GPT so the same policy can be wrapped, ported, or mirrored by Claude without copying large internal assumptions

## Non-Goals
- No engine rewrite
- No forced full parity between GPT and Claude internals in one step
- No broad strategy retuning outside behavior-preserving refactor seams unless explicitly requested

## Core Direction
The shared structure should behave like layered API contracts:

1. Engine-facing policy API
2. Agent wrapper API
3. Policy composition API
4. Typed context API
5. Decision module API
6. Logging and analytics API

Each layer should be usable without importing unrelated implementation detail from the next layer down.

## Runtime Boundary Rule
Cross-agent battles need a stricter boundary than ordinary wrapper reuse.

Shared across runtimes:
- engine-facing model modules that must agree on runtime types
- `config`
- `state`
- `characters`
- `trick_cards`
- `weather_cards`

Isolated per runtime:
- `ai_policy`
- `survival_common`
- `policy_hooks`
- `policy_groups`
- `policy_mark_utils`
- future decision/helper modules that encode agent-specific behavior

Reason:
- if `config.CellKind` or `state.PlayerState` are loaded twice, the engine can hand one runtime types that compare unequal to its own
- if `survival_common` or `ai_policy` are shared, Claude and GPT enhancements can silently leak into each other

So the goal is not "duplicate every module", but "share engine contracts, isolate policy logic".

## Current Coupling Problems

### 1. Monolithic decision ownership
`GPT/ai_policy.py` still owns:
- profile resolution
- survival interpretation
- character scoring
- purchase gating
- lap reward logic
- marker denial logic
- debug logging

This makes wrapper-level reuse possible, but module-level reuse difficult.

### 2. Dict-shaped context drift
`_generic_survival_context()` and adjacent helpers expose large `dict` payloads.
This is flexible, but it is not a stable API:
- field names can drift silently
- GPT and Claude can compute similar concepts with incompatible names
- wrappers cannot validate capability cleanly

### 3. Policy object as implementation bundle
`HeuristicPolicy` is currently both:
- the engine-facing policy adapter
- the full behavior implementation

That prevents easy recomposition into:
- shared wrappers
- agent loaders
- policy assets
- cross-module strategy bundles

### 4. Logging mixed into decision runtime
Decision tracing hooks are attached at the base policy layer, but the structure of debug payloads is still implementation-specific.
That makes simulation summaries reusable, but fine-grained decision analytics are not yet a stable inter-agent contract.

### 5. No intent continuity
The policy evaluates the current state repeatedly, but it does not keep a stable per-player plan.
As a result, one turn can optimize for expansion, the next for survival, and the next for lap value without any explicit transition rule.

## Target API Layers

### Layer A. Engine Policy Contract
Stable surface that the engine calls.

Target artifacts:
- `choose_*` method compatibility table
- `AbstractPlayerAgent` compatibility checklist
- `MultiAgentDispatcher` routing contract

Rule:
- engine only knows one policy object
- dispatcher only knows per-player agents
- per-player agents only need to satisfy the choose-method contract

### Layer B. Agent Wrapper Contract
Stable contract for wrapping GPT/Claude/Random/Gemini policies as player agents.

Target artifacts:
- `agent_id`
- `set_rng(rng)`
- engine-compatible `choose_*` delegation
- optional capability metadata

Recommended additions:
- `supports_debug_payloads() -> bool`
- `policy_profile_key() -> str`
- `decision_contract_version() -> str`

This allows battle runners and summaries to record agent-level metadata without reading internals.

### Layer C. Profile and Composition Contract
Profiles should be data, not hidden runtime branches.

Target artifacts:
- `PolicyProfileSpec`
- `PolicyProfileRegistry`
- future `PolicyAsset`
- future `PolicyAssetFactory`

Required rule:
- profile keys stay stable across GPT and Claude
- aliases may differ, but canonical profile keys must not drift

Recommended next extraction:
- move cleanup thresholds and shard checkpoint tuning into dedicated profile-side config objects
- keep runtime logic reading from config/spec instead of hard-coded mode name checks

### Layer D. Typed Context Contract
Shared typed context should become the main module API between evaluation/decision layers.

Minimum target contexts:
- `SurvivalSignals`
- `CleanupStrategyContext`
- future `TurnContext`

Recommended split:
- raw feature extraction
- context assembly
- decision consumption

Rule:
- decision modules consume typed context objects, not ad hoc dict keys

Immediate GPT opportunity:
- promote the new cleanup-aware strategy context into a reusable typed field group within future `policy/context`

### Layer E. Intent Memory Contract
The current GPT runtime remembers board state through `GameState`, but it does not remember policy intent in a structured way.

That causes:
- inconsistent use of character strengths
- local trick usage that ignores why a character was chosen
- movement and lap decisions that fail to follow through on the prior turn's plan

Target artifacts:
- `PlayerIntentState`
- `TurnPlanContext`
- `PlanTransitionReason`

Required rule:
- each player can keep a lightweight current plan inside the policy runtime
- plan state must be readable by all `choose_*` methods for that player
- plan state must not require engine-side ownership

Recommended fields:
- `plan_key`
- `locked_target_character`
- `locked_block_id`
- `resource_intent`
- `plan_confidence`
- `expires_after_round`

Recommended initial plan keys:
- `lap_engine`
- `survival_recovery`
- `controller_disrupt`
- `land_grab`
- `leader_denial`

This is the main missing contract if we want GPT or Claude policies to feel like one consistent pilot instead of one-off local heuristics.

### Layer F. Decision Module Contract
Each decision axis should be isolatable and testable.

Target modules:
- draft
- final character selection
- lap reward
- purchase
- trick use
- mark target
- marker flip

Required rule:
- one decision module should not need to import unrelated scoring branches directly

Desired interface shape:
```python
decision.choose(state, player, ctx, profile, helpers) -> Decision
```

This keeps wrappers stable even if internals evolve.

### Layer G. Analytics Contract
Logs and summaries should treat agents and policies as first-class identifiers.

Recommended additions:
- `agent_id` per player in per-game output
- `profile_key` per player in summary rows
- optional `decision_contract_version`
- optional `policy_asset_hash` when assets exist

This matters because cross-agent battles need analytics to remain comparable even when internal implementations diverge.

## Concrete Refactor Plan

### Phase 0. Compatibility Inventory
Document exact GPT `choose_*` signatures and compare them against Claude battle plan expectations.

Deliverables:
- `GPT choose_*` signature table
- mismatch list for wrapper adaptation
- wrapper-safe methods vs adaptation-required methods

### Phase 1. Agent-Safe Policy Surface
Make GPT `HeuristicPolicy` easier to wrap without pulling hidden assumptions.

Tasks:
- document canonical profile keys used by GPT
- expose lightweight metadata helpers
- ensure wrapper-safe construction path for one policy instance

Success criteria:
- Claude wrapper can instantiate GPT policy with no engine changes
- no direct import of GPT internal helper functions from Claude wrapper layer

### Phase 2. Typed Cleanup/Survival Context Extraction
Build on the new cleanup-aware context and move toward shared typed context inputs.

Tasks:
- define a reusable cleanup context contract
- standardize shard tier / cleanup stage naming
- reduce duplicated direct reads of raw survival dict fields

Success criteria:
- character/lap/marker logic consume the same cleanup context object
- Claude can mirror the same concept names even with different heuristics

### Phase 3. Decision Boundary Extraction
Separate engine-facing policy wrapper from decision logic.

Tasks:
- extract lap reward decider
- extract marker flip decider
- extract final character / draft decider
- keep `HeuristicPolicy` as orchestration shell

Success criteria:
- wrapper can continue delegating through `HeuristicPolicy`
- unit tests can target extracted decision modules without full-game setup

### Phase 4. Shared Battle Metadata Contract
Align simulation outputs with multi-agent battle needs.

Tasks:
- add `agent_id` and `profile_key` to strategy/player summaries
- keep old fields intact for backward compatibility
- document summary compatibility expectations

Success criteria:
- Claude battle runner can aggregate GPT and Claude players in one report without custom log patching

### Phase 5. PolicyAsset Readiness
Prepare GPT structure for future common asset loading without forcing full adoption immediately.

Tasks:
- identify current hard-coded strategy bundles
- map them to future `PolicyAsset` fields
- isolate constructor wiring from behavior code

Success criteria:
- moving from registry-backed profiles to asset-backed policy composition becomes incremental rather than invasive

## Required Shared Names
To preserve interop, the following names should stay aligned across GPT and Claude:
- profile keys: `balanced`, `control`, `growth`, `avoid_control`, `aggressive`, `token_opt`, `v3_gpt`, `v3_claude`
- cleanup stage names if standardized: `stable`, `strained`, `critical`, `meltdown`
- shard tiers if standardized: `low`, `buffered`, `stable`, `overflow`
- simulation metadata keys: `agent_id`, `profile_key`, `policy_mode`, `lap_policy_mode`

## Risks

### Risk 1. Wrapper works but internals remain brittle
Mitigation:
- prioritize typed context and decider extraction before broad strategy changes

### Risk 2. GPT and Claude use same names with different meanings
Mitigation:
- document semantic meaning for stage/tier keys in plan docs before wider adoption

### Risk 3. Analytics drift across simulators
Mitigation:
- add compatibility metadata without removing existing fields

### Risk 4. Battle integration depends on ai_policy internals
Mitigation:
- keep wrappers thin and use only the public choose-method contract

## Immediate Next Actions
1. Build a `choose_*` compatibility checklist for GPT vs Claude wrapper expectations.
2. Add a small metadata surface to GPT policy objects for `agent_id/profile_key`.
3. Extract the cleanup-aware strategy context into a more explicit shared API shape under future `policy/context`.
4. Add `PlayerIntentState` and `TurnPlanContext` as policy-internal API objects.
5. Route high-value decisions through plan-aware helpers before broader asset extraction.
6. Plan summary/log field additions for multi-agent battle compatibility.
7. Replace direct cross-repo wrapper imports with a runtime loader that isolates policy-local modules while reusing shared engine-contract modules.

## Working Rule
If a refactor does not make it easier to:
- wrap GPT as an independent player agent
- mirror the same concept names in Claude
- test one decision axis without loading the entire policy monolith

then it is not improving architectural independence enough.
