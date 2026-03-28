# PLAN Status Index

## Purpose
This file is the current status index for documents under `PLAN/`.

Use it to answer:
- which plans are still active
- which plans are complete milestone records
- which plans are reference-only
- which plans are superseded and should no longer drive implementation

This index was reviewed on `2026-03-28` against:
- current branch `codex/GPT-MAIN`
- `main`
- `CLAUDE-MAIN`
- `GEMINI-MAIN`

## Canonical Branch Policy

`PLAN/` should be governed by `main`.

Working rule:
- `main` is the canonical planning branch
- active top-level plans should ultimately live on `main`
- feature branches may carry temporary notes, experiments, or branch-local references
- branch-local planning documents should be merged into `main` or downgraded to reference/superseded status

Practical implications:
- do not treat a feature-branch-only plan as the long-term source of truth
- if a branch introduces an important new plan, it should be promoted into `main`
- completed implementation records may remain on branches, but canonical active planning should converge back to `main`

## Canonical Active Plans

### 1. Visual Replay And Playable Simulator
- File: `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- Status: `ACTIVE`
- Role: canonical product/runtime plan for turning the CLI simulator into:
  - a replay viewer
  - a live playable visual game
- Notes:
  - this is the top-level plan to follow for replay and playable visualization
  - it is the main GPT-owned architecture/product plan for this topic

### 2. Turn Advantage Analysis
- File: `PLAN/GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md`
- Status: `ACTIVE`
- Role: GPT-only strategy/analysis track
- Notes:
  - useful for debugging and evaluation
  - not a blocker for shared runtime architecture
  - should not be treated as the main visual runtime plan

## Completed Milestone Records

These documents should be kept as implementation records, not deleted.
They are no longer the active source of truth for future planning.

- `PLAN/[COMPLETE]_GPT_ARCHITECTURE_ALIGNMENT_TASK.md`
- `PLAN/[COMPLETE]_GPT_MODULE_API_INDEPENDENCE_PLAN.md`
- `PLAN/[COMPLETE]_GPT_HELPER_WRAPPER_LIVE_PATH_REFACTOR.md`
- `PLAN/[COMPLETE]_GPT_SCORING_EVALUATOR_REFACTOR.md`
- `PLAN/[COMPLETE]_GPT_LEGACY_BODY_CLEANUP.md`
- `PLAN/[COMPLETE]_GPT_REFACTOR_POLISH.md`
- `PLAN/[COMPLETE]_GPT_ISOLATED_MULTI_AGENT_BATTLE_IMPL.md`
- `PLAN/[COMPLETE]_GPT_TURN_ADVANTAGE_ANALYSIS_PHASE1.md`
- `PLAN/[COMPLETE]_MULTI_AGENT_DISPATCH_IMPL.md`
- `PLAN/[COMPLETE]_CLAUDE_MULTI_AGENT_BATTLE_PLAN.md`

## Reference Plans

These are still useful, but they are not the current top-level execution plan on this branch.

### Visualization Runtime Direction Proposal
- File: `PLAN/[PROPOSAL]_VISUALIZATION_RUNTIME_DIRECTION.md`
- Status: `PROPOSAL`
- Role: recommended architecture opinion for visualization/replay/live-play direction
- Notes:
  - supports the current canonical visualization plan
  - recommends GPT upper architecture plus Claude-style lower substrate

### Claude Architecture Refactor
- File: `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- Status: `REFERENCE`
- Role: Claude-owned architecture reference
- Notes:
  - useful for naming, seam alignment, and shared structure
  - should not be treated as the active GPT execution backlog

### Claude Visual Game Substrate Plan
- Branch-only reference: `CLAUDE-MAIN:PLAN/VISUALIZATION_GAME_PLAN.md`
- Status: `REFERENCE`
- Role: Claude-side lower-layer visualization substrate plan
- Notes:
  - not present on the current branch as a local file
  - still important as a reference for:
    - event stream enrichment
    - board public state
    - player public state
    - movement trace
  - current recommended structure is:
    - GPT owns upper runtime/session/projection/renderer/input architecture
    - Claude substrate plan informs lower event/state contracts

### Local Reference Note For Claude Visualization Substrate
- File: `PLAN/[REFERENCE]_CLAUDE_VISUALIZATION_GAME_SUBSTRATE_PLAN.md`
- Status: `REFERENCE`
- Role: local pointer and summary for the branch-only Claude visualization substrate plan

## Superseded Plans

These should not drive new work unless explicitly revived.

- `PLAN/[SUPERSEDED]_GPT_ARCHITECTURE_REVIEW_AND_IMPROVEMENTS.md`

Reason:
- its observations were useful
- its action items were absorbed into completed architecture/refactor work
- it is now a historical review note, not an active implementation plan

## Current Planning Rule

When deciding what to follow next:

1. Use `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md` for replay/playable game work.
2. Use `PLAN/GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md` only for GPT-side analysis tooling.
3. Use completed documents only as implementation history or rationale.
4. Use Claude documents as reference for shared contracts, not as the active GPT task list.

## Cleanup Decisions

### Keep
- keep all `[COMPLETE]` documents
- keep `CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- keep `GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md`
- keep `GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

### Do Not Use As Primary Drivers
- `[SUPERSEDED]_GPT_ARCHITECTURE_REVIEW_AND_IMPROVEMENTS.md`
- older completed milestone docs

### No Immediate Deletions
No plan document should be deleted right now.

Reason:
- most completed documents are still useful as milestone records
- cross-branch planning work is still evolving
- removing them now would reduce traceability without meaningfully reducing maintenance cost
