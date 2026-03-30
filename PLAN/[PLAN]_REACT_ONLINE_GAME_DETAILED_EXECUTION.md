# [PLAN] React Online Game Detailed Execution

> Canonical location (migrated on 2026-03-31): `docs/architecture/react-online-game-detailed-execution.md`  
> This `PLAN/` file remains as a compatibility mirror for existing links.

Status: `ACTIVE`  
Owner: `Shared (Execution: GPT for backend/frontend tracks)`  
Updated: `2026-03-31`  
Parent: `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`

## Purpose

This document defines the detailed implementation backlog for the React online game transition.

It is intentionally execution-focused:

- exact phase deliverables
- phase entry/exit criteria
- test and verification gates
- risk controls and fallback policy

Audit companion:
- `PLAN/[REVIEW]_PIPELINE_CONSISTENCY_AND_COUPLING_AUDIT.md`

## Current Progress Snapshot (`2026-03-31`)

- `D1` scaffold: in progress
  - created baseline roots: `apps/`, `packages/`, `docs/`, `tests/`, `tools/`
  - added placeholder READMEs for migration-safe structure anchoring
- `B1` baseline: in progress
  - added FastAPI app skeleton at `apps/server/src/app.py`
  - added session lifecycle REST routes (`create/list/get/join/start`)
  - added replay export REST route (`GET /api/v1/sessions/{session_id}/replay`)
  - added in-memory `SessionService` and initial unit tests
- `B2` baseline: in progress
  - added websocket endpoint `WS /api/v1/sessions/{session_id}/stream`
  - added in-memory stream buffer service with monotonic `seq`
  - added baseline `resume(last_seq)` replay behavior and heartbeat messages
  - added seat-token-aware websocket authorization path
  - added subscriber fan-out push path (published event -> connected socket queue)
  - added queue-overflow drop-oldest policy for slow consumers (backpressure baseline)
  - added slow-consumer drop-oldest regression test (`apps/server/tests/test_stream_service.py`)
  - added `resume` gap-too-old guard (`RESUME_GAP_TOO_OLD`) and buffered replay fallback
  - stream message envelope now includes `server_time_ms` on buffered stream path
  - added API-level resume-gap regression test (`apps/server/tests/test_stream_api.py`, fastapi-gated)
  - heartbeat now includes backpressure stats (`subscriber_count`, `drop_count`, `queue_size`)
  - reconnect soak regression is now covered (`apps/server/tests/test_stream_api.py`)
  - production threshold tuning baseline is now env-driven (`apps/server/src/config/runtime_settings.py`)
- `B3` baseline: in progress
  - added in-memory prompt lifecycle service (`pending`, `submit_decision`, `timeout_pending`)
  - added debug prompt route for end-to-end prompt envelope smoke path
  - websocket decision ack now validates pending prompt status (`accepted/rejected/stale`)
  - timeout path now emits public fallback trace event (`decision_timeout_fallback`)
  - added spectator decision block and authenticated player mismatch block
  - added API-level decision auth regression tests (`UNAUTHORIZED_SEAT`, `PLAYER_MISMATCH`)
  - stale-request hardening is now closed (`already_resolved`, duplicate replay guard, missing choice guard)
  - engine fallback execution seam wired (`RuntimeService.execute_prompt_fallback`)
  - timeout fallback event payload now includes execution result fields (`fallback_execution`, `fallback_choice_id`)
- runtime fan-out baseline: in progress
  - all-AI session start now triggers background engine execution
  - emitted vis events are published into websocket stream buffer in order
  - incremental live fan-out is now active (event append -> immediate WS publish bridge)
  - runtime watchdog baseline added (inactivity warning + `last_activity_ms`)
  - frontend connection panel now surfaces watchdog/runtime activity fields
  - watchdog timeout is now configurable per environment (`MRN_RUNTIME_WATCHDOG_TIMEOUT_MS`)
  - structured log retention baseline added:
    - env-driven log rotation settings (`MRN_LOG_FILE_PATH`, `MRN_LOG_FILE_MAX_BYTES`, `MRN_LOG_FILE_BACKUP_COUNT`)
    - rotating file handler bootstrap in server state
    - runtime setting + structured log unit tests
