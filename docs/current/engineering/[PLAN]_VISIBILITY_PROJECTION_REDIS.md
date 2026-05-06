# Visibility Projection Redis Plan

Status: SUPERSEDED by the server authoritative `ViewCommit` contract.
Updated: 2026-05-06

This document is historical. Live UI state must not be rebuilt from stream
history, replay projection, or route-level filtering. RuntimeService writes the
latest viewer-specific `ViewCommit` to Redis atomically with the engine
checkpoint, and WebSocket/REST live recovery reads that cached commit only.

## Goal

Define what data Redis stores, what the backend may send to each frontend viewer, and how hidden/private game information is protected in multiplayer play.

The frontend must never receive sensitive data and then hide it locally. The backend is the visibility boundary. Redis can store canonical private state, but websocket/API output must be projected for the authenticated viewer before delivery.

## Current Code Review

Existing pieces already support this direction:

- Redis canonical state: `game:{session_id}:state`
- Redis checkpoint: `game:{session_id}:checkpoint`
- Redis stream history: `stream:{session_id}:events`
- Redis projected state cache: `game:{session_id}:view_state`
- Stream auth/filtering: `apps/server/src/routes/stream.py`
- View projection modules: `apps/server/src/domain/view_state/*_selector.py`
- Prompt/decision envelopes: `apps/server/src/services/decision_gateway.py`

Current risk:

- `StreamService.publish()` computes `payload.view_state` from unfiltered session history before `routes/stream.py` applies `_filter_stream_message()`.
- The current route filter suppresses some private prompt/event messages, but it does not rebuild or redact `payload.view_state` per viewer.
- Therefore future private view selectors, especially hand/prompt selectors, must not rely on route-level message filtering alone.

## Core Rule

Store canonical data once; expose projected data per viewer.

Redis stores two classes of data:

1. Canonical private data for engine/runtime/recovery/archive.
2. Derived viewer-safe projections for frontend reconnect and stream output.

Only class 2 can be sent to browsers.

## Redis Data To Keep Canonical

### Session And Auth

Keys:

- `session:{session_id}`
- `session:{session_id}:seats`
- `session:{session_id}:tokens`
- `room:{room_no}`
- `room:{room_no}:seats`

Store:

- room status, title, host seat, config
- session status, resolved config, started/completed timestamps
- seat type, display name, participant type
- keyed token hashes only, never raw tokens
- role principal: seat, player id, spectator/admin permission if supported

Frontend visibility:

- public lobby/session manifest only
- token hashes and auth principals are backend-only

### Canonical Engine State

Key:

- `game:{session_id}:state`

Store full deterministic engine state:

- players: positions, cash, shards, hand coins, placed score coins, tile counts, alive state, marks, per-turn flags
- player private state: trick hand card identities, hidden trick identity, drafted/final character state when still private
- board/tile state: tile kind, block/zone, owner, score coins, temporary rent modifiers, pawn positions
- card state: fortune/trick/weather draw order, discard/graveyard order, current weather
- active card faces and marker ownership
- action state: pending actions, scheduled actions, pending turn completion, in-progress action log
- prompt state: prompt sequence, pending prompt request id/type/player

Frontend visibility:

- never send this raw
- projection reads this state and emits only viewer-safe fields

### Canonical Event Stream

Key:

- `game:{session_id}:events` or current `stream:{session_id}:events`

Store authoritative events with visibility metadata:

```json
{
  "schema_version": 1,
  "event_id": "sess:r2:t4:seq31",
  "seq": 31,
  "event_type": "trick_used",
  "actor_player_id": 2,
  "visibility": {"scope": "public"},
  "entity_refs": [
    {"kind": "player", "id": "player:2"},
    {"kind": "card", "id": "trick:1001", "slot": "played"}
  ],
  "payload": {},
  "private_by_player": {
    "2": {"card_name": "재뿌리기", "deck_index": 1001}
  },
  "admin_payload": {}
}
```

Frontend visibility:

- backend calls `project_event_for_viewer(event, viewer)` before websocket/API output
- if the viewer is not allowed, return `null`
- if the viewer is allowed partially, return public payload plus only that viewer's private patch

### Prompt State

Keys:

- `prompt:{session_id}:active`
- `prompt:{session_id}:by_request`
- `prompt_request:{request_id}`
- `prompt_deadlines`

Store:

- request id, request type, player id
- timeout/deadline/fallback metadata
- legal choices and public/private context needed to render the prompt for the target
- accepted choice status
- visibility selector: target player only unless explicitly public

Frontend visibility:

