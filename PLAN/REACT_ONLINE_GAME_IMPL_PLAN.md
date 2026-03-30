# React Online Game Implementation Plan

Status: `ACTIVE`  
Owner: `Shared (Execution: GPT for backend/frontend tracks)`  
Updated: `2026-03-31`  
Depends on: `PLAN/ONLINE_GAME_ARCHITECTURE_PLAN.md`, `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Purpose

This document is the execution plan to move from the current Python-rendered HTML viewer to a React-based playable online game UI.

Primary goals:

- Replace polling viewer with a session-based, WebSocket-first architecture
- Support real human play with parameterized seat model (default profile: up to 4 seats) and AI/human mixed sessions
- Keep engine rules as source of truth and preserve DI boundaries
- Guarantee replay, observability, and maintainability

---

## Current Baseline vs Target

| Item | Current | Target |
|---|---|---|
| Backend framework | Python `http.server` style runtime | FastAPI app with service DI |
| Event delivery | HTTP polling | WebSocket push (`seq` resume) |
| Prompt delivery | HTTP polling | WebSocket prompt channel |
| Decision submission | `POST /decision` | WebSocket decision message |
| Frontend | Server-generated HTML/JS | React + Vite + TypeScript |
| Session model | Single runtime style | Explicit session create/join/start |
| Seat support | Partial | Parameterized seat model (default profile supports 1-4 human seats + AI mix) |

---

## Phase Overview

```text
Phase B1  FastAPI skeleton + REST session API
Phase B2  WS event stream + reconnect resume
Phase B3  Prompt dispatch via WS + timeout fallback
Phase B4  Seat model + auth token + mixed sessions