- `F1` baseline: in progress
  - created React+TS scaffold files under `apps/web`
  - added baseline stream contract types and websocket client
  - added `useGameStream` hook and minimal connection/status UI
  - added first domain reducer slice (`gameStreamReducer`) and hook integration
  - added REST session API client and one-click all-AI session start/connect path
  - added cross-session `seq` reset guard in stream hook
  - added vitest baseline and reducer unit tests
  - added selector/contract parser unit tests for snapshot/timeline/situation extraction
  - added runtime status auto-refresh baseline in app shell
  - added websocket auto-reconnect baseline with incremental backoff
  - upgraded reconnect strategy to exponential backoff + jitter
  - added stream-client reconnect/resume integration tests (`infra/ws/StreamClient.spec.ts`)
  - state-store direction frozen for v1: reducer+selector-first (`useReducer`, no `zustand` dependency)
  - added reducer out-of-order buffering (`pendingBySeq`) with contiguous flush
  - added gap-triggered `resume(last_seq)` request path in stream hook
  - dependency install/build pipeline now green on local environment
  - parser fixtures expanded for less-common payload variants (`dice_roll`, `marker_transferred`, heartbeat backpressure)
  - remaining: parser fixtures for future prompt metadata variants
- `F2` baseline: started
  - split baseline UI into feature components (`status`, `timeline`, `board` placeholder)
  - added stream selector layer (`domain/selectors/streamSelectors.ts`)
  - added snapshot-driven public board/player baseline rendering
  - added topology-aware board projection baseline (`ring`/`line`; default profile uses 40-tile ring)
  - added manifest-driven tile-kind label override path (`labels.tile_kind_labels`) in board renderer
  - added board-near recent incident card stack baseline (`IncidentCardStack`)
  - added last-move board summary and from/to tile highlight baseline
  - added pawn-arrive pulse animation baseline
  - added localized selector labels/detail summaries
  - remaining: optional board-side micro-animation polish
- `F3` baseline: started
  - added prompt selector baseline (`selectActivePrompt`) with ack-aware closing
  - added prompt overlay component with full-card choices and collapse toggle
  - added decision submit wiring from UI (`useGameStream.sendDecision`)
  - added prompt selector unit tests
  - added ack-status unlock handling for rejected/stale decisions
  - added countdown baseline in prompt overlay
  - added keyboard/focus baseline (first-choice focus, focus restore, Escape collapse)
  - added stale/rejected inline feedback messaging in prompt overlay
  - added timeout fallback waiting copy in prompt overlay
  - added prompt-type-specific helper copy baseline
  - added prompt helper catalog split baseline (`request_type` helper map module)
  - expanded helper+label coverage for full human-policy request matrix (`movement`, `runaway_step_choice`, `lap_reward`, `draft_card`, `final_character`, `trick_to_use`, `purchase_tile`, `hidden_trick_card`, `mark_target`, `coin_placement`, `geo_bonus`, `doctrine_relief`, `active_flip`, `specific_trick_reward`, `burden_exchange`)
  - added coverage tests so future prompt-type additions fail fast when helper/label copy is missing
  - prompt overlay is now actionable-seat scoped (local player prompt only)
  - non-local prompts are now shown as non-blocking observer cards to preserve turn-theater readability
- `F4` baseline: started
  - added lobby control panel for custom seat composition and seed/profile inputs
  - added host-start path with explicit host token input
  - added seat-join path (`session_id`, `seat`, `join_token`, `display_name`) with auto-connect
  - added session list refresh panel for in-app lifecycle visibility
  - added create-time join-token state management with seat-based auto-fill
  - added seat-select + one-click join-token apply controls
  - added session-list quick select action (`Use session`)
  - added lobby/match route split baseline (hash-based route tabs)
  - added dedicated lobby page extraction (`features/lobby/LobbyView.tsx`)
  - added route deep-link baseline (`#/match?session=...&token=...`)
  - added connected-state URL cleanup baseline (token stripped from hash)
  - remaining: optional URL short-state policy