- target player receives prompt and legal choices
- other players receive at most a public "waiting for player N" event, if needed
- spectators receive only spectator-safe prompt phase metadata

### Commands

Key:

- `game:{session_id}:commands`

Store:

- accepted player/AI decisions
- request id, player id, choice id, request type
- source stream seq and dedupe metadata

Frontend visibility:

- command stream is backend/runtime/admin only
- frontend sees projected `decision_resolved` events, not raw command entries

### Analysis And Debug

Key:

- `game:{session_id}:analysis`

Store:

- AI scoring traces
- runtime timings
- rule diagnostics
- recovery/debug breadcrumbs

Frontend visibility:

- admin/dev only
- normal players and spectators receive no analysis payload

## Viewer-Safe Projection Data

### Public View State

Key:

- `game:{session_id}:view_state:public`

Include:

- board tile index, owner player id, score coin count, pawn player ids
- f value, weather name/effect, marker owner
- player public stats: display name, cash, shards, owned tile count, public trick names, hidden trick count, score totals
- round/turn/current actor
- public event feed
- public active character slots after reveal

Do not include:

- other players' full hands
- private draft/final choices before reveal
- legal choices for prompts targeting another player
- AI analysis

### Player View State

Key options:

- `game:{session_id}:view_state:player:{player_id}`
- or hash `game:{session_id}:view_state:by_viewer` field `player:{player_id}`

Include public view state plus:

- own full trick hand and hidden trick marker
- own prompt with legal choices
- own draft/final character choices
- own burden exchange choices
- own unresolved private decision feedback
- own hand tray and prompt surface

Do not include:

- other players' private hands
- other players' legal prompt choices
- admin/debug analysis

### Spectator View State

Key:

- `game:{session_id}:view_state:spectator`

Include:

- public board/player/turn/event state
- public prompt phase metadata only

Do not include:

- any private hand/prompt/draft/final-character payload unless the game mode explicitly allows open spectator information

### Admin View State

Key:

- `game:{session_id}:view_state:admin`

Include:

- public view state
- full canonical-derived inspection payloads needed for debugging
- optionally analysis stream summaries

Do not expose through player websocket tokens.

## Visibility Selector Schema

Use an explicit visibility selector on events, prompts, and projection fragments.

```json
{"scope": "public"}
{"scope": "player", "player_id": 2}
{"scope": "players", "player_ids": [1, 3]}
{"scope": "spectator_safe"}
{"scope": "admin"}
{"scope": "backend_only"}
```

Optional fields:

```json
{
  "scope": "player",
  "player_id": 2,
  "redaction": "summary",
  "reason": "own_hand"
}
```

Rules:

- `backend_only` never leaves backend services.
- `admin` requires explicit admin auth.
- `spectator_safe` must not contain hidden hand/prompt/private choice details.
- `public` can go to all connected clients.
- `player` and `players` require matching authenticated player id.

## Entity Ref Selector Schema

Keep target identity separate from visibility.

```json
{"kind": "tile", "id": "tile:31", "board_index": 31, "slot": "owner_badge"}
{"kind": "player", "id": "player:2", "player_id": 2, "slot": "hand_tray"}
{"kind": "card", "id": "trick:1001", "deck_index": 1001, "slot": "prompt_choice"}
{"kind": "prompt", "id": "req_abc", "slot": "active_prompt"}
```

Frontend maps entity refs to DOM/data attributes. Redis should not store brittle CSS selectors.

## Backend Projection Pipeline

Target pipeline:

1. Engine/runtime commits canonical `GameState` and canonical events to Redis.
2. Each event/prompt/derived fragment carries a visibility selector.
3. Backend creates viewer projections using:
   - canonical state
   - canonical event stream
   - session auth principal
   - `project_event_for_viewer(event, viewer)`
   - `project_state_for_viewer(state, viewer)`
4. Backend writes projection caches:
   - public
   - spectator
   - player-specific when private surfaces exist
5. Websocket/API sends only projected messages and projected `view_state`.

Important change:

- Do not attach a single unfiltered `view_state` to canonical stream messages.
- Either attach no `view_state` to canonical messages, or attach only a public-safe view state.
- For websocket delivery, add/rebuild `view_state` after filtering for that viewer.

## Information Classification

### Public

- board layout and tile index
- tile owner and score coin count
- pawn positions
- current round/turn/current actor
- f value and weather
- player display names, cash, shards, owned count, total score
- public trick names and hidden trick count
- revealed active characters
- public events: move, rent paid, purchase, weather, lap reward summary, marker transfer

### Player Private

- own full trick hand and card descriptions
- own hidden trick selection
- own prompt choices and `choice_id`s
- own draft/final character options before reveal
- own burden exchange card details
- own private decision acknowledgements

