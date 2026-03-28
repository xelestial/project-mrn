# [AGREE] Engine Policy Contract Alignment

Status: `AGREE`
Role: `agreed alignment note between shared visual runtime contract and Claude engine dependency review`
Date: 2026-03-28

## Purpose
This document records what is now considered agreed after comparing:

- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- `PLAN/[ANALYSIS]_CLAUDE_ENGINE_DEPENDENCY_REVIEW.md`

The goal is not to accept every analysis point as an immediate task.
The goal is to identify the parts that should now be treated as shared implementation direction.

## Agreed Core Conclusion
The current engine shape is workable for the visual runtime project, but replay/live/human-play work should not continue on top of a loose `hasattr()`-driven policy boundary forever.

The next stable boundary should be:

- engine owns game rules and authoritative mutable runtime state
- adapters own decision-making behavior
- a formal policy contract defines what decisions can be requested
- replay/live visualization consumes engine-derived public state, not policy internals

## What We Agree With

### 1. The Current Engine Is Not A Rewrite Blocker
Agreed:
- the engine dependency graph is not fundamentally broken
- there is no evidence that replay/live work requires a full engine rewrite first
- the current engine can remain the gameplay authority

Meaning:
- visual runtime work should proceed
- the contract boundary should improve, but the engine does not need to be replaced first

### 2. Policy Contract Should Become Explicit
Agreed:
- the current `hasattr()` pattern is too weak as the long-term decision boundary
- replay/live/human runtime needs a clearer engine-to-policy contract
- a `BasePolicy` or equivalent protocol/interface is the right direction

Why this matters:
- it matches the `HumanDecisionAdapter` / `AIDecisionAdapter` split already planned
- it makes GPT / Claude / human seats easier to swap under one runtime
- it reduces ambiguity about which `choose_*` calls the engine may issue

### 3. Engine Should Stay Presentation-Agnostic
Agreed:
- the engine should not know about renderer details
- the engine should not know about replay UI concerns
- visual runtime should consume structured engine outputs through a substrate/projection layer

This aligns directly with:
- `SHARED_VISUAL_RUNTIME_CONTRACT`
- `GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN`

### 4. External Data And Config Loading Should Be Treated Carefully
Agreed:
- `config` and csv-backed content loading can create side-effect-heavy startup behavior
- replay/live runtime should avoid hidden config loading assumptions
- runtime-facing code should prefer explicit configuration and explicit injected sources

This is especially relevant for:
- deterministic replay
- live session reproducibility
- future UI/runtime bootstrapping

### 5. Mutable Engine State Must Remain Authoritative But Not Leak Across Layers
Agreed:
- engine-owned mutable state is acceptable inside the gameplay core
- but it should be wrapped before being exposed to replay/live UI
- public rendering should depend on snapshots/events, not direct policy poking into engine state

This matches our existing truth-source policy:
1. live engine state
2. structured event stream
3. deterministic rerun

## What We Are Not Treating As Immediate Mandatory Work

### 1. Full Engine Dependency Cleanup
Not agreed as an immediate blocker:
- reducing every engine import
- flattening every config dependency
- eliminating all runtime mutability

Reason:
- those are good cleanup targets
- but they are not required before replay/live implementation begins

### 2. Full Engine Refactor Before Visualization
Not agreed:
- we should not pause visualization/runtime work until a large engine refactor is complete

Reason:
- contract hardening is enough for now
- large engine cleanup can remain incremental

## Agreed Immediate Direction

### Phase 1
Keep the current engine as authoritative, but formalize the policy boundary.

### Phase 2
Make replay/live/human adapters depend on a stable decision contract rather than ad-hoc optional hooks.

### Phase 3
Continue substrate/projection work without pushing renderer concerns into engine code.

## Proposed Contract Direction

The contract should move toward a formal policy interface covering the engine-issued decision family, such as:

- `choose_movement`
- `choose_draft_card`
- `choose_final_character`
- `choose_lap_reward`
- `choose_mark_target`
- `choose_purchase_tile`
- `choose_coin_placement_tile`
- `choose_doctrine_relief_target`
- `choose_geo_bonus`
- `choose_active_flip_card`
- `choose_burden_exchange_on_supply`

Important note:
- trick-related calls may remain temporarily outside the first visual-runtime milestone because trick support is currently excluded from first implementation scope

## Agreed Relationship To Existing Plans

### Shared Visual Runtime Contract
This document reinforces, not replaces:
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

### Visual Runtime Product Plan
This document supports, not replaces:
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

### Claude Analysis
This document is the accepted subset of:
- `PLAN/[ANALYSIS]_CLAUDE_ENGINE_DEPENDENCY_REVIEW.md`

## Actionable Outcome

The agreed next architectural move is:

1. keep engine as gameplay authority
2. harden the policy decision contract
3. keep renderer/runtime above the substrate boundary
4. avoid treating engine import/config cleanup as a blocker for replay/live implementation

## Final Summary
Agreed position:

- the engine is good enough to proceed
- the policy boundary needs to become explicit
- the visual runtime should build on substrate/projection contracts, not direct engine/UI coupling
- full engine cleanup remains desirable, but not a prerequisite for starting replay/live development
