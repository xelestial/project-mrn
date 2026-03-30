# PLAN Status Index

## Purpose
This file is the current status index for documents under `PLAN/`.

Use it to answer:
- which plans are still active
- which plans are complete milestone records
- which plans are reference-only
- which plans are superseded and should no longer drive implementation

This index was reviewed on `2026-03-31` against:
- current branch `main`
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
  - implementation status on `main` is now:
    - Phase 1: baseline complete
    - Phase 2: baseline complete
    - Phase 3: baseline complete
    - Phase 4: baseline complete for human-play runtime
    - Phase 5: not complete; still the main forward UI track
  - current document-maintenance gap is now mostly:
    - Phase 5 progress tracking
    - validator parity follow-up as contract fields evolve
  - shared-contract sync update (`2026-03-29`):
    - canonical movement/mark/end payload fields and alias policy were re-aligned in code + contract doc
  - current explicit work split is:
    - GPT: upper runtime, prompt flow, replay/live renderer polish, Phase 5 user-facing UI growth
    - CLAUDE: lower substrate verification, canonical contract stability, validator maintenance, and related lower-layer bug fixes
  - current Phase 5 execution proposal:
    - `PLAN/[PROPOSAL]_GPT_PHASE5_COMMERCIAL_UI_UX_OVERHAUL.md`
    - use it as the active user-facing UX follow-up for the live/replay viewer

