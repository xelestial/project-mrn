# Online Game Architecture Plan

Status: `DRAFT`
Owner: `Shared`
Created: `2026-03-29`

## Purpose

This document specifies the architecture for converting the current local-simulation game into a multiplayer online game where:
- All 4 seats can be independently occupied by a human player or an AI agent
- Backend and frontend are cleanly separated via a stable API contract
- The frontend API is designed so the current HTML renderer can be replaced by a Unity client without engine changes

This is a design plan. It does not replace the existing visualization substrate contract.
Primary dependency: `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

---

## Scope

### In scope
- Backend server architecture (session management, game engine hosting, seat routing)
- REST + WebSocket API contract (session lifecycle, event stream, decision prompts)
- Seat model (human vs AI, join flow, reconnect)
- Frontend client contract (what any renderer must implement)
- Unity migration path (how to replace HTML renderer with Unity client)

### Out of scope
- Specific Unity implementation details
- Authentication / account system (placeholder design only)
- Production deployment / infrastructure (cloud hosting, scaling)
- This document does not define AI policy internals

---

## Ownership Split

| Layer | Owner | Notes |
|-------|-------|-------|
| Game engine (rules, state) | CLAUDE | no change from current |
| AI policy execution | CLAUDE | runs server-side |
| Session server | CLAUDE | new backend component |
| REST API endpoints | CLAUDE | new backend component |
| WebSocket event broadcast | CLAUDE | new backend component |
| Decision prompt dispatch | CLAUDE | routes to AI or human seat |
| HTML renderer | GPT | current frontend |
| Unity renderer | Future client | replaces HTML renderer |
| Frontend input handling | Frontend | human decision adapter |
| Reconnect / lobby UI | Frontend | client responsibility |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    BACKEND (CLAUDE)                      │
│                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌─────────────┐ │
│  │ Session API  │   │  Game Engine │   │  AI Agents  │ │
│  │ (REST)       │──▶│  (per-game   │◀──│  (per seat) │ │
│  │              │   │   instance)  │   │             │ │
│  └──────────────┘   └──────┬───────┘   └─────────────┘ │
│                             │                            │
│                    ┌────────▼────────┐                  │
│                    │  Event Bus      │                  │
│                    │  + Prompt       │                  │
│                    │  Dispatcher     │                  │
│                    └────────┬────────┘                  │
└─────────────────────────────┼───────────────────────────┘
                               │ WebSocket
          ┌────────────────────┼────────────────────┐
          │                    │                     │
   ┌──────▼──────┐    ┌────────▼────┐    ┌──────────▼──┐
   │ HTML Client │    │Unity Client │    │ Spectator   │
   │ (GPT)       │    │(future)     │    │ (any)       │
   └─────────────┘    └─────────────┘    └─────────────┘
```

### Key principles
- The engine runs entirely on the backend. Clients never hold authoritative game state.
- AI seats are resolved server-side with no client involvement.
- Human seats receive prompts over WebSocket and respond over WebSocket.
- All clients (human players, spectators) receive the same vis event stream.
- The frontend has no game logic — it is a renderer + input adapter only.

---

## Seat Model

### Seat type assignment
Each of the 4 seats is assigned at session creation:

```json
{
  "seat": 1,
  "seat_type": "human",
  "player_id": null
}
```

```json
{
  "seat": 2,
  "seat_type": "ai",
  "ai_profile": "balanced"
}
```

`seat_type` values:
- `"human"` — a human client must connect and respond to decision prompts
- `"ai"` — backend runs the policy; no client required for this seat

### Join flow (human seats)
1. Client calls `POST /sessions/{session_id}/join` with seat number + token
2. Server assigns `player_id` and returns a `session_token` for WebSocket auth
3. Client connects to `WS /sessions/{session_id}/stream`
4. Game does not start until all human seats are joined (or timeout triggers AI fallback)

### Reconnect
- Human client can reconnect to `WS /sessions/{session_id}/stream` with existing `session_token`
- Server replays buffered events since last ACK on reconnect
- If human seat is disconnected when a prompt arrives, the server uses `fallback_policy` (from prompt contract)

