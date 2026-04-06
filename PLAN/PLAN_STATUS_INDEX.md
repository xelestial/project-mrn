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
  - stronger worker replacements can now also be gated by `required_worker_adapter`
  - stronger worker replacements can now also be checked against advertised `supported_transports`
  - remote-turn stage/spectator payoff strips now surface worker outcomes as part of the scene instead of only side diagnostics
  - canonical current-turn models now preserve worker readiness state and bounded attempt counts for stage/spectator surfaces
  - the reference worker now sits behind an explicit adapter seam so stronger workers/services can replace it without changing the frozen HTTP contract
  - canonical `public_context` now preserves `external_ai_worker_adapter` alongside worker id / mode / class / decision style
  - the worker seam now has a built-in stronger scored adapter (`priority_score_v1`) that exercises the same contract with distinct adapter/class/style metadata
  - participant defaults can now use `worker_profile` to expand stronger-worker compatibility requirements without repeating every low-level gate
  - local playtest guidance now exists for human + local AI + external AI runs on the stronger-worker path
- Main implementation references:
  - `apps/server/src/external_ai_app.py`
  - `apps/server/src/services/external_ai_worker_service.py`
  - `apps/server/tests/test_external_ai_worker_api.py`
  - `docs/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md`

## Carry-Forward Work

These are the slices that may still reopen, but they are no longer broad implementation queues inside this repository.

### 1. Evidence-only human-play visual drift cleanup
- Status:
  - evidence-only
- What is already closed enough:
  - fortune / purchase / rent / lap reward / mark / flip / weather continuity now survives mixed-seat stage and spectator flows
  - worker success/fallback metadata now appears inside the same remote-turn payoff sequence instead of a detached diagnostics block
- Reopen only if:
  - a real playtest shows a specific feed-like or rule-confusing moment that is not already covered

### 2. Locale/resource residue cleanup
- Status:
  - evidence-only
- What is already closed enough:
  - major selector/component sentence ownership was moved behind locale helpers or resource catalogs
  - `uiText.ts` is now a compatibility shim rather than the primary source of visible copy
- Reopen only if:
  - a newly discovered selector-local phrase or inline user-facing string appears in review or playtest evidence

### 3. Stronger external-worker replacement
- Status:
  - operational follow-up
- What is already closed enough:
  - the runtime/worker HTTP seam is mounted, authenticated, parameter-driven, and localhost-tested
  - stronger worker presets now exist through:
    - `worker_profile`
    - `required_worker_adapter`
    - `required_policy_mode`
    - `required_policy_class`
    - `required_decision_style`
  - built-in stronger scored adapters are already exercised end-to-end
- Remaining value:
  - attach a real deployed external worker/service to the stabilized seam
  - treat any follow-up repo edits as rollout support, not a fresh architecture phase

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

1. keep the repo-side multiplayer runtime/playtest path stable
2. use real playtests to collect any remaining evidence before reopening UI polish
3. keep worker replacement/configuration parameter-driven
4. avoid reopening closed slices without concrete regression evidence

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
  - external worker compatibility now also surfaces replacement metadata (`policy_mode` / `decision_style`) into the same canonical public-context seam
  - stronger worker replacement metadata now also supports explicit `policy_class` gating through the same health/fallback seam
- Current practical state after this checkpoint:
  1. repo-side worker/runtime/prompt/selector carry-forward is closed enough for local human/local-AI/external-AI playtests
  2. the next meaningful step is operational:
     - attach a real stronger external worker/service endpoint
     - run live playtests
  3. any further code work should be evidence-driven:
     - visual drift found in playtests
     - locale residue found in review
     - rollout support needed for a stronger deployed worker

Everything else is currently supporting context, not the main queue.
