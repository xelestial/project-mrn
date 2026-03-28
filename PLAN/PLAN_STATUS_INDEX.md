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

### 0. Shared Visual Runtime Contract
- File: `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
- Status: `ACTIVE`
- Role: first shared implementation blocker for replay/live visualization work
- Notes:
  - defines the shared event, public-state, and prompt boundary
  - should be agreed before parallel GPT/Claude implementation

### 1. Visual Replay And Playable Simulator
- File: `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- Status: `ACTIVE`
- Role: canonical product/runtime plan for turning the CLI simulator into:
  - a replay viewer
  - a live playable visual game
- Notes:
  - this is the top-level plan to follow for replay and playable visualization
  - it is the main GPT-owned architecture/product plan for this topic
  - Phase 2 offline replay viewer is now implemented at minimum viable level
  - Phase 3 live spectator baseline is now implemented at minimum viable level
  - Phase 4 human-play baseline is now implemented for non-trick prompts
  - remaining active work is centered on browser-side response bridge, trick prompts, and later full UI polish

### 2. Turn Advantage Analysis
- File: `PLAN/GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md`
- Status: `ACTIVE`
- Role: GPT-only strategy/analysis track
- Notes:
  - useful for debugging and evaluation
  - not a blocker for shared runtime architecture
  - should not be treated as the main visual runtime plan

### 3. GPT Decision Pipeline Node Plan
- File: `PLAN/GPT_DECISION_PIPELINE_NODE_PLAN.md`
- Status: `ACTIVE`
- Role: active plan for converting GPT AI decisions into node/pipeline form
- Notes:
  - intended to make AI decisions explainable and reusable
  - first implementation explicitly excludes trick pipelines until manual audit

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
- `PLAN/[COMPLETE]_GPT_PHASE2_OFFLINE_REPLAY_VIEWER.md`
- `PLAN/[COMPLETE]_GPT_PHASE3_LIVE_SPECTATOR.md`
- `PLAN/[COMPLETE]_GPT_PHASE4_HUMAN_PLAY_BASELINE.md`
- `PLAN/[COMPLETE]_MULTI_AGENT_DISPATCH_IMPL.md`
- `PLAN/[COMPLETE]_CLAUDE_MULTI_AGENT_BATTLE_PLAN.md`

## Analysis Records

### Engine Dependency Review
- File: `PLAN/[ANALYSIS]_CLAUDE_ENGINE_DEPENDENCY_REVIEW.md`
- Status: `ANALYSIS`
- Role: AI 전략 판단 제외 엔진/게임 구조 의존성 현황 검토
- Notes:
  - 결론: 대규모 리팩터링 불필요
  - 유일한 선택적 개선 항목: `BasePolicy Protocol` (base_policy.py 추가)
  - 시각화 Phase 1-S 진입 전 참고 자료

## Reference Plans

These are still useful, but they are not the current top-level execution plan on this branch.

### Visualization Runtime Direction Proposal
- File: `PLAN/[PROPOSAL]_VISUALIZATION_RUNTIME_DIRECTION.md`
- Status: `PROPOSAL`
- Role: recommended architecture opinion for visualization/replay/live-play direction
- Notes:
  - supports the current canonical visualization plan
  - recommends GPT upper architecture plus Claude-style lower substrate

### PR22 Visualization Fix Split
- File: `PLAN/[PROPOSAL]_GPT_CLAUDE_VISUALIZATION_FIX_SPLIT.md`
- Status: `PROPOSAL`
- Role: corrective ownership split for post-PR22 `main`-branch visualization issues
- Notes:
  - records what must be fixed now on GPT side vs Claude side
  - focuses on Phase 4 stabilization, schema drift cleanup, and contract convergence
  - should be used as a corrective proposal, not as a replacement for the canonical runtime plan

### Engine Policy Contract Alignment
- File: `PLAN/[AGREE]_ENGINE_POLICY_CONTRACT_ALIGNMENT.md`
- Status: `AGREE`
- Role: accepted overlap between Claude engine dependency analysis and the shared visual runtime direction
- Notes:
  - confirms engine rewrite is not a blocker
  - confirms explicit policy protocol/contract is the right next boundary
  - should be treated as an alignment note, not a replacement for the active runtime plan

### Claude Visualization Technical Opinion
- File: `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md`
- Status: `PROPOSAL`
- Role: technical-stack and UI implementation opinion for visualization work
- Notes:
  - useful for concrete implementation choices such as:
    - SVG vs Canvas
    - Vanilla HTML/JS vs heavier frontend stack
    - queue-based human input bridge
    - public vs analysis view split
    - JSON-schema-first contracts
  - should be treated as a technical proposal, not the canonical product plan

### Claude Architecture Refactor
- File: `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- Status: `REFERENCE`
- Role: Claude-owned architecture reference
- Notes:
  - useful for naming, seam alignment, and shared structure
  - should not be treated as the active GPT execution backlog

### Claude Visual Game Substrate Plan
- File: `PLAN/VISUALIZATION_GAME_PLAN.md`
- Status: `REFERENCE`
- Role: Claude-side lower-layer visualization substrate plan
- Notes:
  - still important as a reference for:
    - event stream enrichment
    - board public state
    - player public state
    - movement trace
  - current recommended structure is:
    - GPT owns upper runtime/session/projection/renderer/input architecture
    - Claude substrate plan informs lower event/state contracts

### Claude Visual Game Substrate Branch Reference
- Branch reference: `CLAUDE-MAIN:PLAN/VISUALIZATION_GAME_PLAN.md`
- Status: `REFERENCE`
- Role: same lower-layer substrate plan, preserved as original branch context

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
2. Use `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md` as the shared boundary baseline before parallel implementation.
3. Use `PLAN/GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md` only for GPT-side analysis tooling.
4. Use completed documents only as implementation history or rationale.
5. Use `PLAN/VISUALIZATION_GAME_PLAN.md` as the lower-layer substrate reference for visual runtime work.
6. Use `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md` as a technical-choice proposal, not as the active product plan.
7. Use Claude documents as reference for shared contracts, not as the active GPT task list.

## Cleanup Decisions

### Keep
- keep all `[COMPLETE]` documents
- keep `CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- keep `SHARED_VISUAL_RUNTIME_CONTRACT.md`
- keep `VISUALIZATION_GAME_PLAN.md`
- keep `[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md`
- keep `[PROPOSAL]_GPT_CLAUDE_VISUALIZATION_FIX_SPLIT.md`
- keep `[AGREE]_ENGINE_POLICY_CONTRACT_ALIGNMENT.md`
- keep `GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md`
- keep `GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`
- keep `GPT_DECISION_PIPELINE_NODE_PLAN.md`

### Do Not Use As Primary Drivers
- `[SUPERSEDED]_GPT_ARCHITECTURE_REVIEW_AND_IMPROVEMENTS.md`
- older completed milestone docs

### No Immediate Deletions
No plan document should be deleted right now.

Reason:
- most completed documents are still useful as milestone records
- cross-branch planning work is still evolving
- removing them now would reduce traceability without meaningfully reducing maintenance cost