---

## REST API Contract

Base path: `/api/v1`

### Session lifecycle

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create a new game session |
| `GET` | `/sessions/{id}` | Get session status |
| `POST` | `/sessions/{id}/join` | Join a human seat |
| `POST` | `/sessions/{id}/start` | Start the game (host only) |
| `GET` | `/sessions/{id}/replay` | Get full event log (after game end) |

#### `POST /sessions` request body
```json
{
  "seats": [
    { "seat": 1, "seat_type": "human" },
    { "seat": 2, "seat_type": "ai", "ai_profile": "aggressive" },
    { "seat": 3, "seat_type": "ai", "ai_profile": "balanced" },
    { "seat": 4, "seat_type": "human" }
  ],
  "config": {
    "round_limit": 8,
    "board_variant": "standard"
  }
}
```

#### `POST /sessions` response
```json
{
  "session_id": "abc123",
  "status": "waiting",
  "join_tokens": {
    "1": "tok_seat1_...",
    "4": "tok_seat4_..."
  }
}
```

#### `GET /sessions/{id}` response
```json
{
  "session_id": "abc123",
  "status": "in_progress",
  "seats": [
    { "seat": 1, "seat_type": "human", "connected": true },
    { "seat": 2, "seat_type": "ai", "ai_profile": "aggressive" },
    { "seat": 3, "seat_type": "ai", "ai_profile": "balanced" },
    { "seat": 4, "seat_type": "human", "connected": false }
  ],
  "round_index": 3,
  "turn_index": 11
}
```

---

## WebSocket API Contract

### Connection
```
WS /api/v1/sessions/{session_id}/stream?token={session_token}
```

Spectators connect without a token (read-only stream, no prompts delivered).

### Message envelope (server → client)

All server messages share this envelope:

```json
{
  "msg_type": "event" | "prompt" | "error" | "ack_required",
  "seq": 1042,
  "payload": { ... }
}
```

`seq` is a monotonic sequence number. Clients track the last received seq.
On reconnect, client sends `{ "msg_type": "resume", "last_seq": 1041 }` and server replays from seq 1042.

### Message types (server → client)

#### `event`
A vis stream event. Payload follows the existing vis event schema from `SHARED_VISUAL_RUNTIME_CONTRACT.md`.

```json
{
  "msg_type": "event",
  "seq": 1042,
  "payload": {
    "event_type": "dice_roll",
    "session_id": "abc123",
    "round_index": 3,
    "turn_index": 11,
    "step_index": 0,
    "acting_player_id": 1,
    "public_phase": "movement",
    "timestamp": 1743200000.123,
    "public_payload": {
      "player_id": 1,
      "dice_values": [3, 4],
      "cards_used": [],
      "total_move": 7,
      "move_modifier_reason": null
    }
  }
}
```

#### `prompt`
A decision prompt sent only to the specific human seat.

```json
{
  "msg_type": "prompt",
  "seq": 1055,
  "payload": {
    "request_id": "req_abc123_turn11_mv",
    "request_type": "MovementDecisionRequest",
    "player_id": 1,
    "legal_choices": [
      { "label": "주사위 굴리기", "value": "roll_dice" },
      { "label": "카드 1 사용 (이동 +3)", "value": "use_card_3" }
    ],
    "can_pass": false,
    "timeout_ms": 30000,
    "fallback_policy": "auto_roll_dice",
    "public_context": { ... }
  }
}
```

#### `ack_required`
Server requests the client acknowledge receipt of a specific seq range (used for buffer management).

### Message types (client → server)

#### `decision`
Human player responds to a prompt.

```json
{
  "msg_type": "decision",
  "request_id": "req_abc123_turn11_mv",
  "player_id": 1,
  "choice": "roll_dice"
}
```

#### `resume`
Client reconnects and requests replay from a sequence number.

```json
{
  "msg_type": "resume",
  "last_seq": 1041
}
```

#### `ping` / `pong`
Standard keepalive.

---

## Decision Prompt Routing

The server's prompt dispatcher is the key component that unifies human and AI seats.

