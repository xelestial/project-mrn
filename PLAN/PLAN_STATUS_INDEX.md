# PLAN Status Index

Status: ACTIVE  
Updated: 2026-04-07  
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

## Closed Recently

These are no longer the immediate blockers, but they are recently completed and should be treated as closed slices unless a regression reopens them.

### A. Prompt specialization lock
- Status:
  - closed for the current slice
- What was finished:
  - all known prompt types are now explicitly bound to specialized prompt surfaces
  - the generic prompt grid is now reserved for unknown / future request types only
- Main implementation references:
  - `apps/web/src/features/prompt/PromptOverlay.tsx`
  - `apps/web/src/features/prompt/promptSurfaceCatalog.ts`
  - `apps/web/src/features/prompt/promptSurfaceCatalog.spec.ts`

### B. Prompt/selector locale seam stabilization
- Status:
  - partially closed as a stabilization slice
- What was finished:
  - locale restore survives reload
  - prompt collapsed/meta/purchase wording moved further out of direct component ownership
  - selector-side locale injection path is active
- Remaining follow-up:
  - broader selector/key decoupling still remains active under P0-4 / P1-3

### C. Human specialty prompt seam recovery
- Status:
  - closed for the current seam-repair slice
- What was finished:
  - `pabal_dice_mode` now works as a real human prompt path
  - specialty prompt browser/runtime regressions were extended
- Main implementation references:
  - `GPT/viewer/human_policy.py`
  - `apps/server/tests/test_runtime_service.py`
  - `apps/web/e2e/human_play_runtime.spec.ts`

### D. Turn-handoff visibility recovery
- Status:
  - closed for the current UI continuity slice
- What was finished:
  - payoff continuity now survives `turn_end_snapshot`
  - spectator and stage panels render explicit handoff/result cards
  - browser parity covers remote-turn continuity and handoff
  - canonical decision context now stays visible inside current-turn stage details instead of collapsing to generic request labels
- Main implementation references:
  - `apps/web/src/domain/selectors/streamSelectors.ts`
  - `apps/web/src/features/stage/SpectatorTurnPanel.tsx`
  - `apps/web/src/features/stage/TurnStagePanel.tsx`

### E. External AI worker/service mounting
- Status:
  - closed for the initial open-participant slice
- What was finished:
  - a reference external AI worker now exists as a real HTTP service
  - runtime HTTP transport now has localhost end-to-end integration coverage against that worker
  - local run tooling and runbook are in place for attaching AI seats as real external participants
  - worker health / contract-version / capability metadata is now part of the operational seam
  - auth-header and expected-worker-id validation are now part of the runtime/worker seam too
  - worker payload docs now include a production-shaped external seat example
  - health checks can now be parameter-driven via `healthcheck_policy`
  - worker readiness can now be enforced via `require_ready`
  - total worker call attempts can now be capped via `max_attempt_count`
  - stronger worker replacements can now be gated by `required_policy_mode` / `required_decision_style`
  - stronger worker replacements can now also be checked against advertised `supported_transports`
  - remote-turn stage/spectator payoff strips now surface worker outcomes as part of the scene instead of only side diagnostics
  - canonical current-turn models now preserve worker readiness state and bounded attempt counts for stage/spectator surfaces
- Main implementation references:
  - `apps/server/src/external_ai_app.py`
  - `apps/server/src/services/external_ai_worker_service.py`
  - `apps/server/tests/test_external_ai_worker_api.py`
  - `docs/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md`

## Carry-Forward Work

These are the slices that should still actively drive implementation after the recently-closed work above.

### 1. Fortune / purchase / rent scene payoff
- Status:
  - active
- Why it remains:
  - payoff cards are present, but the scene still needs to feel more like live gameplay than a feed
- Expected direction:
  - stronger fortune reveal staging
  - richer purchase/rent transitions
  - better payoff emphasis during remote turns
  - keep lap reward / mark / flip / weather continuity equally visible

### 2. Specialized prompt simplification
- Status:
  - active
- Why it remains:
  - known prompt types are specialized now, but some layouts still feel inspector-like
- Expected direction:
  - simplify choice cards further
  - keep passive/skip options visually secondary
  - continue reducing request-meta noise

### 3. Provider/decision drift reduction
- Status:
  - active
- Why it remains:
  - canonical lifecycle coverage is much stronger, but the remaining value is now concentrated in:
    - final bridge/router simplification
    - canonical request consumption on the web
    - external worker hardening beyond the reference service
- Expected direction:
  - keep shrinking residual human/AI branch-local logic
  - keep the web aligned to canonical request/public-context fields
  - keep the runtime/client seam stable as more capable external workers replace the reference implementation
  - keep selector-side sentence ownership moving into locale resources instead of inline formatter logic
  - keep external-worker auth/identity/capability checks mandatory even for injected custom transports
  - keep worker readiness / attempt-limit policy parameter-driven and visible in mixed-seat regressions
  - keep decision-response readiness validation aligned with the same public-context seam as health readiness
  - keep stronger-worker metadata compatibility (`policy_mode` / `decision_style`) enforced through the same transport seam
  - keep transport-compatibility validation (`supported_transports`) aligned with the same fallback diagnostics seam

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

## 2026-04-07 Execution Focus

The current implementation focus is:

1. human-play runtime continuity and prompt correctness
2. canonical decision request consumption across engine/server/web
3. string/resource externalization and encoding safety
4. rule parity closure
5. parameter-driven decoupling follow-up

### Current checkpoint note

- Unified decision contract work has advanced substantially:
  - runtime bridge/provider responsibilities were split
  - engine `choose_*` waves now route through an injected `DecisionPort`
  - engine/server decision request metadata is aligned around:
    - `request_type`
    - `player_id`
    - `round_index`
    - `turn_index`
    - `public_context`
    - `fallback_policy`
  - the server bridge now consumes engine-style requests directly
- Web prompt consumption also advanced:
  - `promptSelectors.ts` now reads canonical `legal_choices`
  - `PromptOverlay.tsx` now prefers canonical prompt `public_context` keys
  - turn-stage prompt focus can derive from `legal_choices[].value.tile_index`
- Recently closed slices:
  - prompt specialization lock
  - specialty seam recovery for `pabal_dice_mode`
  - turn-handoff payoff continuity
- Active carry-forward after this checkpoint:
  1. mount a real external AI worker/service against the now-live HTTP transport contract
  2. continue locale ownership reduction in selector-generated summaries
  3. keep closing rule-parity visuals around mark/flip/weather persistence where regression evidence appears
  4. only after that, continue lower-priority parameter/profile expansion

Everything else is currently supporting context, not the main queue.