- parameter-driven decoupling track: started
  - hardcoded sensitivity audit completed (server/runtime/engine/web hotspots)
  - execution source: `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
  - implemented baseline:
    - backend resolved-parameter schema/resolver path
    - runtime config factory path (direct `DEFAULT_CONFIG` boot replaced)
    - session API `parameter_manifest` payload on create/get/start
    - stream `parameter_manifest` event baseline on session start
    - resolver now supports `board_topology` override (`ring`/`line`) for session-scoped projection contracts
    - frontend manifest bootstrap consumption baseline (board/join-seat path)
    - frontend stream reducer manifest-hash rehydrate baseline
    - stream-manifest merge now rehydrates topology + labels in app state (not tiles-only)
    - manifest merge logic extracted to pure helper + unit tests (`domain/manifest/manifestRehydrate.spec.ts`)
    - frontend selector label-catalog split baseline (event code -> display label separation)
    - frontend selector fallback hardening baseline:
      - tolerate malformed latest manifest by scanning previous valid manifest
      - tolerate flat `parameter_manifest` event payload shape
      - synthesize fallback board tiles from `tile_count` when tile list is absent
      - synthesize fallback seat options from `seats.max` when `seats.allowed` is absent
    - frontend fallback regression tests expanded:
      - unknown event code timeline fallback
      - partial/flat manifest parsing fixtures
    - server integration fixtures expanded:
      - non-default profile manifest path (`3-seat + line`) on session create/start stream
      - reconnect replay fixture validates latest manifest variant payload visibility
      - backend transport E2E fixture validates reconnect replay after manifest-hash change
    - web integration fixture expanded:
      - reducer -> selector -> manifest merge chain validated on hash-change reconnect replay (`manifestReconnectFlow.spec.ts`)
    - stream API replay regression coverage expanded for flat manifest payload shape
    - stale-artifact gate helper baseline (`tools/parameter_manifest_gate.py --check`)
    - stale snapshot regression test baseline (`apps/server/tests/test_parameter_manifest_snapshot.py`)
    - CI workflow baseline wired:
      - backend tests
      - manifest snapshot gate check
      - web tests/build
      - file: `.github/workflows/ci.yml`
  - closure update:
    - manifest-hash triggered projection reset baseline is active in reducer path (`gameStreamReducer`)
    - browser reconnect/non-default topology fixture playbooks are versioned under `apps/web/e2e/fixtures/*`
    - fixture integrity is test-gated (`browserFixtureCatalog.spec.ts`)
  - closure update:
    - automated browser-run e2e baseline is now active:
      - `apps/web/playwright.config.ts`
      - `apps/web/e2e/parity.spec.ts`
      - CI step wiring (`npx playwright install --with-deps chromium`, `npm run e2e`)
  - closure update (`2026-03-31`):
    - broader parameter-pack matrix coverage is complete for current scope:
      - backend matrix tests for seat/economy/dice overrides
      - session start matrix-manifest verification
      - Playwright matrix parity scenario (`parameter_matrix_economy_dice_2seat`)
  - Phase 5 UX closure update (`2026-03-31`):
    - match view now supports compact-density layout for long sessions
    - large prompt choice sets now default to compact mode with detail toggle
    - additional event-family wording parity is normalized in selector detail summaries
- contract freeze artifacts (`OI7`): complete baseline
  - added frozen WS schema set under `packages/runtime-contracts/ws/schemas`
  - added canonical WS examples under `packages/runtime-contracts/ws/examples`
  - added schema/example validation test (`apps/server/tests/test_runtime_contract_examples.py`)
- parity checklist artifact (`OI10`): acceptance closed (`2026-03-31`)
  - `PLAN/[CHECKLIST]_LEGACY_VS_REACT_PARITY.md`
  - evidence logs:
    - `result/acceptance/2026-03-31_replay_parity.log`
    - `result/acceptance/2026-03-31_live_human_play.log`
- docs migration (`OI6`): closed (`2026-03-31`)
  - canonical detailed specs now under `docs/api`, `docs/backend`, `docs/frontend`, `docs/architecture`
  - `PLAN/[PLAN]_...` mirrors retain redirect notes for compatibility links
- UI stack decision (`OI4`): complete baseline
  - plain-CSS-first strategy fixed for v1 (`PLAN/[DECISION]_REACT_UI_STACK_STRATEGY.md`)
- legacy-path cleanup (`OI11`): closed (`2026-03-31`)
  - added reference audit script: `tools/legacy_path_audit.py`
  - baseline scan counts (`2026-03-30`): `GPT/`=156, `CLAUDE/`=50, `frontend/`=8
  - active code roots are now clean (`apps/packages/tools`: 0 matches under strict audit)
  - CI strict gate is enabled for active code roots (`.github/workflows/ci.yml`)
- `B4+`: closed baseline (`2026-03-31`)
  - runtime watchdog and structured logging retention policy are active in code
  - structured logs now keep stable correlation fields (`session_id`, `request_id`, `player_id`, `seq`) on every record
  - error payload normalization now includes transport/runtime fallback codes (`HTTP_EXCEPTION`, `INTERNAL_SERVER_ERROR`)
  - prompt/runtime regression sweep (`2026-03-31`): `21 passed, 9 skipped` (`test_error_payload`, `test_structured_log`, `test_stream_api`, `test_stream_service`, `test_runtime_service`, `test_prompt_service`, `test_runtime_contract_examples`)

## Execution Policy

- No rule logic migration into frontend.
- Engine remains the only game authority.
- Every phase includes contract examples and tests in the same PR.
- Any payload shape change requires updates to:
  - `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`
  - this execution plan
  - the API/interface spec docs

## Workstream Map

| Stream | Scope | Primary Owner | Dependency |
|---|---|---|---|
| `B` Backend runtime and API | FastAPI, session lifecycle, WS stream, prompt dispatch | GPT | Shared contract freeze |
| `F` Frontend runtime and UX | React client, state, prompt UX, theater UX | GPT | B stream APIs |
| `Q` Quality and release gates | parity checks, E2E, replay/live regression | Shared | B/F completion |

## Detailed Phases

## B1. Session Service and REST Foundation

Goal:
- Build a FastAPI session lifecycle skeleton.

Implementation:
1. Add `apps/server/src/app.py` composition root.
2. Add in-memory `SessionService` with explicit state machine:
   - `waiting`, `in_progress`, `finished`, `aborted`.
3. Implement:
   - `POST /api/v1/sessions`
   - `GET /api/v1/sessions`
   - `GET /api/v1/sessions/{session_id}`
   - `POST /api/v1/sessions/{session_id}/join`
   - `POST /api/v1/sessions/{session_id}/start`
4. Introduce typed response envelope:
   - `ok`, `data`, `error`.

Definition of done:
- Parameterized seat config can be created and started (default profile includes 4-seat mixed config).
- Host and seat token validation works for join/start.
- Unit tests cover invalid transition attempts.

## B2. Event Streaming and Resume

Goal:
- Deliver `VisEvent` stream over WebSocket with reliable resume.

Implementation:
1. Add `ConnectionRegistry` and `EventBroadcaster`.
2. Add `WS /api/v1/sessions/{id}/stream`.
3. Implement monotonic `seq`.
4. Implement reconnect resume:
   - client sends `resume(last_seq)`.
   - server replays buffered messages from `last_seq + 1`.
5. Add heartbeat and stale connection cleanup.

Definition of done:
- Replay of buffered events works after simulated disconnect.
- Slow client does not block global stream.
- Integration tests verify ordered `seq` replay.

## B3. Prompt Dispatch and Timeout Policy

Goal:
- Route human prompts over WS and preserve engine progress on timeout.

Implementation:
1. Add `PromptDispatcher` abstraction.
2. Route each prompt to seat policy:
   - human: WS prompt
   - AI: internal policy execution
3. Add `request_id` idempotency checks.
4. Add timeout fallback execution exactly once.
5. Emit prompt lifecycle logs:
   - `prompt_sent`
   - `decision_received`
   - `decision_timeout_fallback`
   - `decision_stale_ignored`.

Definition of done:
- Human decision accepted and acknowledged once.
- Duplicate or late decisions rejected consistently.
- Engine progresses even under human timeout.

## B4. Runtime Hardening and Ops Readiness

Goal:
- Stabilize runtime behavior for long-running sessions.

Implementation:
1. Runtime watchdog for stuck prompt/session.
2. Structured JSON logs with correlation fields.
3. Error code normalization and user-facing categories.
4. Restart persistence adapter seam (started baseline):
   - file-backed session/stream state restore path
   - env-gated activation (`MRN_SESSION_STORE_PATH`, `MRN_STREAM_STORE_PATH`)

Definition of done:
- Recoverable faults are surfaced with stable error codes.
- Crash logs contain `session_id`, `request_id`, `player_id`, `seq`.

## B5. Parameter-Driven Config Decoupling

Goal:
- Remove backend/runtime hardcoding sensitivity when gameplay parameters change.

Implementation:
1. Add typed session config validation and `ResolvedGameParameters`.
2. Replace runtime `DEFAULT_CONFIG` boot path with injected config factory.
3. Emit public `parameter_manifest` in stream/session bootstrap.
4. Add compatibility tests for variant parameter packs.
5. Add root-source fingerprint + `manifest_hash` generation and CI stale-artifact gate.

Definition of done:
- Runtime starts from resolved session config without direct global default dependency.
- Stream contract provides enough parameter metadata for dynamic frontend rendering.
- Root-source modification automatically changes emitted manifest hash in runtime bootstrap.

## F1. React Bootstrap and Contracts

Goal:
- Start React app with strict typed contracts and infra ports.

Implementation:
1. Create `apps/web/` (Vite + React + TS strict).
2. Add core contract types for event/prompt envelopes.
3. Add stream client abstraction and state reducer skeleton.
4. Add initial CI checks:
   - lint
   - unit tests
   - type checks.

Definition of done:
- App can connect to stream and show connection state.
- Contract parser tests pass for baseline events.

## F2. Core Match Surfaces

Goal:
- Render board, players, timeline, and situation from stream state.

Implementation:
1. Board tiles and pawn markers.
2. Player panels with economy and trick visibility.
3. Situation and timeline panels with human-readable labels.
4. Event summary cards for key public events.

Definition of done:
- Full public state visible without prompt overlay.
- Replay stream can reconstruct a complete match view.

## F3. Prompt UX and Decision Submission

Goal:
- Provide stable and clear human input experience.

Implementation:
1. Prompt overlay with full-card click targets.
2. Busy lock and spinner only after user click.
3. Collapsible prompt to observe board while waiting.
4. Keyboard accessibility and focus restore.
5. Decision submit and `decision_ack` handling.

Definition of done:
- No accidental double submit.
- No auto-lock without user action.
- Prompt dismiss/restore works during non-human turns.

## F4. Lobby and Join Flow

Goal:
- Human seats can create, join, and start sessions from UI.

Implementation:
1. Session create form with seat assignment.
2. Join with seat token flow.
3. Start controls with host-only constraints.
4. Basic reconnection UX.

Definition of done:
- Session can start from UI using server seat model (default profile supports 1-4 humans + AI mixed).

## F5. Theater and Incident UX

Goal:
- Raise non-human turn readability and event continuity.

Implementation:
1. Turn theater stream for non-human actions.
2. Board-near incident cards for:
   - weather
   - fortune
   - movement
   - purchase
   - rent
   - marker transfer.
3. Pawn movement animations and marker transfer highlights.
4. Bankruptcy and endgame alerts.

Definition of done:
- Human player can follow all other seats without opening debug views.
- Event continuity is visible for economy changes.

## F6. Parity Closure and Cutover

Goal:
- Replace legacy viewer safely.

Implementation:
1. Side-by-side parity checklist against legacy viewer.
2. Replay and live behavior regression suite.
3. Contract freeze for `v1`.
4. Legacy deprecation note and rollback path.

Definition of done:
- Replay parity: pass.
- Live human-play parity: pass.
- Known P0 bug checklist: pass.

## F7. Parameter-Aware Frontend Rendering

Goal:
- Render board/seats/labels from manifest, not fixed literals.

Implementation:
1. Replace fixed 40-tile projection with topology-driven board projection.
2. Replace fixed 4-seat lobby assumptions with server-provided seat model.
3. Move event/tile/prompt labels to manifest-fed label catalog + fallback.
4. Add manifest-hash watcher to force projection cache reset/rehydration on config change.

Definition of done:
- Layout/value/seat parameter changes do not require frontend code edits.
- Manifest hash change is reflected in UI state without manual refresh or code patch.

## Quality Gates (`Q`)

Required for release candidate:

1. Contract tests:
   - all event types
   - all prompt types.
2. Integration tests:
   - reconnect/resume
   - timeout fallback
   - stale decision rejection.
3. E2E tests:
   - one full human seat game
   - one spectator-only game
   - one mixed game in default 4-seat profile
   - one non-default seat-count variant game (parameterized seat model regression)
4. Observability checks:
   - log fields complete
   - error codes normalized.

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Contract drift between backend and frontend | prompt failure / broken UI | freeze contract examples and parser tests in same PR |
| Prompt duplicate handling bugs | wrong user input state | enforce `request_id` idempotency and pending lock rules |
| Resume sequence gap | out-of-sync state | strict contiguous `seq` buffering and replay |
| Overlay blocking gameplay context | poor usability | collapsible prompts + theater cards |
| Hidden/public visibility leak | fairness break | explicit visibility tags and reviewer checklist |

## PR and Documentation Rule

For each implementation PR:

1. Update this execution plan phase checklist.
2. Update related spec file(s):
   - component spec
   - interface spec
   - API spec.
3. Add/extend tests for changed behavior.
4. Update `PLAN/PLAN_STATUS_INDEX.md` if status changed.