```
Engine requests decision
        │
        ▼
   Prompt Dispatcher
        │
   ┌────┴────┐
   │         │
seat_type=  seat_type=
 "human"     "ai"
   │         │
   │         ▼
   │    AI Policy (server-side)
   │    → returns choice immediately
   │
   ▼
WebSocket prompt → human client
Wait for "decision" response (timeout: fallback_policy)
        │
        ▼
Engine receives choice → continues
```

### Fallback policy values (same as existing prompt contract)
- `"auto_roll_dice"` — dice movement fallback
- `"auto_pass"` — trick window pass
- `"auto_cheapest"` — purchase cheapest legal option
- Any `"ai:{profile}"` — delegate to named AI profile as fallback

---

## Event Stream Design

### Broadcast rules
- All events go to all connected clients (human players + spectators)
- Prompt messages go only to the target seat's connection
- `analysis_payload` is stripped from spectator streams (only `public_payload` forwarded)
- For human player connections: same rule — `public_payload` only (no hidden info leaks)

### Event buffering
- Server buffers the last N events per session (default: entire game)
- Reconnecting clients receive buffered events from their `last_seq`
- After game end, the buffer persists for replay access via `GET /sessions/{id}/replay`

---

## Public State Snapshot

On connection (or reconnect), the server sends a `session_snapshot` message containing the full current `BoardPublicState` + all `PlayerPublicState` values. This allows a fresh client to render the current board without replaying all prior events.

```json
{
  "msg_type": "event",
  "seq": 0,
  "payload": {
    "event_type": "session_snapshot",
    "session_id": "abc123",
    "public_payload": {
      "board": { ... },
      "players": [ ... ]
    }
  }
}
```

---

## Frontend Client Contract

Any frontend (HTML or Unity) must implement:

### Required capabilities
1. **WebSocket connection management**: connect, reconnect from `last_seq`, ping/pong
2. **Event stream consumption**: parse and apply all event types from the vis stream
3. **State projection**: maintain a local `BoardPublicState` + `PlayerPublicState[]` from event stream
4. **Prompt rendering**: display prompts for the connected human seat and send `decision` responses
5. **Turn display**: render turn flow (dice, movement, landing, economy phases) from event types

### Event types the frontend must handle
All events from `SHARED_VISUAL_RUNTIME_CONTRACT.md` Layer 1:
- `session_start`, `round_start`, `weather_reveal`
- `draft_pick`, `final_character_choice`
- `turn_start`, `trick_window_open`, `trick_window_closed`, `trick_used`
- `dice_roll`, `player_move`
- `landing_resolved`, `rent_paid`, `tile_purchased`
- `fortune_drawn`, `fortune_resolved`
- `mark_resolved`, `marker_transferred`, `marker_flip`
- `lap_reward_chosen`, `f_value_change`
- `bankruptcy`, `turn_end_snapshot`, `game_end`
- `session_snapshot` (connection init)

### Prompt types the frontend must handle
All prompt types from `SHARED_VISUAL_RUNTIME_CONTRACT.md` Layer 3.

### What the frontend must NOT do
- Execute any game logic or validate legal moves
- Access any hidden information (server never sends it, but client must not derive it)
- Render `analysis_payload` in public-view mode

---

## Unity Migration Path

The current HTML renderer (GPT-built) and a future Unity client are interchangeable because they share the same WebSocket + REST contract. Migration steps:

### Phase A: Contract verification
- Unity client connects to the same WS endpoint
- Verifies it can receive and parse all event types
- Verifies it can send `decision` responses

### Phase B: Parallel run
- Run HTML and Unity side-by-side against the same game session
- Both receive the same event stream
- Verify Unity renders equivalent state

### Phase C: Switch
- Replace HTML renderer with Unity in production
- No backend changes required

### Unity-specific notes
- All payloads are JSON-serializable (already guaranteed by `SHARED_VISUAL_RUNTIME_CONTRACT.md` §Serialization Rule)
- No HTML-specific fields exist in the event schema
- Animation timing is frontend responsibility — events carry timestamps but no animation hints
- `movement_trace.path` provides the exact tile-by-tile path for movement animation
- `crossed_start` flag is sufficient for lap-crossing visual triggers