### 1A. React Online Implementation (Top-Level)
- File: `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- Status: `ACTIVE`
- Role: execution bridge from current Python viewer to React + FastAPI online runtime
- Notes:
  - this is the top-level React transition plan for backend/frontend parallel work
  - it now links detailed companion specs for implementation-level execution
  - D1/B1 baseline code has started (`apps/server` skeleton + repository scaffolds)
  - B2 baseline code has started (websocket stream + in-memory `seq` replay buffer)
  - B3 baseline code has started (prompt pending/timeout/decision-ack skeleton path)
  - B3 timeout fallback trace baseline added (`decision_timeout_fallback`)
  - B2/B3 hardening has started (seat token auth + decision mismatch guards)
  - B2 reconnect hardening baseline added (`RESUME_GAP_TOO_OLD` handling)
  - B2 API regression test baseline added (`apps/server/tests/test_stream_api.py`, fastapi-gated)
  - B3 decision-auth regression test baseline added (`UNAUTHORIZED_SEAT`, `PLAYER_MISMATCH`)
  - B1 replay export baseline added (`GET /api/v1/sessions/{session_id}/replay`)
  - all-AI runtime fan-out baseline has started (background engine run + incremental stream publication)
  - F1 frontend baseline has started (`apps/web` scaffold + stream client/hook)
  - F1 REST session client baseline added (`create/start/runtime-status`) with one-click all-AI start/connect flow
  - F1 test baseline added (Vitest + reducer unit tests)
  - F1 selector/contract parser tests added (`snapshot/timeline/situation`)
  - F1 websocket auto-reconnect baseline added (incremental backoff)
  - F1 reconnect/resume integration test baseline added (`apps/web/src/infra/ws/StreamClient.spec.ts`)
  - F1 stream ordering resilience baseline added (out-of-order buffer + gap-triggered resume request)
  - F2 pre-structure has started (feature component split + selector layer + board placeholder)
  - F2 snapshot baseline added (stream snapshot -> public board/player render)
  - F2 ring-board baseline added (`tile_index` coordinate mapping)
  - OI2 board-layout constant extraction is closed (`2026-03-31`):
    - board projection constants are centralized (`boardProjection`)
    - ring/line grid dimensions are computed via `boardGridForTileCount`
    - React board grid templates no longer rely on fixed `11x11` literals
    - projection regression tests pass (`apps/web/src/features/board/boardProjection.spec.ts`)
  - F2 board-near incident stack baseline added
  - F2 board movement UX baseline added (last-move summary + from/to tile highlight + pawn arrive pulse)
  - F2 selector localization baseline added (Korean event labels + richer timeline detail summaries)
  - F2 selector fixture coverage expanded (dice/marker/heartbeat detail cases)
  - F3 prompt baseline started (active prompt selector + decision submit overlay)
  - F3 rejected/stale ack unlock baseline added
  - F3 prompt countdown baseline added
  - F3 keyboard/focus baseline added (focus restore + Escape collapse)
  - F3 stale/rejected feedback messaging baseline added (prompt overlay inline guidance)
  - F3 prompt-type helper copy baseline added
  - F3 helper catalog split baseline added (`request_type` -> helper map)
  - F3 helper coverage expanded for full request matrix (`burden_exchange`, `runaway_step_choice` 포함)
  - F4 lobby baseline started (custom session create/join/start/session list)
  - F4 join-token state baseline added (seat-based auto-fill from created session)
  - F4 join-token UX polish baseline added (seat select + one-click token apply chips)
  - F4 session-list quick-select baseline added (`Use session`)
  - F4 lobby/match route split baseline added (hash-route tabs)
  - F4 dedicated lobby view extraction baseline added (`features/lobby/LobbyView.tsx`)
  - F4 URL cleanup baseline added (connected match hash removes token parameter)
  - B2 fan-out hardening baseline added (subscriber queue push + slow-consumer drop-oldest policy)
  - B2 slow-consumer drop-oldest regression test baseline added (`apps/server/tests/test_stream_service.py`)
  - B2 backpressure observability baseline added (`heartbeat.payload.backpressure`, drop counters)
  - B2 client reconnect polish added (exponential backoff + jitter)
  - B4 runtime watchdog baseline added (inactivity warning + runtime status activity fields)
  - B4 runtime visibility baseline added in web connection panel (watchdog/last-activity)
  - B4 structured-log retention baseline added (env-driven rotating file handler + tests)
  - runtime async bridge closure (`2026-03-31`):
    - runtime execution now uses `asyncio.to_thread` task bridge
    - watchdog now runs as async task path
  - root-source propagation closure (`2026-03-31`):
    - source file delta -> manifest fingerprint/hash delta test is covered
    - session bootstrap manifest source-change propagation is covered
  - detailed spec docs migration closure (`2026-03-31`):
    - canonical detailed specs are now in `docs/*`
    - `PLAN/[PLAN]_...` spec files are compatibility mirrors with redirect notes
  - B5/F7 fallback hardening added:
    - selector label-catalog split (`event_code` -> display label separation)
    - partial/flat manifest parsing tolerance and fallback regression tests
    - stream-manifest rehydrate now updates topology/labels with tested merge helper path
    - server integration fixtures now include non-default manifest profile replay (`3-seat + line`)
    - web reconnect-flow fixture now validates reducer/selector/rehydrate chain on hash change
    - backend transport E2E fixture now validates reconnect replay after manifest-hash change
  - OI11 active-root cleanup baseline added:
    - strict legacy-path audit for `apps/packages/tools` is now 0-match
    - CI gate added (`python tools/legacy_path_audit.py --roots apps packages tools --strict`)
    - cleanup policy doc added (`docs/architecture/legacy-reference-cleanup-policy.md`)

### 1B. React Detailed Execution Backlog
- File: `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
- Status: `ACTIVE`
- Role: phase-by-phase detailed implementation backlog and DoD gates
- Notes:
  - canonical doc path: `docs/architecture/react-online-game-detailed-execution.md`
  - source of truth for B1-B4, F1-F6 granular delivery checks
  - includes quality gates, risk register, and PR update rules

### 1C. React Component Structure Spec
- File: `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md`
- Status: `ACTIVE`
- Role: detailed component architecture and UI responsibility boundaries
- Notes:
  - canonical doc path: `docs/frontend/react-component-structure-spec.md`
  - defines component tree, feature ownership, selector boundaries, test matrix
  - canonical frontend reference for prompt/board/theater/player-panel composition

### 1D. Online Interface Spec
- File: `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
- Status: `ACTIVE`
- Role: DI-facing backend/frontend interface boundary spec
- Notes:
  - canonical doc path: `docs/backend/online-game-interface-spec.md`
  - defines service protocols, frontend ports, prompt/decision interface mapping
  - canonical boundary reference for adapter-oriented implementation

### 1E. Online API Spec
- File: `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
- Status: `ACTIVE`
- Role: concrete REST + WebSocket API contract
- Notes:
  - canonical doc path: `docs/api/online-game-api-spec.md`
  - defines envelope format, endpoint payloads, ws message types, error catalog
  - implementation and test updates should follow this spec for transport-level changes

### 1F. Repository Directory Specification
- File: `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`
- Status: `ACTIVE`
- Role: target repository layout and migration mapping away from legacy `GPT/`-centric placement
- Notes:
  - defines target `apps/` + `packages/` structure for online runtime
  - specifies write-location policy for new server/web/runtime-contract work
  - provides phased migration map from legacy paths to target paths

### 1G. Implementation Document Usage Guide
- File: `PLAN/[PLAN]_IMPLEMENTATION_DOCUMENT_USAGE_GUIDE.md`
- Status: `ACTIVE`
- Role: mandatory document reading/usage order to prevent mixing legacy and active plans
- Notes:
  - docs-first reading order is now active for detailed specs (`docs/*`)
  - defines authoritative reading order before coding
  - defines conflict resolution and do-not-drive reference docs
  - should be checked before implementation starts

### 1H. Parameter-Driven Runtime Decoupling
- File: `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
- Status: `ACTIVE`
- Role: remove backend/frontend hardcoding sensitivity when gameplay parameters change
- Notes:
  - tracks hardcoded hotspots across server/runtime/engine/web
  - defines `ResolvedGameParameters` + public `parameter_manifest` transition
  - formalizes DI seams for config resolver, config factory, and label/topology adapters
  - now includes root-source auto-propagation guardrails (`source_fingerprints`, `manifest_hash`, CI stale-artifact gate)
  - implementation baseline has started in code:
    - backend resolver/manifest services
    - session API + stream manifest payload
    - runtime config-factory boot path
    - frontend manifest-hash rehydrate baseline
    - frontend stream-manifest topology/labels rehydrate merge baseline (pure helper + tests)
    - frontend selector fallback hardening for partial/flat manifest variants
    - frontend label-catalog split baseline for event display mapping
    - stale-artifact gate helper script (`tools/parameter_manifest_gate.py`)
    - stale snapshot sync test (`apps/server/tests/test_parameter_manifest_snapshot.py`)
    - CI workflow baseline wiring (`.github/workflows/ci.yml`)
  - matrix coverage closure (`2026-03-31`):
    - backend and API tests cover seat/economy/dice variant manifests
    - Playwright parity fixture includes `parameter_matrix_economy_dice_2seat`
  - should be used when changing:
    - tile layout/value
    - character/trick definitions
    - initial resources
    - dice composition
    - UI label/message policy

### 1I. Pipeline Consistency and Coupling Audit
- File: `PLAN/[REVIEW]_PIPELINE_CONSISTENCY_AND_COUPLING_AUDIT.md`
- Status: `ACTIVE REVIEW`
- Role: canonical audit baseline for setting/function/check/verification pipeline consistency
- Notes:
  - consolidates canonical pipeline definitions across active plans/specs
  - tracks coupling hotspots, inconsistent wording, missing tests, and hardcoding risks
  - fallback resiliency finding `F-05` is now closed with matrix fixture/test coverage (`2026-03-31`)
  - should be referenced when updating:
    - parameter manifest/resolver path
    - DI interface contracts
    - quality-gate and test matrix definitions

### 1J. React Store Strategy Decision
- File: `PLAN/[DECISION]_REACT_STATE_STORE_STRATEGY.md`
- Status: `ACTIVE DECISION`
- Role: freeze v1 frontend state-store direction
- Notes:
  - confirms reducer+selector-first baseline for v1
  - defers `zustand` introduction until post-parity v2 trigger
  - should be referenced before changing frontend state architecture

### 1K. Legacy vs React Parity Checklist
- File: `PLAN/[CHECKLIST]_LEGACY_VS_REACT_PARITY.md`
- Status: `ACTIVE CHECKLIST`
- Role: release/cutover readiness artifact
- Notes:
  - canonical doc path: `docs/architecture/legacy-vs-react-parity-checklist.md`
  - tracks transport/prompt/board/decoupling/UX parity state
  - should be updated whenever parity-impacting runtime behavior changes
  - replay parity and live human-play acceptance gates were both closed on `2026-03-31` with evidence logs under `result/acceptance/*`
  - closure review document: `PLAN/[REVIEW]_2026-03-31_REACT_PARITY_ACCEPTANCE.md`

### 1L. React UI Stack Strategy Decision
- File: `PLAN/[DECISION]_REACT_UI_STACK_STRATEGY.md`
- Status: `ACTIVE DECISION`
- Role: freeze v1 UI styling stack choice
- Notes:
  - plain-CSS-first strategy for current phase
  - utility/framework adoption deferred to v2 trigger conditions

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
- Status: `COMPLETE`
- Role: completed implementation record for GPT AI node/pipeline conversion
- Notes:
  - runtime scope is closed in the current committed branch
  - keep as reference for architecture rationale and trace schema behavior

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

### GPT Phase 5 Commercial UI/UX Overhaul
- File: `PLAN/[PROPOSAL]_GPT_PHASE5_COMMERCIAL_UI_UX_OVERHAUL.md`
- Status: `PROPOSAL`
- Role: active Phase 5 user-experience redesign track for replay/live visualization
- Notes:
  - focuses on board-game-grade readability and presentation
  - turns the current Phase 5 viewer from a functional tool UI into a stronger match UI
  - should be treated as the current GPT-owned UX execution proposal under the canonical visualization plan
  - latest audit update (`2026-03-29`) added explicit P0 gaps and follow-up closure tracking:
    - live template text/encoding normalization (closed)
    - turn-theater v2 dominance (closed)
    - board-near incident cards for purchase/rent/fortune/weather (closed)
  - implementation update (`2026-03-29`, continued):
    - `runaway_step_choice` prompt path is now wired end-to-end (engine -> human policy -> renderer)
    - board-near incident cards are now implemented in live viewer (`incident-stack`)
    - network failure visibility baseline is implemented (`network-badge`, reconnect states)
    - keyboard + ARIA baseline for decision overlay is implemented
  - follow-up update (`2026-03-29`, late):
    - replay/live Korean phrase convergence is now centralized via `GPT/viewer/renderers/phrase_dict.py`
    - live renderer now consumes shared phrase maps via injected JSON (`EVENT_LABELS`, `LANDING_TYPE_LABELS`)
    - stale-state network visibility now escalates to `업데이트 지연 Ns`
    - phrase-dictionary regressions are now covered by replay/human-play tests
    - prompt guidance pack is now closed with per-request actionable hints in live prompt summary/overlay

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
2. Use `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md` as the React transition top-level execution plan.
3. Use React detailed specs as active implementation references:
   - `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
   - `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md`
   - `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
   - `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
   - `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`
   - `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
4. Use `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md` as the shared boundary baseline before parallel implementation.
5. Treat current GPT-owned follow-up as:
   - plan/status/contract document maintenance
   - replay/live UI polish for Phase 5
   - human-readable replay/live wording/layout refinement
6. Treat current CLAUDE-owned follow-up as:
   - canonical public-state/event naming convergence
   - validator refresh toward the shared contract
   - substrate completeness review for Phase 5
   - lower-layer bug fixes discovered by that completeness review
   - lower-layer portability discipline for future non-HTML clients
7. Use `PLAN/GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md` only for GPT-side analysis tooling.
8. Use completed documents only as implementation history or rationale.
9. Use `PLAN/VISUALIZATION_GAME_PLAN.md` as the lower-layer substrate reference for visual runtime work.
10. Use `PLAN/[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md` as a technical-choice proposal, not as the active product plan.
11. Use Claude documents as reference for shared contracts, not as the active GPT task list.

## Temporary Execution Mode (`2026-03-30`)

Until explicitly changed, execution ownership is unified:

- GPT executes both GPT-owned and CLAUDE-owned workstreams.
- CLAUDE plans remain valid reference inputs, but implementation queue is single-owner.

Unified priority:

1. contract/parameter stability (`manifest`, hash/fingerprint, interface/API consistency)
2. runtime reliability (resume/timeout/auth/watchdog)
3. parameter-aware frontend rendering (seat/topology/label dynamic path)
4. phase-5 UX closure (human-play readability/continuity)
5. migration and doc relocation polish

Cross-plan guardrail:

- Any task affecting multiple plans must declare primary source-of-truth doc and list impacted specs in the same PR.
  - Latest closure (`2026-03-30`):
  - OI3 prompt-type coverage audit is complete in React track (helper/label catalogs + coverage tests across full human-policy request-type matrix).
  - OI7 WS/prompt schema freeze baseline is complete (`packages/runtime-contracts/ws/schemas`, `packages/runtime-contracts/ws/examples`, and `apps/server/tests/test_runtime_contract_examples.py`).
  - OI8 state-store direction is fixed for v1 (reducer+selector-first; see `PLAN/[DECISION]_REACT_STATE_STORE_STRATEGY.md`).
  - OI4 UI stack direction is fixed for v1 (plain-CSS-first; see `PLAN/[DECISION]_REACT_UI_STACK_STRATEGY.md`).
  - OI11 legacy-path cleanup has an auditable baseline (`tools/legacy_path_audit.py`) with initial counts recorded.
  - OI11 active-code strict gate is now enabled with zero-match baseline (`apps/packages/tools`).
  - Text encoding policy is now hard-gated: tracked text files must be UTF-8 without BOM (`tools/encoding_gate.py`, CI step active).
  - Browser parity fixture baselines are now versioned (`apps/web/e2e/fixtures/non_default_topology_line_3seat.json`, `apps/web/e2e/fixtures/manifest_hash_reconnect.json`) and fixture integrity is test-covered.
  - Playwright browser E2E baseline is now active in CI (`apps/web/playwright.config.ts`, `apps/web/e2e/parity.spec.ts`, workflow `npm run e2e` step).
  - Runtime hardening regression sweep (`2026-03-31`) is recorded in the detailed execution docs (`17 passed, 9 skipped` across prompt/runtime stream suites).
  - Theater continuity baseline now includes non-event prompt/ack flow in the same lane (`selectTheaterFeed`), and alert parity includes runtime critical/warning error channels (`selectCriticalAlerts`).

## Implementation Reading Rule (Mandatory)

Before implementation work, read documents in this order:

1. `PLAN/PLAN_STATUS_INDEX.md`
2. `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
3. `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
4. `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
5. task-specific specs:
   - `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md`
   - `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
   - `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
   - `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`
   - `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
6. `PLAN/[PLAN]_IMPLEMENTATION_DOCUMENT_USAGE_GUIDE.md` for conflict and reference policy

## Current Claude Direction

When reading `PLAN/` from `main`, treat CLAUDE work as:
- lower-layer visualization substrate work
- not upper-layer viewer product work

More concretely, the current intended CLAUDE direction is:
- verify replay/live/public-state payload completeness for Phase 5 consumers
- keep canonical contract names stable and validated
- fix lower-layer substrate bugs revealed by that verification
- avoid reintroducing broad alias-expansion as the default strategy
- avoid absorbing GPT-owned runtime/view responsibilities into substrate documents

If a new Claude-side task is proposed, it should usually fit one of these buckets:
- event/state contract verification
- validator update
- public-state completeness audit
- substrate portability review

If it does not, it should probably be tracked in the GPT-owned top-level runtime plan instead.

## Cleanup Decisions

### Keep
- keep all `[COMPLETE]` documents
- keep `CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
- keep `SHARED_VISUAL_RUNTIME_CONTRACT.md`
- keep `VISUALIZATION_GAME_PLAN.md`
- keep `[PROPOSAL]_CLAUDE_VISUALIZATION_OPINION.md`
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
