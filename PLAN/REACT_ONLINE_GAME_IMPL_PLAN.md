# React Online Game Implementation Plan

Status: `ACTIVE`  
Owner: `Shared (Backend: CLAUDE, Frontend: GPT)`  
Updated: `2026-03-29`  
Depends on: `PLAN/ONLINE_GAME_ARCHITECTURE_PLAN.md`, `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Purpose

This document is the execution plan to move from the current Python-rendered HTML viewer to a React-based playable online game UI.

Primary goals:

- Replace polling viewer with a session-based, WebSocket-first architecture
- Support real human play (up to 4 seats) with AI/human mixed sessions
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
| Seat support | Partial | Full 1-4 human seats + AI mix |

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

Current policy:

- Until `DOCS/API`, `DOCS/FRONTEND`, and `DOCS/BACKEND` scaffolds are created in-repo, these detailed specs are authored in `PLAN/`.
- Once frontend/backend scaffolds exist, these docs should be migrated without changing semantics.

---

## Common Governance

## 1. Document organization and storage

Use this structure consistently:

- `PLAN/`: plans, proposals, status trackers
- `DATA/`: game data specs and data snapshots
- `DOCS/API/`: REST and WebSocket contract docs
- `DOCS/FRONTEND/`: component specs, behavior docs, test matrix
- `DOCS/BACKEND/`: service boundaries, DI graphs, runtime operations
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

New backend package:

```text
CLAUDE/server/
  __init__.py
  app.py
  models.py
  session_manager.py
  game_server.py
  prompt_dispatcher.py
  broadcaster.py
  connection_registry.py
  services/
    session_service.py
    runtime_service.py
    prompt_service.py
    auth_service.py
```

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

```text
frontend/
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

Core hook:

- `useGameStream(sessionId, token)` for WS connect, resume, event reduce, prompt handling

## F2. Component architecture and DI

Feature components:

- Board: tiles, ownership, pawn positions, map overlays
- Players: 4 player status panels
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

1. Update component doc in `DOCS/FRONTEND/components/`
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
- Record matrix in `DOCS/FRONTEND/versions.md`

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
uvicorn CLAUDE.server.app:app --reload --port 8000
```

Frontend:

```bash
cd frontend
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

## Open Items

| # | Item | Owner | Notes |
|---|---|---|---|
| OI1 | Engine sync runtime bridge to async FastAPI | CLAUDE | `asyncio.to_thread`/executor policy |
| OI2 | Extract board tile layout constants from legacy renderer | GPT | Move to shared board schema |
| OI3 | Full prompt type coverage audit in human policy and React UI | GPT | Must pass before F3 close |
| OI4 | Final UI stack decision (plain CSS modules vs utility stack) | GPT | Keep complexity bounded |
| OI5 | Session persistence after restart | CLAUDE | Out of scope for v1 |
| OI6 | Migrate detailed specs from `PLAN/` to `DOCS/*` after scaffold | Shared | Keep links stable with redirect note |
| OI7 | WS and prompt schema freeze with examples | Shared | Required before F3 |
| OI8 | State store final decision (`zustand` only vs hybrid) | GPT | Decide before F2 close |
| OI9 | Structured log retention and rotation policy | CLAUDE | Needed for ops |
| OI10 | Legacy vs React parity checklist artifact | Shared | Required before cutover |
