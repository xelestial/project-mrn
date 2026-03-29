# [PLAN] React Online Game Detailed Execution

Status: `ACTIVE`  
Owner: `Shared (Backend: CLAUDE, Frontend: GPT)`  
Updated: `2026-03-30`  
Parent: `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`

## Purpose

This document defines the detailed implementation backlog for the React online game transition.

It is intentionally execution-focused:

- exact phase deliverables
- phase entry/exit criteria
- test and verification gates
- risk controls and fallback policy

## Current Progress Snapshot (`2026-03-30`)

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
  - remaining: reconnect stress handling and load-level backpressure tuning
- `B3` baseline: in progress
  - added in-memory prompt lifecycle service (`pending`, `submit_decision`, `timeout_pending`)
  - added debug prompt route for end-to-end prompt envelope smoke path
  - websocket decision ack now validates pending prompt status (`accepted/rejected/stale`)
  - timeout path now emits public fallback trace event (`decision_timeout_fallback`)
  - added spectator decision block and authenticated player mismatch block
  - added API-level decision auth regression tests (`UNAUTHORIZED_SEAT`, `PLAYER_MISMATCH`)
  - remaining: engine fallback execution wiring and stale-request hardening
- runtime fan-out baseline: in progress
  - all-AI session start now triggers background engine execution
  - emitted vis events are published into websocket stream buffer in order
  - incremental live fan-out is now active (event append -> immediate WS publish bridge)
  - remaining: runtime watchdog and backpressure tuning
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
  - dependency install/build pipeline now green on local environment
  - remaining: broader domain store expansion and parser/contract tests
- `F2` baseline: started
  - split baseline UI into feature components (`status`, `timeline`, `board` placeholder)
  - added stream selector layer (`domain/selectors/streamSelectors.ts`)
  - added snapshot-driven public board/player baseline rendering
  - added 40-tile ring board layout mapping (`tile_index` -> ring coordinates)
  - added board-near recent incident card stack baseline (`IncidentCardStack`)
  - remaining: pawn movement animation, richer labels/localization, theater depth
- `F3` baseline: started
  - added prompt selector baseline (`selectActivePrompt`) with ack-aware closing
  - added prompt overlay component with full-card choices and collapse toggle
  - added decision submit wiring from UI (`useGameStream.sendDecision`)
  - added prompt selector unit tests
  - added ack-status unlock handling for rejected/stale decisions
  - added countdown baseline in prompt overlay
  - added keyboard/focus baseline (first-choice focus, focus restore, Escape collapse)
  - remaining: stale/timeout user messaging polish
- `F4` baseline: started
  - added lobby control panel for custom seat composition and seed/profile inputs
  - added host-start path with explicit host token input
  - added seat-join path (`session_id`, `seat`, `join_token`, `display_name`) with auto-connect
  - added session list refresh panel for in-app lifecycle visibility
  - added create-time join-token state management with seat-based auto-fill
  - added seat-select + one-click join-token apply controls
  - added session-list quick select action (`Use session`)
  - added lobby/match route split baseline (hash-based route tabs)
  - remaining: dedicated lobby page extraction
- `B4+`: not started in code

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
| `B` Backend runtime and API | FastAPI, session lifecycle, WS stream, prompt dispatch | CLAUDE | Shared contract freeze |
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
- 4-seat mixed config can be created and started.
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
4. Optional persistence adapter seam (no persistence required in v1).

Definition of done:
- Recoverable faults are surfaced with stable error codes.
- Crash logs contain `session_id`, `request_id`, `player_id`, `seq`.

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
- 1-4 humans + AI mixed session can start from UI.

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
   - one mixed 4-seat game.
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