Phase F1  React scaffold + stream client
Phase F2  Board and player panels
Phase F3  Prompt UI and decision flow
Phase F4  Lobby and join flow
Phase F5  Animation and turn-theater polish
Phase F6  Legacy viewer parity audit and cutover
```

Parallel guidance:

- B1-B3 and F1-F2 can run in parallel
- F3 depends on B3 contract freeze
- F4 depends on B1
- F5 depends on F2/F3
- F6 depends on parity checklist and usability review

---

## Detailed Companion Specs (`2026-03-29`)

This plan is the top-level execution document.  
Detailed implementation specifications are maintained in:

- `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
- `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md`
- `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
- `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
- `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md`
- `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
- `PLAN/[REVIEW]_PIPELINE_CONSISTENCY_AND_COUPLING_AUDIT.md`

Current policy:

- Detailed active specs are canonical under `docs/api`, `docs/frontend`, `docs/backend`, and `docs/architecture`.
- `PLAN/[PLAN]_...` mirrors remain for execution tracking and status-driven redirects.
- New online-runtime implementation should follow `PLAN/[PLAN]_REPOSITORY_DIRECTORY_SPEC.md` and update canonical `docs/*` specs in the same task when interfaces change.

---

## Implementation Status Snapshot (`2026-03-31`)

- D1 scaffold and B1 baseline code have started in repository:
  - server skeleton: `apps/server/src/*`
  - migration scaffolds: `apps/web`, `packages/*`, `docs/*`, `tests/*`, `tools/*`
- B2 baseline has started:
  - websocket stream endpoint with heartbeat and `resume(last_seq)` replay
  - in-memory per-session `seq` message buffer service
  - `resume` gap-too-old guard path (`RESUME_GAP_TOO_OLD`) added
  - API-level resume-gap regression test baseline added (`apps/server/tests/test_stream_api.py`)
  - heartbeat backpressure payload baseline added (`subscriber_count`, `drop_count`, `queue_size`)
- B3 baseline has started:
  - prompt pending/timeout/decision-ack service skeleton wired
  - debug prompt route and websocket decision ack flow added
  - prompt timeout fallback trace event baseline added (`decision_timeout_fallback`)
  - engine fallback execution seam wired (`RuntimeService.execute_prompt_fallback`)
  - timeout fallback event now includes execution fields (`fallback_execution`, `fallback_choice_id`)
- B2/B3 hardening has started:
  - websocket token auth for seat vs spectator path
  - unauthorized/mismatched decision rejection paths
  - API-level decision-auth regression tests added (`UNAUTHORIZED_SEAT`, `PLAYER_MISMATCH`)
  - subscriber fan-out queue path with slow-consumer drop-oldest backpressure baseline
  - slow-consumer drop-oldest regression test baseline added (`apps/server/tests/test_stream_service.py`)
  - runtime watchdog baseline added (inactivity warning + `last_activity_ms` in runtime status)
  - structured logging retention baseline added:
    - env-driven log rotation settings (`MRN_LOG_FILE_PATH`, `MRN_LOG_FILE_MAX_BYTES`, `MRN_LOG_FILE_BACKUP_COUNT`)
    - rotating file handler initialization in server state bootstrap
    - runtime settings + structured log unit tests
  - runtime async bridge baseline added:
    - runtime execution now uses `asyncio.to_thread` task bridge
    - watchdog loop now runs as async task (no dedicated watchdog thread)
    - runtime async bridge regression test added (`apps/server/tests/test_runtime_service.py`)
- runtime fan-out baseline has started:
  - all-AI sessions trigger background engine run and stream publish
  - engine append events are now forwarded to websocket stream immediately
- F1 frontend baseline has started:
  - React+TS scaffold under `apps/web`
  - websocket stream client and baseline live connection panel
  - first reducer-driven stream state slice integrated
  - REST session client baseline added (`create/start/runtime-status`)
  - one-click all-AI session create/start + auto-connect flow added
  - Vitest baseline added with reducer unit test
  - selector/contract parser tests added (`snapshot`, `timeline`, `situation`)
  - runtime status auto-refresh baseline added
  - websocket auto-reconnect baseline added (incremental backoff)
  - websocket reconnect polish added (exponential backoff + jitter)
  - stream client reconnect/resume integration tests added (`apps/web/src/infra/ws/StreamClient.spec.ts`)
  - out-of-order stream buffer baseline added in reducer (`pendingBySeq`, contiguous flush)
  - seq-gap triggered resume-request baseline added in stream hook
  - F2 pre-structure started (connection/situation/timeline/board placeholder components)
  - F2 snapshot baseline added (public board tiles + player panels from stream snapshot)
  - F2 ring-board baseline added (default profile: 40-tile coordinate mapping)
  - F2 board-near incident stack baseline added
  - F2 board movement readability baseline added (recent move summary + tile highlight + pawn arrive pulse)
  - F2 localized selector labels baseline added (Korean event labels and detail summaries)
  - F2 parser fixture coverage expanded (dice/marker/heartbeat detail)
  - F3 prompt baseline started (overlay + choice submit + collapse)
  - F3 ack-state handling baseline added (rejected/stale unlock)
  - F3 prompt countdown baseline added
  - F3 keyboard/focus baseline added (first choice focus, Escape collapse)
  - F3 stale/rejected inline feedback baseline added in prompt overlay
  - F3 request-type helper copy baseline added in prompt overlay
  - F3 helper catalog split baseline added (`request_type` -> helper text module)
  - F3 helper coverage expanded for full request-type matrix (`burden_exchange`, `runaway_step_choice` 포함)
  - F2/F3 wording readability hardening (`2026-03-31`) added:
    - selector/event/prompt labels are Korean-first and human-readable
    - theater/timeline/prompt summaries now use user-facing phrasing over engine code terms
  - F5 incident theater depth baseline added (tone badge + seq meta)
  - F4 lobby baseline started (custom create/join/start/session-list in app shell)
  - F4 lobby/match route split baseline added (hash-based route tabs)
  - F4 join-token UX polish baseline added (seat dropdown + one-click token apply)
  - F4 dedicated lobby view extraction baseline added (`features/lobby/LobbyView.tsx`)
  - F4 URL cleanup baseline added (connected match hash token removal)
  - B5 decoupling baseline started:
    - session config resolves through parameter resolver
    - session API now returns `parameter_manifest` on create/get/start
    - stream emits `parameter_manifest` event on session start
    - session parameter resolver now supports `board_topology` override (`ring`/`line`)
    - runtime boot uses injected engine config factory (direct `DEFAULT_CONFIG` path removed)
    - root-source fingerprints + `manifest_hash` baseline is live in session manifest
    - selector label handling now uses catalog split from event codes (display/routing decoupling baseline)
    - selector fallback tolerance expanded for partial/flat manifest payload variants
    - frontend fallback tests expanded for unknown event kinds and partial manifest fixtures
    - stream manifest rehydrate path now updates board topology/label payloads (not tiles-only)
    - manifest rehydrate merge logic extracted to pure helper with unit tests (`apps/web/src/domain/manifest/manifestRehydrate.spec.ts`)
    - server integration tests now cover non-default manifest profile replay (`3-seat + line`)
    - web reconnect-flow fixture now covers hash-change replay chain (`manifestReconnectFlow.spec.ts`)
    - backend transport E2E fixture now covers reconnect replay after manifest-hash change
  - CI baseline added:
    - GitHub Actions workflow wiring for backend tests, manifest gate, web tests/build
    - active-code legacy path gate added (`python tools/legacy_path_audit.py --roots apps packages tools --strict`)
    - file: `.github/workflows/ci.yml`
- next implementation target (maintenance mode):
  - release gate rerun on each contract-impacting change (`C1`) or release candidate cycle
  - validator/contract parity follow-up (`SHARED_VISUAL_RUNTIME_CONTRACT` vs `validate_vis_stream` strict payloads)
  - docs sync pass (`docs/*` canonical specs + `PLAN/PLAN_STATUS_INDEX.md` evidence update in same PR)
  - OI5 persistence track (started):
    - file-backed restart persistence baseline for session/stream state is implemented
    - remaining follow-up: retention policy, restart-time runtime-task recovery policy, and failure-mode hardening
  - completed matrix closure (`2026-03-31`):
    - backend matrix tests (`apps/server/tests/test_parameter_service.py`, `apps/server/tests/test_sessions_api.py`)
    - browser matrix parity fixture (`apps/web/e2e/parity.spec.ts`, `apps/web/e2e/fixtures/parameter_matrix_economy_dice_2seat.json`)
  - root-source propagation closure (`2026-03-31`):
    - root-source file change -> `source_fingerprints` and `manifest_hash` delta tests
    - session bootstrap manifest reflects source changes (`apps/server/tests/test_parameter_propagation.py`)
  - runtime hardening regression sweep (`2026-03-31`):
    - `python -m pytest apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py apps/server/tests/test_stream_api.py apps/server/tests/test_stream_service.py apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_runtime_contract_examples.py`
    - result: `21 passed, 9 skipped` (fastapi-gated stream API tests skipped in this environment)
  - P0 consistency rerun (`2026-03-31`) passed:
    - `python tools/parameter_manifest_gate.py --check`
    - `python tools/encoding_gate.py`
    - `python tools/legacy_path_audit.py --roots apps packages tools --strict`
    - backend parameter path suite: `11 passed, 8 skipped`
    - web manifest/selector suite: `15 passed`
  - P1/P2 revalidation rerun (`2026-03-31`) passed:
    - backend reliability batch:
      - `python -m pytest apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py`
      - result: `14 passed, 9 skipped`
    - frontend reconnect/manifest/projection batch:
      - `cmd /c npm run test -- --run src/infra/ws/StreamClient.spec.ts src/domain/manifest/manifestRehydrate.spec.ts src/domain/manifest/manifestReconnectFlow.spec.ts src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts`
      - result: `23 passed`
  - CLAUDE-track substrate validator cleanup (`2026-03-31`) passed:
    - `python -m pytest GPT/test_visual_runtime_substrate.py` (`2 passed`)
    - `python GPT/test_replay_viewer.py` (`Phase 2: ALL TESTS PASSED`)
  - OI5 baseline start (`2026-03-31`):
    - file-backed restart persistence adapters added for sessions/stream buffers
    - env flags added: `MRN_SESSION_STORE_PATH`, `MRN_STREAM_STORE_PATH`
    - restart persistence regression tests added (`apps/server/tests/test_restart_persistence.py`)
  - contract/validator maintenance-loop check (`2026-03-31`) passed:
    - shared contract payload rows vs strict validator required-field sets were rechecked
    - no canonical drift found for `round_start` / `trick_used`
  - docs migration closure (`2026-03-31`):
    - detailed active specs are mirrored under `docs/api`, `docs/backend`, `docs/frontend`, `docs/architecture`
    - compatibility mirror notes added to matching `PLAN/[PLAN]_...` files
  - P4 operations docs closure (`2026-03-31`):
    - release gate playbook: `docs/architecture/react-fastapi-release-playbook.md`
    - Claude substrate maintenance loop: `docs/architecture/claude-substrate-maintenance-loop.md`
    - implementation usage guide now maps both docs as canonical references

---

## Common Governance

## 1. Document organization and storage

Use this structure consistently:

- `PLAN/`: plans, proposals, status trackers
- `DATA/`: game data specs and data snapshots
- `docs/api/`: REST and WebSocket contract docs
- `docs/frontend/`: component specs, behavior docs, test matrix
- `docs/backend/`: service boundaries, DI graphs, runtime operations
- `SYNC/`: cross-agent handoff notes

Filename conventions:

- `[PLAN]_...` executable plan
- `[PROPOSAL]_...` directional options
- `[REVIEW]_...` audit/checklist output
- `[ADR]_...` architecture decision records

## 2. Rule/data specification policy

Before React cutover, ensure data specs cover:

- Characters and pair flips
- Tricks and burden cards (timing, visibility, constraints)
- Fortune and weather cards
- Marker transfer/flip rules
- Lap reward and bankruptcy behavior

Each spec row must include:

- `id`, `name`, `timing`, `visibility`, `inputs`, `effects`, `end_condition`, `vis_events`

## 3. Source-of-truth hierarchy

1. Engine code (`GPT/engine.py`, `GPT/effect_handlers.py`)  
2. Shared runtime contract (`PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`)  
3. Data definitions (`characters.py`, trick/weather/fortune modules)  
4. Frontend rendering logic (must not redefine rules)

If docs and code disagree, code wins and docs update in same task.

---

## Backend Plan

## B1. FastAPI app and session API

Canonical backend package target:

```text
apps/server/
  src/
    app.py
    routes/
      sessions.py
      stream.py
      health.py
    services/
      session_service.py
      runtime_service.py
      prompt_service.py
      auth_service.py
    infra/
      ws/
      logging/
    adapters/
      engine_adapter.py
      policy_router.py
```

Compatibility note:

- Existing `CLAUDE/server` references are legacy transition notes.
- New implementation should be placed under `apps/server` per repository directory spec.

REST endpoints:

- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{id}`
- `POST /api/v1/sessions/{id}/join`
- `POST /api/v1/sessions/{id}/start`

Session states:

- `waiting -> in_progress -> finished`

## B2. WebSocket event stream

Endpoint:

- `WS /api/v1/sessions/{id}/stream?token=...`

Message types:

- `event`, `prompt`, `decision_ack`, `error`, `heartbeat`

Reconnect:

- Client sends `resume(last_seq)`
- Server replays from `last_seq + 1`

## B3. Prompt dispatch and timeout

Flow:

1. Engine asks policy `choose_X`
2. Prompt dispatcher routes by seat type
3. Human seat receives prompt and responds by `request_id`
4. Timeout uses server-authoritative fallback once
5. Engine proceeds without deadlock

## B4. DI and API boundaries

DI rules:

- Route handlers depend only on service interfaces
- Composition root in `app.py`
- No engine internals imported inside route modules

API rules:

- Versioned path (`/api/v1`)
- Stable response envelope (`ok`, `data`, `error`)
- Explicit error codes for timeout, stale request, unauthorized seat

## B5. Logging and observability

Structured JSON logs:

- Access logs with latency and status
- Prompt lifecycle (`prompt_sent`, `decision_received`, `fallback_timeout`)
- Session lifecycle (`created`, `joined`, `started`, `finished`)
- Critical rule transitions (`marker_transferred`, `marker_flip`, `bankruptcy`)

Required fields:

- `session_id`, `round_index`, `turn_index`, `request_id`, `player_id`, `seq`

## B6. Additional backend constraints

- Backpressure handling for slow WS clients
- Seat token verification and spectator policy
- Runtime watchdog for stuck session threads/tasks
- Future persistence adapter behind interface (optional phase)

---

## Frontend Plan

## F1. React scaffold and stream client

Canonical frontend package target:

```text
apps/web/
  src/
    app/
    core/
      di/
      logger/
      config/
    domain/
      state/
      reducers/
      selectors/
      contracts/
    infra/
      ws/
      api/
      persistence/
    features/
      board/
      players/
      prompt/
      theater/
      lobby/
      replay/
    shared/ui/
  tests/
```

Compatibility note:

- Existing `frontend/` references are legacy scaffold wording.
- New implementation should be placed under `apps/web` per repository directory spec.

Core hook:

- `useGameStream(sessionId, token)` for WS connect, resume, event reduce, prompt handling

## F2. Component architecture and DI

Feature components:

- Board: tiles, ownership, pawn positions, map overlays
- Players: data-driven player status panels (count from manifest/session snapshot)
- Prompt: modal/panel decision UI
- Theater: non-human turn narration and action cards
- Timeline/event log: compact trace and filtering

DI rules:

- UI never directly uses `fetch`/`WebSocket`
- Services injected via container
- Domain reducer is pure and framework-agnostic

## F3. Component-level tests and methods

Test stack:

- Unit: Vitest + React Testing Library
- Contract: payload parser tests for all prompt/event types
- Integration: WS message flow and decision lifecycle
- E2E: Playwright human turn and spectator flow

Test naming:

- `ComponentName.spec.tsx`
- `feature.contract.spec.ts`
- `flow.<scenario>.e2e.spec.ts`

## F4. Documentation update and commit policy

For each frontend feature commit:

1. Update component doc in `docs/frontend/components/`
2. Update API/contract doc if payload changed
3. Update plan status index

Commit title convention:

- `feat(frontend): ...`
- `fix(prompt): ...`
- `refactor(store): ...`
- `docs(plan): ...`
- `test(frontend): ...`

## F5. Lint/style compatibility

- Keep Python style and test pipelines unchanged
- Frontend enforces strict TypeScript + ESLint + Prettier
- Ban direct cross-layer imports (UI -> infra only through feature services)
- No `any` in domain and infra layers

## F6. Library/version baseline

Proposed baseline (exact pins at scaffold date):

- React `19.x`
- Vite `6.x`
- TypeScript `5.x`
- React Router `7.x`
- Zustand `5.x`
- TanStack Query `5.x`
- Vitest, RTL, Playwright (latest stable)

Version lock process:

- Pin exact versions in lockfile
- Record matrix in `docs/frontend/versions.md`

## F7. Required information per UI area

Board and center panel must display:

- Round/turn/weather
- Current actor and marker owner
- Remaining end-time meter
- Last dice result and movement path

Player panel must display:

- Cash, shards, score tokens, owned tiles
- Public tricks, hidden trick count, burdens
- Position, target status, eliminated status
- Remaining dice cards

Prompt panel must display:

- Human-readable request title and timing phase
- Legal choices with effect text
- Timeout countdown
- Pending lock state after click
- Collapse/open controls to avoid blocking observation

## F8. Animation and interaction requirements

Required animation set:

- Pawn move along path (step animation)
- Purchase/rent/weather/fortune as board-near incident cards
- Turn-theater cards for non-human turns
- Marker transfer and card flip visual confirmation

Interaction requirements:

- Full-card click target for each choice option
- Keyboard access for all decision options
- Prompt overlay must be collapsible and restorable

## F9. State management rules

State slices:

- `gameStateSlice` (event-reduced public state)
- `promptSlice` (active prompt, timeout, pending)
- `uiSlice` (layout, panel open/close)
- `networkSlice` (ws status, retries, lag)

Rules:

- Only reducers/services mutate state
- Components consume selectors only
- Out-of-order events buffered until contiguous `seq`
- No duplicate derived state in components

---

## Review Framework

## R1. Design and pipeline review

Before phase close:

- DI boundary check
- Contract diff check
- Failure mode simulation (disconnect, timeout, stale decision, replay resume)

## R2. UI/UX benchmark review

Benchmark against live board game UX patterns (reference only, no direct copying):

- Action readability within 2 seconds
- Choice consequence clarity
- Visual focus integrity during overlays and animations
- Non-human turn observability without blocking human player context

## R3. Rule visibility and usability review

Checklist must verify all public information is represented:

- Economy: rent payer/receiver and cash deltas
- Movement: rolled values, used cards, route, destination
- Effects: weather/fortune text and resulting state
- Marker: transfer and flip progression
- Trick/burden: public list + hidden count + use/remove trace
- Endgame: bankruptcy reason and finish trigger

No release gate passes until checklist is green for:

- One complete replay session
- One complete live human session

---

## Migration and Cutover

## M1. Parity-first strategy

1. Freeze event/prompt contracts  
2. Build React spectator mode first  
3. Add prompt UI by request type groups  
4. Run side-by-side parity tests vs legacy viewer  
5. Remove legacy only after parity gate passes

## M2. Regression gates from known issues

React cutover must explicitly prevent:

- Duplicate prompt rendering for same prompt instance
- Prompt loops caused by stale signatures
- Re-selecting same `active_flip` card in one flip phase
- Human information blocked by non-human overlays

---

## Dev Setup

Backend:

```bash
pip install fastapi uvicorn[standard] websockets
uvicorn apps.server.src.app:app --reload --port 8000
```

Frontend:

```bash
cd apps/web
npm create vite@latest . -- --template react-ts
npm install
npm run dev
```

Vite proxy baseline:

```ts
export default defineConfig({
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

---

## Acceptance Criteria

Backend done when:

- Session API creates/joins/starts sessions reliably
- WS stream pushes all events through `game_end`
- Human prompts and timeout fallback are deterministic
- Reconnect resumes from `last_seq`

Frontend done when:

- Spectator mode is fully watchable
- Human prompt flow is fully playable
- Lobby create/join flows work end-to-end
- Board shows movement, ownership, economy changes, and incident cards
- Turn-theater shows non-human action summary without blocking player context

---

## Unified Priority Order (Single-Owner Mode)

Temporary execution policy:

- GPT executes both prior GPT-owned and CLAUDE-owned tracks until further notice.
- Priority is set to minimize cross-plan regressions and contract churn.

Priority stack:

1. `P0` Contract/parameter stability first
- `parameter_manifest`, `manifest_hash`, `source_fingerprints`
- interface/API consistency freeze before feature expansion
- reason: prevents rework across backend/frontend/replay

2. `P1` Runtime reliability and prompt determinism
- B2/B3/B4 hardening (resume, timeout fallback, auth mismatch, watchdog)
- reason: unstable runtime invalidates all UX and parity testing

3. `P2` Parameter-aware rendering closure
- F7 + decoupling track completion
- topology/seat/label dynamic rendering and rehydrate guards
- reason: blocks hardcoding regressions when rules/config change

4. `P3` Human-play UX closure (Phase 5 quality)
- prompt clarity, theater continuity, board incident visibility, non-human turn readability
- reason: user-facing playability after technical stability is secured
- status update (`2026-03-31`): closed for current v1 scope (long-session density tuning + prompt compact mode + event wording parity hardening)

5. `P4` Migration polish and documentation relocation
- PLAN -> DOCS relocation, legacy reference cleanup, release playbook
- reason: lowest immediate risk to runtime correctness

## Cross-Plan Change Impact Control

Any task must classify and gate its impact before merge.

Impact classes:

- `C1 Contract`: API/WS/interface/manifest shape
- `C2 Runtime`: session/prompt/stream execution behavior
- `C3 Projection`: selector/layout/label/topology rendering
- `C4 UX Only`: wording/style/interaction that does not change rule/state semantics

Required gates by class:

- `C1`: contract tests + spec updates + replay compatibility note
- `C2`: integration tests (resume/timeout/stale/auth) + watchdog check
- `C3`: manifest variant tests (seat/topology/unknown kinds) + rehydrate test
- `C4`: component tests + no-contract-diff proof

Merge rule:

- never merge `C2/C3/C4` changes that depend on an unmerged `C1` delta
- if multiple plans are touched, the PR must list a single source-of-truth document and reference all affected plans/specs

---

## Open Items

| # | Item | Owner | Notes |
|---|---|---|---|
| OI1 | Engine sync runtime bridge to async FastAPI | Shared | Closed (2026-03-31): runtime now bridges blocking engine execution via `asyncio.to_thread` with async watchdog task path |
| OI2 | Extract board tile layout constants from legacy renderer | GPT | Closed (2026-03-31): board projection constants/modules are extracted (`boardProjection` + `boardGridForTileCount`), ring/line grid sizing is parameterized, React board no longer depends on fixed `11x11` template literals, and projection tests pass (`boardProjection.spec.ts`) |
| OI3 | Full prompt type coverage audit in human policy and React UI | GPT | Complete: helper/label catalog + coverage tests enforce full human-policy request-type matrix |
| OI4 | Final UI stack decision (plain CSS modules vs utility stack) | GPT | Complete: plain-CSS-first strategy fixed for v1 (`PLAN/[DECISION]_REACT_UI_STACK_STRATEGY.md`) |
| OI5 | Session persistence after restart | Shared | Started (`2026-03-31`): file-backed restart persistence baseline is in place; follow-up hardening remains for v2 closure |
| OI6 | Migrate detailed specs from `PLAN/` to `docs/*` after scaffold | Shared | Closed (2026-03-31): canonical detailed specs now live under `docs/*`; `PLAN/` mirrors retain redirect notes |
| OI7 | WS and prompt schema freeze with examples | Shared | Complete: frozen schemas/examples under `packages/runtime-contracts/ws/*` + validation test `apps/server/tests/test_runtime_contract_examples.py` |
| OI8 | State store final decision (`zustand` only vs hybrid) | GPT | Complete: reducer+selector-first baseline fixed for v1 (`useReducer` stream store, no zustand dependency in current phase) |
| OI9 | Structured log retention and rotation policy | Shared | Closed (2026-03-31): env-driven rotation settings + bootstrap + test coverage + backend runbook (`docs/backend/runtime-logging-policy.md`) |
| OI10 | Legacy vs React parity checklist artifact | Shared | Closed (2026-03-31): replay parity and live human-play acceptance passes are both complete with logged evidence under `result/acceptance/*` |
| OI11 | Legacy path (`GPT/`, `CLAUDE/`, `frontend/`) reference cleanup | Shared | Closed (2026-03-31): strict active-root gate is clean (`apps/packages/tools`: 0 refs), CI gate active, and cleanup policy documented (`docs/architecture/legacy-reference-cleanup-policy.md`) |
| OI12 | Parameter-manifest and config-resolver decoupling track | Shared | Closed (2026-03-31): resolver/config-factory/manifest stream baseline + Playwright/browser/backend matrix coverage completed (seat/topology/economy/dice variants) |
| OI13 | Root-source change auto-propagation guardrail (fingerprint/hash/CI) | Shared | Closed (2026-03-31): fingerprint/hash CI gate + source-change propagation tests (manifest + session bootstrap) are in place |
