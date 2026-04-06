# PLAN Status Index

Status: ACTIVE  
Updated: 2026-04-05  
Owner: GPT

## Purpose

This file is the execution index for `PLAN/`.

Use it to answer:
- which plans actively drive implementation now
- which plans remain useful but are reference-only
- which plans are historical closure records

Current working rule:
- do not drive implementation from old broad visualization/react migration plans
- do drive implementation from the narrowed execution set below

## Current Execution-Driving Plans

These are the plans that should actively shape implementation order right now.

### 1. Mandatory reading / execution gate
- `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
- Role:
  - always-read rule
  - encoding / DI / worklog / plan-reading policy

### 2. Live priority board
- `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
- Role:
  - the daily execution queue
  - current P0/P1/P2 ordering

### 3. Unified Decision API
- `PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md`
- `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
- Role:
  - canonical decision contract
  - required event ordering:
    - `decision_requested`
    - `decision_resolved` or `decision_timeout_fallback`
    - domain events

### 4. Human play parity / live UX recovery
- `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
- Role:
  - human-play runtime correctness
  - prompt / theater / board / spectator continuity
  - anti-regression source for previously reported UX failures

### 5. Rules alignment
- `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
- `docs/Game-Rules.md`
- Role:
  - game-rule source of truth
  - engine / server / web parity

### 6. String and encoding stability
- `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
- `PLAN/[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`
- Role:
  - remove inline user-facing strings from active UI surfaces
  - prevent mojibake / wording regression
  - establish KO/EN locale-ready architecture

### 7. Parameter decoupling
- `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
- Role:
  - keep engine / server / web resilient to ruleset / parameter changes

## Active But Secondary Plans

These plans still matter, but they are not the first documents to drive day-to-day edits.

### Shared runtime contract
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- Role:
  - payload/public-state contract reference

### Implementation usage guide
- `PLAN/[PLAN]_IMPLEMENTATION_DOCUMENT_USAGE_GUIDE.md`
- Role:
  - reading order and conflict policy

### Repository / interface / API specs
- `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`
- `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
- `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
- `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md`
- `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
- Role:
  - detailed implementation references
  - use when the task specifically touches those boundaries

## Reference-Only Plans

These are useful for architecture history or broader context, but should not directly drive current implementation unless explicitly reactivated.

### High-level historical product/runtime plans
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`

Reason:
- they were correct as umbrella transition plans
- current work is now narrower and should be driven by the execution plans above

### Strategy / audit / proposal references
- `PLAN/[REVIEW]_PIPELINE_CONSISTENCY_AND_COUPLING_AUDIT.md`
- `PLAN/[DECISION]_REACT_STATE_STORE_STRATEGY.md`
- `PLAN/[DECISION]_REACT_UI_STACK_STRATEGY.md`
- `PLAN/[CHECKLIST]_LEGACY_VS_REACT_PARITY.md`
- `PLAN/[PROPOSAL]_VISUALIZATION_RUNTIME_DIRECTION.md`
- `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md`
- `PLAN/[AGREE]_ENGINE_POLICY_CONTRACT_ALIGNMENT.md`
- `PLAN/[ANALYSIS]_CLAUDE_ENGINE_DEPENDENCY_REVIEW.md`
- `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- `PLAN/VISUALIZATION_GAME_PLAN.md`
- `PLAN/[REFERENCE]_CLAUDE_VISUALIZATION_GAME_SUBSTRATE_PLAN.md`

Reason:
- still useful as design rationale
- not current execution queues

### AI-side analysis references
- `PLAN/GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md`
- `PLAN/GPT_DECISION_PIPELINE_NODE_PLAN.md`

Reason:
- useful for AI work
- not the primary driver of current human-play UI/runtime work

## Completed / Historical Records

Keep all `[COMPLETE]` documents as historical implementation records.

They should not be used as active task boards.

## Superseded

- `PLAN/[SUPERSEDED]_GPT_ARCHITECTURE_REVIEW_AND_IMPROVEMENTS.md`

## Current Priority Rule

When choosing the next task, follow this order:

1. `docs/Game-Rules.md`
2. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
3. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
4. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
5. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
6. `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
7. `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
8. `PLAN/[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`
9. `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`

## 2026-04-06 Execution Focus

The current implementation focus is:

1. selector/resource locale detachment
2. human-play runtime continuity and prompt correctness
3. string/resource externalization and encoding safety
4. rule parity closure
5. parameter-driven decoupling follow-up

### Current checkpoint note

- Board move continuity now includes:
  - start badge
  - path-step trail
  - transient ghost-pawn travel overlay
- Prompt locale ownership moved further out of the component layer for collapsed/meta/purchase wording.
- Unified decision contract work also advanced:
  - canonical request-type mapping is shared
  - canonical lifecycle publish helpers are now shared inside `DecisionGateway`

Everything else is currently supporting context, not the main queue.