---

## Backend Component Map

### New components (to be built)

| Component | Path | Responsibility |
|-----------|------|----------------|
| `SessionManager` | `CLAUDE/server/session_manager.py` | create/join/start sessions, seat assignment |
| `GameServer` | `CLAUDE/server/game_server.py` | host one game engine instance per session |
| `EventBroadcaster` | `CLAUDE/server/broadcaster.py` | buffer + broadcast vis events to WebSocket connections |
| `PromptDispatcher` | `CLAUDE/server/prompt_dispatcher.py` | route decision requests to AI or human seat |
| `ConnectionRegistry` | `CLAUDE/server/connection_registry.py` | track active WebSocket connections per session/seat |
| `REST API app` | `CLAUDE/server/app.py` | FastAPI app, REST + WebSocket routes |

### Existing components reused as-is

| Component | Path | Role |
|-----------|------|------|
| Game engine | `CLAUDE/engine.py` | unchanged |
| Public state builders | `CLAUDE/viewer/public_state.py` | unchanged |
| Vis event emission | `CLAUDE/viewer/` | unchanged |
| AI policies | `CLAUDE/policy/` | run inside `PromptDispatcher` for AI seats |

---

## Configuration

### Session config fields
```json
{
  "round_limit": 8,
  "board_variant": "standard",
  "decision_timeout_ms": 30000,
  "fallback_policy": "auto_ai_balanced",
  "spectator_allowed": true,
  "analysis_view_allowed": false
}
```

### AI seat config fields
```json
{
  "seat": 2,
  "seat_type": "ai",
  "ai_profile": "aggressive",
  "think_delay_ms": 0
}
```

`think_delay_ms`: optional artificial delay before AI responds (for pacing in spectator-facing games).

---

## Implementation Order

This plan is intentionally ordered so each phase is independently testable.

### Phase 1. Session REST API
- `SessionManager`: create/join/start/status
- No WebSocket yet — just session state in memory
- Tests: create session, assign seats, join human seat, start

### Phase 2. Engine hosting + event broadcast
- `GameServer`: host engine instance, push vis events to `EventBroadcaster`
- `EventBroadcaster`: buffer + send to mock subscribers
- Tests: one full game runs server-side, all vis events captured

### Phase 3. WebSocket stream
- `ConnectionRegistry`: accept WS connections
- Broadcast buffered events on connect, push new events live
- Tests: client connects mid-game, receives snapshot + remaining events

### Phase 4. AI prompt routing
- `PromptDispatcher`: for AI seats, call policy and return choice immediately
- Tests: all-AI game completes over WebSocket with no human input

### Phase 5. Human prompt routing
- `PromptDispatcher`: for human seats, push prompt over WS, await `decision` response
- Tests: human seat receives prompt, submits decision, game continues

### Phase 6. Reconnect + fallback
- On disconnect: queue prompts, apply fallback after timeout
- On reconnect: replay from `last_seq`
- Tests: disconnect mid-game, reconnect, resume

---

## Acceptance Criteria

This architecture is ready for implementation when:
- All-AI session can run end-to-end via REST start + WebSocket event stream
- Human seat can receive a prompt and submit a response over WebSocket
- A second client (spectator) receives the same event stream without hidden info
- A client reconnecting mid-game recovers full current state
- The WebSocket message format is sufficient for a Unity client to parse without changes

---

## Open Questions

| # | Question | Owner | Status |
|---|----------|-------|--------|
| OQ1 | Should `session_token` use JWT or opaque tokens? | Backend | open |
| OQ2 | Persistent sessions (DB) vs in-memory only? | Backend | in-memory first |
| OQ3 | Maximum concurrent sessions per server? | Infra | out of scope now |
| OQ4 | Does spectator stream strip `analysis_payload` always, or is it configurable? | Shared | default strip |
| OQ5 | Should `think_delay_ms` be per-AI-seat or per-session? | Backend | per-seat |
