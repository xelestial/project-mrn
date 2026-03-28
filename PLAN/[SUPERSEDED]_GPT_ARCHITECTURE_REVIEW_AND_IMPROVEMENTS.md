# GPT Architecture Review And Improvements

## Purpose
Review the current GPT-side architecture against the shared architecture declaration and identify concrete improvements that preserve engine compatibility, improve Claude/GPT interoperability, and reduce coupling through dependency injection.

## Review Basis
- `ARCHITECTURE_REFACTOR_AGREED_SPEC_v1_0.md`
- `ARCHITECTURE_IMPL_GUIDE_v1_0.md`
- `COLLAB_SPEC_v0_3.md`
- Current GPT runtime structure under `GPT/`

## Executive Summary
The current GPT implementation already contains useful extraction seams such as:
- `survival_common.py`
- `policy_hooks.py`
- `policy_mark_utils.py`
- `log_pipeline.py`

However, the main AI runtime is still centered around `ai_policy.py`, and the most important composition contracts remain hard-coded:
- profile selection is string-mode driven
- weights and character values are class constants
- arena composition directly instantiates policy classes
- hooks are mostly logging-oriented, not composition-oriented
- event handlers are event-driven, but default registration is still hard-wired inside engine construction

This means the project already has the right directional ingredients, but not yet the shared architecture shape needed for long-term Claude/GPT parallel evolution.

## Current Strengths

### 1. Engine already exposes useful injection boundaries
- `GameEngine` uses `EventDispatcher`
- effect resolution is already event-driven
- policy decisions are already called through `choose_*` entrypoints
- rule scripts already act as a runtime extension layer

This is good because it means we do not need a deep engine rewrite to reach the target architecture.

### 2. Survival logic has begun to separate from profile logic
- `survival_common.py` is an early version of the spec's survival module split
- the code already distinguishes between generic survival signals and action decisions

This supports the agreed architecture direction where profile and survival should not be fused.

### 3. Logs and event traces are rich enough to support collaborative iteration
- semantic event trace exists
- decision debug payloads exist
- action logs and forensic output exist

This makes it realistic to refactor incrementally without losing behavior visibility.

## Main Gaps

### 1. AI behavior profiles are still hard-coded, not asset-driven
Current GPT behavior profiles are still defined primarily by:
- `character_policy_mode`
- `lap_policy_mode`
- `PROFILE_WEIGHTS`
- `character_values`
- string parsing inside `_profile_from_mode()`

Problems:
- profile identity is not canonicalized through a registry
- alias compatibility is informal instead of explicit
- GPT and Claude can drift in naming even if they intend the same profile
- strategy composition is hidden inside procedural code instead of external assets

Required improvement:
- introduce `PolicyProfileSpec`
- introduce `ProfileRegistry`
- move weight/base-value/group/risk data toward external profile data files
- treat mode strings as compatibility aliases, not the primary source of truth

### 2. Composition root is too coupled to concrete classes
`ArenaPolicy` currently creates `HeuristicPolicy` instances directly.

Problems:
- assembly logic is embedded in runtime policy objects
- there is no neutral factory layer that Claude and GPT can both target
- it is hard to compare "same asset, different implementation" because the composition path is not explicit

Required improvement:
- create `PolicyAsset`
- create `PolicyFactory`
- move runtime assembly into a composition root that resolves registries and assets
- preserve current engine contract by returning objects with the same `choose_*` surface

### 3. Hooks are observability-first, not behavior-composition-first
The current policy hook system is useful for tracing:
- `policy.before_decision`
- `policy.after_decision`

Problems:
- no structured override contract
- no short-circuit or veto model
- no typed decision payload schema
- no unregister or priority
- too much coupling to `choose_*` method naming convention

Required improvement:
- split tracing hooks from behavior hooks
- define explicit policy extension points such as:
  - `decision.context.build`
  - `decision.before_resolve`
  - `decision.override`
  - `decision.after_resolve`
- keep logging hooks as one subscriber, not the core abstraction

### 4. Event-driven design exists, but handler composition is still too static
`EventDispatcher` is a strong base abstraction, but default effect handlers are still registered directly during engine construction.

Problems:
- changing handler packs still implies engine-owned composition
- Claude and GPT cannot easily swap compatible effect packs without modifying assembly code
- there is no formal registry for handler packs or semantic event contributors

Required improvement:
- introduce handler-pack registration or event handler registries
- keep current default handlers as the base pack
- allow composition root to install additional compatible packs
- preserve current semantic event names and payload shapes

### 5. Turn context is still mostly dict-shaped at decision boundaries
The architecture declaration clearly points toward typed `TurnContext`.

Problems:
- helper logic can drift in key names
- feature ownership is unclear
- Claude and GPT can derive similar concepts under slightly different key names
- debug payloads and runtime decisions stay too tightly coupled to internal helper naming

Required improvement:
- add `policy/context/turn_context.py`
- add `policy/context/builder.py`
- let `_generic_survival_context()` coexist temporarily, but progressively wrap or mirror into typed context
- standardize context fields before extracting more decision modules