### Targeted Private

- direct prompts to a player
- target-only effects if a future rule requires private notification
- team-only data if team mode is added

### Spectator-Safe

- public board/player/turn state
- public event feed
- prompt phase without legal choices

### Admin/Analysis

- full canonical state inspection
- all hands and deck order
- AI reasoning/score traces
- recovery checkpoints
- raw command stream

### Backend-Only

- raw auth tokens
- token hashes if not needed outside auth service
- runtime lease owner
- command consumer offsets
- Redis key names or internal lock values

## Implementation Plan

### Phase 1: Define Contracts And Guardrails

- Add `visibility` and `entity_refs` typed schemas in `apps/server/src/domain/view_state/types.py` or a new `visibility/types.py`.
- Add `project_event_for_viewer()` and `project_payload_for_viewer()`.
- Add tests proving private fields are stripped for non-target viewers.
- Add a contract test that no websocket message to a non-target viewer contains:
  - `full_hand`
  - private `legal_choices`
  - private prompt `choice_id`s
  - hidden trick card identity
  - raw command payloads

### Phase 2: Move Filtering Out Of Route Ad Hoc Logic

- Replace `_filter_stream_message()` in `routes/stream.py` with a shared projection service.
- Keep route auth only responsible for building `ViewerContext`.
- Projection service decides visibility and redaction.

### Phase 3: Make View State Viewer-Specific

Historical proposal, now superseded by authoritative `ViewCommit`:

- Message-history projection was considered for viewer-specific snapshots.
- Live code must build viewer snapshots from canonical runtime state only.
- WebSocket resume must send the cached authoritative `ViewCommit`, not replay output.

### Phase 4: Normalize Prompt Visibility

- Prompt envelopes get explicit `visibility: {"scope": "player", "player_id": N}`.
- Decision requested/resolved/timeout events get public and private shapes:
  - public: request type, actor/target, status
  - private target: legal choices, full prompt context
- Hand tray projection uses target-player prompt only.

### Phase 5: Normalize Hand/Card Visibility

- Canonical state keeps full hands/decks.
- Public projection emits per-player:
  - trick count
  - public trick names
  - hidden trick count
- Owner projection emits own:
  - full hand
  - hidden marker
  - usable flags
- Admin projection can emit all hands.

### Phase 6: Redis Projection Cache Layout

Add keys:

```text
game:{session_id}:view_state:public
game:{session_id}:view_state:spectator
game:{session_id}:view_state:player:{player_id}
game:{session_id}:historical_projection_cursor
```

`historical_projection_cursor` stores:

- canonical latest seq
- projection schema version
- generated_at_ms
- projected viewer keys

### Phase 7: Archive Redaction

- Keep canonical archive for backend/admin only.
- Canonical local JSON archives must declare:
  - `schema_name: "mrn.canonical_archive"`
  - `visibility: "backend_canonical"`
  - `browser_safe: false`
- Add optional redacted replay export:
  - public replay
  - player-perspective replay
  - spectator replay
- Redacted browser-facing replay exports must declare:
  - `schema_name: "mrn.redacted_replay_export"`
  - `visibility: "spectator"` or `"player"`
  - `browser_safe: true`
- Never mutate canonical archive to satisfy privacy filtering.

### Phase 8: Admin Canonical Access

- Canonical recovery/archive data may be exposed only through explicit admin APIs.
- Admin APIs must not accept seat/session tokens as admin proof.
- Initial admin auth is `MRN_ADMIN_TOKEN` with either:
  - `X-Admin-Token: <token>`
  - `Authorization: Bearer <token>`
- If `MRN_ADMIN_TOKEN` is empty, admin APIs must return `ADMIN_AUTH_DISABLED`.
- Admin canonical responses must declare:
  - `schema_name: "mrn.admin_recovery"` or a similarly specific admin schema
  - `visibility: "admin"`
  - `browser_safe: false`
- Canonical archive reads are admin-only and must use the archive service path resolver rather than raw path parameters.
- Normal browser routes must keep using projected replay/status payloads.

## Recommended First Slice

Start with the highest leakage-risk path:

1. Introduce `ViewerContext`.
2. Move route stream filtering into `visibility/projector.py`.
3. Stop sending canonical `payload.view_state` blindly.
4. Rebuild `view_state` after viewer filtering for websocket delivery.
5. Add tests around `trick_to_use`, `hidden_trick_card`, `draft_pick`, and `final_character_choice`.

This gives the frontend the same convenience it has now, but the backend becomes the single place that decides what a viewer may know.