## Recommended Architecture Direction

### Phase A. Shared scaffolding first
Create the shared module skeleton under `GPT/`:

```text
policy/
  profile/
  survival/
  context/
  character_eval/
  decision/
  asset/
  registry/
profiles/
policy_profiles/
```

Do this before moving major logic. The immediate goal is structural compatibility with Claude.

### Phase B. Profile identity and registry first
Implement:
- `PolicyProfileSpec`
- `ProfileRegistry`
- canonical name + alias resolution
- stable profile references for logs and summaries

This should happen before large strategy extraction, because profile identity is currently the biggest collaboration drift risk.

### Phase C. Composition root before deep extraction
Implement:
- `PolicyAsset`
- `PolicyFactory`
- `StrategyRegistry`

Then wire current GPT heuristics through that layer while still delegating to existing logic internally.

This gives a behavior-preserving bridge:
- old engine contract remains
- new architecture contract becomes real

### Phase D. Typed context and survival boundaries
Implement:
- `TurnContext`
- `TurnContextBuilder`
- survival strategy interfaces

Then map current helper outputs into typed context step by step.

### Phase E. Extract decision bundles incrementally
Prioritize extraction by coupling and engine sensitivity:
1. lap reward
2. purchase gate
3. draft / final character choice
4. mark target
5. movement
6. trick use
7. marker flip

This order minimizes risk while creating reusable DI seams early.

## Specific Recommendations For AI Behavior Profile Structure

### Recommendation 1. Stop treating mode strings as the real profile
Current mode strings like:
- `heuristic_v1`
- `heuristic_v2_balanced`
- `heuristic_v3_gpt`

should become compatibility aliases only.

Preferred target:
- canonical profile id, for example `heuristic_v3_gpt_exp`
- alias map, for example `heuristic_v3_gpt`
- resolved profile spec from registry

### Recommendation 2. Separate profile data from strategy selection
The profile should carry:
- weights
- character values
- group data
- mark-risk data
- strategy keys

The profile should not itself contain runtime code.

This is the critical step that allows:
- same profile, different survival strategy
- same profile, different purchase decider
- GPT/Claude shared asset contracts with independent internals

### Recommendation 3. Preserve old names through alias registry
To avoid breaking tests and logs:
- keep current public mode strings working
- resolve them through aliases
- record canonical names in logs and summaries

This follows the agreed spec and improves long-term comparability.

## Specific Recommendations For Event And Hook Structure

### Recommendation 1. Keep semantic event names stable
The collaboration spec already defines semantic event naming expectations.

Do not rename existing semantic events casually.
Instead:
- preserve current event names
- add registry-based installation around them
- add typed payload helpers around them if needed

### Recommendation 2. Separate policy hooks from engine semantic events
These are related but should not collapse into one abstraction.

- engine semantic events represent game lifecycle and effect resolution
- policy hooks represent decision lifecycle and customization

They should be interoperable, but remain separate layers.

### Recommendation 3. Introduce behavior-safe hook phases
Suggested evolution:
- `policy.before_decision` remains for tracing
- add a typed context-building phase
- add optional override/veto hooks
- add post-resolution explanation hooks

This would make policy hooks actually useful for collaborative strategy composition instead of only logging.

## Collaboration Compatibility Rules

### Must stay compatible
- engine-facing `choose_*` contract
- semantic event names
- action log shape where possible
- canonical profile names and alias behavior
- stable strategy registry keys
- asset schema and factory contracts

### Can diverge safely
- internal scoring details
- survival formulas
- evaluator implementations
- profile asset contents
- strategy implementation internals

This is the right kind of divergence for Claude/GPT collaboration:
- same structure
- different tactical ideas
- still interoperable

## Suggested First Implementation Steps
1. Add `policy/profile/spec.py`
2. Add `policy/profile/registry.py`
3. Add `policy/registry/strategy_registry.py`
4. Add `policy/asset/policy_asset.py`
5. Add `policy/asset/factory.py`
6. Add `profiles/` JSON files for current GPT data
7. Bridge current `HeuristicPolicy` modes through the new registry and asset layer without changing behavior yet

## Validation Guidance
When migrating, validate at three levels:

### 1. Direct unit tests
- current AI behavior tests
- survival guardrail tests
- log pipeline tests

### 2. Compatibility tests
- old mode string still resolves
- canonical profile name recorded correctly
- same asset can assemble a runtime policy without engine changes

### 3. Simulation-level regression
- same seed, comparable decision outputs
- no broken semantic events
- no missing policy debug payloads

## Conclusion
The project is already close enough to the target shape that this refactor should be treated as a composition and identity refactor, not an engine rewrite.

The highest-value improvements are:
- formal profile identity
- asset/factory composition
- stable strategy registry keys
- typed context
- stronger policy extension hooks

If those are introduced in that order, GPT can move toward the shared architecture while preserving current behavior and keeping the door open for Claude-side parallel work.
